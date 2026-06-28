"""Freshness helpers for health reports.

These helpers compare the current visible rollout surface with generated
clean-source and index manifests. They deliberately mirror clean-source's
keep/drop policy for user + final/fallback assistant messages, so routine
commentary that clean-source intentionally drops does not become a false dirty
signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.host_internal_filter import filter_host_internal_clean_text
from aippocampus_runtime.source.rollout import normalize_rollout


@dataclass(frozen=True)
class RolloutVisibilityStats:
    message_count: int
    last_message_line: int | None
    expected_clean_source_message_count: int
    expected_clean_source_turn_count: int
    last_clean_source_line: int | None


def clean_source_expected_stats(
    messages: list[dict[str, Any]], turns: list[dict[str, Any]]
) -> tuple[int, int, int | None]:
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for message in messages:
        turn_index = message.get("turn_index")
        if isinstance(turn_index, int):
            by_turn.setdefault(turn_index, []).append(message)

    kept_count = 0
    last_line = None
    for turn in turns:
        turn_id = turn.get("id")
        if not isinstance(turn_id, int):
            continue
        items = by_turn.get(turn_id, [])
        user = next((item for item in items if item.get("role") == "user"), None)
        assistant = next((item for item in items if item.get("is_final")), None)
        if assistant is None:
            fallback_line = turn.get("fallback_assistant_line")
            assistant = next((item for item in items if item.get("line") == fallback_line), None)
        for item in (user, assistant):
            if not item:
                continue
            text, _host_internal_filtered = filter_host_internal_clean_text(
                item.get("text") or ""
            )
            if not str(text or "").strip():
                continue
            kept_count += 1
            line = item.get("line")
            if isinstance(line, int):
                last_line = line if last_line is None else max(last_line, line)
    return kept_count, len(turns), last_line


def rollout_visibility_stats(rollout: Path) -> RolloutVisibilityStats:
    messages, turns = normalize_rollout(rollout, include_tools=False)
    expected_clean_count, expected_turn_count, last_clean_line = clean_source_expected_stats(
        messages, turns
    )
    return RolloutVisibilityStats(
        message_count=len(messages),
        last_message_line=messages[-1]["line"] if messages else None,
        expected_clean_source_message_count=expected_clean_count,
        expected_clean_source_turn_count=expected_turn_count,
        last_clean_source_line=last_clean_line,
    )
