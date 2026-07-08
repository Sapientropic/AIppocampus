"""Opt-in agent continuity path over existing recall and AIppo contracts.

This module is deliberately a thin adapter: one callable path for the #1130 pull
gesture without a new memory store, ranking layer, or claim authority. Foreground
packets stay compact; refs/support ledgers appear only after explicit deepen.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
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
    recall_deepen_packet,
)
from aippocampus_runtime.recall import (
    agent_facade_contract as facade,
)
from aippocampus_runtime.recall import macro_foreground, macro_live_recall
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    handle_recovery_fields,
    missing_handle_payload,
    normalize_route_limit,
    policy_boundary,
)
from aippocampus_runtime.recall.agent_recall_primitives import (
    KIND,
    MAX_ROUTES,
    SCHEMA_VERSION,
    _as_path,
    _clean_source_dir,
    _count_forbidden_keys,
    _load_macro_projection,
    _public_payload,
)
from aippocampus_runtime.recall.feedback.capture import capture_feedback as capture_feedback

MACRO_PACKET_SCHEMA_VERSION = "macro-orientation-agent-packet-v0"
MACRO_HANDLE_PREFIX = "macro:project:"
LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"


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
    """Return compact MemoryPackets plus explicit deepen handles for an agent pull.

    aippocampus-stage-map: this function wires recall stages only. Ranking,
    recovery layers, source gates, and foreground-card policy belong in their
    owner modules so future issue fixes do not keep expanding this hot path.
    """

    from aippocampus_runtime.recall.agent_recall_pipeline import (
        run_agent_recall_pipeline,
    )

    return run_agent_recall_pipeline(
        query,
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        macro_state_path=macro_state_path,
        project=project,
        max_routes=max_routes,
        attention_router=attention_router,
        run_semantic_gate=run_semantic_gate,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
        feedback_path=feedback_path,
        opened_route_keys=opened_route_keys,
        include_associative_fallback=include_associative_fallback,
        associative_path_sidecar_dir=associative_path_sidecar_dir,
        associative_path_bridge_path=associative_path_bridge_path,
        associative_path_navigation_path=associative_path_navigation_path,
        associative_path_active_lock_path=associative_path_active_lock_path,
        associative_path_feedback_path=associative_path_feedback_path,
    )


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
    fixture_now = datetime(2026, 6, 12, tzinfo=timezone.utc)
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
    current = macro_state.latest_project_macro_orientation(
        [moving],
        project="AIppocampus",
        now=fixture_now,
    )
    standing_projection = macro_state.latest_project_macro_orientation(
        [standing],
        project="AIppocampus",
        now=fixture_now,
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
