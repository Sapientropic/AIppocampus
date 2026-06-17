"""CLI-only support helpers for the opt-in agent continuity facade."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.aippo import working_contract as aippo_working_contract
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    foreground_recovery_card,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.mcp.public_projection import compact_agent_recall_payload
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import feedback_events

LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
DEFAULT_FEEDBACK_ENV = "AIPPOCAMPUS_FEEDBACK_JSONL"
DEFAULT_MACRO_STATE_RELATIVE_PATHS = (
    Path(".aippocampus") / "macro-orientation.jsonl",
    Path(".aippocampus") / "macro_orientation.jsonl",
)
LOCAL_PRIVATE_HANDLE_FIELDS = [
    "suggested_next_command",
    "foreground_action_card.callable_handle",
    "deepen_requests[].handle",
    "deepen_requests[].callable_handle",
    "deepen_requests[].machine_next_command",
    "deepen_requests[].copy_paste_command",
]
LOCAL_REOPEN_TOKEN_ENCODING = "utf8_xor_v1_not_encryption"
_LOCAL_REOPEN_TOKEN_MASK = 0xA5
MIN_ROUTE_LIMIT = 1
MAX_ROUTE_LIMIT = 25


class RouteLimitError(ValueError):
    """Raised when a caller passes an explicit, unsafe recall route limit."""


def normalize_route_limit(
    value: Any,
    *,
    default: int,
    field: str = "max",
    minimum: int = MIN_ROUTE_LIMIT,
    maximum: int = MAX_ROUTE_LIMIT,
) -> int:
    """Validate route limits without treating explicit zero as "use default".

    The recall facade used to coerce ``0`` through ``value or default`` and then
    clamp other invalid values. That made omitted limits and explicit invalid
    limits indistinguishable, which is surprising in both CLI and MCP surfaces.
    Keep omission ergonomic, but reject values that would silently change the
    caller's requested route budget.
    """

    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RouteLimitError(f"{field} must be an integer") from exc
    if parsed < minimum:
        raise RouteLimitError(f"{field} must be >= {minimum}")
    if parsed > maximum:
        raise RouteLimitError(f"{field} must be <= {maximum}")
    return parsed


def handle_boundary_fields() -> dict[str, Any]:
    return {
        "local_private_fields": list(LOCAL_PRIVATE_HANDLE_FIELDS),
        "handle_boundary": "local_private_reopen_token",
    }


def policy_boundary() -> dict[str, Any]:
    return {
        "opt_in_required": False,
        "activation_model": "explicit_foreground_action",
        "legacy_opt_in_wording_retired": True,
        "default_hook_foreground": False,
        "navigation_only_not_fact": True,
        "source_reopen_required_for_strong_claims": True,
        "low_risk_guidance_allowed_without_reopen": True,
        "public_sdk_stability_claim": False,
        "hosted_api_claim": False,
    }


def agent_recall_missing_query_payload(
    *,
    schema_version: str,
    kind: str,
) -> dict[str, Any]:
    payload = foreground_recovery_card(
        kind=kind,
        status="needs_input",
        error_code="agent_recall_cue_required",
        message="agent recall needs a cue, old decision, issue title, or handoff phrase.",
        safe_next_actions=[
            foreground_template_action(
                action_id="recall_vague_cue",
                label="Run agent recall with a continuity cue",
                command_template='aippocampus agent recall "{cue}" --json',
                requires=["cue"],
                why="Use recall for fuzzy continuity, unfinished work, and old route context.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_template_action(
                action_id="search_exact_phrase",
                label="Search exact clean-source wording",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires=["exact_phrase"],
                why="Use search when you know concrete source wording.",
                mutation_risk="read_only",
                claim_boundary="search_result_requires_source_boundary",
            ),
            foreground_shell_action(
                action_id="check_onboarding_status",
                label="Check source registration",
                command="aippocampus onboard --provider auto --status --json",
                why="Use this if recall/search has no local clean-source surface yet.",
                mutation_risk="read_only",
                claim_boundary="setup_status_not_memory_evidence",
            ),
        ],
    )
    payload.update(
        {
            "schema_version": schema_version,
            "recovery_kind": "aippocampus_agent_recall_recovery",
            "mode": "recall",
            "surface": "agent_cli_or_mcp_adapter",
            "policy_boundary": policy_boundary(),
            "claim_boundary": {
                "can_use_for": ["asking_for_a_cue", "choosing_a_read_only_next_action"],
                "must_reopen_for": ["source_backed_claims", "absence_of_memory_claims"],
                "detail_available_with_template": 'aippocampus agent recall "{cue}" --json --detail full',
                "detail_requires": ["cue"],
            },
        }
    )
    return payload


def _foreground_template_action(
    action_id: str, command_template: str, requires: list[str], label: str, why: str
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "command_template": command_template,
        "requires": list(requires),
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": why,
    }


def _recall_with_cue_action(*, label: str, why: str, action_id: str = "recall_with_cue") -> dict[str, Any]:
    return _foreground_template_action(
        action_id, 'aippocampus agent recall "{cue}" --json', ["cue"], label, why
    )


def _request_index_followup_action(mode: str) -> dict[str, Any]:
    return _foreground_template_action(
        f"{mode}_last_recall_request",
        f"aippocampus agent {mode} --request {{request_index}} --last-recall --json",
        ["last_recall_cache", "request_index"],
        f"Run agent {mode} against a numbered route from the last recall",
        "Requires a fresh recall cache and selected request index.",
    )


def handle_recovery_fields(mode: str) -> dict[str, Any]:
    actions = [
        _recall_with_cue_action(
            label="Run agent recall with a continuity cue",
            why="Recall must run before request-index deepen/explain.",
        ),
        _request_index_followup_action(mode),
    ]
    return {
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": actions[0],
        "follow_up_action": actions[1],
        "agent_next_action": actions[0],
        "next_safe_action": "recall_with_cue_then_request_index",
        "safe_next_actions": actions,
    }


def last_recall_cache_recovery_fields(mode: str) -> dict[str, Any]:
    del mode
    action = _recall_with_cue_action(
        label="Rerun agent recall with full detail",
        why="The last-recall cache was unavailable; rerun recall for a fresh route.",
    ) | {
        "id": "recall_with_cue_full_detail",
        "command_template": 'aippocampus agent recall "{cue}" --json --detail full',
    }
    return {
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": action,
        "agent_next_action": action,
        "next_safe_action": "recall_with_cue_full_detail",
        "safe_next_actions": [action],
    }


def missing_handle_payload(
    *,
    mode: str,
    schema_version: str,
    kind: str,
) -> dict[str, Any]:
    body = {
        "error": {
            "code": "missing_recall_handle",
            "message": f"agent {mode} requires a local handle or --request N --last-recall",
        },
        "next_safe_action": "recall_with_cue_then_request_index",
    }
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": mode,
            "surface": "recall",
            "status": "cannot_verify",
            "ok": False,
            "result" if mode == "deepen" else "explanation": body,
            **handle_recovery_fields(mode),
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
        }
    )


def last_recall_unavailable_payload(
    *,
    mode: str,
    exc: Exception,
    schema_version: str,
    kind: str,
) -> dict[str, Any]:
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": mode,
            "surface": "recall",
            "status": "cannot_verify",
            "ok": False,
            "result": {
                "error": {
                    "code": "last_recall_unavailable",
                    "message": str(exc),
                }
            },
            **last_recall_cache_recovery_fields(mode),
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
        }
    )


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _workspace_feedback_scope_id(cwd: str | Path | None = None) -> str:
    root = Path(cwd or Path.cwd()).expanduser().resolve()
    digest = hashlib.sha256(str(root).encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"workspace_{digest}"


def feedback_lane_resolution(
    explicit: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
    registry_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve the low-authority route-feedback lane for foreground controls.

    The default lane is deliberately registry-backed and workspace-scoped. Do
    not broaden this into a project-local `.aippocampus` write or a global
    unscoped feedback file: route feedback is useful calibration, not source
    truth, and `do-not-use-here` must not bleed across unrelated workspaces.
    """

    if explicit:
        return {
            "path": Path(explicit).expanduser().resolve(),
            "path_source": "argument",
            "scope": "explicit_override",
            "path_label": "explicit-feedback-jsonl",
            "raw_path_emitted": False,
        }
    env_value = os.environ.get(DEFAULT_FEEDBACK_ENV)
    if env_value:
        return {
            "path": Path(env_value).expanduser().resolve(),
            "path_source": "environment",
            "scope": "explicit_override",
            "path_label": f"{DEFAULT_FEEDBACK_ENV}",
            "raw_path_emitted": False,
        }
    scope_id = _workspace_feedback_scope_id(cwd)
    root = Path(registry_dir).expanduser().resolve() if registry_dir else core.aippocampus_registry_dir().resolve()
    return {
        "path": root / "agent" / "feedback" / scope_id / "route-feedback.jsonl",
        "path_source": "default_registry",
        "scope": "current_workspace",
        "scope_id": scope_id,
        "path_label": "registry/agent/feedback/<workspace-scope>/route-feedback.jsonl",
        "raw_path_emitted": False,
        "review_boundary": {
            "local_jsonl_lane": True,
            "source_truth_mutation_allowed": False,
            "remove_or_edit_requires_explicit_local_file_action": True,
        },
    }


