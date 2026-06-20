"""Opt-in agent continuity path over existing recall and AIppo contracts.

This module is deliberately a thin adapter: one callable path for the #1130 pull
gesture without a new memory store, ranking layer, or claim authority. Foreground
packets stay compact; refs/support ledgers appear only after explicit deepen.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.aippo import working_contract as aippo
from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.cli.recovery import action_command_text
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_shell_action,
    shell_quote,
)
from aippocampus_runtime.macro import orientation_producer
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import project_agent_explain_cli_payload
from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    navigation_error_payload,
    normalize_handle,
    recall_context_packet,
    recall_deepen_packet,
)
from aippocampus_runtime.navigation import attention_route_projection
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.recall import (
    agent_deepen_requests,
    agent_packet_compaction,
    agent_semantic_diagnostics,
    architecture_navigation_affordance,
    attention_router_policy,
    background_findings,
    feedback_events,
    foreground_action_card,
    macro_field_live,
    macro_foreground,
    macro_live_recall,
    task_orientation,
)
from aippocampus_runtime.recall import (
    agent_facade_contract as facade,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    DEFAULT_MACRO_STATE_RELATIVE_PATHS,
    agent_recall_missing_query_payload,
    capture_feedback,
    compact_aippo_guidance_card,
    compact_feedback_receipt,
    feedback_lane_resolution,
    handle_boundary_fields,
    handle_from_last_recall_cache,
    handle_recovery_fields,
    last_recall_route_key,
    last_recall_route_wildcard_key,
    last_recall_selector_recovery_fields,
    last_recall_unavailable_payload,
    macro_schema_help,
    macro_state_template,
    mark_last_recall_request_opened,
    missing_feedback_route_payload,
    missing_handle_payload,
    normalize_route_limit,
    opened_route_keys_from_last_recall_cache,
    policy_boundary,
    public_recall_projection,
    query_from_last_recall_cache,
    recall_selector_cache_path,
    render_aippo_human,
    render_deepen_human,
    render_macro_human,
    render_macro_schema_human,
    render_recall_human,
    write_last_recall_cache,
    write_recall_selector_snapshot,
)

SCHEMA_VERSION = "agent-continuity-path-v1"
MACRO_PACKET_SCHEMA_VERSION = "macro-orientation-agent-packet-v0"
KIND = "aippocampus_agent_continuity_path"
MAX_ROUTES = 5
MACRO_HANDLE_PREFIX = "macro:project:"
LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
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
    if explicit:
        return core.canonical_path(explicit)
    global_dir = core.default_thread_clean_source_dir(cwd)
    legacy_dir = cwd / ".aippocampus" / "clean-source"
    if (global_dir / "messages.jsonl").exists() or not (legacy_dir / "messages.jsonl").exists():
        return global_dir
    return legacy_dir


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
    elif route.get("reopenable") or route.get("handle"):
        output_mode = "reopenable_route"
    else:
        output_mode = "direction_only"
    return {
        "route_id": str(route.get("route_id") or "route:unknown"),
        "output_mode": output_mode,
        "claim_permission": "blocked" if output_mode == "ignore_or_blocked" else "no_claim_before_reopen",
        "source_handles": [{"handle": route.get("handle"), "kind": route.get("kind")}]
        if route.get("handle")
        else [],
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
        why_parts = [
            code for code in macro_codes if code.startswith("macro_active_layer")
        ]
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


def _is_aippo_deepen_id(value: Any) -> bool:
    text = str(value or "")
    aippo_id = aippo.AIPPO_ID
    return text in {aippo_id, f"deepen:{aippo_id}"} or text.startswith("deepen:aippo_")


def _macro_route_id(project: str) -> str:
    return f"{MACRO_HANDLE_PREFIX}{project}:latest"


def _macro_project_from_handle(value: Any) -> str | None:
    text = str(value or "")
    if text.startswith("deepen:"):
        text = text[len("deepen:") :]
    if not text.startswith(MACRO_HANDLE_PREFIX) or not text.endswith(":latest"):
        return None
    project = text[len(MACRO_HANDLE_PREFIX) : -len(":latest")]
    return project or None


def _macro_positional_cue_payload(cue: str, *, project: str) -> dict[str, Any]:
    return _public_payload(
        foreground_recovery_card(
            kind=KIND,
            error_code="macro_positional_cue_not_supported",
            message=(
                "agent macro is a project navigation-prior command, not a cue search. "
                "Use agent recall for positional cues."
            ),
            safe_next_actions=[
                foreground_shell_action(
                    action_id="recall_positional_cue",
                    label="Recall this cue",
                    command=f"aippocampus agent recall {shell_quote(cue)} --json",
                    why="A positional macro argument is most likely a continuity cue.",
                    mutation_risk="read_only",
                    claim_boundary="no_claim_before_reopen",
                ),
                foreground_shell_action(
                    action_id="inspect_macro_project",
                    label="Read macro orientation for the project",
                    command=f"aippocampus agent macro --project {shell_quote(project)} --json",
                    why="Use macro only as a navigation prior after project state exists.",
                    mutation_risk="read_only",
                    claim_boundary="macro_orientation_not_source_truth",
                ),
                foreground_shell_action(
                    action_id="explain_macro_schema",
                    label="Explain macro state schema",
                    command="aippocampus agent macro --explain-schema",
                    why="Use this when setting up a local macro-orientation state file.",
                    mutation_risk="read_only",
                    claim_boundary="operator_setup_not_source_evidence",
                ),
            ],
            source_boundary={
                "macro_orientation_is_navigation_only": True,
                "source_reopen_required_before_claims": True,
                "no_write_happened": True,
            },
        )
        | {
            "schema_version": SCHEMA_VERSION,
            "mode": "macro",
            "surface": "macro_orientation",
            "project": project,
            "cue": cue,
        }
    )


def _render_macro_recovery_text(payload: Mapping[str, Any]) -> str:
    actions = [item for item in payload.get("safe_next_actions") or [] if isinstance(item, Mapping)]
    lines = [
        "AIppocampus agent macro: cue provided",
        "decision: use recall for cue-shaped input; macro is only a project navigation prior.",
    ]
    for action in actions[:3]:
        lines.append(f"- {action.get('label') or action.get('id')}: {action.get('command')}")
    lines.append("Boundary: macro orientation is navigation only, not source truth.")
    return "\n".join(lines)


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


def _macro_state_from_projection(projection: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return macro_live_recall.state_from_projection(projection)


def _macro_memory_packet(
    projection: Mapping[str, Any],
    *,
    project: str,
) -> dict[str, Any] | None:
    entry = _macro_state_from_projection(projection)
    if projection.get("status") != "current" or entry is None:
        return None
    if not macro_foreground.state_has_route_signal(entry):
        return None
    route_id = _macro_route_id(project)
    raw_perturbation = entry.get("perturbation")
    perturbation: Mapping[str, Any] = (
        raw_perturbation if isinstance(raw_perturbation, Mapping) else {}
    )
    momentum = macro_foreground.momentum_block(entry)
    foreground_text = macro_foreground.foreground_text(entry)
    return {
        "kind": "aippocampus_memory_packet",
        "packet_kind": "macro_orientation_packet",
        "route_id": route_id,
        "output_mode": "direction_only",
        "authority_level": macro_state.AUTHORITY_LEVEL,
        "action_grammar": macro_state.ACTION_GRAMMAR,
        "claim_permission": macro_state.CLAIM_PERMISSION,
        "foreground_budget_bytes": 360,
        "foreground_text": foreground_text,
        "calibration": {
            "status": "initial_calibration",
            "confidence": "heuristic_low_to_medium",
            "provenance_gloss": "derived from project-local macro state; deepen opens derivation/source trail",
            "source_truth": False,
        },
        "macro_orientation": {
            "movement": perturbation.get("movement"),
            "perturbation": perturbation.get("perturbation"),
            "route_policy": perturbation.get("route_policy"),
            "momentum": {
                "phase": momentum.get("phase"),
                "direction": momentum.get("direction"),
                "route_policy": momentum.get("route_policy"),
            },
        },
        "next_action": "agent_deepen_before_claim",
        "deepen_route_id": f"deepen:{route_id}",
    }


def macro_orientation(
    *,
    project: str = "AIppocampus",
    macro_state_path: str | Path | None = None,
    cwd: str | Path | None = None,
    detail: str = "compact",
) -> dict[str, Any]:
    projection = _load_macro_projection(
        project=project,
        macro_state_path=macro_state_path,
        cwd=cwd,
    )
    packet = _macro_memory_packet(projection, project=project)
    diagnostics: list[str] = []
    if projection.get("status") != "current":
        diagnostics.append("source_required_before_macro_packet")
    elif packet is None:
        diagnostics.append("no_route_or_movement_delta")
    memory_packets = [packet] if packet else []
    deepen_requests = [
        {
            "route_id": packet["route_id"],
            "deepen_route_id": packet["deepen_route_id"],
            "tool": "agent deepen",
            "boundary": "macro_orientation_packet_not_fact",
        }
        for packet in memory_packets
    ]
    forbidden_count = _count_forbidden_keys(memory_packets)
    safe_next_actions: list[dict[str, Any]] = []
    if deepen_requests:
        suggested_next = "agent deepen"
        foreground_action = None
    elif projection.get("status") == "missing_macro_state_path":
        suggested_next = "agent_recall_or_macro_schema_setup"
        producer_status = {
            "state_producer": "available_as_staged_review_path",
            "candidate_queue": orientation_producer.DEFAULT_CANDIDATE_QUEUE.as_posix(),
            "state_ready": False,
            "next_action": (
                "stage source-backed router observations as macro candidates, "
                "then review before writing durable project state"
            ),
            "hot_path_write_allowed": False,
            "total_hexagram_status": "not_produced_by_minimal_producer",
        }
        safe_next_actions = [
            {
                "id": "recall_project_macro_orientation",
                "label": "Recall project macro-orientation context",
                "command_template": 'aippocampus agent recall "{cue}" --json',
                "template_only": True,
                "requires": ["cue"],
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
                "why": (
                    "No macro state exists; ordinary recall is the usable foreground path "
                    "unless the user is setting up macro state."
                ),
            },
            {
                "id": "explain_macro_schema",
                "label": "Explain macro state schema",
                "command": "aippocampus agent macro --explain-schema",
                "mutation_risk": "read_only",
                "claim_boundary": "operator_setup_not_source_evidence",
                "why": "Use this when preparing or repairing a local macro-orientation state file.",
            },
            {
                "id": "init_macro_state_template",
                "label": "Create a macro state template",
                "command": "aippocampus agent macro --init-template --json",
                "mutation_risk": "local_template_stdout_only",
                "claim_boundary": "operator_setup_not_source_evidence",
                "why": "Use this to inspect the expected local JSONL entry shape before writing state.",
            },
        ]
        foreground_action = safe_next_actions[0]
        if detail != "full":
            return _public_payload(
                macro_foreground.compact_missing_state_card(
                    kind=KIND,
                    schema_version=SCHEMA_VERSION,
                    macro_packet_schema_version=MACRO_PACKET_SCHEMA_VERSION,
                    suggested_next=suggested_next,
                    foreground_action=foreground_action,
                    safe_next_actions=safe_next_actions,
                    producer_status=producer_status,
                )
            )
    else:
        suggested_next = "continue_normally"
        foreground_action = None
    action_fields = canonical_foreground_action_fields(foreground_action, safe_next_actions=safe_next_actions) if isinstance(foreground_action, Mapping) else {}
    result = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "macro_packet_schema_version": MACRO_PACKET_SCHEMA_VERSION,
        "mode": "macro",
        "surface": "macro_orientation",
        "status": "ok" if memory_packets else str(projection.get("status") or "no_packet"),
        "opt_in_required": False,
        "memory_packets": memory_packets,
        "deepen_requests": deepen_requests,
        "suggested_next": suggested_next,
        **action_fields,
        "warnings": projection.get("warnings", []),
        "producer_status": {
            "state_producer": "available_as_staged_review_path",
            "candidate_queue": orientation_producer.DEFAULT_CANDIDATE_QUEUE.as_posix(),
            "hot_path_write_allowed": False,
            "total_hexagram_status": "not_produced_by_minimal_producer",
        },
        "diagnostics": diagnostics,
        "metrics": {
            "macro_packet_shown_count": len(memory_packets),
            "foreground_forbidden_key_count": forbidden_count,
        },
        "red_lines": {
            "foreground_source_dump_count": forbidden_count,
            "macro_claim_ready_without_reopen": 0,
            "source_backed_claim_without_reopen": 0,
        },
        "policy_boundary": policy_boundary(),
        "cannot_claim": [
            "source_required_before_macro_packet",
            "macro_orientation_packet_as_fact",
            "bounded_evidence_without_deepen",
        ],
    }
    return _public_payload(result)


def _deepen_macro_orientation(
    *,
    project: str,
    macro_state_path: str | Path | None,
) -> dict[str, Any]:
    projection = _load_macro_projection(project=project, macro_state_path=macro_state_path)
    entry = _macro_state_from_projection(projection)
    if entry is None:
        result: dict[str, Any] = {
            "status": "cannot_verify",
            "projection_status": projection.get("status"),
            "authority_level": macro_state.AUTHORITY_LEVEL,
            "claim_permission": macro_state.CLAIM_PERMISSION,
            "source_refs": [],
            "diagnostics": projection,
        }
    else:
        diagnostics = macro_state.explain_macro_orientation_state(entry)
        result = {
            **diagnostics,
            "projection_status": projection.get("status"),
            "recheck_on": entry.get("recheck_on", []),
            "stale_after_days": entry.get("stale_after_days"),
        }
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "deepen",
            "surface": "macro",
            "status": "ok" if entry is not None else "cannot_verify",
            "result": result,
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["facts_outside_opened_source_scope", "macro_packet_as_fact"],
        }
    )


def _explain_macro_orientation(
    *,
    project: str,
    macro_state_path: str | Path | None,
) -> dict[str, Any]:
    projection = _load_macro_projection(project=project, macro_state_path=macro_state_path)
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "explain",
            "surface": "macro",
            "status": "ok" if projection.get("status") == "current" else "cannot_verify",
            "explanation": {
                "kind": "aippocampus_macro_orientation_explanation",
                "schema_version": MACRO_PACKET_SCHEMA_VERSION,
                "route_id": _macro_route_id(project),
                "decision": "why_macro_orientation",
                "output_mode": "direction_only",
                "claim_permission": macro_state.CLAIM_PERMISSION,
                "next_safe_action": "deepen_or_reopen_source",
                "reason_codes": [
                    "macro_orientation_packet_not_fact",
                    f"projection_status_{projection.get('status')}",
                ],
                "cannot_claim": [
                    "source_truth_without_deepen",
                    "macro_packet_as_full_provenance",
                ],
            },
            "policy_boundary": policy_boundary(),
        }
    )


def _project_workflow_contract() -> dict[str, Any]:
    return aippo.build_project_workflow_public_safe_contract()


def _aippo_red_lines(contract: Mapping[str, Any], activation: Mapping[str, Any]) -> dict[str, int]:
    active_ids = set(activation.get("active_clause_ids") or [])
    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    return {
        "stale_clause_activated_as_current": sum(
            1
            for clause in clauses
            if clause.get("clause_id") in active_ids
            and (clause.get("lifecycle") or {}).get("status")
            in {"stale", "challenged", "blocked", "retired"}
        ),
        "candidate_only_signal_promoted_without_source": sum(
            1
            for clause in clauses
            if clause.get("clause_id") in active_ids
            and (clause.get("authority") or {}).get("class") != "truth_source"
        ),
        "feedback_promoted_without_source": 0,
    }


def recall(
    query: str,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    macro_state_path: str | Path | None = None,
    project: str = "AIppocampus",
    max_routes: int = MAX_ROUTES,
    attention_router: bool | str = False,
    run_semantic_gate: bool = False,
    semantic_gate_mode: str = "off",
    semantic_timeout: int = 12,
    feedback_path: str | Path | None = None,
    opened_route_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Return compact MemoryPackets plus explicit deepen handles for an agent pull."""

    cwd_path = core.canonical_path(cwd or Path.cwd())
    source_dir = _clean_source_dir(cwd_path, clean_source_dir)
    registry_path = (
        _as_path(registry_dir, Path()) if registry_dir else core.aippocampus_registry_dir().resolve()
    )
    requested_limit = normalize_route_limit(max_routes, default=MAX_ROUTES)
    macro_projection = _load_macro_projection(
        project=project,
        macro_state_path=macro_state_path,
        cwd=cwd_path,
    )
    macro_context = macro_live_recall.context_from_projection(macro_projection)
    effective_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=macro_context,
    )
    try:
        packet = recall_context_packet(
            intent=str(query or ""),
            cwd=cwd_path,
            clean_source_dir=source_dir,
            registry_dir=registry_path,
            max_routes=effective_limit,
        )
    except RecallNavigationError as exc:
        action_card = foreground_action_card.build_recall_foreground_action_card(
            status="cannot_verify",
            memory_packets=[],
            deepen_requests=[],
            query=str(query or ""),
        )
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "recall",
                "surface": "agent_cli_or_mcp_adapter",
                "status": "cannot_verify",
                "opt_in_required": False,
                "foreground_action_card": action_card,
                "audit_available": True,
                "memory_packets": [],
                "deepen_requests": [],
                "result": navigation_error_payload(exc),
                "macro_navigation": macro_live_recall.navigation_diagnostics(
                    projection=macro_projection,
                    context=macro_context,
                    requested_limit=requested_limit,
                    effective_limit=effective_limit,
                ),
                "policy_boundary": policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    routes: list[dict[str, Any]] = [
        dict(route) for route in packet.get("routes") or [] if isinstance(route, Mapping)
    ]
    if macro_context is not None:
        foreground_outcomes = [
            outcome
            for route in routes
            for outcome in (route.get("foreground_outcomes") or route.get("runtime_outcomes") or [])
            if isinstance(outcome, Mapping)
        ]
        macro_transition_history = [
            state
            for route in routes
            for state in (route.get("macro_transition_history") or [])
            if state
        ]
        live_macro = macro_field_live.materialize_for_recall(
            query=str(query or ""),
            routes=routes,
            foreground_outcomes=foreground_outcomes,
            macro_transition_history=macro_transition_history,
        )
        macro_projection = macro_field_live.merge_projection(macro_projection, live_macro)
        macro_context = macro_live_recall.context_from_projection(macro_projection)
    macro_navigation = macro_live_recall.navigation_diagnostics(
        projection=macro_projection,
        context=macro_context,
        requested_limit=requested_limit,
        effective_limit=effective_limit,
    )
    macro_metrics: dict[str, Any] = {
        "macro_selected_route_count": 0,
        "macro_wrong_layer_route_count": 0,
        "macro_recheck_trigger_count": 0,
        "macro_reason_code_count": len(macro_navigation["reason_codes"]),
    }
    if macro_context is not None:
        routes, macro_navigation, macro_metrics = macro_live_recall.apply_recall_bias(
            query=str(query or ""),
            routes=routes,
            context=macro_context,
            requested_limit=requested_limit,
            effective_limit=effective_limit,
        )
    router_policy = attention_router_policy.resolve_policy(attention_router)
    feedback_calibration = feedback_events.load_feedback_calibration_report(feedback_path)
    routes, attention_navigation = attention_route_projection.maybe_rerank_routes_with_attention_router(
        enabled=bool(router_policy["enabled"]),
        query=str(query or ""),
        routes=routes,
        max_routes=effective_limit,
        project=project,
        feedback_calibration=feedback_calibration,
    )
    attention_navigation["policy"] = router_policy
    routes = _annotate_route_selection_hints(
        routes,
        macro_navigation=macro_navigation,
        attention_navigation=attention_navigation,
    )
    memory_packets = [_memory_packet_for_route(route) for route in routes]
    deepen_requests = [
        agent_deepen_requests.deepen_request_for_route(
            route,
            memory_packet,
            request_index=index,
        )
        for index, (route, memory_packet) in enumerate(
            zip(routes, memory_packets, strict=True),
            start=1,
        )
        if route.get("handle")
    ]
    already_opened_count = _mark_already_opened_routes(
        memory_packets,
        deepen_requests,
        opened_route_keys=opened_route_keys or set(),
    )
    action_card = foreground_action_card.build_recall_foreground_action_card(
        status="ok" if memory_packets else "no_routes",
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        query=str(query or ""),
        source_registered=_clean_source_has_messages(source_dir),
    )
    navigation_signals = architecture_navigation_affordance.navigation_signals_for_recall(
        query=str(query or ""),
        macro_navigation=macro_navigation,
        attention_navigation=attention_navigation,
        memory_packets=memory_packets,
    )
    semantic_diagnostics = agent_semantic_diagnostics.agent_semantic_gate_diagnostics(
        query=str(query or ""),
        cwd=cwd_path,
        clean_source_dir=source_dir,
        registry_dir=registry_path,
        max_routes=effective_limit,
        run_semantic_gate=run_semantic_gate,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
    )
    forbidden_count = _count_forbidden_keys(memory_packets)
    triage_metrics = _memory_packet_triage_metrics(memory_packets)
    result = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "recall",
        "surface": "agent_cli_or_mcp_adapter",
        "status": "ok" if memory_packets else "no_routes",
        "opt_in_required": False,
        "foreground_action_card": action_card,
        "audit_available": True,
        "memory_packets": memory_packets,
        "deepen_requests": deepen_requests,
        "macro_navigation": macro_navigation,
        "attention_router_navigation": attention_navigation,
        "navigation_signals": navigation_signals,
        "semantic_gate_diagnostics": semantic_diagnostics,
        "suggested_next": "agent deepen" if deepen_requests else "search_memory",
        "suggested_next_command": (
            deepen_requests[0].get("copy_paste_command") if deepen_requests else None
        ),
        **handle_boundary_fields(),
        "policy_boundary": policy_boundary(),
        "metrics": {
            "memory_packet_count": len(memory_packets),
            "deepen_request_count": len(deepen_requests),
            "already_opened_route_count": already_opened_count,
            "macro_orientation_applied": bool(macro_context is not None),
            **attention_route_projection.metrics_for_attention_navigation(attention_navigation),
            "requested_max_routes": requested_limit,
            "effective_max_routes": effective_limit,
            "foreground_forbidden_key_count": forbidden_count,
            **foreground_action_card.card_metrics(action_card),
            **triage_metrics,
            **macro_metrics,
            "source_reopen_success_rate_observed": None,
            "wrong_or_stale_handle_rate_observed": None,
        },
        "red_lines": {
            "foreground_source_dump_count": forbidden_count,
            "source_backed_claim_without_reopen": 0,
            "feedback_promoted_without_source": 0,
        },
        "cannot_claim": [
            "source_truth_without_deepen",
            "default_agent_hook_activation",
            "public_sdk_stability",
        ],
    }
    return _public_payload(result)


