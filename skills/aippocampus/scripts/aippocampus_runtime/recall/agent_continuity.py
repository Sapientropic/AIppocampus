"""Opt-in agent continuity path over existing recall and AIppo contracts.

This module is deliberately a thin adapter: one callable path for the #1130 pull
gesture without a new memory store, ranking layer, or claim authority. Foreground
packets stay compact; refs/support ledgers appear only after explicit deepen.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from aippocampus_runtime import core
from aippocampus_runtime.aippo import working_contract as aippo
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_shell_action,
    shell_quote,
)
from aippocampus_runtime.macro import orientation_producer
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    navigation_error_payload,
    normalize_handle,
    recall_context_packet,
    recall_deepen_packet,
)
from aippocampus_runtime.navigation import attention_route_projection
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import (
    agent_deepen_requests,
    agent_packet_compaction,
    agent_semantic_diagnostics,
    architecture_navigation_affordance,
    attention_router_policy,
    feedback_events,
    foreground_action_card,
    macro_field_live,
    macro_foreground,
    macro_live_recall,
)
from aippocampus_runtime.recall import (
    agent_facade_contract as facade,
)
from aippocampus_runtime.recall import (
    associative_path_fallback as apw_fallback,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    DEFAULT_MACRO_STATE_RELATIVE_PATHS,
    handle_boundary_fields,
    handle_recovery_fields,
    last_recall_route_key,
    last_recall_route_wildcard_key,
    missing_handle_payload,
    normalize_route_limit,
    policy_boundary,
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
    include_associative_fallback: bool = False,
    associative_path_sidecar_dir: str | Path | None = None,
    associative_path_bridge_path: str | Path | None = None,
    associative_path_navigation_path: str | Path | None = None,
    associative_path_active_lock_path: str | Path | None = None,
    associative_path_feedback_path: str | Path | None = None,
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
    triage_metrics = _memory_packet_triage_metrics(memory_packets)
    deepen_requests = [
        agent_deepen_requests.deepen_request_for_route(route, memory_packet, request_index=index)
        for index, (route, memory_packet) in enumerate(
            zip(routes, memory_packets, strict=True),
            start=1,
        )
        if route.get("handle")
    ]
    associative_path_policy, associative_path_fallback = (
        apw_fallback.maybe_append_associative_path_fallback_with_policy(
            include_associative_fallback=include_associative_fallback,
            query=str(query or ""),
            ordinary_status="ok" if memory_packets else "no_routes",
            memory_packets=memory_packets,
            deepen_requests=deepen_requests,
            triage_metrics=triage_metrics,
            cwd=cwd_path,
            sidecar_dir=associative_path_sidecar_dir,
            clean_source_dir=source_dir,
            semantic_bridge_path=associative_path_bridge_path,
            navigation_path=associative_path_navigation_path,
            active_lock_path=associative_path_active_lock_path,
            feedback_path=associative_path_feedback_path or feedback_path,
        )
    )
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
        "associative_path_policy": associative_path_policy,
        "associative_path_fallback": associative_path_fallback,
        "suggested_next": "agent deepen" if deepen_requests else "search_memory",
        "suggested_next_command": deepen_requests[0].get("copy_paste_command") if deepen_requests else None,
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
            **apw_fallback.recall_fallback_metrics(
                include_associative_fallback,
                associative_path_policy,
                associative_path_fallback,
            ),
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


def capture_feedback(
    *,
    route_id: str,
    outcome: str,
    route_kind: str = "active_path",
    reason: str = "",
    feedback_path: str | Path | None = None,
    feedback_lane: Mapping[str, Any] | None = None,
    schema_version: str = SCHEMA_VERSION,
    kind: str = KIND,
) -> dict[str, Any]:
    """Capture low-authority outcome feedback without changing source truth."""

    event = feedback_events.active_flow_event(
        route_id=route_id,
        route_kind=route_kind,
        signal=outcome,
        source_id=route_id,
        reason=reason,
    )
    wrote_event = False
    if feedback_path:
        target = Path(feedback_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        wrote_event = True
    report = feedback_events.recall_feedback_report([event])
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": "feedback",
            "status": "captured",
            "authority": "low_authority_feedback_signal",
            "event": event,
            "feedback_lane": dict(feedback_lane or {}) if feedback_lane else None,
            "feedback_report": report,
            "wrote_event": wrote_event,
            "storage": "jsonl" if wrote_event else "receipt_only",
            "policy_boundary": {
                **policy_boundary(),
                "feedback_is_source_truth": False,
                "feedback_can_ripen_candidate_without_source": False,
                "source_reopen_required_for_claims": True,
            },
            "red_lines": {
                "feedback_promoted_without_source": 0,
                "source_truth_changed_by_feedback": 0,
            },
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


def main(argv: list[str] | None = None) -> int:
    import importlib

    module = importlib.import_module("aippocampus_runtime.recall.agent_continuity_cli")
    cli_main = cast(
        Callable[[list[str] | None], int],
        vars(module)["main"],
    )
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
