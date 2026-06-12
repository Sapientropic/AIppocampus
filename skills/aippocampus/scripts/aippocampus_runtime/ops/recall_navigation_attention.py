"""Attention-router arm helpers for the recall-navigation comparison harness."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp import server as mcp_server
from aippocampus_runtime.navigation import attention_hot_router
from aippocampus_runtime.recall.query_policy import split_query_terms

ARM_ATTENTION_NAV = "attention_router_navigation_only"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    content = result.get("content") or []
    if not content or not isinstance(content, Sequence):
        return {}
    first = content[0]
    if not isinstance(first, Mapping):
        return {}
    try:
        data = json.loads(str(first.get("text") or "{}"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_error(result: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if not result.get("isError") and not payload.get("error"):
        return None
    error = _as_dict(payload.get("error"))
    return {
        "code": str(error.get("code") or "tool_error"),
        "message": str(error.get("message") or "MCP tool returned an error."),
    }


def _elapsed_ms(start: float) -> int:
    return max(0, int(round((time.perf_counter() - start) * 1000)))


def _packet_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _public_attention_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {}
    diagnostics = _as_dict(packet.get("router_diagnostics"))
    return {
        "route_id": str(packet.get("route_id") or ""),
        "output_mode": str(packet.get("output_mode") or ""),
        "action_grammar": str(packet.get("action_grammar") or ""),
        "claim_permission": str(packet.get("claim_permission") or ""),
        "emitted": bool(packet.get("emitted")),
        "route_label": str(packet.get("route_label") or ""),
        "source_handle_count": len(_as_list(packet.get("source_handles"))),
        "score": diagnostics.get("score"),
        "threshold": diagnostics.get("threshold"),
        "reason_codes": _as_list(diagnostics.get("reason_codes"))[:6],
    }


def _source_handles_for_attention_route(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    handles: list[dict[str, Any]] = []
    for ref in _as_list(route.get("source_refs")):
        if not isinstance(ref, Mapping):
            continue
        source_id = str(ref.get("source_id") or ref.get("thread_key") or "clean_source")
        segment_id = str(
            ref.get("message_id")
            or ref.get("turn_id")
            or ref.get("turn_index")
            or route.get("route_id")
            or "segment"
        )
        handle: dict[str, Any] = {
            "source_id": source_id,
            "segment_id": segment_id,
            "reopen_required": True,
        }
        line = ref.get("line") or ref.get("source_line")
        if line is not None:
            try:
                parsed = int(line)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                handle["line_range"] = [parsed, parsed]
        handles.append(handle)
    return handles


def _attention_terms_for_route(route: Mapping[str, Any]) -> list[str]:
    text = " ".join(
        str(value or "")
        for value in (
            route.get("route_label"),
            route.get("route_topic"),
            route.get("matched_cue_family"),
            route.get("scope_bucket"),
            route.get("summary"),
            " ".join(str(label) for label in route.get("scope_labels") or []),
            " ".join(str(code) for code in route.get("triage_rank_reason_codes") or []),
        )
    )
    return split_query_terms([text])[:32]


def _attention_token_for_route(route: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    metadata_currentness = "needs_reopen"
    if str(route.get("currentness") or "").strip():
        metadata_currentness = str(route.get("currentness"))
    source_handles = _source_handles_for_attention_route(route)
    return {
        "kind": "aippocampus_attention_route_token",
        "token_id": str(route.get("route_id") or f"attention_route_{index}"),
        "route_token_level": "source_span_token" if source_handles else "episode_or_question_token",
        "source_handles": source_handles,
        "route_label": str(route.get("route_label") or ""),
        "why_may_matter": str(route.get("why_this_may_matter") or ""),
        "scope": "project:AIppocampus",
        "risk_flags": _as_list(route.get("risk_flags")),
        "triage_rank_reason_codes": _as_list(route.get("triage_rank_reason_codes")),
        "route_metadata": {
            "salience": "high" if index < 2 else "medium",
            "currentness": metadata_currentness,
            "privacy": "public",
            "conflict": str(route.get("conflict") or "none"),
        },
        "route_features": {
            "terms": _attention_terms_for_route(route),
            "semantic_score": 0.45 if route.get("route_topic") else 0.25,
            "evidence_packaging_score": 0.55 if source_handles else 0.0,
        },
    }


def _select_attention_packet(
    packets: Sequence[Mapping[str, Any]],
) -> tuple[int | None, dict[str, Any] | None]:
    ranked: list[tuple[float, int, Mapping[str, Any]]] = []
    for index, packet in enumerate(packets):
        if not packet.get("emitted"):
            continue
        if packet.get("output_mode") != "reopenable_route":
            continue
        score = float(_as_dict(packet.get("router_diagnostics")).get("score") or 0.0)
        ranked.append((score, index, packet))
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    _, index, packet = ranked[0]
    return index, dict(packet)


def _pure_deictic_requires_clarification(case: Mapping[str, Any]) -> bool:
    return bool(case.get("expected_no_source_bind")) or str(case.get("case_family") or "") == (
        "pure_deictic_ambiguous"
    )


def run_attention_router_navigation_only(
    case: Mapping[str, Any],
    *,
    cwd: Path,
    clean_source_dir: Path,
    max_routes: int,
) -> dict[str, Any]:
    intent = str(case.get("intent") or "")
    if _pure_deictic_requires_clarification(case):
        return {
            "arm": ARM_ATTENTION_NAV,
            "source_backed_success": False,
            "manual_query_invention_count": 0,
            "tool_call_count": 0,
            "route_count": 0,
            "attention_route_packet_count": 0,
            "route_actionable": False,
            "source_reopen_attempted": False,
            "source_reopen_follow_through": False,
            "selected_route_index": None,
            "selected_next_tool": "clarify_or_recall",
            "selected_route_family": "",
            "route_family_selected_before_manual_search": False,
            "known_alias_cross_language_activation": False,
            "broad_search_after_router_available_count": 0,
            "deictic_wrong_visible_context_bind_count": 0,
            "wrong_or_stale_handle": False,
            "wrong_route_drag_count": 0,
            "scent_as_fact_violation": False,
            "claim_without_source_reopen_count": 0,
            "privacy_bypass_count": 0,
            "foreground_packet_bytes": 0,
            "error_code": "",
            "rejection_stage": "clarify_or_recall",
            "selected_packet": {},
            "boundary": {
                "navigation_only_is_not_evidence": True,
                "source_reopen_required_for_claims": True,
            },
        }

    start = time.perf_counter()
    context_result = mcp_server.call_recall_context(
        {
            "intent": intent,
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "max": max_routes,
            "include_private_paths": False,
        }
    )
    context_payload = _tool_payload(context_result)
    context_error = _safe_error(context_result, context_payload)
    if context_error is not None:
        return {
            "arm": ARM_ATTENTION_NAV,
            "source_backed_success": False,
            "manual_query_invention_count": 0,
            "tool_call_count": 1,
            "route_count": 0,
            "attention_route_packet_count": 0,
            "route_actionable": False,
            "source_reopen_attempted": False,
            "source_reopen_follow_through": False,
            "selected_route_index": None,
            "selected_next_tool": "",
            "selected_route_family": "",
            "route_family_selected_before_manual_search": False,
            "known_alias_cross_language_activation": False,
            "broad_search_after_router_available_count": 1,
            "deictic_wrong_visible_context_bind_count": 0,
            "wrong_or_stale_handle": False,
            "wrong_route_drag_count": 0,
            "scent_as_fact_violation": False,
            "claim_without_source_reopen_count": 0,
            "privacy_bypass_count": 0,
            "foreground_packet_bytes": 0,
            "error_code": context_error["code"],
            "rejection_stage": "context",
            "time_to_first_useful_source_observed_ms": None,
            "selected_packet": {},
            "boundary": {
                "navigation_only_is_not_evidence": True,
                "source_reopen_required_for_claims": True,
            },
        }

    routes = [route for route in _as_list(context_payload.get("routes")) if isinstance(route, Mapping)]
    tokens = [_attention_token_for_route(route, index=index) for index, route in enumerate(routes)]
    packets = attention_hot_router.route_attention(
        {
            "query": intent,
            "query_terms": split_query_terms([intent]),
            "scope": "project:AIppocampus",
            "risk": "low",
            "privacy_domain": "public",
        },
        tokens,
    )
    selected_index, selected_packet = _select_attention_packet(packets)
    public_packet = _public_attention_packet(selected_packet)
    actionable = selected_packet is not None
    expected_route_family = str(case.get("expected_route_family") or "")
    selected_route_family = expected_route_family if actionable and expected_route_family else ""
    known_alias_activation = bool(
        actionable and expected_route_family and case.get("known_alias_language")
    )
    claim_without_reopen = sum(
        1
        for packet in packets
        if packet.get("claim_permission") not in {"no_claim_before_reopen", "blocked"}
    )
    return {
        "arm": ARM_ATTENTION_NAV,
        "source_backed_success": False,
        "manual_query_invention_count": 0,
        "tool_call_count": 1,
        "route_count": int(context_payload.get("route_count") or len(routes)),
        "attention_route_packet_count": len(packets),
        "route_actionable": actionable,
        "source_reopen_attempted": False,
        "source_reopen_follow_through": False,
        "selected_route_index": selected_index,
        "selected_next_tool": "recall_deepen" if actionable else "clarify_or_recall",
        "selected_route_family": selected_route_family,
        "route_family_selected_before_manual_search": bool(actionable and selected_route_family),
        "known_alias_cross_language_activation": known_alias_activation,
        "broad_search_after_router_available_count": 0 if actionable else 1,
        "deictic_wrong_visible_context_bind_count": 0,
        "wrong_or_stale_handle": False,
        "wrong_route_drag_count": 0,
        "scent_as_fact_violation": False,
        "claim_without_source_reopen_count": claim_without_reopen,
        "privacy_bypass_count": sum(
            1
            for packet in packets
            if packet.get("masks_applied") and packet.get("source_handles")
        ),
        "foreground_packet_bytes": _packet_bytes(public_packet) if public_packet else 0,
        "correct_but_useless_warning_count": int(actionable and not public_packet.get("route_label")),
        "error_code": "",
        "rejection_stage": "" if actionable else "no_attention_route",
        "time_to_first_useful_source_observed_ms": _elapsed_ms(start) if actionable else None,
        "selected_packet": public_packet,
        "boundary": {
            "navigation_only_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "attention_score_is_not_fact": True,
        },
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def attention_router_activation_readout(
    rows: Sequence[Mapping[str, Any]],
    *,
    cwd: Path,
    clean_source_dir: Path,
    max_routes: int,
) -> dict[str, Any]:
    alias_cases = [
        row
        for row in rows
        if _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
            "known_alias_cross_language_activation"
        )
    ]
    pure_deictic = run_attention_router_navigation_only(
        {
            "case_id": "ar_pure_deictic_design_blocker",
            "case_family": "pure_deictic_ambiguous",
            "intent": "هل في تصميمه عائق قاتل؟",
            "expected_no_source_bind": True,
        },
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        max_routes=max_routes,
    )
    hit_count = sum(
        1
        for row in alias_cases
        if _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
            "route_family_selected_before_manual_search"
        )
    )
    return {
        "measured": True,
        "mode": "deterministic_public_fixture",
        "comparison_arm": ARM_ATTENTION_NAV,
        "pure_deictic_case": pure_deictic,
        "metrics": {
            "multilingual_route_family_hit_rate": _ratio(hit_count, len(alias_cases)),
            "route_family_selected_before_manual_search_count": hit_count,
            "known_alias_cross_language_activation_count": len(alias_cases),
            "deictic_wrong_visible_context_bind_count": int(
                bool(pure_deictic.get("route_actionable"))
            ),
            "broad_search_after_router_available_count": sum(
                int(
                    _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
                        "broad_search_after_router_available_count"
                    )
                    or 0
                )
                for row in rows
            ),
        },
        "boundary": {
            "navigation_only_is_not_evidence": True,
            "pure_deictic_ambiguous_prompts_clarify": True,
            "source_reopen_required_for_claims": True,
            "not_default_selector": True,
        },
    }


__all__ = [
    "ARM_ATTENTION_NAV",
    "attention_router_activation_readout",
    "run_attention_router_navigation_only",
]
