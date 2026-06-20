"""Compact agent-facing update status projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.update import status_actions as update_actions


def agent_callable_host_probe_ok(item: dict[str, Any]) -> bool:
    return item.get("surface") == "agent_callable" and (
        (item.get("host_live_probe") or {}).get("ok") is True
    )


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
        "id": f"review_{surface}",
        "label": f"Review {surface.replace('_', ' ')}",
        "surface": surface,
        "reason": compact_text(reason, 220),
        "why": compact_text(reason, 220),
        "claim_boundary": "update_status_not_source_evidence",
        **command_fields,
    }
    if not command_fields:
        result["command"] = "aippocampus update status --operator-json"
        result["manual_instruction"] = (
            manual_instruction
            or "Open the operator status view for the affected update surface before applying repairs."
        )
    result.setdefault("mutation_risk", "read_only")
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
    action_hint_primary_command = update_actions.action_hint_status_command()
    hook_status = str(hooks.get("status") or "not_checked")
    prompt_installed = bool(hooks.get("prompt_installed"))
    lifecycle_installed = bool(hooks.get("lifecycle_installed"))
    prompt_hook_status = hooks.get("prompt_hook_status") if isinstance(hooks, dict) else {}
    if not isinstance(prompt_hook_status, dict):
        prompt_hook_status = {}
    warm_ambient_status = hooks.get("warm_ambient") if isinstance(hooks, dict) else {}
    if not isinstance(warm_ambient_status, dict):
        warm_ambient_status = {}
    warm_activity = warm_ambient_status.get("job_activity")
    if not isinstance(warm_activity, dict):
        warm_activity = {}
    prompt_latency_status = str(
        prompt_hook_status.get("prompt_hook_latency_risk_status") or ""
    )
    foreground_latency_red_lines = _safe_int(
        prompt_hook_status.get("foreground_latency_red_line_violation_count")
    )
    prompt_near_timeout_count = _safe_int(prompt_hook_status.get("near_timeout_event_count"))
    prompt_latency_risk = (
        prompt_latency_status == "near_host_timeout_risk"
        or foreground_latency_red_lines > 0
        or prompt_near_timeout_count > 0
    )
    warm_status = str(warm_ambient_status.get("status") or "")
    warm_queue_state = str(warm_activity.get("queue_state") or "")
    warm_stale_queue = bool(warm_activity.get("stale_queue_blocked")) or warm_status == "blocked"
    provider_status = str(llm.get("status") or "")
    provider_degraded = provider_status in {
        "missing_provider_env_var",
        "child_process_missing_provider_env_var",
    }
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
    plan_surface_filter = summary.get("plan_surface_filter") or []
    if plan_surface_filter:
        for surface in [item for item in needs_action if item != "plugin_cache"][:4]:
            item = surfaces.get(surface) or {}
            command = item.get("next_command") or item.get("documented_install_command")
            reason = f"{surface} status is {item.get('status') or 'attention_needed'}"
            actions.append(_compact_update_action(surface=surface, reason=reason, command=command))
    if prompt_latency_risk and not foreground_partial:
        actions.append(
            _compact_update_action(
                surface="prompt_hook_latency",
                reason=(
                    "prompt hook near-timeout risk: "
                    f"{foreground_latency_red_lines} red-line event(s), "
                    f"{prompt_near_timeout_count} near-timeout event(s)"
                ),
                command="aippocampus hooks prompt status --last --json",
            )
        )
    if warm_stale_queue and not foreground_partial:
        actions.append(
            _compact_update_action(
                surface="warm_ambient",
                reason=f"warm ambient queue is {warm_queue_state or warm_status}",
                command=str(warm_ambient_status.get("next_command") or "aippocampus warm status --json"),
            )
        )
    ambient_installed_for_provider = bool(
        prompt_installed
        or lifecycle_installed
        or action_hints_installed
        or warm_status in {"blocked", "pending"}
    )
    if provider_degraded and ambient_installed_for_provider and not foreground_partial:
        actions.append(
            _compact_update_action(
                surface="provider",
                reason=f"ambient/provider path status is {provider_status}",
                command="aippocampus doctor provider --json",
            )
        )
    if not plan_surface_filter:
        for surface in [item for item in needs_action if item != "plugin_cache"][:4]:
            item = surfaces.get(surface) or {}
            command = item.get("next_command") or item.get("documented_install_command")
            reason = f"{surface} status is {item.get('status') or 'attention_needed'}"
            actions.append(_compact_update_action(surface=surface, reason=reason, command=command))
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
    ambient_issue_codes: list[str] = []
    if hook_status not in {"current", "not_checked"}:
        ambient_issue_codes.append(f"hooks:{hook_status}")
    if action_hints_installed and not action_hints_ready:
        ambient_issue_codes.append(f"action_hints:{action_hints.get('cache_status') or 'not_ready'}")
    if prompt_latency_risk:
        ambient_issue_codes.append("prompt_hook:latency_risk")
    if warm_stale_queue:
        ambient_issue_codes.append(f"warm_ambient:{warm_queue_state or warm_status}")
    if provider_degraded and ambient_installed_for_provider:
        ambient_issue_codes.append(f"provider:{provider_status}")
    active_useful = bool(
        prompt_installed
        and not prompt_latency_risk
        and (
            _safe_int(prompt_hook_status.get("last_prompt_hook_useful_signal_count")) > 0
            or action_hints_ready
        )
    )
    ambient_state = (
        "ready"
        if hook_status == "current"
        and (not action_hints_installed or action_hints_ready)
        and not prompt_latency_risk
        and not warm_stale_queue
        and not (provider_degraded and ambient_installed_for_provider)
        else "degraded"
        if prompt_installed
        or lifecycle_installed
        or action_hints_installed
        or warm_status in {"blocked", "pending"}
        else "not_installed"
        if hook_status in {"missing", "not_checked", "deferred"} and not (prompt_installed or lifecycle_installed)
        else "attention_needed"
    )
    if action_hints_installed and not action_hints_ready:
        ambient_next_command = action_hint_primary_command
        ambient_next_action = "refresh_or_inspect_action_hints"
    elif prompt_latency_risk:
        ambient_next_command = "aippocampus hooks prompt status --last --json"
        ambient_next_action = "inspect_prompt_hook_latency"
    elif warm_stale_queue:
        ambient_next_command = str(
            warm_ambient_status.get("next_command") or "aippocampus warm status --json"
        )
        ambient_next_action = "inspect_warm_queue_or_provider"
    elif provider_degraded and ambient_installed_for_provider:
        ambient_next_command = "aippocampus doctor provider --json"
        ambient_next_action = "inspect_provider"
    elif ambient_state == "ready":
        ambient_next_command = ""
        ambient_next_action = "continue_with_ordinary_recall"
    else:
        ambient_next_command = "aippocampus update status --operator-json"
        ambient_next_action = "inspect_operator_status"
    ambient_recall = {
        "state": ambient_state,
        "active_useful": active_useful,
        "prompt_hook_installed": prompt_installed,
        "lifecycle_hook_installed": lifecycle_installed,
        "action_hints_installed": action_hints_installed,
        "action_hints_ready": action_hints_ready,
        "hot_path_active": action_hints_hot_path_active,
        "latency_risk": {
            "status": prompt_latency_status or "not_checked",
            "foreground_latency_red_line_violation_count": foreground_latency_red_lines,
            "near_timeout_event_count": prompt_near_timeout_count,
            "diagnostic_command": "aippocampus hooks prompt status --last --json",
        },
        "warm_queue": {
            "status": warm_status or "not_checked",
            "queue_state": warm_queue_state or "not_checked",
            "pending_recent_count": _safe_int(warm_activity.get("pending_recent_count")),
            "pending_stale_count": _safe_int(warm_activity.get("pending_stale_count")),
            "stale_queue_blocked": warm_stale_queue,
            "ordinary_recall_usable": bool(
                warm_ambient_status.get("ordinary_recall_usable", True)
            ),
        },
        "provider": {
            "status": provider_status or "not_checked",
            "degraded": bool(provider_degraded and ambient_installed_for_provider),
            "values_redacted": True,
        },
        "issue_codes": ambient_issue_codes,
        "next_action": ambient_next_action,
        "next_command": ambient_next_command,
        "claim_boundary": "ambient readiness is operational status, not source evidence",
    }
    readiness_state = (
        "partial_foreground_status"
        if foreground_partial or deferred_components
        else "ready"
        if bool(summary.get("core_ready")) and not needs_action
        else "attention_needed"
    )
    primary_action = actions[0] if actions else {
        "id": "continue_after_update_status",
        "label": "Continue after update status",
        "message": "Update status has no foreground setup action; continue normal source-backed work.",
        "why": "No update status surface is asking for foreground setup or repair.",
        "mutation_risk": "read_only",
        "claim_boundary": "update_status_not_source_evidence",
        "continue_without_command": True,
    }
    public = {
        "kind": f"aippocampus_update_{report.get('mode') or 'status'}_agent_json",
        "schema_version": schema_version,
        "ok": bool(report.get("ok", True)),
        "mode": report.get("mode") or "status",
        "summary": {
            "core_ready": bool(summary.get("core_ready")),
            "first_magic_moment_ready": bool(summary.get("first_magic_moment_ready")),
            "product_magic_ready": bool(summary.get("product_magic_ready")),
            "core_blockers": summary.get("core_blockers") or [],
            "magic_blockers": summary.get("magic_blockers") or [],
            "agent_callable_ready": agent_ready,
            "agent_callable_host_ready": agent_host_ready,
            "agent_callable_current_thread_visible": agent_thread_visible,
            "agent_callable_status": agent_status,
            "plan_surface_filter": summary.get("plan_surface_filter") or [],
            "plan_scope": summary.get("plan_scope") or "all_surfaces",
            "partial_readiness": bool(deferred_components),
            "deferred_components": [item["id"] for item in deferred_components],
            "dirty_worktree_guards": summary.get("dirty_worktree_guards") or {},
            "ambient_recall_state": ambient_state,
            "needs_action": needs_action,
        },
        "setup_card": {
            "state": readiness_state,
            "usable_now": bool(report.get("ok", True)),
            "partial_readiness": bool(deferred_components),
            "deferred_count": len(deferred_components),
            "first_deferred_component": deferred_components[0]["id"] if deferred_components else None,
            "operator_detail_command": "aippocampus update status --operator-json",
            "claim_boundary": "update status guides setup actions; it is not source evidence",
        },
        "ambient_recall": ambient_recall,
        **(
            {"write_boundary": report["write_boundary"]}
            if isinstance(report.get("write_boundary"), dict)
            else {}
        ),
        **canonical_foreground_action_fields(
            primary_action,
            safe_next_actions=actions[:5] or [primary_action],
        ),
        "claim_boundary": "Setup status is operational guidance, not memory evidence; reopen source before claims.",
        "operator_detail_command": "aippocampus update status --operator-json",
    }
    return redact_sensitive_values(redact_private_paths(public))
