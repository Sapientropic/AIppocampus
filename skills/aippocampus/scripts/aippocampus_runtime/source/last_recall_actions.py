"""Foreground actions for last-recall-scoped source search."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.recall.agent_recall_cache import recall_selector_cache_path


def selector_cache_path(
    *,
    recall_selector: str | None,
    last_recall_path: str | Path | None,
) -> str | Path | None:
    selector = clean_recall_selector(recall_selector)
    if not selector:
        return last_recall_path
    return recall_selector_cache_path(selector, last_recall_path_value=last_recall_path)


def clean_recall_selector(recall_selector: str | None) -> str:
    return str(recall_selector or "").strip()


def deepen_command_for_request(request_index: int, recall_selector: str | None) -> str:
    selector = clean_recall_selector(recall_selector)
    if selector:
        return (
            f"aippocampus agent deepen --request {request_index} "
            f"--recall-selector {shell_quote(selector)} --json"
        )
    return f"aippocampus agent deepen --request {request_index} --last-recall --json"


def deepen_action_for_request(
    request_index: int,
    recall_selector: str | None,
    *,
    action_id: str,
    why: str,
) -> dict[str, Any]:
    selector = clean_recall_selector(recall_selector)
    if selector:
        action = foreground_shell_action(
            action_id=action_id,
            label=f"Deepen recall route {request_index}",
            command=deepen_command_for_request(request_index, selector),
            why=why,
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_claim",
        )
        action["arguments"] = {
            "request_index": request_index,
            "recall_selector": selector,
        }
    else:
        action = foreground_template_action(
            action_id=action_id,
            label=f"Deepen recall route {request_index}",
            command_template=(
                "aippocampus agent deepen --request "
                f"{request_index} --recall-selector {{recall_selector}} --json"
            ),
            requires=["recall_selector"],
            why=why,
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_claim",
        )
        action["arguments"] = {"request_index": request_index}
        action["last_recall_fallback_command"] = (
            f"aippocampus agent deepen --request {request_index} --last-recall --json"
        )
        action["last_recall_fallback_boundary"] = (
            "--last-recall reads a mutable same-machine cache; prefer "
            "--recall-selector from the recall result when it is available."
        )
    return action


def search_command_template(
    *,
    recall_selector: str | None,
    request_scoped: bool,
    phrase_placeholder: str,
) -> dict[str, Any]:
    selector = clean_recall_selector(recall_selector)
    request_part = "--request {request_index} " if request_scoped else ""
    requires = ["request_index", phrase_placeholder] if request_scoped else [phrase_placeholder]
    if selector:
        return {
            "command_template": (
                "aippocampus search --from-last-recall "
                f"--recall-selector {shell_quote(selector)} "
                f"{request_part}\"{{{phrase_placeholder}}}\" --json"
            ),
            "requires": requires,
            "arguments": {"recall_selector": selector},
        }
    return {
        "command_template": (
            f"aippocampus search --from-last-recall {request_part}"
            f"\"{{{phrase_placeholder}}}\" --json"
        ),
        "requires": requires,
        "last_recall_fallback_boundary": (
            "Bare --from-last-recall reads a mutable same-machine cache; prefer "
            "--recall-selector from the recall result when it is available."
        ),
    }


def rerun_recall_action(cue: str | None) -> dict[str, Any]:
    clean_cue = str(cue or "").strip()
    if clean_cue:
        return foreground_shell_action(
            action_id="rerun_recall_for_fresh_search_set",
            label="Rerun recall for fresh route search",
            command=f"aippocampus agent recall {shell_quote(clean_cue)} --json --detail full",
            why="The last recall route set is unavailable or stale; rerun recall before exact route search.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    return foreground_template_action(
        action_id="rerun_recall_for_fresh_search_set",
        label="Rerun recall for fresh route search",
        command_template='aippocampus agent recall "{cue}" --json --detail full',
        requires=["cue"],
        why="The last recall route set is unavailable or stale; rerun recall before exact route search.",
        mutation_risk="read_only",
        claim_boundary="no_claim_before_reopen",
    )


def actions_for_last_recall_search(
    *,
    query_text: str,
    has_matches: bool,
    first_match: Mapping[str, Any] | None,
    recall_selector: str | None = None,
    partial_unavailable_no_matches: bool = False,
    recall_cue: str | None = None,
) -> list[dict[str, Any]]:
    if has_matches and first_match:
        one_route_template = search_command_template(
            recall_selector=recall_selector,
            request_scoped=True,
            phrase_placeholder="exact_phrase",
        )
        return [
            deepen_action_for_request(
                int(first_match.get("request_index") or 1),
                recall_selector,
                action_id="deepen_last_recall_search_hit",
                why=(
                    "Exact wording matched inside a last-recall candidate route; "
                    "deepen that route before quoting or making strong claims."
                ),
            ),
            foreground_template_action(
                action_id="search_one_last_recall_request",
                label="Search one recalled route",
                command_template=str(one_route_template["command_template"]),
                requires=list(one_route_template["requires"]),
                why="Use this when the relevant numbered recall route is known.",
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            )
            | {
                key: value
                for key, value in one_route_template.items()
                if key not in {"command_template", "requires"}
            },
        ]
    refine_template = search_command_template(
        recall_selector=recall_selector,
        request_scoped=False,
        phrase_placeholder="distinctive_phrase",
    )
    no_match_actions = [
        foreground_template_action(
            action_id="refine_last_recall_exact_search",
            label="Refine search inside last recall routes",
            command_template=str(refine_template["command_template"]),
            requires=list(refine_template["requires"]),
            why="The last recall route set did not contain this wording; try a more distinctive phrase.",
            mutation_risk="read_only",
            claim_boundary="search_miss_is_not_absence_of_memory",
        )
        | {
            key: value
            for key, value in refine_template.items()
            if key not in {"command_template", "requires"}
        },
        foreground_shell_action(
            action_id="search_all_registered_sources",
            label="Search all registered sources",
            command=f"aippocampus search --all {shell_quote(query_text)} --json",
            why="Use only if the expected evidence may be outside the routes returned by the last recall.",
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_claim",
        ),
    ]
    if partial_unavailable_no_matches:
        return [rerun_recall_action(recall_cue), *no_match_actions]
    return no_match_actions


__all__ = [
    "actions_for_last_recall_search",
    "clean_recall_selector",
    "deepen_action_for_request",
    "rerun_recall_action",
    "selector_cache_path",
]
