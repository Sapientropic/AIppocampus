"""Recovery payloads for last-recall source search failures."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.last_recall_actions import rerun_recall_action


def selector_recovery_payload(
    *,
    code: str,
    message: str,
    cue: str | None,
    query_text: str,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = [rerun_recall_action(cue)]
    if query_text:
        actions.append(
            foreground_shell_action(
                action_id="search_all_registered_sources",
                label="Search all registered sources",
                command=f"aippocampus search --all {shell_quote(query_text)} --json",
                why=(
                    "The recall selector is invalid, so search all registered sources "
                    "for this phrase rather than opening generic CLI help."
                ),
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            )
        )
        actions.append(
            foreground_shell_action(
                action_id="search_mutable_last_recall_without_selector",
                label="Search mutable last recall without selector",
                command=f"aippocampus search --from-last-recall {shell_quote(query_text)} --json",
                why=(
                    "Use only as a weaker same-machine fallback when the previous recall "
                    "result is still known to be current."
                ),
                mutation_risk="read_only",
                claim_boundary="last_recall_cache_is_mutable_fallback",
            )
        )
    else:
        actions.append(
            foreground_template_action(
                action_id="search_all_registered_sources",
                label="Search all registered sources",
                command_template='aippocampus search --all "{distinctive_phrase}" --json',
                requires=["distinctive_phrase"],
                why="Search all registered sources when the selector path is invalid.",
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            )
        )
    payload: dict[str, Any] = {
        "kind": "aippocampus_last_recall_source_search",
        "ok": False,
        "status": "cannot_verify",
        "search_scope": "last_recall_candidate_sources",
        "query_text": query_text,
        "error": {"code": code, "message": message},
        "selector_recovery": {
            "state": "invalid_recall_selector",
            "rerun_recall_for_fresh_selector": True,
            "last_recall_without_selector_is_weaker_fallback": True,
        },
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
            "last_recall_route_set_required": True,
        },
        "privacy": {
            "paths_included": False,
            "path_redaction": LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": False,
            "opaque_reopen_tokens_emitted": False,
        },
    }
    payload.update(canonical_foreground_action_fields(actions[0], safe_next_actions=actions))
    return redact_sensitive_values(redact_private_paths(payload))

