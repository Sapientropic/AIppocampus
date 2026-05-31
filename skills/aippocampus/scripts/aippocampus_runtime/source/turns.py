"""Shared source-normalized message and turn helpers."""

from __future__ import annotations

import hashlib
from typing import Any


def message_digest(role: str, phase: str, text: str) -> str:
    return hashlib.sha1((role + "\0" + phase + "\0" + text).encode("utf-8")).hexdigest()


def empty_turn(turn_index: int, line_no: int | None, timestamp: str | None) -> dict[str, Any]:
    return {
        "id": turn_index,
        "user_line": line_no,
        "user_timestamp": timestamp,
        "final_line": None,
        "final_timestamp": None,
        "fallback_assistant_line": None,
        "fallback_assistant_timestamp": None,
        "commentary_count": 0,
        "tool_call_count": 0,
        "tool_output_count": 0,
        "start_line": line_no,
        "end_line": line_no,
    }


__all__ = ["empty_turn", "message_digest"]
