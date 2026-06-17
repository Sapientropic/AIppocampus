"""Compact MCP tool-readiness projections for public CLI checks."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.mcp.tool_catalog import TOOLS

KEY_AGENT_NATIVE_TOOLS = (
    "agent_recall",
    "agent_aippo",
    "agent_background",
    "agent_deepen",
    "agent_explain",
)


def visible_tool_names() -> list[str]:
    return sorted(str(tool.get("name") or "") for tool in TOOLS if tool.get("name"))


def tool_names_summary() -> dict[str, Any]:
    names = visible_tool_names()
    return {"ok": True, "tool_count": len(names), "tool_names": names}


def tool_readiness_summary() -> dict[str, Any]:
    names = visible_tool_names()
    key_present = [name for name in KEY_AGENT_NATIVE_TOOLS if name in names]
    missing = [name for name in KEY_AGENT_NATIVE_TOOLS if name not in names]
    payload: dict[str, Any] = {
        "kind": "aippocampus_mcp_tool_readiness",
        "ok": not missing,
        "tool_count": len(names),
        "agent_native_tools_present": not missing,
        "key_tools_present": key_present,
        "missing_key_tools": missing,
        "schema_available": True,
        "full_schema_command": "aippocampus mcp list-tools --json",
    }
    if missing:
        primary = foreground_shell_action(
            action_id="repair_mcp_tool_catalog",
            command="aippocampus plugin install --codex --verify --json",
            label="Repair Codex plugin MCP wiring",
            why="Key agent-native MCP tools are missing; reinstall or verify the local Codex plugin wiring.",
            mutation_risk="writes_local_plugin_cache",
            claim_boundary="install_status_not_memory_evidence",
        )
        status = foreground_shell_action(
            action_id="inspect_mcp_status_after_repair",
            command="aippocampus mcp status",
            label="Recheck MCP tool readiness",
            why="Use after repair to confirm key agent-native tools are visible.",
            mutation_risk="read_only",
            claim_boundary="tool_visibility_not_memory_evidence",
        )
        payload.update(canonical_foreground_action_fields(primary, safe_next_actions=[primary, status]))
    return payload
