"""Foreground action cards for the read-only Cognitive Observatory."""

from __future__ import annotations

from typing import Any


def foreground_action(*, no_rows: bool = False) -> dict[str, Any]:
    if no_rows:
        return {
            "id": "no_observatory_rows_to_route",
            "kind": "no_op",
            "no_op": True,
            "continue_without_command": True,
            "mutation_risk": "none",
            "claim_boundary": "observatory_readout_not_source_truth_or_control_plane",
            "why": "No ready/useful observatory rows are present in this compact readout.",
        }
    return {
        "id": "use_observatory_as_read_only_navigation",
        "kind": "shell_command",
        "command": "aippocampus observatory --summary-json",
        "mutation_risk": "read_only",
        "claim_boundary": "observatory_readout_not_source_truth_or_control_plane",
        "why": "Use ready/useful rows as navigation only; reopen source before claims and use owner tools for mutation.",
    }


def empty_readout_next_actions() -> list[dict[str, Any]]:
    return [
        foreground_action(no_rows=True),
        {
            "id": "check_warm_ambient_status",
            "kind": "shell_command",
            "command": "aippocampus warm status --json",
            "mutation_risk": "read_only",
            "claim_boundary": "warm_ambient_status_not_source_truth_or_control_plane",
            "why": "Check whether optional warm ambient can provide a foreground route signal.",
        },
        {
            "id": "inspect_background_guidance_for_task",
            "kind": "template_command",
            "command_template": 'aippocampus agent background "{task_cue}" --json',
            "requires": ["task_cue"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "background_navigation_not_source_truth",
            "why": "Use a real task cue to inspect reviewed Dream/subconscious findings without starting a broad run.",
        },
        {
            "id": "attach_sleep_cycle_summary",
            "kind": "template_command",
            "command_template": 'aippocampus observatory --sleep-cycle "{sleep_cycle_json}" --summary-json',
            "requires": ["sleep_cycle_json"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "observatory_readout_not_source_truth_or_control_plane",
            "why": "Attach a known local sleep-cycle JSON summary when one already exists.",
        },
    ]
