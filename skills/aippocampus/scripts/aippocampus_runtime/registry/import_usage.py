"""Import CLI usage recovery cards.

This module keeps agent-facing import recovery payloads out of the registry API
entrypoint. The registry API is already a broad command router; adding another
foreground card family there makes future route/search changes harder to audit.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import cli_exit_code_for_error_code
from conversation_sources import PROVIDER_CHOICES


def _arg_present(args: list[str], names: set[str]) -> bool:
    return any(item in names or any(item.startswith(name + "=") for name in names) for item in args)


def _subcommand_index(args: list[str], command: str) -> int | None:
    try:
        return args.index(command)
    except ValueError:
        return None


def import_conversation_usage_payload(missing: list[str]) -> dict[str, Any]:
    normalized_missing = [
        "input_path" if item == "--input/--source" else "format_or_provider"
        for item in missing
    ]
    actions: list[dict[str, Any]] = [
        {
            "id": "show_import_chooser",
            "kind": "shell_command",
            "command": "aippocampus import --json",
            "mutation_risk": "read_only",
            "claim_boundary": "import_recovery_no_write",
            "reason": "show machine-readable import choices without writing registry data",
        },
        {
            "id": "preview_generic_jsonl",
            "kind": "shell_command_template",
            "command_template": (
                "aippocampus import conversation --format generic-jsonl "
                '--input "{input_path}" --dry-run --json'
            ),
            "requires": ["input_path"],
            "mutation_risk": "read_only_preview",
            "claim_boundary": "import_preview_before_write",
            "reason": "validate the transcript before any registry write",
        },
    ]
    return {
        "kind": "aippocampus_import_conversation_recovery",
        "ok": False,
        "status": "needs_input",
        "missing": normalized_missing,
        "error": {
            "code": "usage_error",
            "class": "usage_error",
            "message": "import conversation needs an input file and a provider/format.",
            "missing": missing,
            "written": False,
            "path_redacted": True,
            "next_action": "Choose an import path or provide fields for a dry-run preview.",
        },
        "input_schema": {
            "required": normalized_missing,
            "supported_providers": list(PROVIDER_CHOICES),
            "supported_formats": ["generic-jsonl"],
            "preview_first": True,
        },
        "source_boundary": {
            "explicit_input_required": True,
            "preview_before_write": True,
            "local_paths_redacted_by_default": True,
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "data": None,
    }


def render_import_conversation_error(payload: dict[str, Any]) -> str:
    error = payload.get("error") or {}
    lines = [
        "AIppocampus import conversation",
        f"error: {error.get('message')}",
    ]
    missing = error.get("missing") or []
    if missing:
        lines.append("missing: " + ", ".join(str(item) for item in missing))
    actions = payload.get("safe_next_actions") or []
    chooser = next((item for item in actions if item.get("command")), None)
    template = next((item for item in actions if item.get("command_template")), None)
    if chooser:
        lines.append(f"next: {chooser.get('command')}")
    if template:
        lines.append(f"preview template: {template.get('command_template')}")
    if not chooser and not template and error.get("next_action"):
        lines.append(f"next: {error.get('next_action')}")
    lines.append("written: false")
    lines.append("privacy: local input paths are redacted by default")
    lines.append("boundary: preview/dry-run first; register only after the input is explicit.")
    return "\n".join(lines)


def maybe_handle_import_conversation_usage(raw_args: list[str]) -> int | None:
    index = _subcommand_index(raw_args, "register-source")
    if index is None or any(item in {"-h", "--help"} for item in raw_args):
        return None
    register_args = raw_args[index + 1 :]
    missing: list[str] = []
    if not _arg_present(register_args, {"--input", "--source"}):
        missing.append("--input/--source")
    if not _arg_present(register_args, {"--provider", "--format"}):
        missing.append("--provider/--format")
    if not missing:
        return None
    payload = import_conversation_usage_payload(missing)
    if "--json" in register_args:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_import_conversation_error(payload), file=sys.stderr)
    return cli_exit_code_for_error_code("usage_error")
