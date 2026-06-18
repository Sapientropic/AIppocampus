"""Human-output action helpers for recall CLI renderers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.cli.recovery import action_command_text

DEFAULT_RECALL_CUE_COMMAND = 'aippocampus agent recall "old decision or handoff cue" --json'


def recall_human_next_hint(payload: Mapping[str, Any]) -> str:
    suggested = str(payload.get("suggested_next_command") or "").strip()
    if suggested and "aippo-nav:" not in suggested and len(suggested) <= 160:
        return suggested
    action = payload.get("agent_next_action")
    if isinstance(action, Mapping):
        command = action_command_text(action).strip()
        if command:
            return command
    return DEFAULT_RECALL_CUE_COMMAND
