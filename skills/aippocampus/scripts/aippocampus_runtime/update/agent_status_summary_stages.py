"""Staged compact update-status projection.

The compact status card is foreground product output. Keep proof, raw probe
details, and operator diagnostics in the detail view; this module only selects
the next useful setup action and the four-stage ambient status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.foreground_compact_language import compact_frontstage_projection
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.update import status_actions as update_actions
from aippocampus_runtime.update.agent_status_deferred_projection import (
    deferred_ambient_field_projection,
)
from aippocampus_runtime.update.agent_status_summary_core import (
    TRUE_FOREGROUND_TOOL_FAILURE_STATUSES,
    _agent_callable_readiness_state,
    _compact_update_action,
    _dedupe_status_actions,
    _looks_like_internal_code,
    _prioritize_status_actions,
    _safe_int,
    agent_callable_host_probe_ok,
)

OPERATOR_STATUS_COMMAND = "aippocampus update status --operator-json"


@dataclass
class CompactStatusState:
    summary: dict[str, Any]
    surfaces: dict[str, Any]
    agent: dict[str, Any]
    plugin: dict[str, Any]
    hooks: dict[str, Any]
    llm: dict[str, Any]
    action_hints: dict[str, Any]
    action_hint_foreground: dict[str, Any]
    action_hint_primary_command: str
    foreground_partial: bool
    needs_action: list[str]
    plan_surface_filter: list[Any]
    hook_status: str
    prompt_installed: bool
    lifecycle_installed: bool
    prompt_hook_status: dict[str, Any]
    warm_ambient_status: dict[str, Any]
    warm_activity: dict[str, Any]
    prompt_latency_status: str
    prompt_latency_freshness_status: str
    prompt_latency_historical_status: str
    foreground_latency_red_lines: int
    prompt_near_timeout_count: int
    historical_foreground_latency_red_lines: int
    historical_prompt_near_timeout_count: int
    prompt_latency_risk: bool
    warm_status: str
    warm_queue_state: str
    warm_stale_queue: bool
    provider_status: str
    provider_degraded: bool
    action_hints_ready: bool
    action_hints_useful_signal: bool
    action_hints_installed: bool
    action_hints_hot_path_active: bool


def normalize_status_surfaces(report: dict[str, Any]) -> CompactStatusState:
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
    agent_status_for_needs = str(agent.get("status") or summary.get("agent_callable_status") or "")
    needs_action = [
        str(item)
        for item in summary.get("needs_action") or []
        if str(item)
        and (
            str(item) != "agent_callable"
            or agent_status_for_needs in TRUE_FOREGROUND_TOOL_FAILURE_STATUSES
        )
    ]
    if (
        agent_status_for_needs in TRUE_FOREGROUND_TOOL_FAILURE_STATUSES
        and "agent_callable" not in needs_action
    ):
        needs_action.insert(0, "agent_callable")
    raw_action_hint_foreground = action_hints.get("foreground_action")
    action_hint_foreground = (
        raw_action_hint_foreground if isinstance(raw_action_hint_foreground, dict) else {}
    )
    action_hint_primary_command = str(
        action_hint_foreground.get("command")
        or action_hints.get("next_command")
        or update_actions.action_hint_status_command()
    )
    hook_status = str(hooks.get("status") or "not_checked")
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
        prompt_hook_status.get("prompt_hook_latency_current_status")
        or prompt_hook_status.get("prompt_hook_latency_risk_status")
        or ""
    )
    prompt_latency_freshness_status = str(
        prompt_hook_status.get("prompt_hook_latency_freshness_status") or ""
    )
    prompt_latency_historical_status = str(
        prompt_hook_status.get("prompt_hook_latency_historical_status") or ""
    )
    foreground_latency_red_lines = _safe_int(
        prompt_hook_status.get("foreground_latency_red_line_violation_count")
    )
    prompt_near_timeout_count = _safe_int(prompt_hook_status.get("near_timeout_event_count"))
    historical_foreground_latency_red_lines = _safe_int(
        prompt_hook_status.get("historical_foreground_latency_red_line_violation_count")
    )
    historical_prompt_near_timeout_count = _safe_int(
        prompt_hook_status.get("historical_near_timeout_event_count")
    )
    prompt_latency_risk = (
        prompt_latency_status == "near_host_timeout_risk"
        or foreground_latency_red_lines > 0
        or prompt_near_timeout_count > 0
    )
    warm_status = str(warm_ambient_status.get("status") or "")
    warm_queue_state = str(warm_activity.get("queue_state") or "")
    provider_status = str(llm.get("status") or "")
    return CompactStatusState(
        summary=summary,
        surfaces=surfaces,
        agent=agent,
        plugin=plugin,
        hooks=hooks,
        llm=llm,
        action_hints=action_hints,
        action_hint_foreground=action_hint_foreground,
        action_hint_primary_command=action_hint_primary_command,
        foreground_partial=foreground_partial,
        needs_action=needs_action,
        plan_surface_filter=summary.get("plan_surface_filter") or [],
        hook_status=hook_status,
        prompt_installed=bool(hooks.get("prompt_installed")),
        lifecycle_installed=bool(hooks.get("lifecycle_installed")),
        prompt_hook_status=prompt_hook_status,
        warm_ambient_status=warm_ambient_status,
        warm_activity=warm_activity,
        prompt_latency_status=prompt_latency_status,
        prompt_latency_freshness_status=prompt_latency_freshness_status,
        prompt_latency_historical_status=prompt_latency_historical_status,
        foreground_latency_red_lines=foreground_latency_red_lines,
        prompt_near_timeout_count=prompt_near_timeout_count,
        historical_foreground_latency_red_lines=historical_foreground_latency_red_lines,
        historical_prompt_near_timeout_count=historical_prompt_near_timeout_count,
        prompt_latency_risk=prompt_latency_risk,
        warm_status=warm_status,
        warm_queue_state=warm_queue_state,
        warm_stale_queue=bool(warm_activity.get("stale_queue_blocked")) or warm_status == "blocked",
        provider_status=provider_status,
        provider_degraded=provider_status
        in {"missing_provider_env_var", "child_process_missing_provider_env_var"},
        action_hints_ready=action_hints.get("cache_status") == "with_fresh_records",
        action_hints_useful_signal=bool(action_hints.get("useful")),
        action_hints_installed=bool(action_hints.get("installed")),
        action_hints_hot_path_active=bool(action_hints.get("hot_path_active")),
    )


def collect_operator_deferred_components(state: CompactStatusState) -> list[dict[str, Any]]:
    deferred_components = []
    for name, item in state.surfaces.items():
        if not isinstance(item, dict) or not item.get("operator_detail_available"):
            continue
        deferred_components.append(
            {
                "id": str(item.get("deferred_component") or name),
                "status": str(item.get("status") or "not_checked"),
                "reason": compact_text(str(item.get("reason") or "slow check deferred"), 180),
                "operator_detail_command": OPERATOR_STATUS_COMMAND,
            }
        )
    if (
        state.llm.get("visible_in_current_process") is True
        and state.llm.get("visible_in_child_process") is None
        and not any(item["id"] == "llm_child_process" for item in deferred_components)
    ):
        deferred_components.append(
            {
                "id": "llm_child_process",
                "status": "not_checked",
                "reason": "child-process provider-key inheritance not checked",
                "operator_detail_command": OPERATOR_STATUS_COMMAND,
            }
        )
    return deferred_components


def ambient_installed_for_provider(state: CompactStatusState) -> bool:
    return bool(
        state.prompt_installed
        or state.lifecycle_installed
        or state.action_hints_installed
        or state.warm_status in {"blocked", "pending"}
    )


def _append_surface_actions(actions: list[dict[str, Any]], state: CompactStatusState) -> None:
    for surface in [item for item in state.needs_action if item != "plugin_cache"][:4]:
        item = state.surfaces.get(surface) or {}
        status_code = str(item.get("status") or "attention_needed")
        actions.append(
            _compact_update_action(
                surface=surface,
                reason=status_code,
                command=item.get("next_command") or item.get("documented_install_command"),
                status_code=status_code,
            )
        )


def collect_update_actions(
    report: dict[str, Any],
    state: CompactStatusState,
    deferred_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    foreground_action = update_actions.agent_callable_foreground_action(state.agent)
    agent_action_needed = bool(
        state.agent.get("status")
        and (state.agent.get("next_command") or foreground_action.get("command"))
        and not state.agent.get("ready")
    )
    if agent_action_needed:
        actions.append(
            _compact_update_action(
                surface="agent_callable",
                reason=str(state.agent.get("status") or "foreground tools not verified"),
                command=str(foreground_action.get("command") or state.agent.get("next_command")),
                manual_instruction=foreground_action.get("manual_instruction"),
                status_code=str(state.agent.get("status") or ""),
            )
        )
    # Deferred slow probes are an operator-detail affordance, not a foreground
    # next action. Keeping them out of safe_next_actions prevents agents from
    # replacing the useful setup step with another diagnostics sweep.
    if state.action_hints_installed and not state.action_hints_useful_signal and not state.foreground_partial:
        actions.append(
            _compact_update_action(
                surface="action_hints",
                reason=str(state.action_hints.get("cache_status") or "action-time hints not ready"),
                command=str(state.action_hint_primary_command),
                status_code=str(state.action_hints.get("cache_status") or ""),
            )
        )
    if state.plan_surface_filter:
        _append_surface_actions(actions, state)
        if "hooks" in {str(item) for item in state.plan_surface_filter} and not state.action_hints_installed:
            actions.append(
                _compact_update_action(
                    surface="action_hints",
                    reason="not_installed",
                    command=update_actions.action_hint_status_command(),
                    status_code="not_installed",
                )
            )
    if state.prompt_latency_risk and not state.foreground_partial:
        actions.append(
            _compact_update_action(
                surface="prompt_hook_latency",
                reason=(
                    "prompt hook near-timeout risk: "
                    f"{state.foreground_latency_red_lines} red-line event(s), "
                    f"{state.prompt_near_timeout_count} near-timeout event(s)"
                ),
                command="aippocampus hooks prompt status --last --json",
            )
        )
    if state.warm_stale_queue and not state.foreground_partial:
        actions.append(
            _compact_update_action(
                surface="warm_ambient",
                reason=f"warm ambient queue is {state.warm_queue_state or state.warm_status}",
                command=str(
                    state.warm_ambient_status.get("next_command") or "aippocampus warm status --json"
                ),
            )
        )
    provider_installed = ambient_installed_for_provider(state)
    if state.provider_degraded and provider_installed and not state.foreground_partial:
        actions.append(
            _compact_update_action(
                surface="provider",
                reason=f"ambient/provider path status is {state.provider_status}",
                command="aippocampus doctor provider --json",
            )
        )
    if not state.plan_surface_filter:
        _append_surface_actions(actions, state)
    cache_refresh = state.plugin.get("cache_refresh") if isinstance(state.plugin, dict) else None
    if isinstance(cache_refresh, dict) and cache_refresh.get("ok") is False:
        reason_code = str(
            cache_refresh.get("blocked_reason")
            or cache_refresh.get("installed_cache_status")
            or "plugin cache refresh failed"
        )
        action = _compact_update_action(
            surface="plugin_cache",
            reason=reason_code,
            command=cache_refresh.get("next_command"),
            status_code=reason_code if _looks_like_internal_code(reason_code) else None,
        )
        if cache_refresh.get("candidate_count"):
            action["candidate_count"] = int(cache_refresh.get("candidate_count") or 0)
        actions.append(action)
    elif state.summary.get("plugin_cache_needs_action"):
        plugin_action = (state.plugin.get("plugin_cache_recommended_actions") or [None])[0]
        if plugin_action is None:
            plugin_action = (state.summary.get("plugin_cache_recommended_actions") or [None])[0]
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
            actions.append(
                _compact_update_action(
                    surface=str(action.get("surface") or "next"),
                    reason=str(action.get("reason") or "recommended next action"),
                    command=str(action.get("command")) if action.get("command") else None,
                    manual_instruction=str(action.get("manual_instruction") or "")
                    if action.get("manual_instruction")
                    else None,
                )
            )
    return _dedupe_status_actions(_prioritize_status_actions(actions))


def agent_readiness_public_fields(state: CompactStatusState) -> dict[str, Any]:
    summary = state.summary
    agent_ready_bool = (
        bool(summary.get("agent_callable_ready"))
        if "agent_callable_ready" in summary
        else bool(state.agent.get("ready"))
    )
    agent_host_ready = (
        bool(summary.get("agent_callable_host_ready"))
        if "agent_callable_host_ready" in summary
        else agent_callable_host_probe_ok(state.agent)
    )
    agent_thread_visible = (
        bool(summary.get("agent_callable_current_thread_visible"))
        if "agent_callable_current_thread_visible" in summary
        else bool(state.agent.get("ready"))
    )
    agent_status = state.agent.get("status") or summary.get("agent_callable_status")
    readiness_state = _agent_callable_readiness_state(ready=agent_ready_bool, status=agent_status)
    raw_thread_callable = summary.get(
        "agent_callable_current_thread_callable",
        state.agent.get("current_foreground_key_tools_callable"),
    )
    return {
        "agent_callable_ready": True if readiness_state == "verified" else None if readiness_state == "not_checked" else False,
        "agent_callable_readiness_state": readiness_state,
        "agent_callable_host_ready": agent_host_ready,
        "agent_callable_current_thread_visible": agent_thread_visible,
        "agent_callable_current_thread_callable": None
        if readiness_state == "not_checked"
        else bool(raw_thread_callable),
        "agent_callable_status": agent_status,
    }


def build_ambient_recall_status(
    state: CompactStatusState,
    deferred_components: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_installed = ambient_installed_for_provider(state)
    issue_codes: list[str] = []
    if state.hook_status not in {"current", "not_checked"}:
        issue_codes.append(f"hooks:{state.hook_status}")
    if state.action_hints_installed and not state.action_hints_ready:
        issue_codes.append(f"action_hints:{state.action_hints.get('cache_status') or 'not_ready'}")
    if state.prompt_latency_risk:
        issue_codes.append("prompt_hook:latency_risk")
    if state.warm_stale_queue:
        issue_codes.append(f"warm_ambient:{state.warm_queue_state or state.warm_status}")
    if state.provider_degraded and provider_installed:
        issue_codes.append(f"provider:{state.provider_status}")
    hooks_deferred = state.hook_status in {"not_checked", "deferred"} and any(
        item.get("id") == "hooks_status" for item in deferred_components
    )
    provider_deferred = state.provider_status in {"not_checked", "deferred"} and any(
        item.get("id") == "llm_child_process" for item in deferred_components
    )
    if hooks_deferred and "hooks:deferred" not in issue_codes:
        issue_codes.append("hooks:deferred")
    active_useful = bool(
        state.prompt_installed
        and not state.prompt_latency_risk
        and (
            _safe_int(state.prompt_hook_status.get("last_prompt_hook_useful_signal_count")) > 0
            or state.action_hints_useful_signal
        )
    )
    prompt_hook_active = bool(
        state.prompt_installed
        and str(state.prompt_hook_status.get("last_prompt_hook_status") or "") == "found"
    )
    ambient_callable = bool(
        state.hook_status == "current"
        or state.prompt_installed
        or state.lifecycle_installed
        or state.action_hints_installed
        or state.warm_status in {"blocked", "pending"}
    )
    # Active is intentionally narrower than installed/callable. Prompt latency,
    # stale warm queues, and empty action-hint caches mean the path can exist
    # while still not being useful to the foreground user.
    ambient_active = bool(
        not state.prompt_latency_risk
        and not state.warm_stale_queue
        and (
            prompt_hook_active
            or state.action_hints_hot_path_active
            or state.warm_status in {"pending"}
        )
    )
    ambient_stage = (
        "useful"
        if active_useful
        and not state.prompt_latency_risk
        and not state.warm_stale_queue
        and not (state.provider_degraded and provider_installed)
        else "active"
        if ambient_active
        else "callable"
        if ambient_callable
        else "installed"
    )
    action_hints_stage = (
        "useful"
        if state.action_hints_useful_signal
        else "active"
        if state.action_hints_hot_path_active or state.action_hints_ready
        else "callable"
        if state.action_hints_installed
        else "installed"
    )
    next_action, next_command = _ambient_next_step(state, ambient_stage, provider_installed)
    return {
        "stage": ambient_stage,
        "stage_values": ["installed", "callable", "active", "useful"],
        "useful_signal_present": active_useful,
        **deferred_ambient_field_projection(
            state,
            action_hints_stage=action_hints_stage,
            hooks_deferred=hooks_deferred,
            provider_deferred=provider_deferred,
            provider_installed=provider_installed,
        ),
        "latency_risk": {
            "status": "deferred" if hooks_deferred else state.prompt_latency_status or "not_checked",
            "freshness_status": "deferred"
            if hooks_deferred
            else state.prompt_latency_freshness_status or "not_checked",
            "historical_status": "deferred"
            if hooks_deferred
            else state.prompt_latency_historical_status or "not_checked",
            "foreground_latency_red_line_violation_count": state.foreground_latency_red_lines,
            "near_timeout_event_count": state.prompt_near_timeout_count,
            "historical_foreground_latency_red_line_violation_count": (
                state.historical_foreground_latency_red_lines
            ),
            "historical_near_timeout_event_count": state.historical_prompt_near_timeout_count,
            "diagnostic_command": "aippocampus hooks prompt status --last --json",
        },
        "warm_queue": {
            "status": state.warm_status or "not_checked",
            "queue_state": state.warm_queue_state or "not_checked",
            "pending_recent_count": _safe_int(state.warm_activity.get("pending_recent_count")),
            "pending_stale_count": _safe_int(state.warm_activity.get("pending_stale_count")),
            "stale_queue_blocked": state.warm_stale_queue,
            "ordinary_recall_usable": bool(
                state.warm_ambient_status.get("ordinary_recall_usable", True)
            ),
        },
        "issue_codes": issue_codes,
        "next_action": next_action,
        "next_command": next_command,
        "claim_boundary": "ambient stage is operational status, not source evidence",
    }


def _ambient_next_step(
    state: CompactStatusState,
    ambient_stage: str,
    provider_installed: bool,
) -> tuple[str, str]:
    if state.prompt_latency_risk:
        return "inspect_prompt_hook_latency", "aippocampus hooks prompt status --last --json"
    if state.warm_stale_queue:
        return (
            "inspect_warm_queue_or_provider",
            str(state.warm_ambient_status.get("next_command") or "aippocampus warm status --json"),
        )
    if state.provider_degraded and provider_installed:
        return "inspect_provider", "aippocampus doctor provider --json"
    if state.action_hints_installed and not state.action_hints_ready:
        return "refresh_or_inspect_action_hints", state.action_hint_primary_command
    if ambient_stage == "useful":
        return "continue_with_ordinary_recall", ""
    return "inspect_operator_status", OPERATOR_STATUS_COMMAND


def build_compact_status_payload(
    report: dict[str, Any],
    *,
    schema_version: int,
    state: CompactStatusState,
    deferred_components: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    ambient_recall: dict[str, Any],
) -> dict[str, Any]:
    summary = state.summary
    readiness_state = (
        "partial_foreground_status"
        if state.foreground_partial or deferred_components
        else "ready"
        if bool(summary.get("core_ready")) and not state.needs_action
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
            **agent_readiness_public_fields(state),
            "plan_surface_filter": state.plan_surface_filter,
            "plan_scope": summary.get("plan_scope") or "all_surfaces",
            "partial_readiness": bool(deferred_components),
            "deferred_components": [item["id"] for item in deferred_components],
            "dirty_worktree_guards": summary.get("dirty_worktree_guards") or {},
            "ambient_recall_stage": ambient_recall["stage"],
            "needs_action": state.needs_action,
        },
        "setup_card": {
            "state": readiness_state,
            "usable_now": bool(report.get("ok", True)),
            "partial_readiness": bool(deferred_components),
            "deferred_count": len(deferred_components),
            "first_deferred_component": deferred_components[0]["id"] if deferred_components else None,
            "operator_detail_command": OPERATOR_STATUS_COMMAND,
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
        "operator_detail_available": True,
    }
    return redact_sensitive_values(redact_private_paths(compact_frontstage_projection(public)))


def build_compact_agent_status_report(
    report: dict[str, Any],
    *,
    schema_version: int,
) -> dict[str, Any]:
    state = normalize_status_surfaces(report)
    deferred_components = collect_operator_deferred_components(state)
    actions = collect_update_actions(report, state, deferred_components)
    ambient_recall = build_ambient_recall_status(state, deferred_components)
    return build_compact_status_payload(
        report,
        schema_version=schema_version,
        state=state,
        deferred_components=deferred_components,
        actions=actions,
        ambient_recall=ambient_recall,
    )