def capture_feedback(
    *,
    route_id: str,
    outcome: str,
    route_kind: str = "active_path",
    reason: str = "",
    feedback_path: str | Path | None = None,
    feedback_lane: Mapping[str, Any] | None = None,
    schema_version: str = "agent-continuity-path-v1",
    kind: str = "aippocampus_agent_continuity_path",
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


def compact_feedback_receipt(
    payload: Mapping[str, Any],
    *,
    schema_version: str = "agent-continuity-path-v1",
    kind: str = "aippocampus_agent_continuity_path",
) -> dict[str, Any]:
    raw_event = payload.get("event")
    event: Mapping[str, Any] = raw_event if isinstance(raw_event, Mapping) else {}
    wrote_event = bool(payload.get("wrote_event"))
    raw_lane = payload.get("feedback_lane")
    lane: Mapping[str, Any] = raw_lane if isinstance(raw_lane, Mapping) else {}
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": "feedback",
            "status": payload.get("status") or "captured",
            "ok": True,
            "authority": "low_authority_feedback_signal",
            "receipt": {
                "route_id": event.get("route_id"),
                "route_kind": event.get("route_kind"),
                "outcome": event.get("signal"),
                "reason_recorded": bool(event.get("reason")),
            },
            "write_boundary": {
                "storage": "jsonl" if wrote_event else "receipt_only",
                "wrote_event": wrote_event,
                "will_affect_future_routes": wrote_event,
                "source_truth_changed_by_feedback": False,
                "feedback_is_source_truth": False,
            },
            "feedback_lane": dict(lane) if lane else None,
            "agent_next_action": (
                "Feedback was written to the scoped local calibration lane; continue the task "
                "and reopen source before making claims."
                if wrote_event
                else "This is only a receipt. Add --feedback-jsonl <path> when you want future "
                "agent recall to consume the feedback signal."
            ),
            "operator_json_available": True,
            "policy_boundary": {
                **policy_boundary(),
                "source_reopen_required_for_claims": True,
            },
        }
    )


