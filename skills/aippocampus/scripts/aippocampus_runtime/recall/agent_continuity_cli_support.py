"""CLI-only support helpers for the opt-in agent continuity facade."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.aippo import working_contract as aippo_working_contract
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    canonical_foreground_action_fields,
    command_value_needs_input,
    foreground_recovery_card,
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.mcp.agent_recall_projection import compact_agent_recall_payload
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import feedback_events
from aippocampus_runtime.recall.agent_recall_cache import (
    LAST_RECALL_CACHE_ENV,
    handle_from_last_recall_cache,
    last_recall_cache_path,
    last_recall_route_choices,
    last_recall_route_key,
    last_recall_route_wildcard_key,
    mark_last_recall_request_opened,
    opened_route_keys_from_last_recall_cache,
    query_from_last_recall_cache,
    read_last_recall_cache,
    recall_selector_cache_path,
    write_last_recall_cache,
    write_recall_selector_snapshot,
)
from aippocampus_runtime.recall.agent_recall_cache import (
    public_compact_route_receipts as _public_compact_route_receipts,
)
from aippocampus_runtime.recall.human_actions import recall_human_next_hint

__all__ = [
    "LAST_RECALL_CACHE_ENV",
    "handle_from_last_recall_cache",
    "last_recall_cache_path",
    "last_recall_route_choices",
    "last_recall_route_key",
    "last_recall_route_wildcard_key",
    "mark_last_recall_request_opened",
    "opened_route_keys_from_last_recall_cache",
    "query_from_last_recall_cache",
    "read_last_recall_cache",
    "recall_selector_cache_path",
    "write_last_recall_cache",
    "write_recall_selector_snapshot",
]

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
MIN_ROUTE_LIMIT = 1
MAX_ROUTE_LIMIT = 25
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*=\S+",
    re.I,
)
SOURCE_SNIPPET_CHAR_LIMIT = 420


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
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": why,
    }


def _recall_with_cue_action(*, label: str, why: str, action_id: str = "recall_with_cue") -> dict[str, Any]:
    action = _foreground_template_action(
        action_id, 'aippocampus agent recall "{cue}" --json', ["cue"], label, why
    )
    action.update(
        {
            "tool_name": "agent_recall",
            "arguments_template": {"query": "{cue}"},
        }
    )
    return action


def _request_index_followup_action(mode: str) -> dict[str, Any]:
    action = _foreground_template_action(
        f"{mode}_last_recall_request",
        f"aippocampus agent {mode} --request {{request_index}} --last-recall --json",
        ["last_recall_cache", "request_index"],
        f"Run agent {mode} against a numbered route from the last recall",
        "Requires a fresh recall cache and selected request index.",
    )
    action.update(
        {
            "tool_name": f"agent_{mode}",
            "arguments_template": {
                "request_index": "{request_index}",
                "last_recall": True,
            },
        }
    )
    return action


def _safe_recall_cue(cue: str | None) -> str:
    return str(redact_sensitive_values(redact_private_paths(str(cue or "").strip())) or "")


def _recall_detail_command(cue: str | None) -> str:
    clean_cue = _safe_recall_cue(cue)
    if clean_cue and not command_value_needs_input(clean_cue):
        return f"aippocampus agent recall {shell_quote(clean_cue)} --json --detail full"
    return 'aippocampus agent recall "{cue}" --json --detail full'


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
        "next_safe_action": actions[0],
        "next_safe_action_id": "recall_with_cue",
        "safe_next_actions": actions,
    }


def last_recall_cache_recovery_fields(mode: str, *, cue: str | None = None) -> dict[str, Any]:
    del mode
    clean_cue = _safe_recall_cue(cue)
    detail_command = _recall_detail_command(cue)
    if clean_cue and not command_value_needs_input(clean_cue):
        action = foreground_shell_action(
            action_id="recall_with_cue_full_detail",
            label="Rerun agent recall with full detail",
            command=detail_command,
            why="The last-recall cache was unavailable; rerun recall for a fresh route.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    else:
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
        "next_safe_action": action,
        "next_safe_action_id": "recall_with_cue_full_detail",
        "safe_next_actions": [action],
    }


def last_recall_selector_recovery_fields(
    mode: str,
    *,
    request_index: int,
    cue: str | None = None,
) -> dict[str, Any]:
    fields = last_recall_cache_recovery_fields(mode, cue=cue)
    fields.update(
        {
            "selector_recovery": {
                "status": "stale_or_unavailable",
                "request_index": request_index,
                "cue_preserved": bool(str(cue or "").strip()),
                "reason": "rerun recall before using this mutable last-recall selector",
            },
            "claim_boundary": (
                "last-recall selector could not reopen current source; rerun recall before claims."
            ),
            "operator_detail_command": _recall_detail_command(cue),
        }
    )
    return fields


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
        "next_safe_action_id": "recall_with_cue",
    }
    # Missing selector is a foreground input-recovery case. Malformed or stale
    # handles stay `cannot_verify` in the caller paths because those are source
    # authority failures, not chooser prompts.
    return _public_payload(
        {
            "kind": kind,
            "schema_version": schema_version,
            "mode": mode,
            "surface": "recall",
            "status": "needs_input",
            "surface_class": "foreground_recovery_card",
            "error": body["error"],
            "ok": False,
            "cli_exit_recommended": "nonzero",
            **handle_recovery_fields(mode),
            "claim_boundary": "missing selector; run recall first and reopen/deepen before source-backed claims.",
            "operator_detail_command": f"aippocampus agent {mode} --json --detail full",
        }
    )


def last_recall_unavailable_payload(
    *,
    mode: str,
    exc: Exception,
    schema_version: str,
    kind: str,
    cue: str | None = None,
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
            **last_recall_cache_recovery_fields(mode, cue=cue),
            "claim_boundary": "last-recall cache unavailable; rerun recall before selecting a route.",
            "operator_detail_command": _recall_detail_command(cue),
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
    primary = foreground_template_action(
        action_id="continue_after_feedback",
        label="Continue after feedback",
        command_template='aippocampus agent recall "{cue}" --json',
        requires=["cue"],
        why=(
            "Feedback was recorded as low-authority calibration; continue the task and "
            "reopen source before making claims."
            if wrote_event
            else "Receipt only; provide a feedback lane when future recall should consume this signal."
        ),
        mutation_risk="read_only",
        claim_boundary="no_claim_before_reopen",
    )
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
            **canonical_foreground_action_fields(
                primary,
                safe_next_actions=[
                    primary,
                    foreground_shell_action(
                        action_id="inspect_feedback_lane",
                        label="Inspect feedback lane",
                        command="aippocampus agent feedback --operator-json",
                        why="Use operator detail only when auditing the local feedback lane.",
                        mutation_risk="read_only",
                        claim_boundary="feedback_is_not_source_truth",
                    ),
                ],
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
    outcome_choices = [
        "helped",
        "wrong_route",
        "stale",
        "noisy",
        "not_enough_evidence",
    ]
    route_choices = [
        {
            "id": f"feedback_last_recall_route_{choice['request_index']}",
            "label": f"Record feedback on last recall route {choice['request_index']}",
            "command_template": (
                f"aippocampus agent feedback {shell_quote(choice['route_id'])} "
                "--outcome {{feedback_outcome}} --json"
            ),
            "requires": ["feedback_outcome"],
            "outcome_choices": outcome_choices,
            "route_id": choice["route_id"],
            "request_index": choice["request_index"],
            "source": "last_recall_cache",
            "mutation_risk": "durable_low_authority_feedback_write",
            "claim_boundary": "feedback_is_not_source_truth",
            "why": (
                "Choose this route only after judging it, then fill feedback_outcome; "
                "last recall presence is not success evidence."
            ),
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
            **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
            "write_boundary": {
                "wrote_event": False,
                "storage": "none",
                "feedback_is_source_truth": False,
            },
        }
    )


def public_recall_projection(payload: Mapping[str, Any], *, query: str | None = None) -> dict[str, Any]:
    """Return compact recall JSON suitable for issue/discussion/log paste.

    Plain ``--json`` stays the local diagnostic surface with private reopen
    handles. The public/compact JSON path should be the same frontstage shape a
    foreground agent can actually use: one action, route receipts, and a clear
    source boundary, not a redacted audit dump.
    """

    source = dict(payload)
    source["query"] = query if query is not None else source.get("query")
    source.update(handle_boundary_fields())
    projected = compact_agent_recall_payload(source)
    projected["surface"] = "agent_cli_public_compact"
    projected["routes"] = _public_compact_route_receipts(projected.get("routes"))
    projected.pop("policy_boundary", None)
    cache_available = bool(source.get("last_recall_cache_available"))
    projected["last_recall_cache_available"] = cache_available
    action = projected.get("foreground_action")
    action_map = action if isinstance(action, Mapping) else {}
    raw_action_args = action_map.get("arguments")
    action_args = raw_action_args if isinstance(raw_action_args, Mapping) else {}
    raw_card = source.get("foreground_action_card")
    card_map = raw_card if isinstance(raw_card, Mapping) else {}
    raw_canonical = card_map.get("canonical_action")
    canonical_action = raw_canonical if isinstance(raw_canonical, Mapping) else {}
    raw_canonical_args = canonical_action.get("arguments")
    canonical_args = raw_canonical_args if isinstance(raw_canonical_args, Mapping) else {}
    advertises_last_recall = bool(action_args.get("last_recall")) or "--last-recall" in str(
        action_map.get("command") or action_map.get("cli_command") or ""
    ) or bool(canonical_args.get("last_recall")) or "--last-recall" in str(
        canonical_action.get("command") or canonical_action.get("cli_command") or ""
    )
    if not cache_available and advertises_last_recall:
        recovery_cue = str(
            redact_sensitive_values(redact_private_paths(str(source.get("query") or "").strip()))
            or ""
        )
        if command_value_needs_input(recovery_cue):
            recovery_cue = ""
        repair_action: dict[str, Any] = {
            "id": "repair_last_recall_cache",
            "label": "Repair last recall cache",
            "tool_name": "agent_recall",
            "why": (
                "Recall found route-shaped context, but the same-machine request cache was "
                "not written, so request-index deepen is not available from compact output."
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        }
        if recovery_cue:
            repair_action.update(
                {
                    "arguments": {"query": recovery_cue, "detail": "full"},
                    "command": f"aippocampus agent recall {shell_quote(recovery_cue)} --json --detail full",
                }
            )
        else:
            repair_action.update(
                {
                    "arguments_template": {"query": "{cue}", "detail": "full"},
                    "requires": ["cue"],
                    "template_only": True,
                    "command_template": 'aippocampus agent recall "{cue}" --json --detail full',
                }
            )
        projected["foreground_action"] = repair_action
        projected.update(canonical_foreground_action_fields(repair_action))
        projected["last_recall_cache_recovery_card"] = {
            "status": "cache_unavailable",
            "primary_action": "rerun_recall_or_use_full_local_diagnostics",
            "safe_actions": [repair_action],
            "boundary": "full detail may expose local-private handles; keep it local",
        }
    return projected


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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
    card_status = "needs_input" if not task_text else status
    foreground_action: dict[str, Any]
    if use_hint_available or (status == "ok" and direct_guidance_available):
        foreground_action = {
            "id": next_action or "use_aippo_working_contract_guidance",
            "action_id": next_action or "use_aippo_working_contract_guidance",
            "label": "Use AIppo working guidance",
            "action_type": "use_project_working_guidance",
            "selected_task_families": families[:3],
            "guidance_preview": guidance[:2],
            "mutation_risk": "read_only",
            "claim_boundary": "working_guidance_not_source_truth",
            "why": "AIppo found low-risk project workflow guidance for this task.",
            "continue_without_command": True,
        }
    else:
        if task_text:
            foreground_action = {
                "id": "run_agent_recall_if_prior_source_matters",
                "action_id": "run_agent_recall_if_prior_source_matters",
                "label": "Run recall if prior source matters",
                "tool_name": "agent_recall",
                "arguments": {"query": task_text},
                "command": f"aippocampus agent recall {shell_quote(task_text)} --json",
                "cli_command": f"aippocampus agent recall {shell_quote(task_text)} --json",
                "mutation_risk": "read_only",
                "claim_boundary": "no_aippo_guidance_no_claim",
                "why": "No active AIppo working contract matched strongly enough.",
            }
        else:
            foreground_action = {
                "id": "provide_task_cue",
                "action_id": "provide_task_cue",
                "label": "Provide an AIppo task cue",
                "tool_name": "agent_aippo",
                "arguments_template": {"task": "{task_cue}"},
                "cli_command_template": 'aippocampus agent aippo --task "{task_cue}" --json',
                "requires": ["task_cue"],
                "template_only": True,
                "blocked_by": ["task_cue_required"],
                "mutation_risk": "read_only",
                "claim_boundary": "no_aippo_guidance_no_claim",
                "why": "AIppo needs a concrete task description before it can choose a working contract.",
            }
    safe_next_actions: list[dict[str, Any]] = [dict(foreground_action)]
    if task_text and (use_hint_available or (status == "ok" and direct_guidance_available)):
        safe_next_actions.append(
            {
                "id": "refresh_aippo_guidance_for_task",
                "action_id": "refresh_aippo_guidance_for_task",
                "label": "Refresh AIppo guidance for this task",
                "tool_name": "agent_aippo",
                "arguments": {"task": task_text},
                "mutation_risk": "read_only",
                "claim_boundary": "working_guidance_not_source_truth",
                "why": "Re-run AIppo only if the task wording has changed or the card needs refreshing.",
            }
        )
    if not task_text:
        safe_next_actions.append(
            {
                "id": "run_agent_recall_if_prior_source_matters",
                "action_id": "run_agent_recall_if_prior_source_matters",
                "label": "Run recall if prior source matters",
                "tool_name": "agent_recall",
                "arguments_template": {"query": "{continuity_cue}"},
                "cli_command_template": 'aippocampus agent recall "{continuity_cue}" --json',
                "requires": ["continuity_cue"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "source_reopen_required_before_claims",
                "why": "Use recall first when the task depends on old local source context.",
            }
        )
        safe_next_actions.append(
            {
                "id": "inspect_operator_detail",
                "action_id": "inspect_operator_detail",
                "label": "Inspect AIppo operator detail",
                "tool_name": "agent_aippo",
                "arguments_template": {"task": "{task_cue}", "operator_json": True},
                "cli_command_template": (
                    'aippocampus agent aippo --task "{task_cue}" --json --operator-json'
                ),
                "requires": ["task_cue"],
                "template_only": True,
                "mutation_risk": "read_only",
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
    action_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=safe_next_actions,
    )
    error = (
        {
            "code": "aippo_task_required",
            "message": "AIppo needs a concrete task cue before it can choose a working contract.",
        }
        if not task_text
        else None
    )
    return _public_payload(
        {
            "kind": payload.get("kind"),
            "schema_version": payload.get("schema_version"),
            "mode": "aippo",
            "surface": "agent_aippo_guidance_card",
            "status": card_status,
            "ok": card_status == "ok",
            **({"error": error} if error else {}),
            "task_hint_used": bool(payload.get("task_hint_used")),
            "task_families": families[:4],
            "use_guidance": guidance[:3],
            **action_fields,
            "reason_codes": deduped_reason_codes,
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
        lines.append(f"Next: aippocampus agent deepen {shell_quote(deepen_route)}")
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
            lines.append(f"Next: aippocampus agent deepen {shell_quote(deepen_route)}")
            lines.append("Boundary: heuristic navigation only; deepen opens derivation/source trail.")
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


def _source_message_rank(message: Mapping[str, Any]) -> int:
    source_class = str(message.get("source_use_class") or "").strip()
    phase = str(message.get("phase") or "").strip().casefold()
    role = str(message.get("role") or "").strip().casefold()
    if source_class == "foreground_continuity_source":
        return 0
    if role in {"user", "assistant"} and phase not in {"audit", "debug", "tool"}:
        return 1
    if phase in {"commentary", "final_answer"}:
        return 2
    return 3


def _primary_source_snippet_text(messages: Any) -> str:
    if not isinstance(messages, list | tuple):
        return ""
    ranked = sorted(
        ((index, item) for index, item in enumerate(messages, start=1) if isinstance(item, Mapping)),
        key=lambda item: (_source_message_rank(item[1]), item[0]),
    )
    for _, message in ranked:
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        compact = core.compact_text(text, SOURCE_SNIPPET_CHAR_LIMIT)
        compact = SENSITIVE_ASSIGNMENT_RE.sub("<sensitive-value-redacted>", compact)
        redacted = str(redact_sensitive_values(redact_private_paths(compact)) or "").strip()
        if redacted:
            return redacted
    return ""


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
        snippet = _primary_source_snippet_text(window.get("messages"))
        if snippet:
            lines.append("Source: " + snippet)
        why = str(data.get("why_this_may_matter") or "").strip()
        if why:
            lines.append("Why: " + core.compact_text(why, 160))
        lines.append("Next: use --json --detail full only when you need the whole opened window.")
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
    if deepen_requests:
        first = deepen_requests[0]
        next_action = str(first.get("human_next_action") or "").strip()
        selector_id = str(payload.get("recall_selector_id") or "").strip()
        if selector_id:
            request_index = int(first.get("request_index") or 1)
            next_action = (
                f"aippocampus agent deepen --request {request_index} "
                f"--recall-selector {selector_id}"
            )
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
    else:
        lines.append(f"Next: {recall_human_next_hint(payload)}")
    lines.append("Boundary: route only; reopen source before quoting or making strong claims.")
    return "\n".join(lines)
