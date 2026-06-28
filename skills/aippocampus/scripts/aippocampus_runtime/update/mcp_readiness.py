"""Read-only MCP host readiness projection for the update frontdoor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.update.agent_callable import (
    command_availability,
    mcp_command_repair_options,
)

OLD_MCP_SCRIPT_NAMES = ("aippocampus_mcp_server.py",)
CURRENT_MCP_MARKERS = ("aippocampus_runtime.mcp.server", "aippocampus mcp")


def status_mcp(repo_root: Path, mcp_config: Path | None = None) -> dict[str, Any]:
    path = mcp_config or repo_root / "plugins" / "aippocampus" / ".mcp.json"
    if not path.exists():
        return {
            "surface": "mcp",
            "status": "missing",
            "source_path": str(path),
            "target_path": str(path),
            "stale_flat_script": False,
            "manual_review_needed": True,
            "safety_notes": ["MCP config is inspected read-only; apply does not rewrite host configs"],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "surface": "mcp",
            "status": "invalid",
            "source_path": str(path),
            "target_path": str(path),
            "error": str(exc),
            "manual_review_needed": True,
            "safety_notes": ["MCP config parse failed; no mutation attempted"],
        }
    server = ((data.get("mcpServers") or {}).get("aippocampus") or {}) if isinstance(data, dict) else {}
    serialized = json.dumps(server, ensure_ascii=False)
    command = str(server.get("command") or "")
    args = [str(item) for item in server.get("args") or []]
    stale = any(name in serialized for name in OLD_MCP_SCRIPT_NAMES)
    current = any(marker in serialized for marker in CURRENT_MCP_MARKERS) or (
        command == "aippocampus" and args[:1] == ["mcp"]
    )
    if stale:
        status = "stale"
    elif current:
        status = "current"
    else:
        status = "detect_only"
    availability = command_availability(command)
    repair_options = mcp_command_repair_options(command)
    return {
        "surface": "mcp",
        "status": status,
        "package_artifact_current": status == "current",
        "source_path": str(path),
        "target_path": str(path),
        "stale_flat_script": stale,
        "current_module_entrypoint": current,
        "manual_review_needed": status != "current",
        "server_command_present": bool(server),
        "mcp_command": command or None,
        "mcp_args": args,
        "mcp_command_resolves": availability["resolves"],
        "mcp_command_resolved_path": availability["resolved_path"],
        "mcp_command_uses_ambiguous_python": Path(command).name.casefold()
        in {"python", "python.exe"},
        "mcp_command_uses_console_script": command == "aippocampus",
        "python_available": availability["python_available"],
        "python3_available": availability["python3_available"],
        "aippocampus_console_script_available": availability["console_script_available"],
        "mcp_command_repair_options": repair_options if not availability["resolves"] else [],
        "recommended_actions": [
            "put the aippocampus console script on PATH, or register one of mcp_command_repair_options in the host"
        ]
        if not availability["resolves"]
        else [],
        "portable_module_command": f"{Path(sys.executable).name} -m aippocampus_runtime.mcp.server",
        "safety_notes": [
            "MCP package artifacts are not the same as foreground host tool visibility",
            "MCP host/user config is preserved; update reports stale commands instead of rewriting it",
        ],
    }


__all__ = ["status_mcp"]
