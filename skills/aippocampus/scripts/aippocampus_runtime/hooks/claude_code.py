#!/usr/bin/env python3
"""Claude Code hook contract status, dry-run, and isolated synthetic smoke.

This module is deliberately not a configuration-mutating installer. Claude Code
has a different upstream hook schema from Codex; keep the first supported slice
as a dry-run/status/handler contract so provider onboarding cannot be mistaken
for host-hook installation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HOST = "claude-code"
CONFIG_SURFACE = "claude_settings_json"
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
OFFICIAL_HOOKS_REFERENCE = "https://code.claude.com/docs/en/hooks"
OFFICIAL_HOOKS_GUIDE = "https://code.claude.com/docs/en/hooks-guide"
CONTRACT_INTAKE_DATE = "2026-06-09"
STATUS_VOCABULARY = (
    "not_installed",
    "installable",
    "installed",
    "firing",
    "blocked",
    "unsupported_version",
    "unsupported_event",
)
SUPPORTED_HANDLER_EVENTS = ("UserPromptSubmit", "Stop")
CONTRACT_ONLY_EVENTS = ("PostToolUse", "PostToolBatch", "PreCompact", "PostCompact")
SENSITIVE_SMOKE_MARKERS = (
    "synthetic prompt marker must not leak",
    "synthetic-session-marker",
    "<redacted:transcript-path>",
    "<redacted:cwd>",
    "synthetic tool payload marker must not leak",
)


@dataclass(frozen=True)
class HookOutcome:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    status: str = "installable"


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def redacted_settings_path(path: Path | None) -> str | None:
    return "<redacted:claude-settings-json>" if path is not None else None


def load_settings(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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


def installed_events(settings: dict[str, Any]) -> set[str]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return set()
    installed: set[str] = set()
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                command = str(handler.get("command") or "") if isinstance(handler, dict) else ""
                if any(marker in command for marker in HANDLER_MARKERS):
                    installed.add(str(event))
    return installed


def read_observed_events(event_log_path: Path | None) -> set[str]:
    if event_log_path is None or not event_log_path.exists():
        return set()
    seen: set[str] = set()
    with event_log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except Exception:
                continue
            event_name = str(item.get("hook_event_name") or item.get("event") or "")
            if event_name:
                seen.add(event_name)
    return seen


def event_status(
    event: str,
    *,
    installed: set[str],
    observed: set[str],
) -> str:
    if event in observed:
        return "firing"
    if event in installed:
        return "installed"
    if event in SUPPORTED_HANDLER_EVENTS:
        return "installable"
    return "unsupported_event"


def event_report(event: str, *, installed: set[str], observed: set[str]) -> dict[str, Any]:
    status = event_status(event, installed=installed, observed=observed)
    if event == "UserPromptSubmit":
        role = "ambient_prompt_route"
        blocker = None
    elif event == "Stop":
        role = "completion_lifecycle_fail_open"
        blocker = None
    elif event in {"PostToolUse", "PostToolBatch"}:
        role = "tool_surface_capture"
        blocker = "raw_tool_payload_sanitizer_not_shipped"
    else:
        role = "compaction_survival_route"
        blocker = "compact_summary_source_truth_boundary_not_shipped"
    report: dict[str, Any] = {
        "role": role,
        "status": status,
        "handler_shipped": event in SUPPORTED_HANDLER_EVENTS,
        "official_contract_event": True,
    }
    if blocker:
        report["blocker"] = blocker
    return report


def status_report(
    *,
    settings_path: Path | None = None,
    event_log_path: Path | None = None,
) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    settings = load_settings(settings_path)
    installed = installed_events(settings)
    observed = read_observed_events(event_log_path)
    events = {
        event: event_report(event, installed=installed, observed=observed)
        for event in (*SUPPORTED_HANDLER_EVENTS, *CONTRACT_ONLY_EVENTS)
    }
    installed_any = bool(installed & set(SUPPORTED_HANDLER_EVENTS))
    settings_status = "installed" if installed_any else "not_installed"
    if any(item["status"] == "firing" for item in events.values()):
        settings_status = "firing"
    return {
        "ok": True,
        "host": HOST,
        "config_surface": CONFIG_SURFACE,
        "settings": {
            "status": settings_status,
            "path": redacted_settings_path(settings_path),
            "path_redacted": True,
        },
        "official_contract": {
            "intake_date": CONTRACT_INTAKE_DATE,
            "reference": OFFICIAL_HOOKS_REFERENCE,
            "guide": OFFICIAL_HOOKS_GUIDE,
            "supported_handler_events": list(SUPPORTED_HANDLER_EVENTS),
            "contract_only_events": list(CONTRACT_ONLY_EVENTS),
        },
        "events": events,
        "status_vocabulary": list(STATUS_VOCABULARY),
        "cannot_claim": [
            "real_host_hook_firing_without_event_log",
            "no_configuration_mutating_installer",
            "post_tool_payload_capture",
            "compaction_survival_packet_quality",
            "all_claude_code_versions",
        ],
    }


def dry_run_report(*, settings_path: Path | None = None) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    command_report = handler_command_report()
    next_step = (
        "copy the dry-run handlers into Claude settings only after explicit local approval"
        if command_report["copy_paste_ready"]
        else "put the aippocampus console script or a Python module command on the Claude hook PATH before copying handlers"
    )
    return {
        "ok": True,
        "host": HOST,
        "action": "dry_run",
        "would_write": False,
        "settings_path": redacted_settings_path(settings_path),
        "path_redacted": True,
        "handler_command": command_report,
        "proposed_hooks": proposed_hooks(command_report=command_report),
        "rollback": "remove the displayed handlers from the selected Claude settings file",
        "blocker": "configuration_mutating_installer_not_shipped",
        "next_operator_step": next_step,
    }


def hook_event_from_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def bounded_context(event_name: str) -> str:
    if event_name == "UserPromptSubmit":
        return (
            "AIppocampus Claude Code UserPromptSubmit hook is active. "
            "Use MCP or clean-source routes before making memory claims; raw prompt text was not logged."
        )
    return (
        "AIppocampus Claude Code completion hook is active. "
        "Maintenance is fail-open and source-backed claims still require clean-source reopen."
    )


def handle_hook_event(event: dict[str, Any], *, diagnostic_context: bool = False) -> HookOutcome:
    event_name = str(event.get("hook_event_name") or "")
    if event_name not in SUPPORTED_HANDLER_EVENTS:
        return HookOutcome(exit_code=0, status="unsupported_event")
    if not diagnostic_context:
        return HookOutcome(exit_code=0, status="installable")
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": bounded_context(event_name),
        }
    }
    return HookOutcome(
        exit_code=0,
        stdout=json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        status="installable",
    )


def synthetic_events() -> dict[str, dict[str, Any]]:
    return {
        "UserPromptSubmit": {
            "session_id": "synthetic-session-marker",
            "transcript_path": "<redacted:transcript-path>",
            "cwd": "<redacted:cwd>",
            "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "synthetic prompt marker must not leak",
        },
        "Stop": {
            "session_id": "synthetic-session-marker",
            "transcript_path": "<redacted:transcript-path>",
            "cwd": "<redacted:cwd>",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "synthetic tool payload marker must not leak",
        },
    }


def synthetic_smoke_report() -> dict[str, Any]:
    event_results: dict[str, Any] = {}
    combined = ""
    for event_name, event in synthetic_events().items():
        outcome = handle_hook_event(event, diagnostic_context=(event_name == "UserPromptSubmit"))
        event_results[event_name] = {
            "exit_code": outcome.exit_code,
            "stdout_empty": outcome.stdout == "",
            "stderr_empty": outcome.stderr == "",
            "status": outcome.status,
        }
        combined += outcome.stdout + outcome.stderr
    leaks = [marker for marker in SENSITIVE_SMOKE_MARKERS if marker in combined]
    return {
        "ok": not leaks and all(item["exit_code"] == 0 for item in event_results.values()),
        "host": HOST,
        "contract": {
            "reference": OFFICIAL_HOOKS_REFERENCE,
            "guide": OFFICIAL_HOOKS_GUIDE,
            "intake_date": CONTRACT_INTAKE_DATE,
        },
        "events": event_results,
        "privacy": {
            "raw_prompt_omitted": "synthetic prompt marker must not leak" not in combined,
            "session_id_omitted": "synthetic-session-marker" not in combined,
            "transcript_path_omitted": "<redacted:transcript-path>" not in combined,
            "tool_payload_omitted": "synthetic tool payload marker must not leak" not in combined,
            "leak_count": len(leaks),
        },
        "cannot_claim": [
            "real_host_hook_firing",
            "persistent_claude_settings_installed",
            "post_tool_payload_capture",
            "compaction_survival_packet_quality",
        ],
    }


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["status", "dry-run", "smoke", "handle"],
        nargs="?",
        default="status",
    )
    parser.add_argument("--settings-json", type=Path)
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--diagnostic-context", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    if args.action == "handle":
        try:
            outcome = handle_hook_event(
                hook_event_from_stdin(),
                diagnostic_context=args.diagnostic_context,
            )
        except Exception as exc:
            outcome = HookOutcome(exit_code=0, stderr="", status=f"blocked:{type(exc).__name__}")
        if outcome.stdout:
            sys.stdout.write(outcome.stdout)
        if outcome.stderr:
            sys.stderr.write(outcome.stderr)
        return outcome.exit_code

    if args.action == "dry-run":
        payload = dry_run_report(settings_path=args.settings_json)
    elif args.action == "smoke":
        payload = synthetic_smoke_report()
    else:
        payload = status_report(settings_path=args.settings_json, event_log_path=args.event_log)

    if args.json_output:
        print_json(payload)
    else:
        print(f"Claude Code hook status: {payload.get('settings', {}).get('status', payload.get('action'))}")
        print(f"host: {HOST}")
        print(f"config surface: {CONFIG_SURFACE}")
        print("configuration mutation: dry-run only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