def activate_aippo(*, task: str = "") -> dict[str, Any]:
    """Return the compact project/workflow AIppo activation packet."""

    contract = _project_workflow_contract()
    activation = aippo.activation_packet_from_working_contract(contract, task=task)
    usefulness = aippo.usefulness.usefulness_metrics(contract, activation)
    red_lines = _aippo_red_lines(contract, activation)
    has_guidance = bool(activation.get("active_clause_count") or activation.get("use_guidance"))
    result = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "aippo",
        "surface": "project_workflow_ai_ppocampus",
        "status": "ok" if has_guidance else "no_active_contract",
        "opt_in_required": False,
        "task_hint_used": bool(str(task or "").strip()),
        "activation_packet": activation,
        "policy_boundary": policy_boundary(),
        "metrics": {
            "active_clause_count": activation.get("active_clause_count", 0),
            **usefulness,
            "foreground_forbidden_key_count": _count_forbidden_keys(activation),
        },
        "red_lines": red_lines,
        "cannot_claim": [
            "aippo_marketplace_readiness",
            "claim_ready_facts_without_source_reopen",
            "default_foreground_activation",
        ],
    }
    return _public_payload(result)


def _operator_aippo_payload_with_foreground_card(
    payload: dict[str, Any],
    guidance_card: dict[str, Any],
    *,
    task: str,
) -> dict[str, Any]:
    activation_packet = dict(payload.get("activation_packet") or {})
    foreground_action = guidance_card.get("foreground_action")
    if isinstance(foreground_action, dict):
        action_id = str(foreground_action.get("action_id") or foreground_action.get("id") or "")
        activation_packet["foreground_action_id"] = action_id
        if not str(task or "").strip() and action_id == "provide_task_cue":
            # The working contract's internal fallback is "stay_silent", but
            # operator JSON is still a foreground surface. Preserve the raw
            # contract decision while aligning the visible next action with the
            # input-required card so agents do not see two competing primaries.
            activation_packet["contract_next_action"] = activation_packet.get("next_action")
            activation_packet["next_action"] = "provide_task_cue"
            activation_packet["next_action_basis"] = "foreground_input_required"
            activation_packet["availability_basis"] = "task_cue_required"
            activation_packet["blocked_by"] = ["task_cue_required"]
    return {
        **payload,
        "status": guidance_card.get("status", payload.get("status")),
        "ok": guidance_card.get("ok", payload.get("ok")),
        **({"error": guidance_card["error"]} if isinstance(guidance_card.get("error"), dict) else {}),
        "activation_packet": activation_packet,
        "foreground_action_contract": guidance_card.get(
            "foreground_action_contract",
            FOREGROUND_ACTION_CONTRACT_VERSION,
        ),
        "foreground_action": guidance_card.get("foreground_action"),
        "safe_next_actions": guidance_card.get("safe_next_actions", []),
        "foreground_guidance_card": guidance_card,
    }


