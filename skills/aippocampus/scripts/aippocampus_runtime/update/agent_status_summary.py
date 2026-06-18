"""Compact agent-facing update status projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import foreground_readiness_card
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
        "surface": surface,
        "reason": compact_text(reason, 220),
        **command_fields,
    }
    if "manual_instruction" in result:
        result["manual_instruction"] = compact_text(str(result["manual_instruction"]), 220)
    return {key: value for key, value in result.items() if value not in (None, "")}


def compact_agent_status_report(
    report: dict[str, Any],
    *,
    schema_version: int,
) -> dict[str, Any]:
    summary = report.get("summary") or report.get("post_status") or {}
    foreground_partial = bool(
        summary.get("partial_readiness") or summary.get("plan_scope") == "foreground_partial"
    )
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
    llm = surfaces.get("llm") or {}
    action_hints = hooks.get("action_hints") if isinstance(hooks, dict) else {}
    if not isinstance(action_hints, dict):
        action_hints = {}
    needs_action = [
        str(item)
        for item in summary.get("needs_action") or []
        if str(item) not in {"", "agent_callable"}
    ]
    action_hints_ready = action_hints.get("cache_status") == "with_fresh_records"
    action_hints_installed = bool(action_hints.get("installed"))
    action_hints_hot_path_active = bool(action_hints.get("hot_path_active"))
    action_hints_setup_role = str(
        action_hints.get("setup_role")
        or (
            "ready"
            if action_hints_ready
            else "cleanup_or_prepare_required"
            if action_hints_installed
            else "recommended_for_trusted_codex"
        )
    )
    action_hint_recommended_actions = update_actions.action_hint_recommended_actions()
    action_hint_primary_command = update_actions.action_hint_status_command()
    deferred_components = []
    for name, item in surfaces.items():
        if not isinstance(item, dict) or not item.get("operator_detail_available"):
            continue
        deferred_components.append(
            {
                "id": str(item.get("deferred_component") or name),
                "status": str(item.get("status") or "not_checked"),
                "reason": compact_text(str(item.get("reason") or "slow check deferred"), 180),
                "operator_detail_command": "aippocampus update status --operator-json",
            }
        )
    if (
        llm.get("visible_in_current_process") is True
        and llm.get("visible_in_child_process") is None
        and not any(item["id"] == "llm_child_process" for item in deferred_components)
    ):
        deferred_components.append(
            {
                "id": "llm_child_process",
                "status": "not_checked",
                "reason": "child-process provider-key inheritance not checked",
                "operator_detail_command": "aippocampus update status --operator-json",
            }
        )
    actions: list[dict[str, Any]] = []
    if deferred_components:
        actions.append(
            _compact_update_action(
                surface="operator_detail",
                reason="full operator readiness sweep deferred",
                command="aippocampus update status --operator-json",
            )
        )
    if not action_hints_ready and not foreground_partial:
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
    readiness_state = (
        "partial_foreground_status"
        if foreground_partial or deferred_components
        else "ready"
        if bool(summary.get("core_ready")) and not needs_action
        else "attention_needed"
    )
    readiness_card = foreground_readiness_card(
        subject="update_status",
        scope=str(summary.get("plan_scope") or "all_surfaces"),
        state=readiness_state,
        usable_now=bool(report.get("ok", True)),
        blocks_first_recall=False,
        blocks_exact_latest=bool(deferred_components),
        recommended=[
            str(card.get("id") or "")
            for card in foreground_cards
            if isinstance(card, dict) and str(card.get("id") or "")
        ],
        next_actions=[
            card
            for card in foreground_cards[:2]
            if isinstance(card, dict)
        ],
        claim_boundary=(
            "update readiness guides setup actions; it is not source evidence "
            "and partial foreground status is not release-grade readiness"
        ),
    )
    public = {
        "kind": f"aippocampus_update_{report.get('mode') or 'status'}_agent_json",
        "schema_version": schema_version,
        "ok": bool(report.get("ok", True)),
        "mode": report.get("mode") or "status",
        "summary": {
            "core_ready": bool(summary.get("core_ready")),
            "magic_ready": bool(summary.get("magic_ready")),
            "magic_ready_semantics": str(
                summary.get("magic_ready_semantics")
                or "legacy_alias_for_product_magic_ready"
            ),
            "subsystem_magic_ready": bool(summary.get("subsystem_magic_ready")),
            "first_magic_moment_ready": bool(summary.get("first_magic_moment_ready")),
            "product_magic_ready": bool(summary.get("product_magic_ready")),
            "core_blockers": summary.get("core_blockers") or [],
            "magic_blockers": summary.get("magic_blockers") or [],
            "agent_callable_ready": agent_ready,
            "agent_callable_host_ready": agent_host_ready,
            "agent_callable_current_thread_visible": agent_thread_visible,
            "agent_callable_status": agent_status,
            "host_conformance_label": conformance.get("label"),
            "action_hints_ready": action_hints_ready,
            "action_hints_installed": action_hints_installed,
            "action_hints_hot_path_active": action_hints_hot_path_active,
            "action_hints_status": str(action_hints.get("cache_status") or "not_installed_optional"),
            "dirty_worktree_guards": summary.get("dirty_worktree_guards") or {},
            "plan_surface_filter": summary.get("plan_surface_filter") or [],
            "plan_scope": summary.get("plan_scope") or "all_surfaces",
            "partial_readiness": bool(deferred_components),
            "deferred_components": [item["id"] for item in deferred_components],
            "foreground_actions": [
                str(card.get("id") or "")
                for card in foreground_cards
                if str(card.get("id") or "")
            ],
            "needs_action": needs_action,
        },
        "partial_readiness": {
            "status": "partial" if deferred_components else "complete",
            "deferred_components": deferred_components,
            "operator_detail_command": "aippocampus update status --operator-json",
            "claim_boundary": (
                "partial foreground status can guide safe next action but is not "
                "release-grade or exact latest readiness"
            ),
        },
        **(
            {"write_boundary": report["write_boundary"]}
            if isinstance(report.get("write_boundary"), dict)
            else {}
        ),
        "readiness_card": readiness_card,
        "foreground_status_cards": foreground_cards,
        "action_hints": {
            "installed": bool(action_hints.get("installed")),
            "ready": action_hints_ready,
            "hot_path_active": action_hints_hot_path_active,
            "warning_state": str(action_hints.get("warning_state") or ""),
            "status": str(action_hints.get("cache_status") or "not_installed_optional"),
            "cache_path_configured": bool(action_hints.get("cache_path_configured")),
            "cache_exists": bool(action_hints.get("cache_exists")),
            "cache_record_count": int(action_hints.get("cache_record_count") or 0),
            "fresh_record_count": int(action_hints.get("fresh_record_count") or 0),
            "expired_record_count": int(action_hints.get("expired_record_count") or 0),
            "malformed_cache_line_count": int(action_hints.get("malformed_cache_line_count") or 0),
            "provider_counts": action_hints.get("provider_counts") or {},
            "optional": False,
            "setup_role": action_hints_setup_role,
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
