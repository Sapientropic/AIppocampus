"""Foreground action cards for the self-note CLI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)


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
    append_note_action: dict[str, Any] = foreground_template_action(
        action_id="append_direction_only_note",
        label="Append a short direction-only self-note",
        command_template='aippocampus self-note append --current-thread "{note_text}" --json',
        requires=["note_text"],
        why="Use only for low-authority handoff, posture, or route scent; reopen source for factual claims.",
        mutation_risk="explicit_self_note_write",
        claim_boundary="direction_only_note_not_source_truth",
    )
    stdin_note_action = foreground_shell_action(
        action_id="append_direction_only_note_from_stdin",
        label="Pipe a short direction-only note",
        command="aippocampus self-note append --current-thread --stdin --json",
        why="Use when the note text is easier to provide through stdin; keep it summary-level.",
        mutation_risk="explicit_self_note_write",
        claim_boundary="direction_only_note_not_source_truth",
    )
    recall_action: dict[str, Any] = foreground_template_action(
        action_id="use_source_backed_recall_instead",
        label="Use recall when you need source-backed evidence",
        command_template='aippocampus agent recall "{cue}" --json',
        requires=["cue"],
        why="Self-notes are scent only; recall/deepen is the path for evidence-backed claims.",
        mutation_risk="read_only",
        claim_boundary="no_claim_before_reopen",
    )
    search_action: dict[str, Any] = foreground_template_action(
        action_id="search_exact_phrase_instead",
        label="Search clean source for an exact phrase",
        command_template='aippocampus search "{exact_phrase}" --json',
        requires=["exact_phrase"],
        why="Use when the cue is a phrase from source material rather than a direction-only margin note.",
        mutation_risk="read_only",
        claim_boundary="source_reopen_required_before_claim",
    )
    next_actions: dict[str, dict[str, Any]] = {
        "agent_self_note_empty": append_note_action,
        "agent_self_note_raw_payload_rejected": foreground_template_action(
            action_id="summarize_direction_only_note",
            label="Summarize the breadcrumb before writing a self-note",
            command_template=(
                'aippocampus self-note append --current-thread '
                '"{short_direction_only_summary}" --json'
            ),
            requires=["short_direction_only_summary"],
            why="Do not store raw tool output, logs, or source text as a self-note.",
            mutation_risk="explicit_self_note_write",
            claim_boundary="direction_only_note_not_source_truth",
        ),
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
    primary_action = next_actions.get(code, recall_action)
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=safe_next_actions.get(code, [primary_action, recall_action, search_action]),
    )
    payload = {
        "kind": "aippocampus_agent_self_note_append",
        "ok": False,
        "status": "needs_input" if code == "agent_self_note_empty" else "rejected",
        "error": error,
        **action_fields,
        "privacy_boundary": dict(privacy_boundary),
    }
    if details:
        error["details"] = {
            key: value
            for key, value in details.items()
            if isinstance(value, (str, int, float, bool))
        }
    return payload


def self_note_lookup_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "list_notes",
            "label": "List scoped self-notes",
            "command": "aippocampus self-note list --json",
            "mutation_risk": "read_only",
            "claim_boundary": "direction_only_not_source_truth",
            "why": "Use this to pick a concrete note_id without broadening scope.",
        },
        {
            "id": "search_notes",
            "label": "Search scoped self-notes",
            "command_template": 'aippocampus self-note search "{cue}" --json',
            "template_only": True,
            "requires": ["cue"],
            "mutation_risk": "read_only",
            "claim_boundary": "direction_only_not_source_truth",
            "why": "Use when you have a cue for weak direction-only atmosphere.",
        },
        {
            "id": "source_backed_recall",
            "label": "Use source-backed recall instead",
            "command_template": 'aippocampus agent recall "{cue}" --json',
            "template_only": True,
            "requires": ["cue"],
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "why": "Use for facts, continuity claims, or exact source-backed context.",
        },
    ]


def self_note_empty_list_actions() -> list[dict[str, Any]]:
    continue_action = {
        "id": "continue_without_self_notes",
        "label": "Continue without self-notes",
        "continue_without_command": True,
        "mutation_risk": "none",
        "claim_boundary": "direction_only_empty_state_not_source_truth",
        "why": (
            "No scoped self-notes exist; continue, or use source-backed recall when "
            "facts or continuity matter."
        ),
    }
    lookup_actions = self_note_lookup_actions()
    return [continue_action, lookup_actions[2], lookup_actions[1]]


def empty_notes_state(command: str, query: str = "") -> dict[str, Any]:
    actions = self_note_lookup_actions()
    if command == "search":
        return {
            "decision": "empty",
            "message": "No agent self-note matched this cue.",
            "query": query,
            "agent_next_action": actions[1],
            "safe_next_actions": actions,
            "authority": "direction_only_empty_state",
        }
    actions = self_note_empty_list_actions()
    return {
        "decision": "empty",
        "message": "No agent self-notes have been recorded yet.",
        "agent_next_action": actions[0],
        "safe_next_actions": actions,
        "authority": "direction_only_empty_state",
    }


def self_note_lookup_action_fields(*, command: str) -> dict[str, Any]:
    actions = self_note_lookup_actions()
    primary_index = 1 if command == "search" else 0
    return canonical_foreground_action_fields(actions[primary_index], safe_next_actions=actions)


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