def deepen(
    handle: Any,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    macro_state_path: str | Path | None = None,
    project: str = "AIppocampus",
    max_matches: int = MAX_ROUTES,
) -> dict[str, Any]:
    """Deepen a recall navigation handle or project AIppo activation id."""

    if handle is None:
        return missing_handle_payload(mode="deepen", schema_version=SCHEMA_VERSION, kind=KIND)
    if _is_aippo_deepen_id(handle):
        contract = _project_workflow_contract()
        result = {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "deepen",
            "surface": "aippo",
            "status": "ok",
            "result": aippo.deepen_aippo_working_contract(contract),
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["facts_outside_opened_source_scope"],
        }
        return _public_payload(result)

    macro_project = _macro_project_from_handle(handle)
    if macro_project is not None:
        return _deepen_macro_orientation(
            project=macro_project,
            macro_state_path=macro_state_path,
        )

    cwd_path = core.canonical_path(cwd or Path.cwd())
    source_dir = _clean_source_dir(cwd_path, clean_source_dir)
    registry_path = (
        _as_path(registry_dir, Path()) if registry_dir else core.aippocampus_registry_dir().resolve()
    )
    match_limit = normalize_route_limit(max_matches, default=MAX_ROUTES)
    try:
        payload = recall_deepen_packet(
            handle=handle,
            clean_source_dir=source_dir,
            registry_dir=registry_path,
            max_matches=match_limit,
        )
    except RecallNavigationError as exc:
        error_payload = navigation_error_payload(exc)
        macro_projection = _load_macro_projection(
            project=project,
            macro_state_path=macro_state_path,
            cwd=cwd_path,
        )
        macro_context = macro_live_recall.context_from_projection(macro_projection)
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "deepen",
                "surface": "recall",
                "status": "cannot_verify",
                "ok": False,
                "cli_exit_recommended": "nonzero",
                "error": error_payload.get("error"),
                "result": error_payload,
                **handle_recovery_fields("deepen"),
                "macro_navigation_diagnostics": macro_live_recall.navigation_diagnostics(
                    projection=macro_projection,
                    context=macro_context,
                    requested_limit=match_limit,
                ),
                "policy_boundary": policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    macro_projection = _load_macro_projection(
        project=project,
        macro_state_path=macro_state_path,
        cwd=cwd_path,
    )
    macro_context = macro_live_recall.context_from_projection(macro_projection)
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "deepen",
            "surface": "recall",
            "status": "ok",
            "result": payload,
            "macro_navigation_diagnostics": macro_live_recall.navigation_diagnostics(
                projection=macro_projection,
                context=macro_context,
                requested_limit=match_limit,
            ),
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["facts_outside_opened_source_scope"],
        }
    )


