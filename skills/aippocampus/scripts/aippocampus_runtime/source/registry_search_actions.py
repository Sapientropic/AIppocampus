from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import (
    foreground_shell_action,
    foreground_template_action,
)


def registry_search_actions(
    *,
    query: str,
    has_matches: bool,
    first_match: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if has_matches and first_match:
        command = str(first_match.get("reopen_command") or "").strip()
        actions = [
            foreground_shell_action(
                action_id="open_registry_search_source_window",
                label="Open the first registry search source window",
                command=command,
                why=(
                    "Registry search found capped snippets; open the selected "
                    "bounded source window before quoting or making strong claims."
                ),
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            ),
            foreground_template_action(
                action_id="diagnostic_registry_search_with_paths",
                label="Rerun registry search with local paths",
                command_template='aippocampus search --all "{exact_phrase}" --include-paths --json',
                requires=["exact_phrase"],
                why="Local diagnostic opt-in for finding the exact clean-source artifact.",
                mutation_risk="read_only",
                claim_boundary="local_paths_are_operator_diagnostics",
            ),
        ]
        return [
            action for action in actions if action.get("command") or action.get("command_template")
        ]
    return [
        foreground_template_action(
            action_id="refine_registry_exact_search",
            label="Refine registry exact search",
            command_template='aippocampus search --all "{distinctive_phrase}" --json',
            requires=["distinctive_phrase"],
            why="No registry snippet matched; try a more distinctive phrase or term set.",
            mutation_risk="read_only",
            claim_boundary="search_miss_is_not_absence_of_memory",
        ),
        foreground_template_action(
            action_id="recall_before_exact_search",
            label="Use recall for vague continuity cues",
            command_template='aippocampus agent recall "{cue}" --json',
            requires=["cue"],
            why="Use recall when the user remembers the situation but not exact wording.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
        foreground_shell_action(
            action_id="check_registered_sources",
            label="Check registered source status",
            command="aippocampus onboard --provider auto --status --json",
            why="Use this if the expected old source may not be registered locally.",
            mutation_risk="read_only",
            claim_boundary="host_status_not_source_evidence",
        ),
    ]