def missing_feedback_route_payload(
    *,
    schema_version: str = "agent-continuity-path-v1",
    kind: str = "aippocampus_agent_continuity_path",
) -> dict[str, Any]:
    route_choices = [
        {
            "id": f"feedback_last_recall_route_{choice['request_index']}",
            "label": f"Record feedback on last recall route {choice['request_index']}",
            "command": (
                f"aippocampus agent feedback {choice['route_id']} "
                "--outcome source_reopen_success --json"
            ),
            "route_id": choice["route_id"],
            "request_index": choice["request_index"],
            "source": "last_recall_cache",
            "mutation_risk": "durable_low_authority_feedback_write",
            "claim_boundary": "feedback_is_not_source_truth",
            "why": "Use when the selected route from the current recall was helpful.",
        }
        for choice in last_recall_route_choices(limit=3)
    ]
    fallback_actions = [
        _recall_with_cue_action(
            action_id="recall_before_feedback",
            label="Find a route before recording feedback",
            why="Feedback needs a route_id from a recall result.",
        ),
        {
            "id": "deepen_if_needed",
            "command": "aippocampus agent deepen --request 1 --last-recall --json",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "why": "Use after recall when you need to inspect the first route before judging it.",
        },
        {
            "id": "record_route_feedback",
            "command_template": (
                "aippocampus agent feedback {route_id} --outcome {feedback_outcome} --json"
            ),
            "requires": ["route_id", "feedback_outcome"],
            "mutation_risk": "durable_low_authority_feedback_write",
            "claim_boundary": "feedback_is_not_source_truth",
            "why": "Use once a concrete route id and outcome are known.",
        },
    ]
    actions = route_choices or fallback_actions
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": "feedback",
            "status": "needs_route_id",
            "ok": False,
            "last_recall_route_choice_count": len(route_choices),
            "agent_next_action": actions[0],
            "foreground_action": actions[0],
            "safe_next_actions": actions,
            "write_boundary": {
                "wrote_event": False,
                "storage": "none",
                "feedback_is_source_truth": False,
            },
        }
    )