def explain(
    handle: Any,
    *,
    macro_state_path: str | Path | None = None,
    project: str = "AIppocampus",
) -> dict[str, Any]:
    """Return public-safe reason codes for a recall handle or AIppo id."""

    if handle is None:
        return missing_handle_payload(mode="explain", schema_version=SCHEMA_VERSION, kind=KIND)
    if _is_aippo_deepen_id(handle):
        contract = _project_workflow_contract()
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "explain",
                "surface": "aippo",
                "status": "ok",
                "explanation": aippo.explain_aippo_working_contract(contract),
                "policy_boundary": policy_boundary(),
            }
        )
    macro_project = _macro_project_from_handle(handle)
    if macro_project is not None:
        return _explain_macro_orientation(
            project=macro_project,
            macro_state_path=macro_state_path,
        )
    try:
        normalized = normalize_handle(handle)
    except RecallNavigationError as exc:
        macro_projection = _load_macro_projection(project=project, macro_state_path=macro_state_path)
        macro_context = macro_live_recall.context_from_projection(macro_projection)
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "explain",
                "surface": "recall",
                "status": "cannot_verify",
                "ok": False,
                "cli_exit_recommended": "nonzero",
                "explanation": navigation_error_payload(exc),
                **handle_recovery_fields("explain"),
                "macro_navigation_diagnostics": macro_live_recall.navigation_diagnostics(
                    projection=macro_projection,
                    context=macro_context,
                    requested_limit=MAX_ROUTES,
                ),
                "policy_boundary": policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    kind = str(normalized.get("kind") or "source_ref")
    route_id = str(
        normalized.get("route_id") or normalized.get("domain_id") or normalized.get("lock_id") or ""
    )
    reason = "reopenable_route_available"
    if kind == "continuity_domain":
        reason = "continuity_domain_route_available"
    elif kind == "active_recall_lock":
        reason = "active_recall_lock_route_available"
    macro_projection = _load_macro_projection(project=project, macro_state_path=macro_state_path)
    macro_context = macro_live_recall.context_from_projection(macro_projection)
    macro_diagnostics = macro_live_recall.navigation_diagnostics(
        projection=macro_projection,
        context=macro_context,
        requested_limit=MAX_ROUTES,
    )
    reason_codes = [
        reason,
        "handle_is_navigation_not_fact",
        *macro_diagnostics["reason_codes"],
    ]
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "explain",
            "surface": "recall",
            "status": "ok",
            "explanation": {
                "kind": "aippocampus_route_explanation",
                "schema_version": facade.SCHEMA_VERSION,
                "route_id": route_id,
                "decision": "why_recall",
                "output_mode": "reopenable_route",
                "claim_permission": "no_claim_before_reopen",
                "next_safe_action": "reopen_source",
                "reason_codes": macro_live_recall.append_unique_codes(
                    (),
                    reason_codes,
                    limit=6,
                ),
                "cannot_claim": ["source_truth_without_deepen", "foreground_packet_as_full_provenance"],
            },
            "macro_navigation_diagnostics": macro_diagnostics,
            "policy_boundary": policy_boundary(),
        }
    )


