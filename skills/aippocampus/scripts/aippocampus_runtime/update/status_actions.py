"""Small action helpers for update-status summaries."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import command_value_needs_input

PLUGIN_CACHE_ACTION_STATUSES = {
    "missing",
    "missing_manifest",
    "stale_version",
    "stale_hash",
}
PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND = "aippocampus plugin install --codex --verify --compact-json"


def plugin_cache_needs_action(plugin: dict[str, Any]) -> bool:
    """Return whether plugin cache repair is actionable enough for top summary.

    A repo-local plugin package can be current while a configured or
    auto-detected Codex installed cache is stale. Keep that as top-level action
    so agents do not have to spelunk nested JSON. Plain ``not_configured``
    optional cache state stays quiet unless a real cache path exists.
    """

    for layer_name in ("local_marketplace", "installed_cache"):
        layer = plugin.get(layer_name) or {}
        status = str(layer.get("status") or "")
        if status in PLUGIN_CACHE_ACTION_STATUSES and layer.get("root_path"):
            return True
    return False


def unique_names(names: list[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        if name and name not in result:
            result.append(name)
    return result


def plan_surface_filter(mode: str, values: list[Any] | None) -> list[str]:
    return unique_names([str(item) for item in values or []]) if mode == "plan" else []


def filter_plan_surface_groups(
    plan_filter: list[str],
    actionable: list[str],
    core_blockers: list[str],
    magic_blockers: list[str],
    optional_surfaces: list[str],
    operator_blockers: list[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    if not plan_filter:
        return actionable, core_blockers, magic_blockers, optional_surfaces, operator_blockers
    filter_set = set(plan_filter)
    keep = lambda names: [name for name in names if name in filter_set]
    return (
        [name for name in actionable if name in filter_set or (name == "plugin_cache" and "plugin" in filter_set)],
        keep(core_blockers),
        keep(magic_blockers),
        keep(optional_surfaces),
        keep(operator_blockers),
    )


def render_surface_names(mode: str, summary: dict[str, Any]) -> tuple[str, ...] | list[str]:
    if mode == "plan" and summary.get("plan_surface_filter"):
        return list(summary.get("plan_surface_filter") or [])
    return ("skill", "hooks", "llm", "cli", "mcp", "plugin", "agent_callable")


def plugin_cache_action_lines(plugin: dict[str, Any]) -> list[str]:
    if not plugin_cache_needs_action(plugin):
        return []
    actions = plugin.get("plugin_cache_recommended_actions") or []
    lines = ["  warn: configured plugin cache/marketplace is stale or missing"]
    if actions:
        lines.append("  next: " + str(actions[0]))
    return lines


def action_hint_recommended_actions() -> list[dict[str, str]]:
    """Executable action-time hint setup choices for trusted Codex installs.

    Action hints remain fail-open route guidance, not source evidence and not a
    recall blocker. The setup itself is still recommended for trusted Codex
    environments so a successful prompt/lifecycle install is not misread as the
    whole foreground experience.
    """

    return [
        {
            "id": "refresh_action_hints",
            "label": "Refresh action-hint cache",
            "why": "A fresh cache keeps action-time route hints useful without making them source evidence.",
            "command": "aippocampus hooks action refresh-cache --write --json",
            "mutation_risk": "explicit_local_cache_write",
            "claim_boundary": "action_hints_are_navigation_not_source_evidence",
        },
        {
            "id": "install_action_hints",
            "label": "Install action-time hints",
            "why": "Trusted Codex sessions can use action hints as fail-open navigation for common foreground moves.",
            "command": "aippocampus hooks action install --json",
            "mutation_risk": "writes_local_hooks_config",
            "claim_boundary": "action_hints_are_navigation_not_source_evidence",
        },
        {
            "id": "rollback_action_hints",
            "label": "Rollback action-time hints",
            "why": "Rollback removes local hook hints when they are stale, unwanted, or causing foreground friction.",
            "command": "aippocampus hooks action uninstall --json",
            "mutation_risk": "writes_local_hooks_config",
            "claim_boundary": "action_hints_are_navigation_not_source_evidence",
        },
    ]


def action_hint_status_command() -> str:
    return "aippocampus hooks action status --json"


def _extract_command_template(value: str) -> str:
    if "`" in value:
        parts = value.split("`")
        if len(parts) >= 3 and parts[1].strip():
            return parts[1].strip()
    text = value.strip()
    if text.casefold().startswith("run "):
        text = text[4:].strip()
    return text


def _requires_for_command_template(template: str) -> list[str]:
    lowered = template.casefold()
    requires: list[str] = []
    if "<path>" in lowered:
        requires.append("local_path")
    if "--plugin-marketplace-dir" in lowered:
        requires.append("plugin_marketplace_dir")
    if "--plugin-installed-dir" in lowered:
        requires.append("plugin_installed_dir")
    return requires or ["operator_input"]


def executable_update_action_fields(
    command: Any,
    *,
    fallback_command: str | None = None,
    manual_instruction: str | None = None,
) -> dict[str, Any]:
    raw = str(command or "").strip()
    if not raw:
        return {}
    if not command_value_needs_input(raw):
        result: dict[str, Any] = {"command": raw}
        if manual_instruction:
            result["manual_instruction"] = manual_instruction
        return result
    template = _extract_command_template(raw)
    result = {
        "command_template": template,
        "requires": _requires_for_command_template(template),
        "template_only": fallback_command is None,
        "manual_instruction": manual_instruction or raw,
    }
    if fallback_command:
        result["command"] = fallback_command
        result["template_only"] = False
    return result


def _shellish_command(command: Any) -> str | None:
    text = str(command or "").strip()
    if not text:
        return None
    if text.startswith(("aippocampus ", "python ", "python3 ", "uvx ")):
        return text
    return None


def agent_callable_foreground_action(item: dict[str, Any]) -> dict[str, str]:
    """Split foreground-tool verification prose from executable shell commands."""

    status = str(item.get("status") or "")
    raw_next = str(item.get("next_command") or "")
    if status in {
        "host_live_probe_ok_foreground_probe_not_checked",
        "host_live_probe_ok_current_thread_unverified",
        "host_registered_tools_unverified",
    }:
        return {
            "command": (
                "aippocampus update status --foreground-tools-visible "
                "--agent-json"
            ),
            "manual_instruction": (
                "First call agent_recall and agent_deepen in this foreground thread. "
                "--foreground-key-tools-callable is only a caller assertion; if a key "
                "tool fails, rerun status with --foreground-key-tool-failure "
                "\"brief sanitized error\"."
            ),
        }
    if status == "foreground_mcp_runtime_mismatch":
        return {
            "command": 'aippocampus agent recall "old decision or handoff cue" --json',
            "manual_instruction": (
                "Reload Codex Desktop or restart the MCP transport before trusting "
                "foreground tools; use the CLI fallback when the foreground tool call fails."
            ),
        }
    if status == "host_live_probe_key_tools_failed":
        return {
            "command": "aippocampus plugin install --codex --verify",
            "manual_instruction": (
                "Reload Codex Desktop or restart the MCP host after the plugin verify step."
            ),
        }
    shell = _shellish_command(raw_next)
    if shell:
        return {"command": shell}
    return {
        "command": "aippocampus update status --json",
        "manual_instruction": raw_next or "Check foreground tool visibility before claiming agent-callable readiness.",
    }


def agent_callable_probe_lines(item: dict[str, Any]) -> list[str]:
    probe = item.get("host_live_probe") or {}
    if item.get("status") == "foreground_mcp_runtime_mismatch":
        lines = ["  warn: current foreground MCP connection failed key agent-native tools"]
        action = agent_callable_foreground_action(item)
        if action.get("manual_instruction"):
            lines.append("  note: " + action["manual_instruction"])
        lines.append("  next: " + action["command"])
        return lines
    if item.get("ready") and probe.get("ok"):
        return [f"  host probe: {probe.get('source')} ok"]
    if probe.get("ok"):
        if item.get("foreground_probe_state") == "not_requested":
            lines = [
                "  host probe: ok; foreground tool discovery was not checked in this status call"
            ]
        else:
            lines = ["  host probe: ok; current foreground thread tool discovery is unverified"]
        action = agent_callable_foreground_action(item)
        if action.get("manual_instruction"):
            lines.append("  note: " + action["manual_instruction"])
        lines.append("  next: " + action["command"])
        return lines
    if not item.get("ready"):
        return ["  warn: foreground host tool visibility is not confirmed"]
    return []


def foreground_status_cards(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the small user/agent-facing next cards for update status.

    These cards deliberately sit above the package/operator surface inventory.
    A current plugin package, a host probe, and current-thread tool visibility
    are three different states; flattening them into one ``needs_action`` list
    is what made the update flow feel stuck after successful installs.
    """

    summary = report.get("summary") or report.get("post_status") or {}
    surfaces = report.get("surfaces") or {}
    plugin = surfaces.get("plugin") or {}
    hooks = surfaces.get("hooks") or {}
    agent = surfaces.get("agent_callable") or {}
    action_hints = hooks.get("action_hints") if isinstance(hooks, dict) else {}
    if not isinstance(action_hints, dict):
        action_hints = {}
    foreground_partial = bool(
        summary.get("partial_readiness") or summary.get("plan_scope") == "foreground_partial"
    )
    cards: list[dict[str, Any]] = []
    partial_readiness_card: dict[str, Any] | None = None
    if foreground_partial:
        partial_readiness_card = {
            "id": "partial_readiness",
            "label": "Open full update readiness",
            "status": "slow_checks_deferred",
            "why": "Foreground status skipped operator freshness sweeps and should not be treated as release-grade readiness.",
            "command": "aippocampus update status --operator-json",
            "deferred_components": summary.get("deferred_components") or [],
            "mutation_risk": "read_only",
            "claim_boundary": "update_status_not_source_evidence",
        }
    if bool(summary.get("agent_callable_host_ready")) and not bool(
        summary.get("agent_callable_ready")
    ):
        stale = agent.get("status") == "foreground_mcp_runtime_mismatch"
        not_checked = agent.get("foreground_probe_state") == "not_requested"
        action = agent_callable_foreground_action(agent)
        cards.append(
            {
                "id": "current_thread_tool_discovery",
                "label": "Verify current-thread tools",
                "status": (
                    "foreground_mcp_runtime_mismatch"
                    if stale
                    else "host_ready_foreground_probe_not_checked"
                    if not_checked
                    else "host_ready_current_thread_unverified"
                ),
                "why": (
                    "The host probe passed, but this status call did not check whether the foreground thread can see or call AIppocampus tools."
                    if not_checked
                    else "The host probe passed, but this foreground thread has not proved it can see and call the AIppocampus tools."
                ),
                "command": action["command"],
                "mutation_risk": "read_only",
                "claim_boundary": "current_thread_tool_probe_not_source_evidence",
                **(
                    {"manual_instruction": action["manual_instruction"]}
                    if action.get("manual_instruction")
                    else {}
                ),
            }
        )
    if partial_readiness_card:
        cards.append(partial_readiness_card)
    cache_refresh = plugin.get("cache_refresh") if isinstance(plugin, dict) else None
    if isinstance(cache_refresh, dict) and cache_refresh.get("auto_refresh_blocked"):
        reason = str(cache_refresh.get("blocked_reason") or "plugin_cache_auto_resolution_blocked")
        if cache_refresh.get("candidate_count"):
            reason = f"{reason}: {int(cache_refresh.get('candidate_count') or 0)} candidates"
        command_fields = executable_update_action_fields(
            cache_refresh.get("next_command") or PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND,
            fallback_command=PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND,
            manual_instruction=(
                "If the ordinary Codex refresh is not the intended cache, use the template "
                "with an explicit local plugin cache path."
            ),
        )
        cards.append(
            {
                "id": "plugin_cache_recovery",
                "label": "Recover Codex plugin cache",
                "status": reason,
                "why": "The plugin package can be current while the installed Codex cache still needs a human-friendly refresh path.",
                "mutation_risk": "writes_local_plugin_cache",
                "claim_boundary": "update_status_not_source_evidence",
                **command_fields,
            }
        )
    elif summary.get("plugin_cache_needs_action"):
        action_card = (plugin.get("recommended_action_cards") or [None])[0]
        plugin_command_fields: dict[str, Any]
        if isinstance(action_card, dict):
            plugin_command_fields = {
                key: value
                for key, value in action_card.items()
                if key
                in {
                    "command",
                    "command_template",
                    "requires",
                    "template_only",
                    "manual_instruction",
                }
            }
        else:
            command = (
                (plugin.get("plugin_cache_recommended_actions") or [None])[0]
                or (summary.get("plugin_cache_recommended_actions") or [None])[0]
                or PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND
            )
            plugin_command_fields = executable_update_action_fields(
                command,
                fallback_command=PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND,
                manual_instruction=(
                    "Use the ordinary Codex plugin refresh unless a custom marketplace/cache path "
                    "is intentionally being repaired."
                ),
            )
        cards.append(
            {
                "id": "plugin_cache_recovery",
                "label": "Refresh Codex plugin cache",
                "status": "plugin_cache_needs_refresh",
                "why": "The local package is separate from the Codex plugin cache used by the host.",
                "mutation_risk": "writes_local_plugin_cache",
                "claim_boundary": "update_status_not_source_evidence",
                **plugin_command_fields,
            }
        )
    action_hints_useful = bool(action_hints.get("useful"))
    if not action_hints_useful and not foreground_partial:
        installed = bool(action_hints.get("installed"))
        raw_foreground_action = action_hints.get("foreground_action")
        foreground_action = (
            raw_foreground_action if isinstance(raw_foreground_action, dict) else {}
        )
        cards.append(
            {
                "id": "action_hint_cache" if installed else "action_hint_setup",
                "label": "Review action-time hints",
                "status": str(
                    action_hints.get("cache_status")
                    or ("action_hints_cache_not_ready" if installed else "not_installed")
                ),
                "why": (
                    "Action-time hints are recommended setup for trusted Codex sessions, but remain fail-open navigation hints rather than source evidence or a recall blocker."
                ),
                "command": str(
                    foreground_action.get("command")
                    or action_hints.get("next_command")
                    or action_hint_status_command()
                ),
                "mutation_risk": str(
                    foreground_action.get("mutation_risk") or "read_only"
                ),
                "claim_boundary": "action_hints_are_navigation_not_source_evidence",
                "recommended_next_actions": action_hint_recommended_actions(),
            }
        )
    if (
        not foreground_partial
        and not bool(summary.get("core_ready"))
        and summary.get("core_blockers")
    ):
        blocker = str((summary.get("core_blockers") or ["skill"])[0])
        dirty_guards = summary.get("dirty_worktree_guards") or {}
        dirty_guard = dirty_guards.get(blocker) if isinstance(dirty_guards, dict) else None
        if isinstance(dirty_guard, dict):
            safe_next_actions = list(dirty_guard.get("safe_next_actions") or [])
            cards.append(
                {
                    "id": "core_repair",
                    "label": "Inspect dirty worktree before repair",
                    "status": "blocked_dirty_worktree",
                    "why": (
                        "The first core repair would write across a dirty git worktree; inspect or plan before applying."
                    ),
                    "command": (
                        str(safe_next_actions[0].get("command"))
                        if safe_next_actions and isinstance(safe_next_actions[0], dict)
                        else "git status --short"
                    ),
                    "blocked_command": f"aippocampus update apply --surface {blocker}",
                    "dirty_worktree_detected": True,
                    "dirty_paths": list(dirty_guard.get("dirty_paths") or []),
                    "would_write": dirty_guard.get("would_write") or {},
                    "safe_next_actions": safe_next_actions,
                    "override": dirty_guard.get("override"),
                    "mutation_risk": "read_only",
                    "claim_boundary": "update_status_not_source_evidence",
                }
            )
        else:
            cards.append(
                {
                    "id": "core_repair",
                    "label": "Repair core update surface",
                    "status": f"{blocker}_not_ready",
                    "why": "Fix the first core surface before chasing optional plugin or hook polish.",
                    "command": f"aippocampus update apply --surface {blocker}",
                    "mutation_risk": "writes_local_install_surface",
                    "claim_boundary": "update_status_not_source_evidence",
                }
            )
    return cards[:4]