def public_recall_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return compact recall JSON suitable for issue/discussion/log paste.

    Plain ``--json`` stays the local diagnostic surface with private reopen
    handles. The public/compact JSON path should be the same frontstage shape a
    foreground agent can actually use: one action, route receipts, and a clear
    source boundary, not a redacted audit dump.
    """

    source = dict(payload)
    source.update(handle_boundary_fields())
    projected = compact_agent_recall_payload(source)
    projected.update(handle_boundary_fields())
    projected["surface"] = "agent_cli_public_compact"
    projected["output_boundary"] = "public_compact_no_local_private_handles"
    cache_available = bool(source.get("last_recall_cache_available"))
    projected["last_recall_cache_available"] = cache_available
    action = projected.get("foreground_action")
    action_map = action if isinstance(action, Mapping) else {}
    raw_action_args = action_map.get("arguments")
    action_args = raw_action_args if isinstance(raw_action_args, Mapping) else {}
    advertises_last_recall = bool(action_args.get("last_recall")) or "--last-recall" in str(
        action_map.get("cli_command") or ""
    )
    if not cache_available and advertises_last_recall:
        projected["foreground_action"] = {
            "action_id": "repair_last_recall_cache",
            "tool_name": "agent_recall",
            "arguments": {"query": "<same cue>", "detail": "full"},
            "cli_command": 'aippocampus agent recall "<same cue>" --json --detail full',
            "why": (
                "Recall found route-shaped context, but the same-machine request cache was "
                "not written, so request-index deepen is not available from compact output."
            ),
            "claim_boundary": "no_claim_before_reopen",
        }
        projected["last_recall_cache_recovery_card"] = {
            "status": "cache_unavailable",
            "primary_action": "rerun_recall_or_use_full_local_diagnostics",
            "safe_actions": [
                'aippocampus agent recall "<same cue>" --json',
                'aippocampus agent recall "<same cue>" --json --detail full',
            ],
            "boundary": "full detail may expose local-private handles; keep it local",
        }
    return projected


def compact_aippo_guidance_card(payload: Mapping[str, Any], *, task: str = "") -> dict[str, Any]:
    """Project AIppo activation into a foreground guidance card.

    ``activate_aippo`` remains the local/operator envelope so deepen/explain
    tests and audits can inspect the working contract. The default CLI/MCP
    surface should not start by dumping activation_packet/metrics/red_lines;
    it should tell the foreground agent whether there is usable guidance and
    what source boundary still applies.
    """

    packet_raw = payload.get("activation_packet")
    packet: Mapping[str, Any] = packet_raw if isinstance(packet_raw, Mapping) else {}
    guidance = [str(item) for item in packet.get("use_guidance") or [] if str(item).strip()]
    families = [str(item) for item in packet.get("task_families") or [] if str(item).strip()]
    status = str(payload.get("status") or "unknown")
    next_action = str(packet.get("next_action") or "").strip()
    active_clause_count = int(packet.get("active_clause_count") or 0)
    available_raw = packet.get("available_active_clause_count")
    available_active_clause_count = (
        int(available_raw)
        if isinstance(available_raw, (int, float)) and not isinstance(available_raw, bool)
        else active_clause_count
    )
    contract_active_clause_count = int(packet.get("contract_active_clause_count") or 0)
    active_not_foreground_available_count = int(
        packet.get("active_not_foreground_available_count") or 0
    )
    suppressed_clause_count = int(packet.get("suppressed_clause_count") or 0)
    direct_guidance_available = bool(guidance and next_action and next_action != "use_hint")
    use_hint_available = (
        status == "ok"
        and bool(guidance)
        and next_action == "use_hint"
        and available_active_clause_count > 0
    )
    deepen_route_id = str(packet.get("deepen_route_id") or "").strip()
    contract_action_raw = packet.get("contract_action")
    contract_action = (
        dict(contract_action_raw)
        if isinstance(contract_action_raw, Mapping)
        else aippo_working_contract.contract_deepen_action(deepen_route_id)
        if deepen_route_id
        else None
    )
    task_text = str(task or "").strip()
    foreground_action: dict[str, Any]
    if use_hint_available or (status == "ok" and direct_guidance_available):
        foreground_action = {
            "id": next_action or "use_aippo_working_contract_guidance",
            "action_id": next_action or "use_aippo_working_contract_guidance",
            "tool_name": "agent_aippo",
            "arguments": {
                "task_families": families[:3],
                "guidance": guidance[:2],
            },
            "claim_boundary": "working_guidance_not_source_truth",
            "why": "AIppo found low-risk project workflow guidance for this task.",
        }
    else:
        if task_text:
            foreground_action = {
                "id": "run_agent_recall_if_prior_source_matters",
                "action_id": "run_agent_recall_if_prior_source_matters",
                "tool_name": "agent_recall",
                "arguments": {"query": task_text},
                "cli_command": f'aippocampus agent recall "{task_text}" --json',
                "claim_boundary": "no_aippo_guidance_no_claim",
                "why": "No active AIppo working contract matched strongly enough.",
            }
        else:
            foreground_action = {
                "id": "provide_task_cue",
                "action_id": "provide_task_cue",
                "tool_name": "agent_aippo",
                "arguments_template": {"task": "{task_cue}"},
                "cli_command_template": 'aippocampus agent aippo --task "{task_cue}" --json',
                "requires": ["task_cue"],
                "template_only": True,
                "claim_boundary": "no_aippo_guidance_no_claim",
                "why": "AIppo needs a concrete task description before it can choose a working contract.",
            }
    safe_next_actions: list[dict[str, Any]] = [dict(foreground_action)]
    if not task_text:
        safe_next_actions.append(
            {
                "id": "run_agent_recall_if_prior_source_matters",
                "action_id": "run_agent_recall_if_prior_source_matters",
                "tool_name": "agent_recall",
                "arguments_template": {"query": "{continuity_cue}"},
                "cli_command_template": 'aippocampus agent recall "{continuity_cue}" --json',
                "requires": ["continuity_cue"],
                "template_only": True,
                "claim_boundary": "source_reopen_required_before_claims",
                "why": "Use recall first when the task depends on old local source context.",
            }
        )
        safe_next_actions.append(
            {
                "id": "inspect_operator_detail",
                "action_id": "inspect_operator_detail",
                "tool_name": "agent_aippo",
                "arguments_template": {"task": "{task_cue}", "operator_json": True},
                "cli_command_template": (
                    'aippocampus agent aippo --task "{task_cue}" --json --operator-json'
                ),
                "requires": ["task_cue"],
                "template_only": True,
                "claim_boundary": "local_operator_diagnostic_not_public_claim",
                "why": "Open the full activation packet only for local operator diagnostics.",
            }
        )
    elif contract_action:
        safe_next_actions.append(dict(contract_action))
    reason_codes: list[str] = []
    no_contract_reason = str(packet.get("no_active_contract_reason") or "").strip()
    if no_contract_reason:
        reason_codes.append(no_contract_reason)
    if families and not guidance:
        reason_codes.append("related_task_needs_reopen_or_contract_ripening")
    elif not families and task_text:
        reason_codes.append("no_task_family_match")
    if next_action == "use_hint" and guidance and available_active_clause_count <= 0:
        reason_codes.append("use_hint_blocked_no_available_active_clause")
    deduped_reason_codes: list[str] = []
    seen_reason_codes: set[str] = set()
    for reason_code in reason_codes:
        if reason_code in seen_reason_codes:
            continue
        seen_reason_codes.add(reason_code)
        deduped_reason_codes.append(reason_code)
    return _public_payload(
        {
            "kind": payload.get("kind"),
            "schema_version": payload.get("schema_version"),
            "mode": "aippo",
            "surface": "agent_aippo_guidance_card",
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "status": status,
            "ok": status == "ok",
            "task_hint_used": bool(payload.get("task_hint_used")),
            "task_families": families[:4],
            "use_guidance": guidance[:3],
            "foreground_action": foreground_action,
            "agent_next_action": foreground_action,
            "safe_next_actions": safe_next_actions,
            "reason_codes": deduped_reason_codes,
            "contract_status": {
                "active_clause_count": active_clause_count,
                "available_active_clause_count": available_active_clause_count,
                "contract_active_clause_count": contract_active_clause_count,
                "active_not_foreground_available_count": active_not_foreground_available_count,
                "suppressed_clause_count": suppressed_clause_count,
                "availability_basis": str(
                    packet.get("availability_basis")
                    or "unknown_packet_projection"
                ),
            },
            "match_diagnostics": {
                "task_family_count": len(families),
                "selected_clause_count": active_clause_count,
                "available_active_clause_count": available_active_clause_count,
                "contract_active_clause_count": contract_active_clause_count,
                "active_not_foreground_available_count": active_not_foreground_available_count,
                "direct_guidance_available": direct_guidance_available,
            },
            "contract_action": contract_action,
            "boundary": {
                "authority": "working_guidance",
                "navigation_only_not_fact": True,
                "source_reopen_required_for_claims": True,
                "candidate_surfaces_are_not_truth": True,
            },
            "claim_boundary": {
                "can_use_for": ["low_risk_working_guidance", "next_action_choice"],
                "must_reopen_for": [
                    "source_backed_facts",
                    "public_product_readiness",
                    "exact_user_history_claims",
                ],
                "detail_available_with_template": (
                    'aippocampus agent aippo --task "{task_cue}" --json --operator-json'
                ),
                "detail_requires": ["task_cue"],
            },
            "operator_json_available": True,
            "operator_json_command_template": (
                'aippocampus agent aippo --task "{task_cue}" --json --operator-json'
            ),
            "operator_json_requires": ["task_cue"],
        }
    )


def last_recall_cache_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get(LAST_RECALL_CACHE_ENV)
    if env:
        return Path(env).resolve()
    return core.aippocampus_registry_dir().resolve() / "agent" / "last-recall.json"


def _encode_local_reopen_token(value: Any) -> dict[str, Any]:
    """Encode a local reopen token so it is not stored as ordinary text.

    This is an accidental-disclosure guard for a same-machine cache, not a
    cryptographic promise. The handle remains local-private navigation material;
    public output should keep using `--public` / `--compact-json`.
    """

    raw_text = (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if isinstance(value, Mapping)
        else str(value or "")
    )
    raw = raw_text.encode("utf-8")
    return {
        "encoding": LOCAL_REOPEN_TOKEN_ENCODING,
        "bytes": [byte ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw],
    }


def _decode_local_reopen_token(value: Any) -> str:
    if isinstance(value, Mapping) and value.get("encoding") == LOCAL_REOPEN_TOKEN_ENCODING:
        raw_bytes = value.get("bytes")
        if not isinstance(raw_bytes, list):
            return ""
        try:
            return bytes(int(byte) ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw_bytes).decode(
                "utf-8"
            )
        except (TypeError, ValueError, UnicodeDecodeError):
            return ""
    return ""


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _public_projection_route_ids(data: Mapping[str, Any]) -> dict[int, str]:
    route_ids: dict[int, str] = {}
    for route in data.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        try:
            index = int(route.get("route_index") or 0)
        except (TypeError, ValueError):
            index = 0
        route_id = str(route.get("route_id") or "").strip()
        if index > 0 and route_id:
            route_ids[index] = route_id
    return route_ids


def write_last_recall_cache(
    deepen_requests: Iterable[Any],
    *,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
    project: str,
    max_matches: int,
    schema_version: str,
    path: str | Path | None = None,
) -> bool:
    requests: list[dict[str, Any]] = []
    for request in deepen_requests:
        if not isinstance(request, Mapping) or not request.get("handle"):
            continue
        requests.append(
            {
                "request_index": request.get("request_index"),
                "route_id": request.get("route_id"),
                "local_reopen_token": _encode_local_reopen_token(request.get("handle")),
            }
        )
    if not requests:
        return False
    target = last_recall_cache_path(path)
    cache = {
        "kind": "aippocampus_agent_last_recall",
        "schema_version": schema_version,
        "written_at": core.now_utc(),
        "requests": requests[:25],
        "context": {
            "cwd": str(cwd) if cwd else None,
            "project": project,
            "max": max_matches,
            "path_scope": "cwd_only_explicit_overrides_required",
        },
        "privacy_boundary": {
            "local_cache_only": True,
            "default_human_output_prints_cache_path": False,
            "derived_local_source_paths_persisted": False,
            "opaque_handles_are_navigation_not_facts": True,
            "opaque_handles_cleartext_persisted": False,
            "local_reopen_token_encoding": LOCAL_REOPEN_TOKEN_ENCODING,
            "local_reopen_token_encoding_is_encryption": False,
        },
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        # Local-only reopen handles are not credentials, but they are still
        # intentionally private navigation tokens. The cache stores an encoded
        # token for same-machine follow-through only; keep it out of human
        # output and avoid persisting derived source/registry paths above.
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        return False
    return True


def read_last_recall_cache(path: str | Path | None = None) -> dict[str, Any]:
    target = last_recall_cache_path(path)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("last recall cache has an unsupported shape")
    if data.get("kind") == "aippocampus_agent_last_recall":
        return data
    if (
        path is not None
        and data.get("kind") == "aippocampus_agent_continuity_path"
        and data.get("surface") == "agent_cli_public_compact"
    ):
        default_target = last_recall_cache_path(None)
        if target != default_target and default_target.exists():
            fallback = read_last_recall_cache(None)
            fallback["public_projection_request_path"] = True
            fallback["public_projection_route_ids"] = _public_projection_route_ids(data)
            return fallback
        raise ValueError(
            "public compact recall projection needs the same-machine last recall cache; rerun agent recall"
        )
    raise ValueError("last recall cache has an unsupported shape")


def last_recall_route_choices(path: str | Path | None = None, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return route ids from the same-machine last-recall cache without handles.

    Personal controls and feedback only need the route id to write scoped,
    low-authority calibration. Keep local reopen tokens and source paths out of
    these foreground cards; those remain in deepen/explain flows.
    """

    try:
        cache = read_last_recall_cache(path)
    except Exception:
        return []
    choices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for request in cache.get("requests") or []:
        if not isinstance(request, Mapping):
            continue
        route_id = str(request.get("route_id") or "").strip()
        if not route_id or route_id in seen:
            continue
        try:
            request_index = int(request.get("request_index") or len(choices) + 1)
        except (TypeError, ValueError):
            request_index = len(choices) + 1
        choices.append(
            {
                "request_index": request_index,
                "route_id": route_id,
                "source": "last_recall_cache",
            }
        )
        seen.add(route_id)
        if len(choices) >= limit:
            break
    return choices


