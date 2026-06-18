"""Foreground CLI recovery cards for facade-owned command boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.cli.errors import (
    cli_error_object,
    cli_error_payload,
    cli_exit_code_for_error_code,
)
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.public_output import emit_public_text

JSON_REQUEST_FLAGS = {
    "--json",
    "--agent-json",
    "--compact-json",
    "--detail-json",
    "--operator-json",
    "--public-json",
    "--summary-json",
}


def args_request_json(args: list[str]) -> bool:
    return any(arg in JSON_REQUEST_FLAGS for arg in args)


def action_command_text(action: Mapping[str, Any]) -> str:
    return str(
        action.get("command")
        or action.get("cli_command")
        or action.get("command_template")
        or action.get("cli_command_template")
        or action.get("id")
        or "aippocampus --help"
    )


def script_recovery_action(script_name: str, args: list[str]) -> dict[str, Any]:
    command = args[0] if args else ""
    if script_name == "agent_continuity.py" and command == "recall":
        return foreground_template_action(
            action_id="rerun_agent_recall_with_cue",
            label="Run recall with a cue",
            command_template='aippocampus agent recall "{cue}" --json',
            requires=["cue"],
            why="Recall needs a continuity cue before it can return source-backed routes.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    if script_name == "agent_continuity.py" and command == "macro":
        return foreground_shell_action(
            action_id="inspect_macro_schema",
            label="Inspect macro state schema",
            command="aippocampus agent macro --explain-schema",
            why="Use this when a macro state file is missing, malformed, or being repaired.",
            mutation_risk="read_only",
            claim_boundary="operator_setup_not_source_evidence",
        )
    if script_name == "sync_bundle.py":
        return foreground_shell_action(
            action_id="check_sync_status",
            label="Check sync status",
            command="aippocampus sync status --json",
            why="Status is the read-only recovery surface for sync manifest failures.",
            mutation_risk="read_only",
            claim_boundary="sync_status_not_source_evidence",
        )
    if script_name == "storage_governance.py":
        return foreground_shell_action(
            action_id="preview_storage_gc",
            label="Preview storage cleanup",
            command="aippocampus storage gc --dry-run --summary-json --cwd .",
            why="Storage cleanup should recover through dry-run before any local write.",
            mutation_risk="read_only_preview",
            claim_boundary="gc_plan_not_cleanup_receipt",
        )
    if script_name == "latest_reply.py":
        return foreground_shell_action(
            action_id="inspect_latest_reply",
            label="Inspect latest final reply",
            command="aippocampus latest-reply --cwd . --json",
            why="Latest reply is navigation context, not a memory fact by itself.",
            mutation_risk="read_only",
            claim_boundary="latest_reply_is_navigation_not_memory_fact",
        )
    return foreground_shell_action(
        action_id="inspect_cli_help",
        label="Inspect AIppocampus help",
        command="aippocampus --help",
        why="Use the facade help to choose a supported foreground command.",
        mutation_risk="read_only",
        claim_boundary="help_is_not_source_evidence",
    )


def _system_exit_message(stderr_text: str) -> str:
    lines = [line.strip() for line in str(stderr_text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if "error:" in line:
            return line.split("error:", maxsplit=1)[-1].strip()
    return lines[-1] if lines else "Invalid or incomplete aippocampus command."


def module_exception_payload(
    script_name: str,
    args: list[str],
    exc: BaseException,
    *,
    stderr_text: str = "",
) -> dict[str, Any]:
    action = script_recovery_action(script_name, args)
    payload = (
        {
            "ok": False,
            "error": cli_error_object(
                "usage_error",
                _system_exit_message(stderr_text),
            ),
            "data": None,
        }
        if isinstance(exc, SystemExit)
        else cli_error_payload(exc)
    )
    payload.update(
        {
            "kind": "aippocampus_cli_recovery_error",
            "status": "error",
            "surface": "cli_facade",
            "entrypoint": Path(script_name).stem,
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "foreground_action": action,
            "agent_next_action": action,
            "safe_next_actions": [action],
            "recovery_boundary": {
                "raw_traceback_suppressed": True,
                "local_paths_redacted": True,
                "recovery_guidance_is_not_source_evidence": True,
            },
        }
    )
    return redact_sensitive_values(redact_private_paths(payload))


def render_module_exception_text(payload: dict[str, Any]) -> str:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    action = payload.get("agent_next_action")
    action_map = action if isinstance(action, Mapping) else {}
    lines = [
        f"Error: {error.get('code') or 'runtime_error'}. Try: {action_command_text(action_map)}",
    ]
    message = str(error.get("message") or "").strip()
    if message:
        lines.append(f"Reason: {message}")
    lines.append("Boundary: recovery guidance is not source evidence.")
    return "\n".join(lines) + "\n"


def handle_module_exception(
    script_name: str,
    args: list[str],
    exc: BaseException,
    *,
    stderr_text: str = "",
) -> int:
    payload = module_exception_payload(script_name, args, exc, stderr_text=stderr_text)
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    exit_code = cli_exit_code_for_error_code(str(error.get("code") or "runtime_error"))
    if args_request_json(args):
        emit_public_text(json.dumps(payload, ensure_ascii=False, indent=2), end="")
    else:
        emit_public_text(render_module_exception_text(payload), end="", stream=sys.stderr)
    return exit_code
