"""Compact foreground projection for warm ambient status."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import sanitize_external_model_payload
from aippocampus_runtime.warm_ambient.scheduler import JOB_SCHEMA_VERSION, WARM_STATUS_COMMAND

WARM_STATUS_DETAIL_COMMAND = "aippocampus warm status --detail full --json"
WARM_STATUS_OPERATOR_COMMAND = "aippocampus warm status --operator-json"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _compact_warm_choice(action: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": action.get("id"),
        "label": action.get("label"),
        "mutation_risk": action.get("mutation_risk"),
        "claim_boundary": action.get("claim_boundary"),
        "why": action.get("why"),
    }
    if action.get("command"):
        payload["command"] = action.get("command")
    if action.get("command_template"):
        payload["command_template"] = action.get("command_template")
        payload["template_only"] = True
    if action.get("requires"):
        payload["requires"] = action.get("requires")
    if action.get("manual_only"):
        payload["manual_only"] = True
    if action.get("continue_without_command"):
        payload["continue_without_command"] = True
    if action.get("manual_instruction"):
        payload["manual_instruction"] = action.get("manual_instruction")
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def compact_warm_status_card(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project warm status into the default foreground card.

    The full status payload intentionally keeps operator-only repair detail
    such as env toggles, manual stale-queue cleanup, and scan diagnostics. The
    default CLI card stays action-led so a blocked optional warm queue does not
    bury the useful next step or look like a first-recall failure.
    """

    activity = _mapping(payload.get("job_activity"))
    status = str(payload.get("status") or "unknown")
    queue_state = str(activity.get("queue_state") or "unknown")
    blocked_stale = bool(status == "blocked" and activity.get("stale_queue_blocked"))
    foreground_action = dict(_mapping(payload.get("foreground_action")))
    if not foreground_action:
        foreground_action = {
            "id": "check_warm_status",
            "label": "Check warm status",
            "command": WARM_STATUS_COMMAND,
            "mutation_risk": "read_only",
            "why": "Inspect optional warm ambient status.",
        }
    safe_next_actions: list[Mapping[str, Any]] = []
    allowed_blocked_actions = {
        "probe_warm_worker_once",
    }
    allowed_default_actions = {
        "recheck_warm_status",
        "continue_with_ordinary_recall",
    }
    for action_value in payload.get("safe_next_actions") or []:
        action = _mapping(action_value)
        action_id = str(action.get("id") or "")
        allowed_actions = allowed_blocked_actions if blocked_stale else allowed_default_actions
        if action_id in allowed_actions:
            safe_next_actions.append(_compact_warm_choice(action))
        if len(safe_next_actions) >= (1 if blocked_stale else 2):
            break
    detail_action: Mapping[str, Any] = {
        "id": "open_warm_status_detail",
        "label": "Open warm status detail",
        "command": WARM_STATUS_DETAIL_COMMAND,
        "mutation_risk": "read_only",
        "why": "Use detail when provider diagnostics, env toggles, or stale-queue cleanup guidance are needed.",
    }
    action_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=(
            [foreground_action, *safe_next_actions]
            if blocked_stale
            else [foreground_action, *safe_next_actions, detail_action][:4]
        ),
    )
    warm_ambient_state = str(payload.get("warm_ambient_state") or "callable")
    warm_ambient_recently_useful = bool(payload.get("warm_ambient_recently_useful"))
    primary_command = (
        foreground_action.get("command")
        or foreground_action.get("command_template")
        or payload.get("next_command")
    )
    card = {
        "kind": "aippocampus_warm_ambient_status_card",
        "schema_version": JOB_SCHEMA_VERSION,
        "detail": "compact",
        "surface": "foreground_decision_card",
        "command_ok": bool(payload.get("command_ok", True)),
        "ok": bool(payload.get("ok")),
        "status": "blocked_stale_queue" if blocked_stale else status,
        "warm_ambient_ok": bool(payload.get("warm_ambient_ok")),
        "warm_ambient_state": warm_ambient_state,
        "warm_ambient_recently_useful": warm_ambient_recently_useful,
        "ordinary_recall_usable": bool(payload.get("ordinary_recall_usable")),
        "warm_not_blocking_recall": True,
        "summary": {
            "queue_state": queue_state,
            "pending_recent_count": _safe_int(activity.get("pending_recent_count")),
            "pending_stale_count": _safe_int(activity.get("pending_stale_count")),
            "completed_count": _safe_int(activity.get("completed_count")),
            "useful_result_count": _safe_int(activity.get("useful_result_count")),
            "worker": str(activity.get("worker_evidence") or "not_available"),
            "usefulness_evidence": str(activity.get("usefulness_evidence") or "none"),
        },
        "decision": {
            "primary": foreground_action.get("label") or "Check warm status",
            "primary_command": primary_command,
            "reason": (
                "Warm ambient has a blocked stale queue, but ordinary recall remains usable; use detail only for optional queue management."
                if blocked_stale
                else "Warm ambient recently produced useful cache output; ordinary recall can still reopen sources."
                if warm_ambient_recently_useful
                else "Ordinary recall is usable; warm ambient is optional and not currently useful evidence."
            ),
        },
        **action_fields,
        "manage_command": WARM_STATUS_DETAIL_COMMAND if blocked_stale else None,
        "operator_json_available": {
            "detail_full_command": WARM_STATUS_DETAIL_COMMAND,
            "operator_json_command": WARM_STATUS_OPERATOR_COMMAND,
        },
    }
    return sanitize_external_model_payload(card)
