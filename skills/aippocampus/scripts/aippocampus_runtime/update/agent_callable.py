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
from aippocampus_runtime.source.io_kernel import load_json_dict

PLUGIN_SECTION_RE = re.compile(r'^\s*\[plugins\."([^"]+)"\]\s*$')
MCP_SECTION_RE = re.compile(r'^\s*\[(?:mcp_servers|mcpServers)\."?([^"\]]+)"?\]\s*$')
HOST_PROBE_REPORT_RELATIVE = Path("aippocampus") / "host-probe" / "codex-plugin-install.json"
AGENT_NATIVE_TOOL_NAMES = {
    "agent_recall",
    "agent_aippo",
    "agent_background",
    "agent_deepen",
    "agent_explain",
}
KEY_AGENT_TOOL_NAMES = {"agent_recall", "agent_aippo", "agent_background"}


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


def mcp_command_preflight(command: str = "aippocampus") -> dict[str, Any]:
    availability = command_availability(command)
    repair_options = mcp_command_repair_options(command)
    resolves = bool(availability.get("resolves"))
    return {
        "kind": "aippocampus_mcp_command_preflight",
        "command": command,
        "resolves": resolves,
        "status": "ready" if resolves else "console_script_not_resolvable",
        "repair_options": repair_options,
        "primary_repair_command": repair_options[0] if repair_options else "python -m pip install -e .",
        "claim_boundary": (
            "Codex plugin host-probe success does not prove that a bare MCP command "
            "will resolve in every host process."
        ),
        "privacy": {"resolved_path_emitted": False},
    }


