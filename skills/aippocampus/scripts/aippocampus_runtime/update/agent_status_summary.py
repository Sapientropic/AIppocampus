"""Compact agent-facing update status projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.update import status_actions as update_actions


def agent_callable_host_probe_ok(item: dict[str, Any]) -> bool:
    return item.get("surface") == "agent_callable" and (
        (item.get("host_live_probe") or {}).get("ok") is True
    )


def _compact_update_action(
    *,
    surface: str,
    reason: str,
    command: str | None = None,
    manual_instruction: str | None = None,
) -> dict[str, Any]:
    result = {
        "surface": surface,
        "reason": compact_text(reason, 220),
        "command": command,
        "manual_instruction": compact_text(manual_instruction, 220)
        if manual_instruction
        else None,
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
    conformance = surfaces.get("host_conformance") or {}
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
    action_hint_recommended_actions = update_actions.action_hint_recommended_actions()
    action_hint_primary_command = (
        action_hints.get("next_command")
        or action_hint_recommended_actions[0]["command"]
    )
    actions: list[dict[str, Any]] = []
    if not action_hints_ready:
        actions.append(
            _compact_update_action(
                surface="action_hints",
                reason=str(action_hints.get("cache_status") or "action-time hints not ready"),
                command=str(action_hint_primary_command),
            )
        )
    agent_next_action = update_actions.agent_callable_foreground_action(agent)
    if agent.get("status") and (agent.get("next_command") or agent_next_action.get("command")) and not agent.get("ready"):
        actions.append(
            _compact_update_action(
                surface="agent_callable",
                reason=str(agent.get("status") or "foreground tools not verified"),
                command=str(agent_next_action.get("command") or agent.get("next_command")),
                manual_instruction=agent_next_action.get("manual_instruction"),
            )
        )
    for surface in [item for item in needs_action if item != "plugin_cache"][:4]:
        item = surfaces.get(surface) or {}
        command = item.get("next_command") or item.get("documented_install_command")
        reason = f"{surface} status is {item.get('status') or 'attention_needed'}"
        actions.append(_compact_update_action(surface=surface, reason=reason, command=command))
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
                    manual_instruction=str(action.get("manual_instruction") or "")
                    if action.get("manual_instruction")
                    else None,
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
    foreground_cards = update_actions.foreground_status_cards(report)
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
            "host_conformance_label": conformance.get("label"),
            "action_hints_ready": action_hints_ready,
            "action_hints_installed": bool(action_hints.get("installed")),
            "action_hints_status": str(action_hints.get("cache_status") or "not_installed_optional"),
            "dirty_worktree_guards": summary.get("dirty_worktree_guards") or {},
            "plan_surface_filter": summary.get("plan_surface_filter") or [],
            "plan_scope": summary.get("plan_scope") or "all_surfaces",
            "foreground_actions": [
                str(card.get("id") or "")
                for card in foreground_cards
                if str(card.get("id") or "")
            ],
            "needs_action": needs_action,
        },
        "foreground_status_cards": foreground_cards,
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
            "optional": False,
            "setup_role": "ready" if action_hints_ready else "recommended_for_trusted_codex",
            "fail_open": True,
            "recall_blocking": False,
            "next_command": action_hint_primary_command,
            "recommended_next_actions": action_hint_recommended_actions,
            "claim_boundary": (
                "action-time hints are recommended setup for trusted Codex sessions, "
                "but remain navigation-only and never source truth or a recall blocker"
            ),
        },
        "agent_callable": {
            "status": agent_status,
            "host_live_probe_status": (agent.get("host_live_probe") or {}).get("status"),
            "host_live_probe_ok": (
                (agent.get("host_live_probe") or {}).get("ok") is True
                or agent_host_ready
            ),
            "tools_visible": agent.get("tools_visible"),
            "key_tools_callable": agent.get("key_tools_callable"),
            "key_tools_callable_source": agent.get("current_foreground_key_tools_source"),
            "key_tools_callable_asserted_by_caller": bool(
                agent.get("current_foreground_key_tools_asserted_by_caller")
            ),
            "key_tools_callable_verified": bool(agent.get("current_foreground_key_tools_verified")),
            "live_host_schema_stale": bool(agent.get("live_host_schema_stale")),
            "key_tool_failures": agent.get("key_tool_failures") or [],
            "current_thread_tool_discovery": agent.get("current_thread_tool_discovery"),
            "foreground_probe_requested": bool(agent.get("foreground_probe_requested")),
            "foreground_probe_state": agent.get("foreground_probe_state"),
            "foreground_tools_visible": agent.get("foreground_tools_visible"),
            "next_command": agent_next_action.get("command"),
            "manual_instruction": agent_next_action.get("manual_instruction"),
            "claim_boundary": agent.get("claim_boundary"),
        },
        "host_conformance": {
            "label": conformance.get("label"),
            "dimensions": conformance.get("dimensions") or {},
            "next_action": conformance.get("next_action"),
            "claim_boundary": conformance.get("claim_boundary"),
        },
        "next_actions": actions[:5],
    }
    return redact_sensitive_values(redact_private_paths(public))
