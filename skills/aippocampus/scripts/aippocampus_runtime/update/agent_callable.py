"""Foreground agent-callable readiness diagnostics for the update facade."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

PLUGIN_SECTION_RE = re.compile(r'^\s*\[plugins\."([^"]+)"\]\s*$')
MCP_SECTION_RE = re.compile(r'^\s*\[(?:mcp_servers|mcpServers)\."?([^"\]]+)"?\]\s*$')
HOST_PROBE_REPORT_RELATIVE = Path("aippocampus") / "host-probe" / "codex-plugin-install.json"
AGENT_NATIVE_TOOL_NAMES = {
    "agent_recall",
    "agent_aippo",
    "agent_deepen",
    "agent_explain",
}
KEY_AGENT_TOOL_NAMES = {"agent_recall", "agent_aippo"}


def default_host_probe_report_path(codex_home_path: Path) -> Path:
    return codex_home_path / HOST_PROBE_REPORT_RELATIVE


def write_host_probe_report(codex_home_path: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {"status": "not_written", "reason": "no_probe_payload"}
    path = default_host_probe_report_path(codex_home_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "written",
        "source": "plugin_install_verify",
        "default_for": "aippocampus update status --json",
    }


def command_availability(command: str) -> dict[str, Any]:
    resolved_path = None
    if command:
        command_path = Path(command)
        if command_path.is_absolute():
            resolved_path = str(command_path) if command_path.exists() else None
        else:
            resolved_path = shutil.which(command)
    return {
        "resolves": bool(resolved_path),
        "resolved_path": resolved_path,
        "python_available": shutil.which("python") is not None,
        "python3_available": shutil.which("python3") is not None,
        "console_script_available": shutil.which("aippocampus") is not None,
    }


def mcp_command_repair_options(command: str) -> list[str]:
    """Return host-facing MCP repair options without treating fallbacks as readiness.

    The packaged plugin should prefer the console script (`aippocampus mcp`).
    If a host lacks that script but has Python module access, this diagnostic
    gives the operator a concrete repair path instead of silently treating a
    stale or missing command as agent-callable readiness.
    """

    options: list[str] = []
    if shutil.which("aippocampus"):
        options.append("aippocampus mcp")
    current_executable = str(Path(sys.executable))
    if " " in current_executable:
        current_executable = f'"{current_executable}"'
    options.append(f"{current_executable} -m aippocampus_runtime.cli.facade mcp")
    if shutil.which("python3"):
        options.append("python3 -m aippocampus_runtime.cli.facade mcp")
    if shutil.which("python"):
        options.append("python -m aippocampus_runtime.cli.facade mcp")
    options.append("uvx aippocampus mcp")
    seen: set[str] = set()
    unique: list[str] = []
    for option in options:
        if option == f"{command} mcp" or option in seen:
            continue
        seen.add(option)
        unique.append(option)
    return unique


def load_json_file(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "invalid_probe_report",
            "ok": False,
            "source": "host_probe_report",
        }
    return value if isinstance(value, dict) else None


def _read_config_text(codex_home_path: Path) -> str:
    config_path = codex_home_path / "config.toml"
    if not config_path.exists():
        return ""
    try:
        return config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _configured_plugin_ids(config_text: str) -> list[str]:
    ids: list[str] = []
    for line in config_text.splitlines():
        match = PLUGIN_SECTION_RE.match(line)
        if match:
            ids.append(match.group(1))
    return ids


def _configured_mcp_server_ids(config_text: str) -> list[str]:
    ids: list[str] = []
    for line in config_text.splitlines():
        match = MCP_SECTION_RE.match(line)
        if match:
            ids.append(match.group(1))
    return ids


def _host_probe_status(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "status": "not_provided",
            "ok": False,
            "source": "not_provided",
            "tool_names": [],
            "tool_call_ok": False,
        }

    codex_tool_names = [
        str(item)
        for item in ((payload.get("mcp_status") or {}).get("tool_names") or [])
    ]
    codex_tool_call_ok = (
        payload.get("mcp_tool_is_error") is False
        and isinstance(payload.get("mcp_tool_payload"), dict)
        and bool(payload.get("mcp_tool_payload"))
    )
    raw_key_smokes = payload.get("key_tool_smokes") or []
    key_tool_smokes = [
        redact_sensitive_values(redact_private_paths(item))
        for item in raw_key_smokes
        if isinstance(item, dict)
    ]
    key_tool_failures = [
        {
            "tool": str(item.get("tool") or "key_tool"),
            "error_code": item.get("error_code"),
            "error_message": item.get("error_message"),
        }
        for item in key_tool_smokes
        if not item.get("ok")
    ]
    key_tools_callable = None
    if key_tool_smokes:
        key_tools_callable = not key_tool_failures
    if key_tool_failures:
        return {
            "status": "key_tool_smoke_failed",
            "ok": False,
            "source": "codex_app_server_smoke",
            "tool_names": sorted(codex_tool_names),
            "tool_call_ok": codex_tool_call_ok,
            "key_tool_smokes": key_tool_smokes,
            "key_tools_callable": False,
            "key_tool_failures": key_tool_failures,
        }
    if bool(payload.get("validation_ok")) and codex_tool_call_ok:
        return {
            "status": "ok",
            "ok": True,
            "source": "codex_app_server_smoke",
            "tool_names": sorted(codex_tool_names),
            "tool_call_ok": True,
            "key_tool_smokes": key_tool_smokes,
            "key_tools_callable": key_tools_callable,
        }

    raw_tool_call = payload.get("tool_call")
    tool_call: dict[str, Any] = raw_tool_call if isinstance(raw_tool_call, dict) else {}
    claude_tool_call_ok = (
        bool(tool_call.get("ok"))
        and str(tool_call.get("status")) == "called_memory_health"
    )
    if claude_tool_call_ok or str(payload.get("status")) == "tool_call_reachable":
        return {
            "status": "ok",
            "ok": True,
            "source": "claude_code_host_tool_call_smoke",
            "tool_names": [str(tool_call.get("tool_name") or "memory_health")],
            "tool_call_ok": True,
            "key_tool_smokes": [],
            "key_tools_callable": None,
        }

    raw_diagnostic = payload.get("persistent_config_diagnostic")
    diagnostic: dict[str, Any] = raw_diagnostic if isinstance(raw_diagnostic, dict) else {}
    if bool(diagnostic.get("ok")) and diagnostic.get("status") == "healthy":
        raw_detail = diagnostic.get("detail")
        detail: dict[str, Any] = raw_detail if isinstance(raw_detail, dict) else {}
        return {
            "status": "ok",
            "ok": True,
            "source": "claude_code_persistent_mcp_diagnostic",
            "tool_names": ["memory_health"] if detail.get("memory_health_listed") else [],
            "tool_call_ok": detail.get("tool_is_error") is False,
            "key_tool_smokes": [],
            "key_tools_callable": None,
        }

    return {
        "status": str(payload.get("status") or "probe_not_successful"),
        "ok": False,
        "source": "host_probe_report",
        "tool_names": sorted(codex_tool_names),
        "tool_call_ok": False,
        "key_tool_smokes": key_tool_smokes,
        "key_tools_callable": key_tools_callable,
    }


def status_agent_callable(
    codex_home_path: Path,
    surfaces: dict[str, dict[str, Any]],
    *,
    host_probe: dict[str, Any] | None = None,
    foreground_tools_visible_asserted: bool = False,
) -> dict[str, Any]:
    config_text = _read_config_text(codex_home_path)
    plugin_ids = _configured_plugin_ids(config_text)
    mcp_ids = _configured_mcp_server_ids(config_text)
    host_plugin_installed = any("aippocampus" in item.casefold() for item in plugin_ids)
    host_mcp_registered = any("aippocampus" == item.casefold() for item in mcp_ids)
    host_probe_status = _host_probe_status(host_probe)
    foreground_override = os.environ.get("AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE")
    foreground_tools_visible: bool | None
    if foreground_tools_visible_asserted:
        foreground_tools_visible = True
    elif foreground_override in {"1", "true", "TRUE", "yes"}:
        foreground_tools_visible = True
    elif host_plugin_installed or host_mcp_registered:
        foreground_tools_visible = None
    elif host_probe_status.get("ok") is True:
        foreground_tools_visible = None
    else:
        foreground_tools_visible = False

    cli = surfaces.get("cli") or {}
    mcp = surfaces.get("mcp") or {}
    plugin = surfaces.get("plugin") or {}
    package_artifact_current = bool(
        mcp.get("package_artifact_current") or plugin.get("package_artifact_current")
    )
    key_tools_callable = host_probe_status.get("key_tools_callable")
    key_tool_failed = key_tools_callable is False
    ready = foreground_tools_visible is True and not key_tool_failed
    host_probe_tool_names = {
        str(item) for item in host_probe_status.get("tool_names") or []
    }
    agent_native_tools_in_host_probe = sorted(host_probe_tool_names & AGENT_NATIVE_TOOL_NAMES)
    missing_agent_native_tools = sorted(AGENT_NATIVE_TOOL_NAMES - host_probe_tool_names)
    current_thread_discovery = (
        "tools_visible_but_key_tools_failed"
        if key_tool_failed
        else
        "verified_by_operator_override"
        if ready
        else "unknown_or_stale"
        if host_probe_status.get("ok") is True or host_plugin_installed or host_mcp_registered
        else "not_configured"
    )
    if key_tool_failed:
        status = "host_live_probe_key_tools_failed"
    elif host_probe_status.get("ok") is True and not ready:
        status = "host_live_probe_ok_current_thread_unverified"
    elif host_probe_status.get("ok") is True and ready:
        status = "host_live_probe_ok_current_thread_verified"
    elif ready:
        status = "ready"
    elif host_plugin_installed or host_mcp_registered:
        status = "host_registered_tools_unverified"
    elif package_artifact_current:
        status = "artifact_current_host_not_exposed"
    else:
        status = "host_not_exposed"

    next_command = "aippocampus update status --json"
    if key_tool_failed:
        next_command = "reload Codex Desktop/plugin tools or restart the MCP host, then rerun aippocampus plugin install --codex --verify"
    elif host_probe_status.get("ok") is True and not ready:
        next_command = "reload Codex Desktop or refresh plugin tools if agent-native tools are missing"
    elif host_probe_status.get("ok") is True:
        next_command = "aippocampus update status --json"
    elif not cli.get("console_script_available_on_path") and cli.get("module_entrypoint_available"):
        next_command = f"{Path(sys.executable).name} -m aippocampus_runtime.cli.facade agent recall"
    elif not host_plugin_installed and not host_mcp_registered:
        next_command = "enable the AIppocampus plugin/MCP in the active agent host"

    return {
        "surface": "agent_callable",
        "status": status,
        "ready": ready,
        "package_artifact_current": package_artifact_current,
        "console_script_available_on_path": bool(cli.get("console_script_available_on_path")),
        "host_plugin_installed_or_enabled": host_plugin_installed,
        "host_mcp_registered": host_mcp_registered,
        "mcp_command_resolves": bool(mcp.get("mcp_command_resolves")),
        "host_live_probe": host_probe_status,
        "host_probe_tool_count": len(host_probe_tool_names),
        "host_probe_agent_native_tools": agent_native_tools_in_host_probe,
        "host_probe_missing_agent_native_tools": missing_agent_native_tools,
        "tools_visible": foreground_tools_visible,
        "key_tools_callable": key_tools_callable,
        "key_tool_smokes": host_probe_status.get("key_tool_smokes") or [],
        "key_tool_failures": host_probe_status.get("key_tool_failures") or [],
        "live_host_schema_stale": key_tool_failed,
        "foreground_tools_visible": foreground_tools_visible,
        "foreground_tools_visibility_source": (
            "cli:--foreground-tools-visible"
            if foreground_tools_visible_asserted
            else "env:AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE"
            if foreground_override
            else "current_thread_unverified_after_host_probe"
            if host_probe_status.get("ok") is True
            else "host_config_probe"
        ),
        "current_thread_tool_discovery": current_thread_discovery,
        "next_command": next_command,
        "claim_boundary": (
            "package artifacts being current does not prove that the current "
            "foreground agent can call AIppocampus MCP/plugin tools; tools visible "
            "does not prove key recall tools are callable"
        ),
        "safety_notes": [
            "This is host exposure/readiness, not core recall quality",
            "Unknown foreground tool visibility should not be reported as ready",
        ],
    }


__all__ = [
    "command_availability",
    "default_host_probe_report_path",
    "load_json_file",
    "mcp_command_repair_options",
    "status_agent_callable",
    "write_host_probe_report",
]