def foreground_status_lines(report: dict[str, Any]) -> list[str]:
    cards = foreground_status_cards(report)
    if not cards:
        return ["- Frontstage next: nothing blocking the ordinary first-recall path."]
    lines = ["- Frontstage next:"]
    for card in cards[:3]:
        lines.append(f"  {card.get('id')}: {card.get('status')}")
        if card.get("command"):
            lines.append(f"  next: {card.get('command')}")
    return lines


def post_apply_next_actions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    applied_names = {
        str(item.get("surface") or "")
        for item in results
        if item.get("applied") and item.get("ok")
    }
    if not ({"plugin", "hooks"} & applied_names):
        return []
    return [
        {
            "id": "review_agent_callable_after_apply",
            "label": "Verify foreground tools after apply",
            "surface": "agent_callable",
            "reason": (
                "local plugin or hook files changed; the host may need a reload "
                "before the current foreground thread can see updated tools"
            ),
            "why": (
                "Local plugin or hook files changed; the current foreground thread should prove tool visibility again before claiming agent-callable readiness."
            ),
            "command": (
                "aippocampus update status --foreground-tools-visible "
                "--agent-json"
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "current_thread_tool_probe_not_source_evidence",
            "manual_instruction": (
                "Reload Codex Desktop after local plugin or hook files change, then call "
                "agent_recall and agent_deepen in the foreground thread before rerunning status. "
                "--foreground-key-tools-callable is only a caller assertion and does not certify "
                "the current MCP transport."
            ),
        }
    ]


def apply_next_action_lines(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for action in report.get("next_actions") or []:
        if not isinstance(action, dict):
            continue
        command = action.get("command")
        if command:
            lines.append(f"- Next: {command}")
    return lines
