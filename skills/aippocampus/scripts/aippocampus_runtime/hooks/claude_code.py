#!/usr/bin/env python3
"""Claude Code hook status, explicit install/uninstall, and synthetic smoke.

Claude Code uses a different upstream hook schema from Codex, so mutation stays
behind explicit `install` / `uninstall` commands. Status and dry-run remain
read-only and unsupported events stay contract-only until their privacy boundary
is implemented.
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

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)

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
    settings, _ = read_settings_for_status(path)
    return settings


def read_settings_for_status(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None or not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "settings_json_unreadable"
    except OSError:
        return {}, "settings_json_unreadable"
    if not isinstance(data, dict):
        return {}, "settings_json_root_not_object"
    return data, None


def _mutation_settings_error(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return "claude_settings_json_invalid"
    if isinstance(exc, ValueError):
        return "claude_settings_json_root_not_object"
    if isinstance(exc, OSError):
        return "claude_settings_unreadable"
    return "claude_settings_unavailable"


def _mutation_blocked_result(
    *,
    action: str,
    settings_path: Path,
    error_code: str,
    command_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = status_report(settings_path=settings_path)
    rollback = (
        "aippocampus hooks claude-code uninstall --json"
        if action == "install"
        else "aippocampus hooks claude-code install --json"
    )
    return {
        "ok": False,
        "host": HOST,
        "action": action,
        "wrote": False,
        "changed": False,
        "settings_path": redacted_settings_path(settings_path),
        "path_redacted": True,
        "error": {
            "code": error_code,
            "message": "Claude settings JSON could not be safely mutated; repair it locally and rerun status.",
        },
        "handler_command": command_report or handler_command_report(),
        "settings": status["settings"],
        "rollback_command": rollback,
        "agent_next_action": status["agent_next_action"],
        "safe_next_actions": status["safe_next_actions"],
    }


def load_settings_for_mutation(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Claude settings JSON root must be an object")
    return data


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def _is_aippocampus_handler(handler: Any) -> bool:
    command = str(handler.get("command") or "") if isinstance(handler, dict) else ""
    return any(marker in command for marker in HANDLER_MARKERS)


def _without_aippocampus_handlers(groups: Any) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            cleaned.append(dict(group))
            continue
        kept_handlers = [handler for handler in handlers if not _is_aippocampus_handler(handler)]
        if kept_handlers:
            updated = dict(group)
            updated["hooks"] = kept_handlers
            cleaned.append(updated)
    return cleaned


def _install_supported_hooks(
    settings: dict[str, Any],
    *,
    command_report: dict[str, Any],
) -> dict[str, Any]:
    updated = json.loads(json.dumps(settings, ensure_ascii=False))
    hooks = updated.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        updated["hooks"] = hooks
    for event in SUPPORTED_HANDLER_EVENTS:
        groups = _without_aippocampus_handlers(hooks.get(event))
        groups.append(handler_entry(event, command_report=command_report))
        hooks[event] = groups
    return updated


def _uninstall_supported_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(settings, ensure_ascii=False))
    hooks = updated.get("hooks")
    if not isinstance(hooks, dict):
        return updated
    for event in SUPPORTED_HANDLER_EVENTS:
        groups = _without_aippocampus_handlers(hooks.get(event))
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        updated.pop("hooks", None)
    return updated


def _mutation_result(
    *,
    action: str,
    settings_path: Path,
    before: dict[str, Any],
    after: dict[str, Any],
    wrote: bool,
    command_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = status_report(settings_path=settings_path)
    changed = before != after
    if command_report is None:
        command_report = handler_command_report()
    rollback = (
        "aippocampus hooks claude-code uninstall --json"
        if action == "install"
        else "aippocampus hooks claude-code install --json"
    )
    return {
        "ok": True,
        "host": HOST,
        "action": action,
        "wrote": wrote,
        "changed": changed,
        "settings_path": redacted_settings_path(settings_path),
        "path_redacted": True,
        "handler_command": command_report,
        "settings": status["settings"],
        "events": {
            event: status["events"][event]
            for event in SUPPORTED_HANDLER_EVENTS
        },
        "rollback_command": rollback,
        "agent_next_action": status["agent_next_action"],
        "safe_next_actions": status["safe_next_actions"],
        "privacy_boundary": {
            "local_path_serialized": False,
            "raw_prompt_serialized": False,
            "unsupported_events_installed": False,
        },
        "cannot_claim": [
            "real_host_hook_firing_without_event_log",
            "post_tool_payload_capture",
            "compaction_survival_packet_quality",
            "all_claude_code_versions",
        ],
    }


def install_hooks(*, settings_path: Path | None = None) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    command_report = handler_command_report()
    if not command_report.get("command_resolvable"):
        return {
            "ok": False,
            "host": HOST,
            "action": "install",
            "wrote": False,
            "changed": False,
            "settings_path": redacted_settings_path(settings_path),
            "path_redacted": True,
            "error": {
                "code": "handler_command_not_resolvable",
                "message": "Put the aippocampus console script or module fallback on the Claude hook PATH before install.",
            },
            "handler_command": command_report,
            "rollback_command": "aippocampus hooks claude-code uninstall --json",
        }
    try:
        before = load_settings_for_mutation(settings_path)
    except Exception as exc:
        return _mutation_blocked_result(
            action="install",
            settings_path=settings_path,
            error_code=_mutation_settings_error(exc),
            command_report=command_report,
        )
    after = _install_supported_hooks(before, command_report=command_report)
    changed = before != after
    if changed:
        save_settings(settings_path, after)
    return _mutation_result(
        action="install",
        settings_path=settings_path,
        before=before,
        after=after,
        wrote=changed,
        command_report=command_report,
    )


def uninstall_hooks(*, settings_path: Path | None = None) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    try:
        before = load_settings_for_mutation(settings_path)
    except Exception as exc:
        return _mutation_blocked_result(
            action="uninstall",
            settings_path=settings_path,
            error_code=_mutation_settings_error(exc),
        )
    after = _uninstall_supported_hooks(before)
    changed = before != after
    if changed:
        save_settings(settings_path, after)
    return _mutation_result(
        action="uninstall",
        settings_path=settings_path,
        before=before,
        after=after,
        wrote=changed,
    )


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
    settings_blocker: str | None = None,
) -> str:
    if settings_blocker and event in SUPPORTED_HANDLER_EVENTS:
        return "blocked"
    if event in observed:
        return "firing"
    if event in installed:
        return "installed"
    if event in SUPPORTED_HANDLER_EVENTS:
        return "installable"
    return "unsupported_event"


def event_report(
    event: str,
    *,
    installed: set[str],
    observed: set[str],
    settings_blocker: str | None = None,
) -> dict[str, Any]:
    status = event_status(
        event,
        installed=installed,
        observed=observed,
        settings_blocker=settings_blocker,
    )
    if event == "UserPromptSubmit":
        role = "ambient_prompt_route"
        blocker = settings_blocker
    elif event == "Stop":
        role = "completion_lifecycle_fail_open"
        blocker = settings_blocker
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


def unsupported_event_summary(events: dict[str, dict[str, Any]]) -> dict[str, Any]:
    unsupported = {
        event: row
        for event, row in events.items()
        if row.get("status") == "unsupported_event"
    }
    blockers = {
        event: str(row.get("blocker") or "unsupported_event")
        for event, row in unsupported.items()
    }
    return {
        "count": len(unsupported),
        "events": list(unsupported),
        "blockers": blockers,
        "action": "do_not_install_or_claim_unsupported_events_yet",
    }


def foreground_action_card(
    *,
    settings_status: str,
    events: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    installable = [
        event
        for event in SUPPORTED_HANDLER_EVENTS
        if events.get(event, {}).get("status") == "installable"
    ]
    installed_or_firing = [
        event
        for event in SUPPORTED_HANDLER_EVENTS
        if events.get(event, {}).get("status") in {"installed", "firing"}
    ]
    primary: dict[str, Any]
    if settings_status == "blocked":
        primary = {
            "id": "repair_claude_code_settings_json",
            "label": "Repair Claude Code settings JSON",
            "manual_instruction": (
                "Fix the local Claude settings JSON root, then rerun "
                "`aippocampus hooks claude-code status --json`."
            ),
            "mutation_risk": "manual_config_repair",
            "claim_boundary": "host_setup_not_memory_evidence",
        }
    elif settings_status == "not_installed" and installable:
        primary = foreground_shell_action(
            action_id="preview_claude_code_supported_hooks",
            label="Preview supported Claude Code hooks",
            command="aippocampus hooks claude-code dry-run --json",
            why=(
                "UserPromptSubmit and Stop have shipped handlers; dry-run shows the exact "
                "Claude settings entries without mutating configuration."
            ),
            mutation_risk="read_only",
            claim_boundary="host_setup_not_memory_evidence",
        )
    elif installed_or_firing:
        primary = foreground_shell_action(
            action_id="run_claude_code_hook_smoke",
            label="Run synthetic Claude Code hook smoke",
            command="aippocampus hooks claude-code smoke --json",
            why="Use synthetic smoke to check the handler contract without logging real prompts.",
            mutation_risk="read_only",
            claim_boundary="host_setup_not_memory_evidence",
        )
    else:
        primary = foreground_shell_action(
            action_id="use_claude_code_onboarding_instead",
            label="Check Claude Code local history onboarding",
            command="aippocampus onboard --provider claude-code --status --json",
            why="Use provider onboarding/MCP when host hooks are not the right path.",
            mutation_risk="read_only",
            claim_boundary="setup_status_not_memory_evidence",
        )
    safe_actions = [
        dict(primary),
        foreground_shell_action(
            action_id="check_claude_code_local_history",
            label="Check Claude Code local history",
            command="aippocampus onboard --provider claude-code --status --json",
            why="Local transcript onboarding is the fallback continuity route when hooks are not desired.",
            mutation_risk="read_only",
            claim_boundary="setup_status_not_memory_evidence",
        ),
        foreground_shell_action(
            action_id="check_mcp_status",
            label="Check MCP readiness",
            command="aippocampus mcp status",
            why="Use when Claude Code should reach AIppocampus through MCP rather than hooks.",
            mutation_risk="read_only",
            claim_boundary="host_status_not_memory_evidence",
        ),
    ]
    if settings_status == "blocked":
        safe_actions.append(
            foreground_shell_action(
                action_id="preview_claude_code_supported_hooks_after_repair",
                label="Preview supported Claude Code hooks",
                command="aippocampus hooks claude-code dry-run --json",
                why="Use after the settings JSON is repaired to see exactly what install would write.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            )
        )
    if settings_status == "not_installed" and installable:
        safe_actions.append(
            foreground_shell_action(
                action_id="install_claude_code_supported_hooks",
                label="Install supported Claude Code hooks",
                command="aippocampus hooks claude-code install --json",
                why="Explicitly write only the shipped UserPromptSubmit and Stop hook handlers.",
                mutation_risk="explicit_config_write",
                claim_boundary="host_setup_not_memory_evidence",
            )
        )
    if installed_or_firing:
        safe_actions.append(
            foreground_shell_action(
                action_id="uninstall_claude_code_supported_hooks",
                label="Uninstall supported Claude Code hooks",
                command="aippocampus hooks claude-code uninstall --json",
                why="Rollback removes only AIppocampus handlers for shipped Claude Code events.",
                mutation_risk="explicit_config_write",
                claim_boundary="host_setup_not_memory_evidence",
            )
        )
    return {
        "surface": "claude_code_hooks_status",
        "status": settings_status,
        "supported_installable_events": installable,
        "supported_installed_or_firing_events": installed_or_firing,
        "unsupported_events": unsupported_event_summary(events),
        "primary": dict(primary),
        "safe_next_actions": safe_actions,
        "claim_boundary": {
            "hook_status_is_host_setup_evidence": True,
            "memory_claims_require_source_reopen": True,
            "unsupported_events_are_not_supported": True,
            "no_configuration_mutation_happened": True,
        },
    }


def status_report(
    *,
    settings_path: Path | None = None,
    event_log_path: Path | None = None,
) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    settings, settings_blocker = read_settings_for_status(settings_path)
    installed = installed_events(settings)
    observed = read_observed_events(event_log_path)
    events = {
        event: event_report(
            event,
            installed=installed,
            observed=observed,
            settings_blocker=settings_blocker,
        )
        for event in (*SUPPORTED_HANDLER_EVENTS, *CONTRACT_ONLY_EVENTS)
    }
    installed_any = bool(installed & set(SUPPORTED_HANDLER_EVENTS))
    if settings_blocker:
        settings_status = "blocked"
    else:
        settings_status = "installed" if installed_any else "not_installed"
    if any(item["status"] == "firing" for item in events.values()):
        settings_status = "firing"
    foreground_action = foreground_action_card(settings_status=settings_status, events=events)
    return {
        "ok": True,
        "host": HOST,
        "config_surface": CONFIG_SURFACE,
        "settings": {
            "status": settings_status,
            "path": redacted_settings_path(settings_path),
            "path_redacted": True,
            **({"blocker": settings_blocker} if settings_blocker else {}),
        },
        "official_contract": {
            "intake_date": CONTRACT_INTAKE_DATE,
            "reference": OFFICIAL_HOOKS_REFERENCE,
            "guide": OFFICIAL_HOOKS_GUIDE,
            "supported_handler_events": list(SUPPORTED_HANDLER_EVENTS),
            "contract_only_events": list(CONTRACT_ONLY_EVENTS),
        },
        "events": events,
        "foreground_action": foreground_action,
        "agent_next_action": foreground_action["primary"],
        "safe_next_actions": foreground_action["safe_next_actions"],
        "status_vocabulary": list(STATUS_VOCABULARY),
        "cannot_claim": [
            "real_host_hook_firing_without_event_log",
            "post_tool_payload_capture",
            "compaction_survival_packet_quality",
            "all_claude_code_versions",
        ]
        + (["claude_settings_status_blocked"] if settings_blocker else []),
    }


def dry_run_report(*, settings_path: Path | None = None) -> dict[str, Any]:
    settings_path = default_settings_path() if settings_path is None else settings_path
    command_report = handler_command_report()
    ready_action = foreground_shell_action(
        action_id="install_claude_code_hooks_after_review",
        command="aippocampus hooks claude-code install --json",
        label="Install Claude Code hooks after review",
        why="The dry-run handler command is resolvable; install is still an explicit local write.",
        mutation_risk="writes_claude_settings",
        claim_boundary="host_hook_install_status_not_memory_evidence",
    )
    blocked_action = foreground_shell_action(
        action_id="inspect_claude_code_hook_status",
        command="aippocampus hooks claude-code status --json",
        label="Inspect Claude Code hook status",
        why="The handler command is not safely resolvable yet; inspect status after fixing PATH or module fallback.",
        mutation_risk="read_only",
        claim_boundary="host_hook_status_not_memory_evidence",
    )
    primary_action = ready_action if command_report["copy_paste_ready"] else blocked_action
    safe_actions = [primary_action]
    next_step = (
        "run aippocampus hooks claude-code install --json after reviewing this dry-run"
        if command_report["copy_paste_ready"]
        else "make the handler command resolvable, then run aippocampus hooks claude-code status --json"
    )
    payload = {
        "ok": True,
        "host": HOST,
        "action": "dry_run",
        "would_write": False,
        "settings_path": redacted_settings_path(settings_path),
        "path_redacted": True,
        "handler_command": command_report,
        "proposed_hooks": proposed_hooks(command_report=command_report),
        "install_command": "aippocampus hooks claude-code install --json",
        "rollback_command": "aippocampus hooks claude-code uninstall --json",
        "rollback": "aippocampus hooks claude-code uninstall --json",
        "next_operator_step": next_step,
    }
    payload.update(
        canonical_foreground_action_fields(
            primary_action,
            safe_next_actions=safe_actions,
        )
    )
    return payload


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
        choices=["status", "dry-run", "install", "uninstall", "smoke", "handle"],
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
    elif args.action == "install":
        payload = install_hooks(settings_path=args.settings_json)
    elif args.action == "uninstall":
        payload = uninstall_hooks(settings_path=args.settings_json)
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
        print("configuration mutation: explicit install/uninstall only")
    return 0 if payload.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
