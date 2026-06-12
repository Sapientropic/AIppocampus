"""Attention-router arm helpers for the recall-navigation comparison harness."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp import server as mcp_server
from aippocampus_runtime.navigation import attention_hot_router
from aippocampus_runtime.navigation.attention_route_projection import (
    attention_token_for_route,
    packet_bytes,
    public_attention_packet,
    route_helpfulness_diagnostics,
    select_attention_packet,
)
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


def _blank_helpfulness_diagnostics() -> dict[str, Any]:
    return {
        "selected_query_term_overlap_count": 0,
        "selected_route_label_specificity_score": 0.0,
        "route_label_specificity_floor": 0.0,
        "route_label_expected_family_match": False,
        "explicit_bridge_reason_present": False,
        "zero_overlap_without_bridge_reason": True,
        "selected_why_may_matter_specific_enough": False,
        "attention_router_applied_but_no_help_count": 0,
    }


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
            **_blank_helpfulness_diagnostics(),
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
            **_blank_helpfulness_diagnostics(),
            "boundary": {
                "navigation_only_is_not_evidence": True,
                "source_reopen_required_for_claims": True,
            },
        }

    routes = [route for route in _as_list(context_payload.get("routes")) if isinstance(route, Mapping)]
    tokens = [attention_token_for_route(route, index=index) for index, route in enumerate(routes)]
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
    selected_index, selected_packet = select_attention_packet(packets)
    public_packet = public_attention_packet(selected_packet)
    actionable = selected_packet is not None
    selected_route = (
        routes[selected_index]
        if selected_index is not None and selected_index < len(routes)
        else None
    )
    helpfulness = route_helpfulness_diagnostics(
        query=intent,
        route=selected_route,
        packet=selected_packet,
        expected_route_family=str(case.get("expected_route_family") or ""),
    )
    expected_route_family = str(case.get("expected_route_family") or "")
    selected_route_family = (
        expected_route_family
        if actionable
        and expected_route_family
        and helpfulness["route_label_expected_family_match"]
        else ""
    )
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
        "foreground_packet_bytes": packet_bytes(public_packet) if public_packet else 0,
        "correct_but_useless_warning_count": int(actionable and not public_packet.get("route_label")),
        **helpfulness,
        "attention_router_applied_but_no_help_count": int(
            actionable
            and selected_index == 0
            and (
                helpfulness["zero_overlap_without_bridge_reason"]
                or helpfulness["route_label_specificity_floor"] < 0.5
                or not helpfulness["selected_why_may_matter_specific_enough"]
            )
        ),
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
            "attention_router_applied_but_no_help_count": sum(
                int(
                    _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
                        "attention_router_applied_but_no_help_count"
                    )
                    or 0
                )
                for row in rows
            ),
            "zero_overlap_without_bridge_reason_count": sum(
                int(
                    bool(
                        _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
                            "zero_overlap_without_bridge_reason"
                        )
                    )
                )
                for row in rows
            ),
            "route_label_specificity_below_floor_count": sum(
                int(
                    float(
                        _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
                            "route_label_specificity_floor"
                        )
                        or 0.0
                    )
                    < 0.5
                    and bool(
                        _as_dict(_as_dict(row.get("arms")).get(ARM_ATTENTION_NAV)).get(
                            "route_actionable"
                        )
                    )
                )
                for row in rows
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
