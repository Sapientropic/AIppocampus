"""Small action helpers for update-status summaries."""

from __future__ import annotations

from typing import Any

PLUGIN_CACHE_ACTION_STATUSES = {
    "missing",
    "missing_manifest",
    "stale_version",
    "stale_hash",
}


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


def plugin_cache_action_lines(plugin: dict[str, Any]) -> list[str]:
    if not plugin_cache_needs_action(plugin):
        return []
    actions = plugin.get("plugin_cache_recommended_actions") or []
    lines = ["  warn: configured plugin cache/marketplace is stale or missing"]
    if actions:
        lines.append("  next: " + str(actions[0]))
    return lines


def agent_callable_probe_lines(item: dict[str, Any]) -> list[str]:
    probe = item.get("host_live_probe") or {}
    if item.get("ready") and probe.get("ok"):
        return [f"  host probe: {probe.get('source')} ok"]
    if probe.get("ok"):
        lines = ["  host probe: ok; current foreground thread tool discovery is unverified"]
        if item.get("next_command"):
            lines.append("  next: " + str(item.get("next_command")))
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
    cards: list[dict[str, Any]] = []
    if bool(summary.get("agent_callable_host_ready")) and not bool(
        summary.get("agent_callable_current_thread_visible")
    ):
        cards.append(
            {
                "id": "current_thread_tool_discovery",
                "status": "host_ready_current_thread_unverified",
                "why": "The host probe passed, but this foreground thread has not proved it can see the AIppocampus tools.",
                "command": str(
                    agent.get("next_command")
                    or "reload Codex Desktop, then run `aippocampus update status --foreground-tools-visible --agent-json`"
                ),
            }
        )
    cache_refresh = plugin.get("cache_refresh") if isinstance(plugin, dict) else None
    if isinstance(cache_refresh, dict) and cache_refresh.get("auto_refresh_blocked"):
        reason = str(cache_refresh.get("blocked_reason") or "plugin_cache_auto_resolution_blocked")
        if cache_refresh.get("candidate_count"):
            reason = f"{reason}: {int(cache_refresh.get('candidate_count') or 0)} candidates"
        cards.append(
            {
                "id": "plugin_cache_recovery",
                "status": reason,
                "why": "The plugin package can be current while the installed Codex cache still needs a human-friendly refresh path.",
                "command": str(
                    cache_refresh.get("next_command")
                    or "aippocampus plugin install --codex --verify --compact-json"
                ),
            }
        )
    elif summary.get("plugin_cache_needs_action"):
        command = (
            (plugin.get("plugin_cache_recommended_actions") or [None])[0]
            or (summary.get("plugin_cache_recommended_actions") or [None])[0]
            or "aippocampus plugin install --codex --verify --compact-json"
        )
        cards.append(
            {
                "id": "plugin_cache_recovery",
                "status": "plugin_cache_needs_refresh",
                "why": "The local package is separate from the Codex plugin cache used by the host.",
                "command": str(command),
            }
        )
    if action_hints.get("installed") and action_hints.get("cache_status") != "with_fresh_records":
        cards.append(
            {
                "id": "action_hint_cache",
                "status": str(action_hints.get("cache_status") or "action_hints_cache_not_ready"),
                "why": "Action-time hints are optional PreToolUse nudges; refresh the prepared cache when you want them.",
                "command": str(
                    action_hints.get("next_command")
                    or "aippocampus hooks action refresh-cache --write --json"
                ),
            }
        )
    if not bool(summary.get("core_ready")) and summary.get("core_blockers"):
        blocker = str((summary.get("core_blockers") or ["skill"])[0])
        cards.append(
            {
                "id": "core_repair",
                "status": f"{blocker}_not_ready",
                "why": "Fix the first core surface before chasing optional plugin or hook polish.",
                "command": f"aippocampus update apply --surface {blocker}",
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
            "surface": "agent_callable",
            "reason": (
                "local plugin or hook files changed; the host may need a reload "
                "before the current foreground thread can see updated tools"
            ),
            "command": (
                "reload Codex Desktop, then run "
                "`aippocampus update status --foreground-tools-visible --agent-json` "
                "from a thread that can see AIppocampus tools"
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