def build_macro_orientation_packet_fixture_report() -> dict[str, Any]:
    moving = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        changing_lines=(1,),
        source_refs=({"source_id": "fixture-macro-source"},),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="人",
        momentum={"basis": {"support_delta": 0.95}},
    )
    standing = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        source_refs=({"source_id": "fixture-standing-source"},),
        updated_at="2026-06-11T11:00:00Z",
        active_layer="人",
    )
    current = macro_state.latest_project_macro_orientation([moving], project="AIppocampus")
    standing_projection = macro_state.latest_project_macro_orientation(
        [standing],
        project="AIppocampus",
    )
    packet = _macro_memory_packet(current, project="AIppocampus")
    standing_packet = _macro_memory_packet(standing_projection, project="AIppocampus")
    cases: list[dict[str, Any]] = [
        {
            "case_id": "manual_search_avoided_by_macro_route_delta",
            "packet": packet,
            "effect": "manual_search_avoided",
        },
        {
            "case_id": "wrong_layer_recall_reduced",
            "packet": packet,
            "effect": "wrong_layer_recall_reduced",
        },
        {
            "case_id": "premature_broad_closeout_blocked",
            "packet": packet,
            "effect": "reopen_before_public_claim",
        },
        {
            "case_id": "standing_state_suppressed",
            "packet": standing_packet,
            "effect": "suppressed_no_route_delta",
        },
    ]
    shown = [case for case in cases if isinstance(case.get("packet"), Mapping)]
    metrics = {
        "claim_ready_macro_packets": sum(
            1
            for case in shown
            if case["packet"]["claim_permission"] == "bounded_claim_allowed"
        ),
        "manual_search_avoided_count": sum(
            1 for case in shown if case["effect"] == "manual_search_avoided"
        ),
        "wrong_layer_recall_reduced_count": sum(
            1 for case in shown if case["effect"] == "wrong_layer_recall_reduced"
        ),
        "premature_broad_closeout_blocked_count": sum(
            1 for case in shown if case["effect"] == "reopen_before_public_claim"
        ),
        "next_action_usefulness_count": sum(
            1
            for case in shown
            if case["packet"]["next_action"] == "agent_deepen_before_claim"
        ),
        "suppressed_no_route_delta_count": sum(1 for case in cases if not case["packet"]),
    }
    report = {
        "kind": "macro_orientation_agent_packet_fixture_report",
        "schema_version": MACRO_PACKET_SCHEMA_VERSION,
        "ok": (
            metrics["claim_ready_macro_packets"] == 0
            and metrics["manual_search_avoided_count"] >= 1
            and metrics["wrong_layer_recall_reduced_count"] >= 1
            and metrics["premature_broad_closeout_blocked_count"] >= 1
            and metrics["next_action_usefulness_count"] >= 1
            and metrics["suppressed_no_route_delta_count"] >= 1
        ),
        "cases": cases,
        "metrics": metrics,
        "authority_level": macro_state.AUTHORITY_LEVEL,
        "claim_permission": macro_state.CLAIM_PERMISSION,
    }
    return _public_payload(report)


def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

