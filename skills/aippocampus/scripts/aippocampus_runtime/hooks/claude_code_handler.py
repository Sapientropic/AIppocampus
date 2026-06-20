"""Claude Code hook handler command resolution."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any

HANDLER_MODULE = "aippocampus_runtime.hooks.claude_code"
HANDLER_FACADE_MODULE = "aippocampus_runtime.cli.facade"
CONSOLE_SCRIPT = "aippocampus"
CONSOLE_HANDLER_COMMAND = "aippocampus hooks claude-code handle"
PYTHON_MODULE_COMMANDS = (
    ("python3", "python3 -m aippocampus_runtime.cli.facade hooks claude-code handle"),
    ("python", "python -m aippocampus_runtime.cli.facade hooks claude-code handle"),
    ("py", "py -3 -m aippocampus_runtime.cli.facade hooks claude-code handle"),
)
HANDLER_MARKERS = (HANDLER_MODULE, HANDLER_FACADE_MODULE, CONSOLE_HANDLER_COMMAND)
SUPPORTED_HANDLER_EVENTS = ("UserPromptSubmit", "Stop")


def _module_available() -> bool:
    return importlib.util.find_spec(HANDLER_FACADE_MODULE) is not None


def handler_command_report() -> dict[str, Any]:
    console_available = shutil.which(CONSOLE_SCRIPT) is not None
    module_available = _module_available()
    fallback: dict[str, Any] | None = None
    if module_available:
        for executable, command in PYTHON_MODULE_COMMANDS:
            if shutil.which(executable) is not None:
                fallback = {
                    "command": command,
                    "executable": executable,
                    "resolution_source": f"path_{executable}_module",
                }
                break

    if console_available:
        command = CONSOLE_HANDLER_COMMAND
        command_kind = "console_script"
        command_resolvable = True
        resolution_source = "path_console_script"
        reason_code = "console_script_on_path"
    elif fallback is not None:
        command = fallback["command"]
        command_kind = "module_fallback"
        command_resolvable = True
        resolution_source = str(fallback["resolution_source"])
        reason_code = "console_script_missing_from_path_module_fallback_available"
    else:
        command = CONSOLE_HANDLER_COMMAND
        command_kind = "console_script_unverified"
        command_resolvable = False
        resolution_source = "not_resolvable"
        reason_code = "operator_path_setup_required"

    return {
        "command": command,
        "command_kind": command_kind,
        "command_resolvable": command_resolvable,
        "command_resolution_source": resolution_source,
        "console_script_resolvable": console_available,
        "module_fallback_available": fallback is not None,
        "module_import_available": module_available,
        "module_fallback_command": fallback["command"] if fallback else None,
        "resolved_executable_path_emitted": False,
        "copy_paste_ready": command_resolvable,
        "reason_code": reason_code,
    }


def handler_command(report: dict[str, Any] | None = None) -> str:
    report = handler_command_report() if report is None else report
    command = report.get("command")
    return str(command) if command else CONSOLE_HANDLER_COMMAND


def handler_entry(event_name: str, *, command_report: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "matcher": "" if event_name in {"UserPromptSubmit", "Stop"} else "*",
        "hooks": [
            {
                "type": "command",
                "command": handler_command(command_report),
                "timeout": 3,
            }
        ],
    }


def proposed_hooks(command_report: dict[str, Any] | None = None) -> dict[str, Any]:
    command_report = handler_command_report() if command_report is None else command_report
    return {
        event: [handler_entry(event, command_report=command_report)]
        for event in SUPPORTED_HANDLER_EVENTS
    }


def is_aippocampus_handler_command(command: str) -> bool:
    return any(marker in command for marker in HANDLER_MARKERS)