def handle_from_last_recall_cache(
    *,
    request_index: int,
    path: str | Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    cache = read_last_recall_cache(path)
    requests = [request for request in cache.get("requests") or [] if isinstance(request, Mapping)]
    for request in requests:
        try:
            index = int(request.get("request_index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index == request_index:
            public_route_ids = cache.get("public_projection_route_ids")
            expected_route_id = (
                str(public_route_ids.get(request_index) or "").strip()
                if isinstance(public_route_ids, Mapping)
                else ""
            )
            actual_route_id = str(request.get("route_id") or "").strip()
            if expected_route_id and actual_route_id != expected_route_id:
                raise ValueError(
                    "same-machine last recall cache does not match the public recall projection"
                )
            handle = _decode_local_reopen_token(request.get("local_reopen_token"))
            if not handle and request.get("handle"):
                # Backward compatibility for caches written before the
                # local-reopen-token boundary existed.
                handle = str(request.get("handle") or "")
            return handle, dict(cache.get("context") or {})
    raise ValueError(f"last recall cache does not contain request {request_index}")


def macro_state_template(project: str) -> dict[str, Any]:
    return dict(
        macro_state.build_macro_orientation_state(
            project=project,
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "replace-with-clean-source-or-review-ref"},),
            updated_at=macro_state.utc_now_iso(),
        )
    )


def macro_schema_help(project: str, *, schema_version: str) -> dict[str, Any]:
    return {
        "kind": "aippocampus_macro_orientation_schema_help",
        "schema_version": schema_version,
        "project": project,
        "jsonl_path_candidates": [str(path) for path in DEFAULT_MACRO_STATE_RELATIVE_PATHS],
        "required_fields": [
            "kind=macro_orientation_state",
            "schema_version=0.1",
            "scope.kind=project",
            "scope.project",
            "hexagram",
            "changing_lines",
            "source_refs",
            "updated_at",
            "authority_level=navigation_only",
            "claim_permission=no_claim_before_reopen",
        ],
        "producer_hint": (
            "Append one JSON object per line to .aippocampus/macro-orientation.jsonl, "
            "or pass --macro-state-jsonl explicitly."
        ),
        "template": macro_state_template(project),
        "boundary": "macro_orientation_is_navigation_only_not_fact",
    }


def render_macro_schema_human(payload: Mapping[str, Any]) -> str:
    del payload
    lines = [
        "AIppocampus agent macro schema",
        "Required: project scope, hexagram, changing_lines, source_refs, updated_at.",
        "Default file: .aippocampus/macro-orientation.jsonl",
        "Boundary: navigation only; source refs are reopen routes, not proof.",
        "Use --init-template --json for a copyable JSONL row.",
    ]
    return "\n".join(lines)


def render_aippo_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    lines = [f"AIppo: {status}"]
    packet = payload.get("activation_packet")
    activation = packet if isinstance(packet, Mapping) else {}
    guidance = [str(item) for item in activation.get("use_guidance") or [] if str(item).strip()]
    if status == "no_active_contract":
        lines.append("No active working contract matched this task.")
        lines.append("Use instead: aippocampus agent recall <query> if prior source matters.")
    elif guidance:
        lines.append("Use: " + " | ".join(core.compact_text(item, 96) for item in guidance[:2]))
    else:
        lines.append("No compact guidance surfaced.")
    deepen_route = str(activation.get("deepen_route_id") or "").strip()
    if deepen_route:
        lines.append(f"Next: aippocampus agent deepen {deepen_route}")
    else:
        lines.append("Next: continue normally; use --json for diagnostics.")
    lines.append("Boundary: working guidance only; reopen source before factual claims.")
    return "\n".join(lines)


def render_macro_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    lines = [f"AIppocampus agent macro: {status}"]
    packets = [packet for packet in payload.get("memory_packets") or [] if isinstance(packet, Mapping)]
    if packets:
        packet = packets[0]
        lines.append(core.compact_text(str(packet.get("foreground_text") or "Macro route available."), 160))
        deepen_route = str(packet.get("deepen_route_id") or "").strip()
        if deepen_route:
            lines.append(f"Next: aippocampus agent deepen {deepen_route}")
    else:
        diagnostics = [str(item) for item in payload.get("diagnostics") or [] if str(item)]
        if diagnostics:
            lines.append("Why: " + ", ".join(diagnostics[:3]))
        actions: list[str] = []
        for action in payload.get("safe_next_actions") or []:
            if not isinstance(action, Mapping):
                continue
            command = str(action.get("command") or "").strip()
            if not command:
                command = str(action.get("command_template") or action.get("id") or "").strip()
            if command:
                actions.append(command)
            if len(actions) == 3:
                break
        if actions:
            lines.extend(
                ("Next: " if index == 0 else "Or: ") + command
                for index, command in enumerate(actions)
            )
        else:
            lines.append("Expected: .aippocampus/macro-orientation.jsonl or --macro-state-jsonl.")
            lines.append("Repair: aippocampus agent macro --explain-schema")
    lines.append("Boundary: macro orientation is navigation only, not source truth.")
    return "\n".join(lines)


def render_deepen_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    surface = str(payload.get("surface") or "unknown")
    lines = [f"AIppocampus agent deepen: {status}", f"Surface: {surface}"]
    result = payload.get("result")
    data = _mapping_or_empty(result)
    if status != "ok":
        error = _mapping_or_empty(data.get("error"))
        message = error.get("message") or data.get("message") or "Could not verify this handle."
        lines.append("Why: " + core.compact_text(str(message), 180))
        lines.append("Next: rerun agent recall and use the fresh handle.")
    elif surface == "aippo":
        ledger = _mapping_or_empty(data.get("source_support_ledger"))
        lines.append(f"Source support refs: {ledger.get('source_ref_count', 0)}")
        lines.append("Next: use --json only when auditing the working contract source ledger.")
    elif surface == "macro":
        validation = _mapping_or_empty(data.get("validation"))
        lines.append(f"Macro validation: {'ok' if validation.get('ok') else 'needs_attention'}")
        lines.append("Next: inspect --json before using source refs or derivation details.")
    else:
        window = _mapping_or_empty(data.get("source_window"))
        message_count = int(window.get("message_count") or len(window.get("messages") or []))
        evidence = data.get("evidence_level") or data.get("support_level") or "source_open"
        lines.append(f"Evidence: {evidence}; source windows opened: {message_count}")
        why = str(data.get("why_this_may_matter") or "").strip()
        if why:
            lines.append("Why: " + core.compact_text(why, 160))
        lines.append("Next: rerun with --json to inspect the source window for exact wording.")
    lines.append("Boundary: use opened source only within scope; no broad claims from the handle.")
    return "\n".join(lines)


def render_recall_human(payload: Mapping[str, Any]) -> str:
    packets = [packet for packet in payload.get("memory_packets") or [] if isinstance(packet, Mapping)]
    deepen_requests = [
        request for request in payload.get("deepen_requests") or [] if isinstance(request, Mapping)
    ]
    lines = [f"AIppocampus agent recall: {payload.get('status') or 'unknown'}"]
    if not packets:
        lines.append("No compact route surfaced.")
    for index, packet in enumerate(packets[:3], start=1):
        label = (
            packet.get("route_topic")
            or packet.get("route_label")
            or packet.get("route_id")
            or "memory route"
        )
        next_action = packet.get("recommended_next") or packet.get("next_action") or "reopen_source"
        lines.append(f"{index}. {label} -> {next_action}")
        hint = packet.get("selection_hint")
        if isinstance(hint, Mapping) and hint.get("source"):
            lines.append(f"   why: {hint.get('source')}:{hint.get('why') or 'selected'}")
        reason_codes = packet.get("route_delta_reason_codes") or packet.get("triage_rank_reason_codes")
        if isinstance(reason_codes, list) and reason_codes:
            lines.append("   codes: " + ", ".join(str(code) for code in reason_codes[:3]))
    navigation = payload.get("navigation_signals")
    if isinstance(navigation, Mapping):
        signals = [str(signal) for signal in navigation.get("signals") or [] if str(signal)]
        if signals:
            action = str(navigation.get("next_safe_action") or "deepen_before_claim")
            lines.append(f"Navigation: {', '.join(signals[:3])} -> {action}")
    suggested_command = str(payload.get("suggested_next_command") or "").strip()
    if deepen_requests:
        first = deepen_requests[0]
        next_action = str(first.get("human_next_action") or "").strip()
        if payload.get("last_recall_cache_available") and (
            "--json for callable handle" in next_action
            or "--json --detail full for local-private handle" in next_action
        ):
            request_index = int(first.get("request_index") or 1)
            next_action = f"aippocampus agent deepen --request {request_index} --last-recall"
        if not next_action:
            request_index = int(first.get("request_index") or 1)
            next_action = (
                f"deepen route {request_index}; rerun with --json --detail full "
                "for local-private handle"
            )
        lines.append(f"Next: {next_action}.")
    elif suggested_command and "aippo-nav:" not in suggested_command and len(suggested_command) <= 160:
        lines.append(f"Next: {suggested_command}")
    else:
        lines.append(f"Next: {payload.get('suggested_next') or 'continue_normally'}")
    lines.append("Boundary: route only; reopen source before quoting or making strong claims.")
    return "\n".join(lines)
