from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import (
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.source.artifact_role import match_is_demoted_artifact


def registry_search_actions(
    *,
    query: str,
    has_matches: bool,
    first_match: Mapping[str, Any] | None,
    useful_target_hit: bool = True,
    first_match_usefulness_status: str = "",
    low_coverage_only_matches: bool = False,
) -> list[dict[str, Any]]:
    if low_coverage_only_matches:
        return [
            foreground_shell_action(
                action_id="broaden_registry_search_for_query_anchors",
                label="Broaden registry search",
                command=(
                    f"aippocampus search --all {shell_quote(query)} "
                    "--search-budget deep --json"
                ),
                why=(
                    "Registry search found nearby snippets, but none carried the "
                    "distinctive query anchors together; search deeper or refine the phrase "
                    "before opening a source."
                ),
                mutation_risk="read_only",
                claim_boundary="search_matches_not_target_evidence",
            ),
            foreground_template_action(
                action_id="refine_registry_exact_search",
                label="Refine registry exact search",
                command_template='aippocampus search --all "{distinctive_phrase}" --json',
                requires=["distinctive_phrase"],
                why="Use a more distinctive phrase before treating nearby registry hits as source evidence.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ]
    if has_matches and first_match:
        if match_is_demoted_artifact(first_match):
            return [
                foreground_shell_action(
                    action_id="broaden_registry_search_for_topic_bearing_hit",
                    label="Broaden registry search",
                    command=(
                        f"aippocampus search --all {shell_quote(query)} "
                        "--search-budget deep --json"
                    ),
                    why=(
                        "The first registry hit looks like validation, fixture, or closeout "
                        "material; use diagnostic search before treating it as the target source."
                    ),
                    mutation_risk="read_only",
                    claim_boundary="search_hit_not_yet_topic_bearing_source",
                ),
                foreground_template_action(
                    action_id="recall_before_artifact_hit",
                    label="Use recall before artifact hit",
                    command_template='aippocampus agent recall "{cue}" --json',
                    requires=["cue"],
                    why="Use a richer cue when exact search mostly finds diagnostic artifacts.",
                    mutation_risk="read_only",
                    claim_boundary="no_claim_before_reopen",
                ),
            ]
        if not useful_target_hit:
            if first_match_usefulness_status == "identifier_not_found":
                return [
                    foreground_template_action(
                        action_id="refine_registry_identifier_search",
                        label="Search a different source identifier",
                        command_template='aippocampus search --all "{source_identifier}" --json',
                        requires=["source_identifier"],
                        why=(
                            "The query looks like a source identifier, but the first registry hit "
                            "did not contain that exact identifier. Do not open a fuzzy hit as evidence."
                        ),
                        mutation_risk="read_only",
                        claim_boundary="exact_identifier_not_found_in_registry_hit",
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
            if first_match_usefulness_status == "source_route_not_reopenable":
                return [
                    foreground_shell_action(
                        action_id="broaden_registry_search_for_reopenable_source",
                        label="Broaden registry search",
                        command=(
                            f"aippocampus search --all {shell_quote(query)} "
                            "--search-budget deep --json"
                        ),
                        why=(
                            "The first registry hit lacks a stable clean-source reopen key; "
                            "search deeper before treating it as source evidence."
                        ),
                        mutation_risk="read_only",
                        claim_boundary="search_hit_not_reopenable_source",
                    ),
                    foreground_template_action(
                        action_id="refine_registry_exact_search",
                        label="Refine registry exact search",
                        command_template='aippocampus search --all "{distinctive_phrase}" --json',
                        requires=["distinctive_phrase"],
                        why=(
                            "Use a phrase that can reopen a clean-source window, not only an index hit."
                        ),
                        mutation_risk="read_only",
                        claim_boundary="no_claim_before_reopen",
                    ),
                ]
            return [
                foreground_shell_action(
                    action_id="broaden_registry_search_for_query_anchors",
                    label="Broaden registry search",
                    command=(
                        f"aippocampus search --all {shell_quote(query)} "
                        "--search-budget deep --json"
                    ),
                    why=(
                        "Registry search found nearby snippets, but the first hit does not carry "
                        "the distinctive query anchors; search deeper before opening a source."
                    ),
                    mutation_risk="read_only",
                    claim_boundary="search_matches_not_target_evidence",
                ),
                foreground_template_action(
                    action_id="refine_registry_exact_search",
                    label="Refine registry exact search",
                    command_template='aippocampus search --all "{distinctive_phrase}" --json',
                    requires=["distinctive_phrase"],
                    why="Use a more distinctive phrase before treating nearby registry hits as source evidence.",
                    mutation_risk="read_only",
                    claim_boundary="no_claim_before_reopen",
                ),
            ]
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