def load_json_file(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    result = load_json_dict(path)
    if int(result.loss.get("non_object_json_count") or 0):
        return None
    if int(result.loss.get("total_loss_count") or 0):
        return {
            "status": "invalid_probe_report",
            "ok": False,
            "source": "host_probe_report",
        }
    return result.data if result.data else None


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
    foreground_key_tools_callable_asserted: bool = False,
    foreground_key_tool_failure: str | None = None,
) -> dict[str, Any]:
    config_text = _read_config_text(codex_home_path)
    plugin_ids = _configured_plugin_ids(config_text)
    mcp_ids = _configured_mcp_server_ids(config_text)
    host_plugin_installed = any("aippocampus" in item.casefold() for item in plugin_ids)
    host_mcp_registered = any("aippocampus" == item.casefold() for item in mcp_ids)
    host_probe_status = _host_probe_status(host_probe)
    foreground_override = os.environ.get("AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE")
    foreground_key_override = os.environ.get("AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE")
    foreground_failure = (
        foreground_key_tool_failure
        or os.environ.get("AIPPOCAMPUS_FOREGROUND_KEY_TOOL_FAILURE")
        or ""
    ).strip()
    truthy_env_values = {"1", "true", "TRUE", "yes"}
    falsy_env_values = {"0", "false", "FALSE", "no", "off"}
    foreground_key_override_true = foreground_key_override in truthy_env_values
    foreground_visibility_requested = (
        foreground_tools_visible_asserted
        or foreground_key_tools_callable_asserted
        or foreground_override is not None
    )
    foreground_probe_requested = (
        foreground_visibility_requested
        or foreground_key_override is not None
        or bool(foreground_failure)
    )
    foreground_tools_visible: bool | None
    if foreground_key_tools_callable_asserted:
        foreground_tools_visible = True
    elif foreground_key_override_true:
        foreground_tools_visible = True
    elif foreground_tools_visible_asserted:
        foreground_tools_visible = True
    elif foreground_override in truthy_env_values:
        foreground_tools_visible = True
    elif foreground_override in falsy_env_values:
        foreground_tools_visible = False
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
    current_thread_key_tools_callable: bool | None = None
    current_thread_key_source: str | None = None
    current_thread_key_tools_verified = False
    current_thread_key_tools_asserted = False
    if foreground_failure:
        current_thread_key_tools_callable = False
        current_thread_key_source = "current_foreground_key_tool_failure"
    elif foreground_key_tools_callable_asserted:
        current_thread_key_tools_callable = True
        current_thread_key_source = "cli:--foreground-key-tools-callable"
        current_thread_key_tools_asserted = True
    elif foreground_key_override_true:
        current_thread_key_tools_callable = True
        current_thread_key_source = "env:AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE"
        current_thread_key_tools_asserted = True
    key_tool_failed = key_tools_callable is False or current_thread_key_tools_callable is False
    # Caller-supplied flags can describe what the foreground agent observed, but
    # they are not the observation itself. Keep full-continuity readiness gated
    # on an explicit same-transport proof path so a stale MCP connection cannot
    # be certified by an optimistic status command.
    ready = (
        foreground_tools_visible is True
        and current_thread_key_tools_verified
        and not key_tool_failed
    )
    host_probe_tool_names = {
        str(item) for item in host_probe_status.get("tool_names") or []
    }
    agent_native_tools_in_host_probe = sorted(host_probe_tool_names & AGENT_NATIVE_TOOL_NAMES)
    missing_agent_native_tools = sorted(AGENT_NATIVE_TOOL_NAMES - host_probe_tool_names)
    foreground_probe_state = (
        "foreground_key_tool_call_failed"
        if current_thread_key_tools_callable is False
        else "asserted_by_caller_key_tool_calls_unverified"
        if current_thread_key_tools_asserted
        else "verified_by_current_foreground_key_tool_calls"
        if current_thread_key_tools_verified
        else "tools_visible_but_key_tools_failed"
        if key_tool_failed
        else "tools_visible_key_tools_unverified"
        if foreground_tools_visible is True
        else "foreground_tools_not_visible"
        if foreground_tools_visible is False and foreground_probe_requested
        else "foreground_probe_not_checked"
        if host_probe_status.get("ok") is True or host_plugin_installed or host_mcp_registered
        else "not_configured"
    )
    if (
        not foreground_probe_requested
        and foreground_probe_state == "foreground_probe_not_checked"
    ):
        foreground_probe_state = "not_requested"
    current_thread_discovery = (
        "foreground_probe_not_checked"
        if foreground_probe_state == "not_requested"
        else foreground_probe_state
    )
    if current_thread_key_tools_callable is False:
        status = "foreground_mcp_runtime_mismatch"
    elif key_tools_callable is False:
        status = "host_live_probe_key_tools_failed"
    elif host_probe_status.get("ok") is True and ready:
        status = "host_live_probe_ok_current_thread_verified"
    elif host_probe_status.get("ok") is True and not foreground_probe_requested:
        status = "host_live_probe_ok_foreground_probe_not_checked"
    elif host_probe_status.get("ok") is True and not ready:
        status = "host_live_probe_ok_current_thread_unverified"
    elif ready:
        status = "ready"
    elif host_plugin_installed or host_mcp_registered:
        status = "host_registered_tools_unverified"
    elif package_artifact_current:
        status = "artifact_current_host_not_exposed"
    else:
        status = "host_not_exposed"

    next_command = "aippocampus update status --json"
    if current_thread_key_tools_callable is False:
        next_command = (
            "reload Codex Desktop or restart the MCP transport, then use the CLI fallback: "
            'aippocampus agent recall "<cue>" --json'
        )
    elif key_tools_callable is False:
        next_command = (
            "reload Codex Desktop/plugin tools or restart the MCP host, then rerun "
            "aippocampus plugin install --codex --verify"
        )
    elif host_probe_status.get("ok") is True and not ready:
        next_command = "aippocampus update status --foreground-tools-visible --agent-json"
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
        "key_tools_callable": (
            current_thread_key_tools_callable
            if current_thread_key_tools_callable is not None
            else key_tools_callable
        ),
        "host_probe_key_tools_callable": key_tools_callable,
        "current_foreground_key_tools_callable": current_thread_key_tools_callable,
        "current_foreground_key_tools_source": current_thread_key_source,
        "current_foreground_key_tools_asserted_by_caller": current_thread_key_tools_asserted,
        "current_foreground_key_tools_verified": current_thread_key_tools_verified,
        "current_foreground_key_tool_failure": (
            redact_private_paths(foreground_failure) if foreground_failure else None
        ),
        "key_tool_smokes": host_probe_status.get("key_tool_smokes") or [],
        "key_tool_failures": host_probe_status.get("key_tool_failures") or [],
        "live_host_schema_stale": key_tool_failed,
        "foreground_tools_visible": foreground_tools_visible,
        "foreground_tools_visibility_source": (
            "cli:--foreground-tools-visible"
            if foreground_tools_visible_asserted
            else "cli:--foreground-key-tools-callable"
            if foreground_key_tools_callable_asserted
            else "env:AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE"
            if foreground_override is not None
            else "env:AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE"
            if foreground_key_override is not None
            else "not_checked_in_this_status_call"
            if host_probe_status.get("ok") is True and not foreground_probe_requested
            else "host_config_probe"
        ),
        "foreground_probe_requested": foreground_probe_requested,
        "foreground_probe_state": foreground_probe_state,
        "current_thread_tool_discovery": current_thread_discovery,
        "next_command": next_command,
        "claim_boundary": (
            "package artifacts being current does not prove that the current "
            "foreground agent can call AIppocampus MCP/plugin tools; tools visible "
            "does not prove key recall/deepen tools are callable"
        ),
        "safety_notes": [
            "This is host exposure/readiness, not core recall quality",
            "Foreground tool visibility and current-connection key-tool calls are separate states",
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
