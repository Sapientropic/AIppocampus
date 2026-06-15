"""Compact MCP tool-readiness projections for public CLI checks."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.mcp.tool_catalog import TOOLS

KEY_AGENT_NATIVE_TOOLS = ("agent_recall", "agent_aippo", "agent_deepen", "agent_explain")


def visible_tool_names() -> list[str]:
    return sorted(str(tool.get("name") or "") for tool in TOOLS if tool.get("name"))


def tool_names_summary() -> dict[str, Any]:
    names = visible_tool_names()
    return {"ok": True, "tool_count": len(names), "tool_names": names}


def tool_readiness_summary() -> dict[str, Any]:
    names = visible_tool_names()
    key_present = [name for name in KEY_AGENT_NATIVE_TOOLS if name in names]
    missing = [name for name in KEY_AGENT_NATIVE_TOOLS if name not in names]
    return {
        "kind": "aippocampus_mcp_tool_readiness",
        "ok": not missing,
        "tool_count": len(names),
        "agent_native_tools_present": not missing,
        "key_tools_present": key_present,
        "missing_key_tools": missing,
        "schema_available": True,
        "full_schema_command": "aippocampus mcp list-tools --json",
    }
