"""Discussion/current-source guards for compact agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.source.discussion_atlas_pointer import discussion_atlas_action


def _without_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", {})}


def current_source_probe_has_match(payload: Mapping[str, Any]) -> bool:
    probe = payload.get("current_source_anchor_probe")
    if not isinstance(probe, Mapping):
        return False
    try:
        return int(probe.get("match_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def maybe_promote_discussion_atlas_action(
    *,
    payload: Mapping[str, Any],
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    status: str,
    labels_low_specificity: bool,
    recovery_cue: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    pointer = payload.get("discussion_atlas_pointer")
    action = discussion_atlas_action(pointer if isinstance(pointer, dict) else None, query=recovery_cue)
    if not action:
        return foreground_action, safe_next_actions, pointer
    if str(foreground_action.get("id") or "") == "reopen_already_opened_route_context":
        return foreground_action, safe_next_actions, pointer
    should_promote = (
        status == "no_routes"
        or labels_low_specificity
        or str(foreground_action.get("id") or "")
        in {
            "search_registry_sources_for_original_cue_anchors",
            "refine_low_specificity_recall_cue",
            "open_repo_familiarity_source",
        }
        or str(foreground_action.get("tool_name") or "") == "search_memory"
    )
    if not should_promote:
        return foreground_action, safe_next_actions, pointer
    ordinary = _without_empty(normalize_foreground_action(foreground_action))
    if ordinary:
        safe_next_actions = [ordinary, *safe_next_actions]
    return action, safe_next_actions, pointer
