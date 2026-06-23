"""Repo-familiarity foreground promotion for compact agent recall."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.mcp import agent_recall_discussion_projection as discussion_projection
from aippocampus_runtime.mcp import agent_recall_recovery_projection as recovery_projection


def maybe_promote_repo_familiarity_action(
    *,
    payload: Mapping[str, Any],
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    repo_familiarity_fallback: dict[str, Any] | None,
    repo_familiarity_action: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    if not (
        repo_familiarity_action
        and not discussion_projection.current_source_probe_has_match(payload)
        and recovery_projection.repo_familiarity_query_anchor_alignment(
            repo_familiarity_fallback
        )
        != "no_overlap"
        and recovery_projection.repo_familiarity_should_replace_foreground_action(
            foreground_action
        )
    ):
        return foreground_action, safe_next_actions, None
    ordinary = core.strip_empty(
        normalize_foreground_action(foreground_action),
        drop_empty_dicts=True,
    )
    ordinary_action_id = str(ordinary.get("id") or ordinary.get("action_id") or "")
    if ordinary:
        safe_next_actions = [ordinary, *safe_next_actions]
    foreground_action = repo_familiarity_action
    if isinstance(repo_familiarity_fallback, dict):
        repo_familiarity_fallback["primary_action"] = "open_repo_familiarity_source"
        if ordinary_action_id:
            repo_familiarity_fallback["ordinary_recovery_action_id"] = ordinary_action_id
    return foreground_action, safe_next_actions, repo_familiarity_fallback
