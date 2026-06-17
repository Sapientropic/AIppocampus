"""Foreground action cards for the self-note CLI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action


def append_error_payload(
    code: str,
    *,
    privacy_boundary: Mapping[str, Any],
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    messages = {
        "agent_self_note_empty": "self-note append needs a short note, --stdin input, or a source-backed cue.",
        "agent_self_note_raw_payload_rejected": "self-note append refused raw tool/log payload text.",
    }
    append_note_action: dict[str, Any] = {
        "id": "append_direction_only_note",
        "label": "Append a short direction-only self-note",
        "command_template": 'aippocampus self-note append --current-thread "{note_text}" --json',
        "requires": ["note_text"],
        "why": "Use only for low-authority handoff, posture, or route scent; reopen source for factual claims.",
        "mutation_risk": "explicit_self_note_write",
        "claim_boundary": "direction_only_note_not_source_truth",
    }
    stdin_note_action = foreground_shell_action(
        action_id="append_direction_only_note_from_stdin",
        label="Pipe a short direction-only note",
        command="aippocampus self-note append --current-thread --stdin --json",
        why="Use when the note text is easier to provide through stdin; keep it summary-level.",
        mutation_risk="explicit_self_note_write",
        claim_boundary="direction_only_note_not_source_truth",
    )
    recall_action: dict[str, Any] = {
        "id": "use_source_backed_recall_instead",
        "label": "Use recall when you need source-backed evidence",
        "command_template": 'aippocampus agent recall "{cue}" --json',
        "requires": ["cue"],
        "why": "Self-notes are scent only; recall/deepen is the path for evidence-backed claims.",
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }
    search_action: dict[str, Any] = {
        "id": "search_exact_phrase_instead",
        "label": "Search clean source for an exact phrase",
        "command_template": 'aippocampus search "{exact_phrase}" --json',
        "requires": ["exact_phrase"],
        "why": "Use when the cue is a phrase from source material rather than a direction-only margin note.",
        "mutation_risk": "read_only",
        "claim_boundary": "source_reopen_required_before_claim",
    }
    next_actions: dict[str, dict[str, Any]] = {
        "agent_self_note_empty": append_note_action,
        "agent_self_note_raw_payload_rejected": {
            "id": "summarize_direction_only_note",
            "label": "Summarize the breadcrumb before writing a self-note",
            "command_template": (
                'aippocampus self-note append --current-thread '
                '"{short_direction_only_summary}" --json'
            ),
            "requires": ["short_direction_only_summary"],
            "why": "Do not store raw tool output, logs, or source text as a self-note.",
            "mutation_risk": "explicit_self_note_write",
            "claim_boundary": "direction_only_note_not_source_truth",
        },
    }
    safe_next_actions = {
        "agent_self_note_empty": [
            append_note_action,
            dict(stdin_note_action),
            recall_action,
            search_action,
        ],
        "agent_self_note_raw_payload_rejected": [
            next_actions["agent_self_note_raw_payload_rejected"],
            recall_action,
            search_action,
        ],
    }
    error: dict[str, Any] = {"code": code, "message": messages.get(code, code)}
    payload = {
        "kind": "aippocampus_agent_self_note_append",
        "ok": False,
        "error": error,
        "agent_next_action": next_actions.get(code, recall_action),
        "safe_next_actions": safe_next_actions.get(code, [recall_action, search_action]),
        "privacy_boundary": dict(privacy_boundary),
    }
    if details:
        error["details"] = {
            key: value
            for key, value in details.items()
            if isinstance(value, (str, int, float, bool))
        }
    return payload


def format_action_for_human(action: Any) -> list[str]:
    if not isinstance(action, Mapping):
        return [str(action)]
    lines = [str(action.get("label") or action.get("id") or "Choose a next action")]
    command = action.get("command")
    command_template = action.get("command_template")
    requires = action.get("requires")
    if command:
        lines.append("command: " + str(command))
    if command_template:
        if isinstance(requires, list) and requires:
            lines.append("requires: " + ", ".join(str(item) for item in requires))
        lines.append("template: " + str(command_template))
    return lines
