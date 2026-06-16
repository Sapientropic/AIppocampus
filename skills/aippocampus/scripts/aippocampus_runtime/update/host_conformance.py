"""Host-agnostic continuity conformance projection.

This is a status/readout layer, not a new install surface. It keeps host labels
comparable across Codex, Claude Code, generic MCP, and CLI-only workflows without
turning any one host integration into a universal continuity claim.
"""

from __future__ import annotations

from typing import Any

CONFORMANCE_LABELS = (
    "unavailable",
    "cli_only",
    "recall_only",
    "recall_deepen",
    "ambient_recall_deepen",
    "full_continuity_path",
)


def _tool_names(agent: dict[str, Any]) -> set[str]:
    return {str(item) for item in agent.get("host_probe_agent_native_tools") or []}


def build_host_conformance_status(surfaces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cli = surfaces.get("cli") or {}
    hooks = surfaces.get("hooks") or {}
    agent = surfaces.get("agent_callable") or {}
    tools = _tool_names(agent)
    cli_available = bool(
        cli.get("console_script_available_on_path") or cli.get("module_entrypoint_available")
    )
    recall_callable = bool(agent.get("ready")) and "agent_recall" in tools
    deepen_callable = bool(agent.get("ready")) and "agent_deepen" in tools
    ambient_hints = hooks.get("status") == "current" and bool(hooks.get("action_hints_installed"))
    live_schema_fresh = agent.get("live_host_schema_stale") is not True
    first_magic_path = bool(recall_callable and deepen_callable and live_schema_fresh)

    if recall_callable and deepen_callable and ambient_hints:
        label = "ambient_recall_deepen"
    elif recall_callable and deepen_callable:
        label = "recall_deepen"
    elif recall_callable:
        label = "recall_only"
    elif cli_available:
        label = "cli_only"
    else:
        label = "unavailable"

    if (
        label == "ambient_recall_deepen"
        and hooks.get("lifecycle_installed")
        and first_magic_path
        and bool(agent.get("foreground_tools_visible"))
    ):
        label = "full_continuity_path"

    return {
        "surface": "host_conformance",
        "status": "current",
        "label": label,
        "labels": list(CONFORMANCE_LABELS),
        "dimensions": {
            "discoverable": cli_available or bool(agent.get("host_plugin_installed_or_enabled")),
            "recall_callable": recall_callable,
            "deepen_callable": deepen_callable,
            "ambient_hints_available": ambient_hints,
            "current_thread_visible": agent.get("foreground_tools_visible") is True,
            "live_schema_fresh": live_schema_fresh,
            "foreground_redaction_boundary": True,
            "cli_manual_fallback": cli_available,
            "first_magic_moment_path": first_magic_path,
        },
        "next_action": agent.get("next_command")
        if agent.get("live_host_schema_stale")
        else "aippocampus update status --agent-json",
        "claim_boundary": (
            "Conformance labels describe the current host affordance shape; they do "
            "not prove recall quality, all-client support, or source truth without reopen."
        ),
    }


__all__ = ["CONFORMANCE_LABELS", "build_host_conformance_status"]
