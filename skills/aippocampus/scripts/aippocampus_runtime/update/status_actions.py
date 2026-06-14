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
