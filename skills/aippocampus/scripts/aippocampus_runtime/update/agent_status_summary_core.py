"""Shared primitives for compact update-status projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.update import status_actions as update_actions

INTERNAL_STATUS_REASON_COPY = {
    "host_live_probe_ok_foreground_probe_not_checked": (
        "The host can launch AIppocampus, but this foreground thread has not yet "
        "proved the recall/deepen tools are visible."
    ),
    "host_live_probe_ok_current_thread_unverified": (
        "The host probe passed, but this foreground thread still needs a live "
        "tool-visibility check."
    ),
    "host_registered_tools_unverified": (
        "AIppocampus tools are registered with the host, but this thread has not "
        "verified they are callable."
    ),
    "foreground_mcp_runtime_mismatch": (
        "The current foreground MCP connection does not match the host probe; "
        "use the CLI fallback or reload the host before trusting tool status."
    ),
    "host_live_probe_key_tools_failed": (
        "The host probe reached AIppocampus, but key foreground tools failed and "
        "the plugin cache likely needs repair."
    ),
    "with_missing_cache_file": (
        "Action-time hints are installed, but their prepared cache file is missing."
    ),
    "with_empty_cache": (
        "Action-time hints are installed, but the prepared cache has no records yet."
    ),
    "with_expired_records": (
        "Action-time hints are installed, but the prepared records are expired."
    ),
    "with_fresh_records": "Action-time hints have fresh prepared records.",
    "not_installed": "This foreground helper is not installed yet.",
    "missing_provider_env_var": (
        "A foreground ambient path is installed, but provider-key visibility is degraded."
    ),
    "child_process_missing_provider_env_var": (
        "Provider keys are visible here, but the child-process path has not inherited them."
    ),
    "multiple_candidates": (
        "The plugin cache refresh has multiple possible targets and needs an explicit choice."
    ),
    "plugin_cache_auto_resolution_blocked": (
        "The plugin cache refresh cannot safely choose a target automatically."
    ),
}
TRUE_FOREGROUND_TOOL_FAILURE_STATUSES = {
    "foreground_mcp_runtime_mismatch",
    "host_live_probe_key_tools_failed",
}
STATUS_ACTION_PRIORITY = {
    "prompt_hook_latency": 10,
    "warm_ambient": 20,
    "provider": 30,
    "hooks": 35,
    "action_hints": 40,
    # Plugin cache repair is important, but it is a nested install/cache
    # follow-up rather than the foreground state itself. Keep it in
    # safe_next_actions so agents can execute the concrete repair command,
    # while letting direct foreground/provider blockers remain the primary card.
    "plugin_cache": 65,
    "operator_detail": 90,
}
AGENT_CALLABLE_NOT_CHECKED_STATUSES = {
    "host_live_probe_ok_foreground_probe_not_checked",
    "host_live_probe_ok_current_thread_unverified",
    "host_registered_tools_unverified",
}


def agent_callable_host_probe_ok(item: dict[str, Any]) -> bool:
    return item.get("surface") == "agent_callable" and (
        (item.get("host_live_probe") or {}).get("ok") is True
    )


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _looks_like_internal_code(value: str) -> bool:
    text = value.strip()
    if not text or " " in text:
        return False
    return "_" in text or ":" in text


def _surface_label(surface: str) -> str:
    return surface.replace("_", " ")


def _readable_action_reason(surface: str, raw_reason: str) -> tuple[str, str | None]:
    reason = raw_reason.strip()
    if not reason:
        return f"{_surface_label(surface).capitalize()} needs review.", None
    if reason in INTERNAL_STATUS_REASON_COPY:
        return INTERNAL_STATUS_REASON_COPY[reason], reason
    if _looks_like_internal_code(reason):
        return (
            f"{_surface_label(surface).capitalize()} needs attention; run the linked "
            "status command for the current setup detail.",
            reason,
        )
    return reason, None


def _compact_update_action(
    *,
    surface: str,
    reason: str,
    command: str | None = None,
    manual_instruction: str | None = None,
    status_code: str | None = None,
    diagnostic_code: str | None = None,
) -> dict[str, Any]:
    readable_reason, inferred_code = _readable_action_reason(surface, reason)
    status_code = (status_code or "").strip() or None
    diagnostic_code = (diagnostic_code or inferred_code or "").strip() or None
    command_fields = update_actions.executable_update_action_fields(
        command,
        fallback_command=(
            update_actions.PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND
            if surface == "plugin_cache"
            else None
        ),
        manual_instruction=manual_instruction,
    )
    result = {
        "id": f"review_{surface}",
        "label": f"Review {surface.replace('_', ' ')}",
        "surface": surface,
        "reason": compact_text(readable_reason, 220),
        "why": compact_text(readable_reason, 220),
        "claim_boundary": "update_status_not_source_evidence",
        **command_fields,
    }
    if status_code:
        result["status_code"] = status_code
    if diagnostic_code and diagnostic_code != status_code:
        result["diagnostic_code"] = diagnostic_code
    if not command_fields:
        result["command"] = "aippocampus update status --operator-json"
        result["manual_instruction"] = (
            manual_instruction
            or "Open the operator status view for the affected update surface before applying repairs."
        )
    result.setdefault(
        "mutation_risk",
        update_actions.foreground_command_mutation_risk(
            result.get("command") or result.get("command_template")
        ),
    )
    if "manual_instruction" in result:
        result["manual_instruction"] = compact_text(str(result["manual_instruction"]), 220)
    return {key: value for key, value in result.items() if value not in (None, "")}


def _status_action_priority(action: dict[str, Any]) -> int:
    surface = str(action.get("surface") or "")
    if surface == "agent_callable":
        status_code = str(action.get("status_code") or action.get("diagnostic_code") or "")
        if status_code in TRUE_FOREGROUND_TOOL_FAILURE_STATUSES:
            return 0
        # A host-ok-but-current-thread-unverified probe is important, but it is
        # not allowed to bury measured foreground friction such as prompt hook
        # latency or a blocked warm queue. Otherwise status cards teach agents
        # to repeat the generic "verify tools" step while the user still feels
        # every prompt stalling.
        return 60
    return STATUS_ACTION_PRIORITY.get(surface, 55)


def _prioritize_status_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        action
        for _priority, _index, action in sorted(
            (
                (_status_action_priority(action), index, action)
                for index, action in enumerate(actions)
            ),
            key=lambda item: (item[0], item[1]),
        )
    ]


def _dedupe_status_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one foreground card per surface after priority ordering.

    The raw status report can mention the same surface from multiple places:
    direct surface readiness, summary.needs_action, and late next_actions. The
    compact agent card is an execution queue, so repeating the same surface
    teaches agents to do the same repair twice and can hide the next real
    blocker behind a duplicate primary action.
    """

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for action in actions:
        surface = str(action.get("surface") or action.get("id") or "")
        if surface and surface in seen:
            continue
        if surface:
            seen.add(surface)
        deduped.append(action)
    return deduped


def _agent_callable_readiness_state(*, ready: bool, status: Any) -> str:
    if ready:
        return "verified"
    status_text = str(status or "")
    if status_text in AGENT_CALLABLE_NOT_CHECKED_STATUSES:
        return "not_checked"
    if status_text in TRUE_FOREGROUND_TOOL_FAILURE_STATUSES:
        return "failed"
    return "not_ready"
