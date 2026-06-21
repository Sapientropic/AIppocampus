"""Command-safety guards for public runtime contracts."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping

EXECUTABLE_COMMAND_FIELDS = {
    "command",
    "cli_command",
    "next_command",
    "apply_command",
    "preview_command",
    "write_command",
    "search_command",
    "recommended_public_command",
    "object_storage_command",
}

_NON_EXECUTABLE_FIELD_MARKERS = (
    "template",
    "example",
    "manual_instruction",
    "requires",
)

_ANGLE_PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
_BRACE_PLACEHOLDER_RE = re.compile(
    r"\{(?:cue|continuity_cue|exact_phrase|input_path|output_path|"
    r"request_index|task|query|note_text|card_id|arc_handle|scope|handle)\}"
)
_SAMPLE_COMMAND_PHRASES = (
    "old decision or handoff cue",
    "distinctive exact phrase",
    "distinctive old phrase",
    "old continuity cue",
    "old cue",
    "route to pause",
    "route to forget here",
    "route to quiet",
    "issue:#123",
    "issue title",
    "issue body",
)
_NON_RUNNABLE_COMMAND_MARKERS = {
    "no-op",
    "continue-without-cleanup",
}


def command_value_needs_input(value: object) -> bool:
    """Return whether a command-like value is not directly executable."""

    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if _ANGLE_PLACEHOLDER_RE.search(text) or _BRACE_PLACEHOLDER_RE.search(text):
        return True
    lowered = text.casefold()
    if lowered.startswith("run `") or "`" in text:
        return True
    return any(phrase in lowered for phrase in _SAMPLE_COMMAND_PHRASES)


def command_value_is_non_runnable_marker(value: object) -> bool:
    """Return whether a command-like field is a semantic marker, not a command."""

    if not isinstance(value, str):
        return False
    return value.strip().casefold() in _NON_RUNNABLE_COMMAND_MARKERS


def shell_quote(value: object) -> str:
    """Quote one concrete value for copy-pasteable shell commands."""

    return shlex.quote(str(value or ""))


def executable_command_violations(payload: object) -> list[dict[str, str]]:
    """Find placeholder/prose values in machine-executable fields."""

    violations: list[dict[str, str]] = []

    def allowed_context(path: tuple[str, ...]) -> bool:
        return any(any(marker in part for marker in _NON_EXECUTABLE_FIELD_MARKERS) for part in path)

    def walk(value: object, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                next_path = (*path, key_text)
                if key_text in EXECUTABLE_COMMAND_FIELDS and not allowed_context(next_path):
                    marker_reason = (
                        "executable_field_is_non_runnable_marker"
                        if command_value_is_non_runnable_marker(item)
                        else ""
                    )
                    if marker_reason:
                        violations.append(
                            {
                                "path": ".".join(next_path),
                                "field": key_text,
                                "reason": marker_reason,
                                "value": str(item),
                            }
                        )
                    elif command_value_needs_input(item):
                        violations.append(
                            {
                                "path": ".".join(next_path),
                                "field": key_text,
                                "reason": "executable_field_needs_input",
                                "value": str(item),
                            }
                        )
                if key_text == "arguments" and not allowed_context(next_path):
                    walk_machine_arguments(item, next_path)
                walk(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, (*path, str(index)))

    def walk_machine_arguments(value: object, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                next_path = (*path, str(key))
                if command_value_needs_input(item):
                    violations.append(
                        {
                            "path": ".".join(next_path),
                            "field": "arguments",
                            "reason": "machine_arguments_need_input",
                            "value": str(item),
                        }
                    )
                walk_machine_arguments(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk_machine_arguments(item, (*path, str(index)))

    walk(payload, ())
    return violations
