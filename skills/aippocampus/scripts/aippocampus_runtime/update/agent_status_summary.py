"""Compact agent-facing update status projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def agent_callable_host_probe_ok(item: dict[str, Any]) -> bool:
    return item.get("surface") == "agent_callable" and (
        (item.get("host_live_probe") or {}).get("ok") is True
    )


def _compact_update_action(*, surface: str, reason: str, command: str | None = None) -> dict[str, Any]:
    result = {
        "surface": surface,
        "reason": compact_text(reason, 220),
        "command": command,
    }
    return {key: value for key, value in result.items() if value not in (None, "")}


def compact_agent_status_report(
    report: dict[str, Any],
    *,
    schema_version: int,
) -> dict[str, Any]:
    summary = report.get("summary") or report.get("post_status") or {}
    surfaces = report.get("surfaces") or {}
    if not surfaces:
        surfaces = {
            str(item.get("surface")): item
            for item in report.get("applied_surfaces") or []
            if isinstance(item, dict) and item.get("surface")
        }
    agent = surfaces.get("agent_callable") or {}
    plugin = surfaces.get("plugin") or {}
    hooks = surfaces.get("hooks") or {}
    action_hints = hooks.get("action_hints") if isinstance(hooks, dict) else {}
    if not isinstance(action_hints, dict):
        action_hints = {}
    needs_action = [
        str(item)
        for item in summary.get("needs_action") or []
        if str(item) not in {"", "agent_callable"}
    ]
    action_hints_ready = action_hints.get("cache_status") == "with_fresh_records"
    actions: list[dict[str, Any]] = []
    if action_hints.get("installed") and not action_hints_ready and action_hints.get("next_command"):
        actions.append(
            _compact_update_action(
                surface="action_hints",
                reason=str(action_hints.get("cache_status") or "action-time hints not ready"),
                command=str(action_hints.get("next_command")),
            )
        )
    for surface in [item for item in needs_action if item != "plugin_cache"][:4]:
        item = surfaces.get(surface) or {}
        command = item.get("next_command") or item.get("documented_install_command")
        reason = f"{surface} status is {item.get('status') or 'attention_needed'}"
        actions.append(_compact_update_action(surface=surface, reason=reason, command=command))
    if agent.get("next_command") and not agent.get("ready"):
        actions.append(
            _compact_update_action(
                surface="agent_callable",
                reason=str(agent.get("status") or "foreground tools not verified"),
                command=str(agent.get("next_command")),
            )
        )
    cache_refresh = plugin.get("cache_refresh") if isinstance(plugin, dict) else None
    if isinstance(cache_refresh, dict) and cache_refresh.get("ok") is False:
        reason = str(
            cache_refresh.get("blocked_reason")
            or cache_refresh.get("installed_cache_status")
            or "plugin cache refresh failed"
        )
        if cache_refresh.get("candidate_count"):
            reason = f"{reason}: {int(cache_refresh.get('candidate_count') or 0)} candidates"
        actions.append(
            _compact_update_action(
                surface="plugin_cache",
                reason=reason,
                command=cache_refresh.get("next_command"),
            )
        )
    elif summary.get("plugin_cache_needs_action"):
        plugin_action = (plugin.get("plugin_cache_recommended_actions") or [None])[0]
        if plugin_action is None:
            plugin_action = (summary.get("plugin_cache_recommended_actions") or [None])[0]
        actions.append(
            _compact_update_action(
                surface="plugin_cache",
                reason="installed Codex plugin cache or local marketplace is stale",
                command=str(plugin_action) if plugin_action else None,
            )
        )
    if bool(report.get("ok", True)):
        for action in report.get("next_actions") or []:
            if not isinstance(action, dict):
                continue
            surface = str(action.get("surface") or "next")
            reason = str(action.get("reason") or "recommended next action")
            command = action.get("command")
            actions.append(
                _compact_update_action(
                    surface=surface,
                    reason=reason,
                    command=str(command) if command else None,
                )
            )
    agent_ready = (
        bool(summary.get("agent_callable_ready"))
        if "agent_callable_ready" in summary
        else bool(agent.get("ready"))
    )
    agent_host_ready = (
        bool(summary.get("agent_callable_host_ready"))
        if "agent_callable_host_ready" in summary
        else agent_callable_host_probe_ok(agent)
    )
    agent_thread_visible = (
        bool(summary.get("agent_callable_current_thread_visible"))
        if "agent_callable_current_thread_visible" in summary
        else bool(agent.get("ready"))
    )
    agent_status = agent.get("status") or summary.get("agent_callable_status")
    public = {
        "kind": f"aippocampus_update_{report.get('mode') or 'status'}_agent_json",
        "schema_version": schema_version,
        "ok": bool(report.get("ok", True)),
        "mode": report.get("mode") or "status",
        "summary": {
            "core_ready": bool(summary.get("core_ready")),
            "magic_ready": bool(summary.get("magic_ready")),
            "core_blockers": summary.get("core_blockers") or [],
            "magic_blockers": summary.get("magic_blockers") or [],
            "agent_callable_ready": agent_ready,
            "agent_callable_host_ready": agent_host_ready,
            "agent_callable_current_thread_visible": agent_thread_visible,
            "agent_callable_status": agent_status,
            "action_hints_ready": action_hints_ready,
            "action_hints_installed": bool(action_hints.get("installed")),
            "action_hints_status": str(action_hints.get("cache_status") or "not_installed_optional"),
            "needs_action": needs_action,
        },
        "action_hints": {
            "installed": bool(action_hints.get("installed")),
            "ready": action_hints_ready,
            "status": str(action_hints.get("cache_status") or "not_installed_optional"),
            "cache_path_configured": bool(action_hints.get("cache_path_configured")),
            "cache_exists": bool(action_hints.get("cache_exists")),
            "cache_record_count": int(action_hints.get("cache_record_count") or 0),
            "fresh_record_count": int(action_hints.get("fresh_record_count") or 0),
            "expired_record_count": int(action_hints.get("expired_record_count") or 0),
            "malformed_cache_line_count": int(action_hints.get("malformed_cache_line_count") or 0),
            "provider_counts": action_hints.get("provider_counts") or {},
            "optional": True,
            "next_command": action_hints.get("next_command"),
            "claim_boundary": "action-time hints are optional PreToolUse cache-backed nudges, not ambient hook readiness or source truth",
        },
        "agent_callable": {
            "status": agent_status,
            "host_live_probe_status": (agent.get("host_live_probe") or {}).get("status"),
            "host_live_probe_ok": (
                (agent.get("host_live_probe") or {}).get("ok") is True
                or agent_host_ready
            ),
            "current_thread_tool_discovery": agent.get("current_thread_tool_discovery"),
            "foreground_tools_visible": agent.get("foreground_tools_visible"),
            "next_command": agent.get("next_command"),
            "claim_boundary": agent.get("claim_boundary"),
        },
        "next_actions": actions[:5],
    }
    return redact_sensitive_values(redact_private_paths(public))
