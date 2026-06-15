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
    summary = report.get("summary") or {}
    surfaces = report.get("surfaces") or {}
    agent = surfaces.get("agent_callable") or {}
    plugin = surfaces.get("plugin") or {}
    needs_action = [
        str(item)
        for item in summary.get("needs_action") or []
        if str(item) not in {"", "agent_callable"}
    ]
    actions: list[dict[str, Any]] = []
    for surface in needs_action[:4]:
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
    if summary.get("plugin_cache_needs_action"):
        plugin_action = (plugin.get("plugin_cache_recommended_actions") or [None])[0]
        actions.append(
            _compact_update_action(
                surface="plugin_cache",
                reason="installed Codex plugin cache or local marketplace is stale",
                command=str(plugin_action) if plugin_action else None,
            )
        )
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
            "agent_callable_ready": bool(agent.get("ready")),
            "agent_callable_host_ready": agent_callable_host_probe_ok(agent),
            "agent_callable_current_thread_visible": bool(agent.get("ready")),
            "agent_callable_status": agent.get("status"),
            "needs_action": needs_action,
        },
        "agent_callable": {
            "status": agent.get("status"),
            "host_live_probe_status": (agent.get("host_live_probe") or {}).get("status"),
            "host_live_probe_ok": (agent.get("host_live_probe") or {}).get("ok") is True,
            "current_thread_tool_discovery": agent.get("current_thread_tool_discovery"),
            "foreground_tools_visible": agent.get("foreground_tools_visible"),
            "next_command": agent.get("next_command"),
            "claim_boundary": agent.get("claim_boundary"),
        },
        "next_actions": actions[:5],
    }
    return redact_sensitive_values(redact_private_paths(public))
