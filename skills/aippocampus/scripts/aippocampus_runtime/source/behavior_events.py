#!/usr/bin/env python3
"""Structured behavior-event extraction for Codex rollout clean source."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampuslib import iter_jsonl

TOOL_EXIT_CODE_RE = re.compile(r"Exit code:\s*(-?\d+)", re.IGNORECASE)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _tool_call_id(payload: dict[str, Any]) -> str:
    return str(payload.get("call_id") or payload.get("id") or payload.get("tool_call_id") or "")


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("name") or payload.get("tool_name") or payload.get("type") or "tool")


def _tool_input(payload: dict[str, Any]) -> Any:
    for key in ("arguments", "args", "input", "parameters"):
        if key in payload:
            return _parse_maybe_json(payload.get(key))
    return {}


def _tool_output_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if output is None:
        output = payload.get("content")
    if isinstance(output, str):
        return output
    if output is None:
        return ""
    return json.dumps(output, ensure_ascii=False, sort_keys=True)


def _input_command(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("command", "cmd", "script"):
            if key in value:
                return str(value.get(key) or "")
    return ""


def classify_tool_command(tool_name: str, command: str = "") -> str:
    """Return a coarse, non-sensitive tool command class."""

    material = f"{tool_name}\n{command}".casefold()
    if any(
        token in material
        for token in (
            "pytest",
            "unittest",
            "run_tests.py",
            "cargo test",
            " tests\\",
            " tests/",
            "\ntests\\",
            "\ntests/",
        )
    ):
        return "test"
    if any(token in material for token in (" rg ", "\nrg ", "ripgrep", "select-string", "grep")):
        return "search"
    if any(token in material for token in ("get-content", "read_file", "view_image")):
        return "read"
    if any(token in material for token in (" git ", "\ngit ", "gh issue", "gh pr")):
        return "vcs"
    if "shell_command" in material or command:
        return "shell"
    if "web_search" in material:
        return "web_search"
    return "tool"


def parse_tool_exit_code(output_text: str) -> int | None:
    match = TOOL_EXIT_CODE_RE.search(output_text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _call_ref(call_id: str) -> str:
    return hashlib.sha1(call_id.encode("utf-8")).hexdigest()[:16] if call_id else ""


def extract_rollout_behavior_events(rollout: Path) -> list[dict[str, Any]]:
    """Extract structured tool/test behavior traces from a Codex rollout.

    The clean-source event lane records that a tool call happened and whether a
    bounded observation looked successful or failed. It stores hashes and coarse
    classes, not raw stdout, shell commands, full arguments, or local paths.
    """

    events: list[dict[str, Any]] = []
    current_turn = 0
    calls_by_ref: dict[str, dict[str, Any]] = {}
    for line_no, item in iter_jsonl(rollout):
        timestamp = item.get("timestamp")
        typ = item.get("type")
        payload = item.get("payload") or {}
        if typ == "event_msg" and payload.get("type") == "user_message":
            current_turn += 1
            continue
        if typ != "response_item" or not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype == "function_call":
            tool_name = _tool_name(payload)
            tool_input = _tool_input(payload)
            command = _input_command(tool_input)
            input_text = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
            call_ref = _call_ref(_tool_call_id(payload))
            event = {
                "line": line_no,
                "timestamp": timestamp,
                "turn_index": current_turn or None,
                "event_kind": "tool_call_requested",
                "tool_payload_kind": "function_call",
                "tool_name": tool_name,
                "call_ref": call_ref,
                "command_class": classify_tool_command(tool_name, command),
                "input_sha256": _sha256_text(input_text),
                "input_field_names": sorted(tool_input.keys()) if isinstance(tool_input, dict) else [],
                "behavior_backed": True,
            }
            if call_ref:
                calls_by_ref[call_ref] = event
            events.append(event)
            continue
        if ptype not in {"function_call_output", "web_search_call"}:
            continue

        output_text = _tool_output_text(payload)
        call_ref = _call_ref(_tool_call_id(payload))
        prior = calls_by_ref.get(call_ref, {})
        exit_code = parse_tool_exit_code(output_text)
        status = "unknown"
        hard_event_kind = "tool_call_observed"
        if exit_code is not None:
            status = "succeeded" if exit_code == 0 else "failed"
            hard_event_kind = "tool_call_succeeded" if exit_code == 0 else "tool_call_failed"
        elif ptype == "web_search_call":
            status = "succeeded"
            hard_event_kind = "tool_call_succeeded"
        tool_name = prior.get("tool_name") or _tool_name(payload)
        events.append(
            {
                "line": line_no,
                "timestamp": timestamp,
                "turn_index": current_turn or None,
                "event_kind": "tool_call_observed",
                "hard_event_kind": hard_event_kind,
                "tool_payload_kind": str(ptype),
                "tool_name": tool_name,
                "call_ref": call_ref,
                "command_class": prior.get("command_class")
                or classify_tool_command(str(tool_name), ""),
                "exit_code": exit_code,
                "status": status,
                "observation_sha256": _sha256_text(output_text),
                "behavior_backed": True,
            }
        )
    return events