def _route_limit_arg(value: str) -> int:
    try:
        return normalize_route_limit(value, default=MAX_ROUTES)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus agent",
        description=(
            "Agent continuity path: recall old context, deepen source, then use "
            "AIppo/background/explain/feedback as supporting actions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "First useful loop:\n"
            '  aippocampus agent recall "old cue" --json\n'
            "  aippocampus agent deepen --request 1 --last-recall --json\n"
            '  aippocampus agent aippo "task cue" --json\n'
            '  aippocampus agent background "task cue" --json\n'
            "  aippocampus agent feedback <route_id> --outcome source_reopen_success --json\n\n"
            "Default recall JSON is compact and foreground-safe. Use --detail full only for "
            "local diagnostics that may include private handles."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    recall_parser = sub.add_parser(
        "recall",
        usage="aippocampus agent recall \"old cue\" [--json] [options]",
        description=(
            "Agent recall task card:\n"
            "  Use for fuzzy continuity cues, old decisions, interrupted work, and handoffs.\n"
            "  Default compact JSON is the foreground-safe surface; --public is a compatibility alias.\n"
            "  Use `aippocampus search \"exact phrase\"` for exact wording lookup.\n"
            "  Treat recall packets as routes; deepen/reopen before factual, stale, or public claims.\n"
            "  Use --detail full only for local diagnostics that may expose private handles."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    recall_parser.add_argument("query", nargs="*")
    recall_parser.add_argument("--query", dest="query_flag")
    recall_parser.add_argument("--cwd")
    recall_parser.add_argument("--clean-source-dir")
    recall_parser.add_argument("--registry-dir")
    recall_parser.add_argument("--macro-state-jsonl")
    recall_parser.add_argument("--project", default="AIppocampus")
    recall_parser.add_argument("--max", type=_route_limit_arg, default=MAX_ROUTES)
    recall_parser.add_argument("--attention-router", action="store_true", help="Use attention router opt-in route sorting.")
    recall_parser.add_argument("--attention-router-mode", choices=attention_router_policy.VALID_MODES)
    recall_parser.add_argument(
        "--feedback-jsonl",
        help="Optional low-authority route feedback JSONL used only for bounded route ordering metadata.",
    )
    recall_parser.add_argument("--semantic", choices=["off", "auto", "on"])
    recall_parser.add_argument("--semantic-gate-mode", choices=["off", "auto", "on"])
    recall_parser.add_argument("--run-semantic-gate", action="store_true")
    recall_parser.add_argument("--semantic-timeout", type=int, default=12)
    recall_parser.add_argument("--last-recall-path")
    recall_parser.add_argument(
        "--public",
        "--compact-json",
        action="store_true",
        dest="public_json",
        help="Compatibility alias for the default compact JSON foreground surface.",
    )
    recall_parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="Use full only for local diagnostics that may include private reopen handles.",
    )
    recall_parser.add_argument("--json", action="store_true")

    task_orientation.add_agent_subparser(sub)

    aippo_parser = sub.add_parser(
        "aippo",
        description=(
            "AIppo guidance card:\n"
            "  Use when a project/workflow task might already have a low-risk working contract.\n"
            "  Default JSON is a compact foreground card, not the operator audit envelope.\n"
            "  Use guidance for planning/review/patch shape only; reopen source before claims.\n"
            "  If no contract matches, run agent recall instead of treating silence as failure."
        ),
        epilog=(
            "Examples:\n"
            "  aippocampus agent aippo --task \"fix hook install UX\" --json\n"
            "  aippocampus agent aippo \"semantic gate MCP health\" --json\n"
            "  aippocampus agent aippo <task> --json --operator-json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    aippo_parser.add_argument("task", nargs="*")
    aippo_parser.add_argument("--task", dest="task_flag")
    aippo_parser.add_argument(
        "--public",
        action="store_true",
        help="Compatibility no-op: AIppo activation output is already public-safe.",
    )
    aippo_parser.add_argument("--json", action="store_true")
    aippo_parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit the full activation envelope for local diagnostics.",
    )
    background_parser = sub.add_parser(
        "background",
        usage='aippocampus agent background "task cue" --json [options]',
        description=(
            "Reviewed background findings card:\n"
            "  Surfaces already reviewed/source-linked Dream or subconscious working-memory rows.\n"
            "  Findings are navigation only; reopen source before claims; no jobs or raw paths."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    background_parser.add_argument("cue", nargs="*")
    background_parser.add_argument("--task", dest="task_flag")
    background_parser.add_argument("--registry-dir")
    background_parser.add_argument("--working-memory")
    background_parser.add_argument("--project", default="AIppocampus")
    background_parser.add_argument("--max", type=_route_limit_arg, default=4)
    background_parser.add_argument("--detail", choices=["compact", "detail", "full", "operator"], default="compact")
    background_parser.add_argument("--operator-json", action="store_true")
    background_parser.add_argument("--json", action="store_true")
    macro_parser = sub.add_parser(
        "macro",
        description=(
            "Macro-orientation navigation card:\n"
            "  Use when project motion, layer, or phase may change which source route to open first.\n"
            "  Do not use macro as source truth, proof, or a replacement for agent recall/deepen.\n"
            "  For exact wording, disputed facts, public claims, or release notes, run recall/deepen.\n"
            "  Schema/template commands are advanced operator setup for the navigation prior."
        ),
        epilog=(
            "Examples:\n"
            "  aippocampus agent macro --project AIppocampus\n"
            "  aippocampus agent recall \"old cue\" --json\n"
            "  aippocampus agent macro --explain-schema\n"
            "  aippocampus agent macro --init-template --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    macro_parser.add_argument("cue", nargs="*")
    macro_parser.add_argument("--project", default="AIppocampus")
    macro_parser.add_argument("--cwd")
    macro_parser.add_argument("--macro-state-jsonl")
    macro_parser.add_argument("--init-template", action="store_true")
    macro_parser.add_argument("--explain-schema", action="store_true")
    macro_parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    macro_parser.add_argument("--operator-json", action="store_true", help="Emit full macro-orientation audit ledgers.")
    macro_parser.add_argument("--json", action="store_true")

    deepen_parser = sub.add_parser(
        "deepen",
        usage="aippocampus agent deepen --request 1 --last-recall --json [options]",
        description=(
            "Agent deepen task card:\n"
            "  Ordinary path: run recall, then reopen a numbered request from the last-recall cache.\n"
            "  Copy-paste: aippocampus agent deepen --request 1 --last-recall --json\n"
            "  Raw handles are local/private diagnostics; do not paste them into public output.\n"
            "  If the cache is missing or stale, rerun agent recall or pass an explicit handle locally.\n"
            "  Deepen opens source windows; use it before exact wording, disputed, or high-risk claims."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    deepen_parser.add_argument("handle", nargs="?")
    deepen_parser.add_argument("--handle", dest="handle_option")
    deepen_parser.add_argument("--request", type=int)
    deepen_parser.add_argument("--last-recall", action="store_true")
    deepen_parser.add_argument("--last-recall-path")
    deepen_parser.add_argument(
        "--recall-selector",
        help="Opaque local selector id from compact agent recall output.",
    )
    deepen_parser.add_argument("--cwd")
    deepen_parser.add_argument("--clean-source-dir")
    deepen_parser.add_argument("--registry-dir")
    deepen_parser.add_argument("--macro-state-jsonl")
    deepen_parser.add_argument("--project", default="AIppocampus")
    deepen_parser.add_argument("--max", type=_route_limit_arg, default=MAX_ROUTES)
    deepen_parser.add_argument(
        "--detail", choices=["compact", "full"], default="compact",
        help="Use full only for local diagnostics that include source-window messages.",
    )
    deepen_parser.add_argument("--json", action="store_true")

    explain_parser = sub.add_parser(
        "explain",
        usage="aippocampus agent explain --request 1 --last-recall --json [options]",
        description=(
            "Agent explain task card:\n"
            "  Ordinary path: explain a numbered route from the last-recall cache.\n"
            "  Copy-paste: aippocampus agent explain --request 1 --last-recall --json\n"
            "  Raw handles remain local/private diagnostics; prefer request numbers in foreground output.\n"
            "  Explanation is routing context, not source evidence."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explain_parser.add_argument("handle", nargs="?")
    explain_parser.add_argument("--handle", dest="handle_option")
    explain_parser.add_argument("--request", type=int)
    explain_parser.add_argument("--last-recall", action="store_true")
    explain_parser.add_argument("--last-recall-path")
    explain_parser.add_argument(
        "--recall-selector",
        help="Opaque local selector id from compact agent recall output.",
    )
    explain_parser.add_argument("--macro-state-jsonl")
    explain_parser.add_argument("--project", default="AIppocampus")
    explain_parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    explain_parser.add_argument("--json", action="store_true")

    feedback_parser = sub.add_parser(
        "feedback",
        description=(
            "Record whether a recall/deepen route helped. By default this writes durable "
            "low-authority route calibration to a scoped local lane; --feedback-jsonl can "
            "override the lane explicitly. Feedback is never source truth."
        ),
        epilog=(
            "Default durable example:\n"
            "  aippocampus agent feedback <route_id> --outcome helped --json\n\n"
            "Explicit lane examples:\n"
            "  aippocampus agent feedback <route_id> --outcome helped --feedback-jsonl <local-feedback.jsonl> --json\n"
            "  aippocampus agent feedback <route_id> --outcome wrong --reason wrong-project --feedback-jsonl <local-feedback.jsonl> --json\n\n"
            "Use `aippocampus do-not-use-here <route_id> --json` "
            "when the user wants an explicit quieting control."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    feedback_parser.add_argument("route_id", nargs="?")
    feedback_parser.add_argument(
        "--outcome",
        default="candidate_delivered",
        help=(
            "What happened in plain words first: helped/useful, wrong/noisy, stale, "
            "prevented. Stored outcome values: "
            + ", ".join(sorted(feedback_events.ACTIVE_FLOW_SIGNALS))
            + "; aliases include helped=source_reopen_success, wrong=wrong_route_drag, "
            "stale=expired."
        ),
    )
    feedback_parser.add_argument(
        "--route-kind",
        default="active_path",
        help="Route kind: " + ", ".join(sorted(feedback_events.ROUTE_KINDS)) + ".",
    )
    feedback_parser.add_argument("--reason", default="")
    feedback_parser.add_argument("--feedback-jsonl")
    feedback_parser.add_argument("--cwd")
    feedback_parser.add_argument("--registry-dir")
    feedback_parser.add_argument("--json", action="store_true")
    feedback_parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit full feedback report diagnostics instead of the compact receipt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "recall":
        query = args.query_flag or " ".join(args.query)
        if not str(query or "").strip():
            payload = agent_recall_missing_query_payload(
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            if args.json:
                _json_out(payload)
            else:
                actions = [
                    action
                    for action in payload.get("safe_next_actions") or []
                    if isinstance(action, Mapping)
                ]
                lines = ["AIppocampus agent recall: cue required"]
                if actions:
                    lines.append(f"Try: {action_command_text(actions[0])}")
                if len(actions) > 1:
                    lines.append(f"Then: {action_command_text(actions[1])}")
                lines.append("Boundary: recovery guidance is not source evidence.")
                emit_public_text("\n".join(lines), stream=sys.stderr)
            return 2
        payload = recall(
            query,
            cwd=args.cwd,
            clean_source_dir=args.clean_source_dir,
            registry_dir=args.registry_dir,
            macro_state_path=args.macro_state_jsonl,
            project=args.project,
            max_routes=args.max,
            attention_router=args.attention_router_mode or args.attention_router,
            run_semantic_gate=args.run_semantic_gate,
            semantic_gate_mode=args.semantic or args.semantic_gate_mode or "off",
            semantic_timeout=args.semantic_timeout,
            feedback_path=feedback_lane_resolution(
                args.feedback_jsonl,
                cwd=args.cwd,
                registry_dir=args.registry_dir,
            )["path"],
            opened_route_keys=opened_route_keys_from_last_recall_cache(args.last_recall_path),
        )
        cache_written = write_last_recall_cache(
            payload.get("deepen_requests") or [],
            query=query,
            cwd=args.cwd,
            clean_source_dir=args.clean_source_dir,
            registry_dir=args.registry_dir,
            macro_state_path=args.macro_state_jsonl,
            project=args.project,
            max_matches=args.max,
            schema_version=SCHEMA_VERSION,
            path=args.last_recall_path,
        )
        selector_id = write_recall_selector_snapshot(args.last_recall_path) if cache_written else None
        payload = {
            **payload,
            "last_recall_cache_available": cache_written,
            "recall_selector_available": bool(selector_id),
            "recall_selector_id": selector_id,
        }
        if args.json:
            if args.public_json or args.detail != "full":
                payload = public_recall_projection(payload, query=query)
            else:
                payload = {
                    "detail": "full",
                    "output_boundary": "local_private_diagnostic_full",
                    "foreground_guidance": (
                        "Use --detail full only for local diagnostics; foreground agents should "
                        "prefer compact JSON or the human request-index action."
                    ),
                    **payload,
                }
            _json_out(payload)
        else:
            print(render_recall_human(payload))
        # A recall miss is still a successful orientation report: it carries
        # recovery actions and attention diagnostics. Hard source/read errors
        # continue through the shared exit-code helper below.
        if payload.get("mode") == "recall" and payload.get("status") in {"ok", "no_routes"}:
            return 0
        return exit_code_for_payload(payload)
    if args.command == "orient":
        return task_orientation.run_agent_command(args, _json_out)
    if args.command == "aippo":
        task = args.task_flag or " ".join(args.task)
        payload = activate_aippo(task=task)
        if args.json:
            guidance_card = compact_aippo_guidance_card(payload, task=task)
            if args.operator_json:
                payload = _operator_aippo_payload_with_foreground_card(
                    payload,
                    guidance_card,
                    task=task,
                )
            else:
                payload = guidance_card
            _json_out(payload)
        else:
            print(render_aippo_human(payload))
        return 2 if payload.get("status") == "needs_input" else 0
    if args.command == "background":
        cue = args.task_flag or " ".join(args.cue)
        payload = background_findings.background_findings_card(
            cue,
            registry_dir=args.registry_dir,
            working_memory_path=args.working_memory,
            project=args.project,
            limit=args.max,
            detail="operator" if args.operator_json else args.detail,
        )
        if args.json:
            _json_out(payload)
        else:
            print("AIppocampus agent background: " + str(payload.get("status") or "unknown") + "\nfindings: " + str(payload.get("finding_count") or 0))
            action = payload.get("foreground_action")
            if isinstance(action, Mapping):
                print("next: " + str(action.get("command") or action.get("command_template") or action.get("id")))
            print("boundary: background findings are navigation only until source is reopened.")
        return 2 if payload.get("status") == "needs_input" else 0
    if args.command == "macro":
        macro_cue = " ".join(args.cue).strip()
        if macro_cue and not args.init_template and not args.explain_schema:
            payload = _macro_positional_cue_payload(macro_cue, project=args.project)
            if args.json:
                _json_out(payload)
            else:
                print(_render_macro_recovery_text(payload))
            return 2
        if args.init_template:
            payload = macro_state_template(args.project)
            if args.json:
                _json_out(payload)
            else:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0
        if args.explain_schema:
            payload = macro_schema_help(
                args.project,
                schema_version=MACRO_PACKET_SCHEMA_VERSION,
            )
            if args.json:
                _json_out(payload)
            else:
                print(render_macro_schema_human(payload))
            return 0
        payload = macro_orientation(
            project=args.project,
            macro_state_path=args.macro_state_jsonl,
            cwd=args.cwd,
            detail="full" if args.operator_json else args.detail,
        )
        if args.json:
            _json_out(payload)
        else:
            print(render_macro_human(payload))
        return 0
    if args.command == "deepen":
        handle = args.handle_option or args.handle
        cached_context: dict[str, Any] = {}
        has_request_selector = bool(args.recall_selector or args.last_recall or args.request is not None)
        selector_cache_path: str | Path | None = args.last_recall_path
        if has_request_selector:
            try:
                if args.recall_selector:
                    selector_cache_path = recall_selector_cache_path(
                        args.recall_selector,
                        last_recall_path_value=args.last_recall_path,
                    )
                handle, cached_context = handle_from_last_recall_cache(
                    request_index=int(args.request or 1),
                    path=selector_cache_path,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                payload = last_recall_unavailable_payload(
                    mode="deepen",
                    exc=exc,
                    schema_version=SCHEMA_VERSION,
                    kind=KIND,
                    cue=query_from_last_recall_cache(selector_cache_path),
                )
                if args.json:
                    _json_out(payload)
                else:
                    print(render_deepen_human(payload))
                return 2
        payload = deepen(
            handle,
            cwd=args.cwd or cached_context.get("cwd"),
            clean_source_dir=args.clean_source_dir or cached_context.get("clean_source_dir"),
            registry_dir=args.registry_dir or cached_context.get("registry_dir"),
            macro_state_path=args.macro_state_jsonl or cached_context.get("macro_state_jsonl"),
            project=args.project or cached_context.get("project") or "AIppocampus",
            max_matches=args.max,
        )
        request_index = int(args.request or 1) if has_request_selector else None
        if request_index is not None and payload.get("status") == "cannot_verify":
            recovery_cue = (
                str(cached_context.get("query") or "").strip()
                or query_from_last_recall_cache(selector_cache_path)
            )
            payload.update(
                last_recall_selector_recovery_fields(
                    "deepen",
                    request_index=request_index,
                    cue=recovery_cue,
                )
            )
            payload.pop("policy_boundary", None)
            payload.pop("cannot_claim", None)
        if request_index is not None and payload.get("status") == "ok":
            try:
                mark_last_recall_request_opened(
                    request_index,
                    path=selector_cache_path,
                    outcome="source_open",
                )
            except Exception:
                pass
        if args.json:
            if args.detail == "full":
                payload = {"detail": "full", "output_boundary": "local_private_diagnostic_full", **payload}
            else:
                payload = compact_agent_deepen_payload(
                    payload,
                    request_index=request_index,
                    last_recall=request_index is not None,
                    recall_selector=str(args.recall_selector or ""),
                    surface="agent_cli_source_court_compact",
                )
            _json_out(payload)
        else:
            print(render_deepen_human(payload))
        return 2 if payload.get("status") == "cannot_verify" or payload.get("ok") is False else 0
    if args.command == "explain":
        handle = args.handle_option or args.handle
        explain_cached_context: dict[str, Any] = {}
        has_request_selector = bool(args.recall_selector or args.last_recall or args.request is not None)
        selector_cache_path = args.last_recall_path
        if has_request_selector:
            try:
                if args.recall_selector:
                    selector_cache_path = recall_selector_cache_path(
                        args.recall_selector,
                        last_recall_path_value=args.last_recall_path,
                    )
                handle, explain_cached_context = handle_from_last_recall_cache(
                    request_index=int(args.request or 1),
                    path=selector_cache_path,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                payload = last_recall_unavailable_payload(
                    mode="explain",
                    exc=exc,
                    schema_version=SCHEMA_VERSION,
                    kind=KIND,
                    cue=query_from_last_recall_cache(selector_cache_path),
                )
                if args.json:
                    _json_out(project_agent_explain_cli_payload(payload, args, surface="agent_cli_route_explain_compact"))
                else:
                    projected = project_agent_explain_cli_payload(
                        payload,
                        args,
                        surface="agent_cli_route_explain_compact",
                    )
                    raw_error = projected.get("error")
                    error_map: Mapping[str, Any] = raw_error if isinstance(raw_error, Mapping) else {}
                    raw_action = projected.get("foreground_action")
                    foreground_action: Mapping[str, Any] = (
                        raw_action if isinstance(raw_action, Mapping) else {}
                    )
                    print("AIppocampus agent explain: cannot verify last recall cache")
                    print("Reason: " + str(error_map.get("code") or "last_recall_unavailable"))
                    next_template = foreground_action.get("command_template") or foreground_action.get("cli_command_template")
                    next_command = foreground_action.get("command") or foreground_action.get("cli_command")
                    if next_template:
                        print("Next: " + str(next_template))
                    elif next_command:
                        print("Next: " + str(next_command))
                    else:
                        print('Next: rerun `aippocampus agent recall "<cue>" --json`, then explain a request number.')
                return 2
        payload = explain(
            handle,
            macro_state_path=args.macro_state_jsonl or explain_cached_context.get("macro_state_jsonl"),
            project=args.project or explain_cached_context.get("project") or "AIppocampus",
        )
        if args.json:
            _json_out(project_agent_explain_cli_payload(payload, args, surface="agent_cli_route_explain_compact"))
        else:
            status = str(payload.get("status") or "unknown")
            explanation = payload.get("explanation")
            data = explanation if isinstance(explanation, Mapping) else {}
            raw_error = data.get("error")
            error = raw_error if isinstance(raw_error, Mapping) else {}
            if status == "cannot_verify":
                print("AIppocampus agent explain: cannot verify handle")
                print("Reason: " + str(error.get("code") or "malformed recall handle"))
                print(
                    "Use: run `aippocampus agent recall --json --detail full ...` and pass "
                    "`deepen_requests[].handle`, or use `agent deepen --request N --last-recall`."
                )
            else:
                print("AIppocampus agent explain: ok")
                print("next_safe_action: " + str(data.get("next_safe_action") or "reopen_source"))
        return 2 if payload.get("status") == "cannot_verify" or payload.get("ok") is False else 0
    if args.command == "feedback":
        if not args.route_id:
            payload = missing_feedback_route_payload(
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            if args.json:
                _json_out(payload)
            else:
                print("AIppocampus agent feedback: route_id required")
                next_action = payload.get("foreground_action")
                command = (
                    next_action.get("command")
                    or next_action.get("command_template")
                    or next_action.get("id")
                    if isinstance(next_action, Mapping)
                    else next_action
                )
                print("Next: " + str(command))
            return 2
        try:
            lane = feedback_lane_resolution(
                args.feedback_jsonl,
                cwd=args.cwd,
                registry_dir=args.registry_dir,
            )
            payload = capture_feedback(
                route_id=args.route_id,
                outcome=args.outcome,
                route_kind=args.route_kind,
                reason=args.reason,
                feedback_path=lane["path"],
                feedback_lane=lane,
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
        except feedback_events.InvalidFeedbackValue as exc:
            payload = _public_payload(
                {
                    "kind": KIND,
                    "schema_version": SCHEMA_VERSION,
                    "mode": "feedback",
                    "status": "rejected",
                    "ok": False,
                    "error": {
                        "code": "invalid_feedback_value",
                        "field": exc.field,
                        "value": exc.value,
                        "valid_values": sorted(exc.accepted),
                        "aliases": dict(
                            sorted((exc.aliases or feedback_events.OUTCOME_ALIASES).items())
                        ),
                    },
                }
            )
            _json_out(payload)
            return 2
        if args.json or args.operator_json:
            _json_out(
                payload
                if args.operator_json
                else compact_feedback_receipt(payload, schema_version=SCHEMA_VERSION, kind=KIND)
            )
        else:
            compact = compact_feedback_receipt(
                payload,
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            print("AIppocampus agent feedback: captured")
            print("storage: " + str(compact["write_boundary"]["storage"]))
            print("next: " + str(compact["foreground_action"]))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
