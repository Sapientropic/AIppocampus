"""Shared primitives for agent recall facades and staged pipelines."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import agent_facade_contract as facade
from aippocampus_runtime.recall import agent_packet_compaction
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    DEFAULT_MACRO_STATE_RELATIVE_PATHS,
    last_recall_route_key,
    last_recall_route_wildcard_key,
)
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir

SCHEMA_VERSION = "agent-continuity-path-v1"
KIND = "aippocampus_agent_continuity_path"
MAX_ROUTES = 5
FOREGROUND_FORBIDDEN_KEYS = {
    "source_refs",
    "source_handles",
    "source_id",
    "message_id",
    "turn_id",
    "head_votes",
    "masks_applied",
    "raw_text",
}


def _as_path(value: str | Path | None, fallback: Path) -> Path:
    if value is None or value == "":
        return fallback
    return Path(value).resolve() if isinstance(value, Path) else Path(str(value)).resolve()


def _clean_source_dir(cwd: Path, explicit: str | Path | None = None) -> Path:
    return resolve_clean_source_dir(cwd, explicit)


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _count_forbidden_keys(value: Any) -> int:
    if isinstance(value, Mapping):
        count = sum(1 for key in value if str(key) in FOREGROUND_FORBIDDEN_KEYS)
        return count + sum(_count_forbidden_keys(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_forbidden_keys(item) for item in value)
    return 0


def _route_kind(route: Mapping[str, Any]) -> str:
    return str(route.get("kind") or "navigation_route").strip() or "navigation_route"


def _route_label(route: Mapping[str, Any]) -> str:
    explicit = str(route.get("route_label") or "").strip()
    if explicit:
        return explicit
    kind = _route_kind(route)
    title = str(route.get("title") or "").strip()
    if title:
        return f"{kind}: {title}"
    return kind


def _route_why(route: Mapping[str, Any]) -> str:
    explicit = str(route.get("why_this_may_matter") or "").strip()
    if explicit and route.get("route_label"):
        return explicit
    kind = _route_kind(route)
    if kind == "continuity_domain":
        return "Continuity domain matched the cue; deepen before using details."
    if kind == "pathlet":
        return "Ordered route chain matched the cue; reopen source before claims."
    if kind == "thread_candidate":
        return "Thread candidate matched the cue; locate source refs before relying on it."
    return "Clean-source route matched the cue; reopen before using details."


def _triage_reason_codes(route: Mapping[str, Any], output_mode: str) -> list[str]:
    explicit = [
        str(code)
        for code in route.get("triage_rank_reason_codes") or []
        if str(code).strip()
    ]
    if explicit:
        return explicit[:4]
    reason_codes = [f"route_kind_{_route_kind(route)}"]
    if output_mode == "reopenable_route":
        reason_codes.append("source_reopen_required")
    if route.get("scope_labels"):
        reason_codes.append("scope_label_available")
    if str(route.get("evidence_level") or "") in {"needs_reopen", "needs_domain_deepen"}:
        reason_codes.append("reopen_before_claim")
    return reason_codes[:4]


def _triage_risk_flags(route: Mapping[str, Any], output_mode: str) -> list[str]:
    raw_flags = route.get("risk_flags")
    flags: list[str] = []
    if isinstance(raw_flags, list | tuple):
        flags = [str(flag) for flag in raw_flags if str(flag).strip()]
    if output_mode == "reopenable_route":
        flags.append("source_reopen_required")
    currentness = str(route.get("currentness") or "").casefold()
    conflict = str(route.get("conflict") or "").casefold()
    if currentness in {"stale", "needs_reopen", "superseded"}:
        flags.append("check_currentness")
    if conflict and conflict not in {"none", "unknown"}:
        flags.append("conflict_requires_deepen")
    result: list[str] = []
    for flag in flags:
        if flag not in result:
            result.append(flag)
    return result[:6]


def _route_packet_from_navigation_route(route: Mapping[str, Any]) -> dict[str, Any]:
    action = str(route.get("action_grammar") or "")
    if action == "ignore_or_blocked":
        output_mode = "ignore_or_blocked"
    elif route.get("reopenable") is True or (
        route.get("handle")
        and route.get("reopenable") is not False
        and _route_kind(route) != "thread_candidate"
    ):
        output_mode = "reopenable_route"
    else:
        output_mode = "direction_only"
    source_handles = []
    if output_mode == "reopenable_route" and route.get("handle"):
        source_handles = [{"handle": route.get("handle"), "kind": route.get("kind")}]
    return {
        "route_id": str(route.get("route_id") or "route:unknown"),
        "output_mode": output_mode,
        "claim_permission": "blocked"
        if output_mode == "ignore_or_blocked"
        else "no_claim_before_reopen",
        "source_handles": source_handles,
        "head_votes": [],
        "masks_applied": ["blocked"] if output_mode == "ignore_or_blocked" else [],
        "route_label": _route_label(route),
        "why_may_matter": _route_why(route),
        "preview_permission": "route_selection_only",
        "route_kind": _route_kind(route),
        "matched_cue_family": route.get("matched_cue_family"),
        "scope_bucket": route.get("scope_bucket"),
        "route_topic": route.get("route_topic"),
        "label_granularity": route.get("label_granularity"),
        "route_label_specificity_score": route.get("route_label_specificity_score"),
        "risk_flags": _triage_risk_flags(route, output_mode),
        "triage_rank_reason_codes": _triage_reason_codes(route, output_mode),
    }


def _memory_packet_for_route(route: Mapping[str, Any]) -> dict[str, Any]:
    packet = facade.memory_packet_from_route_packet(_route_packet_from_navigation_route(route))
    if packet["next_action"] == "use_hint" and route.get("handle"):
        packet["next_action"] = "reopen_source"
    route_topic = _safe_code_text(route.get("route_topic"))
    if route_topic and not packet.get("route_topic"):
        packet["route_topic"] = route_topic
    route_kind = _safe_code_text(route.get("kind"))
    if route_kind == "thread_candidate":
        packet["route_kind"] = route_kind
    source_chain_role = _safe_code_text(route.get("source_chain_role"))
    if source_chain_role:
        packet["source_chain_role"] = source_chain_role
    matched_cue_family = _safe_code_text(route.get("matched_cue_family"))
    if matched_cue_family:
        packet["matched_cue_family"] = matched_cue_family
    hint = _selection_hint_for_route(route)
    if hint:
        packet["selection_hint"] = hint
    reason_codes = _safe_code_list(route.get("_route_delta_reason_codes"), limit=4)
    if reason_codes:
        packet["route_delta_reason_codes"] = reason_codes
    recommended_next = str(route.get("_recommended_next") or "").strip()
    if recommended_next:
        packet["recommended_next"] = recommended_next
    return _fit_memory_packet_with_route_delta(packet)


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _clean_source_has_messages(source_dir: Path) -> bool:
    messages = source_dir / "messages.jsonl"
    if not messages.exists():
        return False
    try:
        with messages.open("r", encoding="utf-8") as handle:
            return any(line.strip() for line in handle)
    except OSError:
        return False


def _safe_code_list(value: Any, *, limit: int = 4) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    out: list[str] = []
    for item in value:
        clean = "".join(
            ch for ch in str(item).strip()[:80] if ch.isalnum() or ch in {"_", "-", ":"}
        )
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _safe_code_text(value: Any, *, limit: int = 80) -> str:
    clean = "".join(
        ch for ch in str(value or "").strip()[:limit] if ch.isalnum() or ch in {"_", "-", ":"}
    )
    return clean


def _selection_hint_for_route(route: Mapping[str, Any]) -> dict[str, str]:
    raw = route.get("_selection_hint")
    if not isinstance(raw, Mapping):
        return {}
    source = str(raw.get("source") or "").strip()
    why = core.compact_text(str(raw.get("why") or "").strip(), 160)
    if not source or not why:
        return {}
    return {"source": source[:80], "why": why}


def _fit_memory_packet_with_route_delta(packet: dict[str, Any]) -> dict[str, Any]:
    return agent_packet_compaction.fit_memory_packet_with_route_delta(packet)


def _unique_codes(*groups: Any, limit: int = 4) -> list[str]:
    out: list[str] = []
    for group in groups:
        for code in _safe_code_list(group, limit=limit):
            if code not in out:
                out.append(code)
            if len(out) >= limit:
                return out
    return out


def _annotate_route_selection_hints(
    routes: list[dict[str, Any]],
    *,
    macro_navigation: Mapping[str, Any],
    attention_navigation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    annotated = [dict(route) for route in routes]
    if not annotated:
        return annotated

    if macro_navigation.get("applied"):
        macro_codes = _safe_code_list(macro_navigation.get("reason_codes"), limit=4)
        active_layer = str(macro_navigation.get("active_layer") or "").strip()
        why_parts = [code for code in macro_codes if code.startswith("macro_active_layer")]
        if active_layer and not why_parts:
            why_parts.append(f"macro_active_layer_{active_layer}")
        annotated[0]["_selection_hint"] = {
            "source": "macro_orientation",
            "why": why_parts[0] if why_parts else "macro_active_layer",
        }
        annotated[0]["_route_delta_reason_codes"] = _unique_codes(
            ["macro_orientation_recall_prior"],
            annotated[0].get("_route_delta_reason_codes"),
            limit=4,
        )
        annotated[0]["_recommended_next"] = "deepen_this_route_first"

    if attention_navigation.get("enabled") and attention_navigation.get("top_route_changed"):
        selected_id = str(attention_navigation.get("selected_route_id") or "").strip()
        target_index = 0
        if selected_id:
            for index, route in enumerate(annotated):
                if str(route.get("route_id") or "") == selected_id:
                    target_index = index
                    break
        selected = annotated[target_index]
        selected["_selection_hint"] = {
            "source": "attention_router",
            "why": "top_route_changed",
        }
        selected["_route_delta_reason_codes"] = _unique_codes(
            ["attention_router_top_route_changed"],
            selected.get("_route_delta_reason_codes"),
            limit=4,
        )
        selected["_recommended_next"] = "deepen_this_route_first"
    return annotated


def _selection_hint_present(packet: Mapping[str, Any]) -> bool:
    label = str(packet.get("route_label") or "").strip()
    hint = str(packet.get("display_hint") or "").strip()
    return bool(label) and bool(
        hint
        and hint != "A source route may matter; reopen it before using the detail."
    )


def _triage_signature(packet: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(packet.get("route_label") or "").casefold(),
            str(packet.get("display_hint") or "").casefold(),
            ",".join(str(code) for code in packet.get("triage_rank_reason_codes") or []),
        ]
    )


def _memory_packet_triage_metrics(memory_packets: list[dict[str, Any]]) -> dict[str, Any]:
    triage_packets = [
        packet
        for packet in memory_packets
        if packet.get("output_mode") in {"bounded_summary_as_route", "reopenable_route"}
    ]
    signatures = {
        _triage_signature(packet)
        for packet in triage_packets
        if _selection_hint_present(packet)
    }
    distinctiveness = round(len(signatures) / len(triage_packets), 3) if triage_packets else 0.0
    return {
        "packet_triage_distinctiveness": distinctiveness,
        "blind_deepen_required_count": sum(
            1
            for packet in triage_packets
            if packet.get("output_mode") == "reopenable_route"
            and packet.get("next_action") == "reopen_source"
            and not _selection_hint_present(packet)
        ),
        "top_route_selection_hint_present_count": sum(
            1 for packet in triage_packets if _selection_hint_present(packet)
        ),
        "topic_label_present_count": sum(1 for packet in triage_packets if packet.get("route_topic")),
        "scope_only_label_count": sum(
            1
            for packet in triage_packets
            if packet.get("label_granularity") == "scope_bucket_only"
        ),
        "route_label_specificity_floor": min(
            (
                float(packet.get("route_label_specificity_score") or 0)
                for packet in triage_packets
            ),
            default=0.0,
        ),
    }


def _mark_already_opened_routes(
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    *,
    opened_route_keys: set[str],
) -> int:
    if not opened_route_keys:
        return 0
    requests_by_route = {
        str(request.get("route_id") or ""): request
        for request in deepen_requests
        if isinstance(request, Mapping)
    }
    opened_count = 0
    for packet in memory_packets:
        route_id = str(packet.get("route_id") or "").strip()
        if not route_id:
            continue
        request = requests_by_route.get(route_id)
        route_key = last_recall_route_key(
            route_id,
            request.get("handle_sha256_12") if request else None,
        )
        wildcard_key = last_recall_route_wildcard_key(route_id)
        exact_opened = bool(route_key and route_key in opened_route_keys)
        route_opened = exact_opened or bool(wildcard_key and wildcard_key in opened_route_keys)
        if not route_opened:
            continue
        packet["already_opened"] = True
        packet["recommended_next"] = "use_opened_route_context_or_deepen_if_scope_changed"
        packet["next_action"] = "use_opened_route_context_or_deepen_if_scope_changed"
        packet["opened_route_context"] = {
            "status": "opened_in_this_local_session",
            "same_route_and_handle_digest": exact_opened,
            "reopen_again_only_if_scope_changed": True,
        }
        if request:
            request["already_opened"] = True
        opened_count += 1
    return opened_count


def _load_macro_projection(
    *,
    project: str,
    macro_state_path: str | Path | None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    state_path = _resolve_macro_state_path(macro_state_path, cwd=cwd)
    if state_path is None:
        return {
            "kind": "macro_orientation_latest_projection",
            "project": project,
            "status": "missing_macro_state_path",
            "usable_as_current_navigation_pointer": False,
            "usable_as_current_instruction": False,
            "authority_level": macro_state.AUTHORITY_LEVEL,
            "claim_permission": macro_state.CLAIM_PERMISSION,
        }
    warnings: list[dict[str, Any]] = []
    entries = macro_state.load_macro_orientation_states(state_path, warnings=warnings)
    projection = macro_state.latest_project_macro_orientation(entries, project=project)
    if warnings:
        projection = {**projection, "warnings": warnings}
    return projection


def _resolve_macro_state_path(
    macro_state_path: str | Path | None,
    *,
    cwd: str | Path | None = None,
) -> Path | None:
    if macro_state_path is not None and str(macro_state_path) != "":
        return Path(macro_state_path).resolve()
    if cwd is None:
        return None
    root = core.canonical_path(cwd)
    # Default recall may consume only project-local macro state. Do not broaden
    # this into global registry or private rollout discovery without a separate
    # privacy review: macro is a navigation prior, not ambient evidence.
    for relative in DEFAULT_MACRO_STATE_RELATIVE_PATHS:
        candidate = root / relative
        if candidate.is_file():
            return candidate.resolve()
    return None
