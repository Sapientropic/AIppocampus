"""Discussion/current-source guards for compact agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.source.discussion_atlas_pointer import discussion_atlas_action


def _discussion_pointer_is_explicit(pointer: Any) -> bool:
    return isinstance(pointer, Mapping) and pointer.get("match_basis") == "explicit_discussion_reference"


def _local_source_followthrough_action(action: Mapping[str, Any]) -> bool:
    """Return true when the current primary can already open local source evidence.

    Discussion Atlas rows are public navigation hints. They can rescue a generic
    recovery card, but they must not displace the direct local source path that
    recall just produced; doing so makes the foreground agent walk away from the
    source-backed follow-through the user asked this product to preserve.
    """

    tool_name = str(action.get("tool_name") or "")
    if tool_name in {"agent_deepen", "recall_deepen", "get_turn_context"}:
        return True
    action_id = str(action.get("id") or action.get("action_id") or "")
    return action_id in {
        "deepen_associative_path_fallback",
        "reopen_already_opened_route_context",
        "open_registry_search_source_window",
        "reopen_search_match_source",
        "use_opened_source_window",
    }


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
    followup_actions: list[dict[str, Any]],
    status: str,
    labels_low_specificity: bool,
    recovery_cue: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    pointer = payload.get("discussion_atlas_pointer")
    action = discussion_atlas_action(pointer if isinstance(pointer, dict) else None, query=recovery_cue)
    if not action:
        return foreground_action, followup_actions, pointer
    if (
        _local_source_followthrough_action(foreground_action)
        and not _discussion_pointer_is_explicit(pointer)
    ):
        return foreground_action, followup_actions, pointer
    explicit_discussion = _discussion_pointer_is_explicit(pointer)
    should_promote = (
        explicit_discussion
        or status == "no_routes"
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
        return foreground_action, followup_actions, pointer
    ordinary = core.strip_empty(
        normalize_foreground_action(foreground_action),
        drop_empty_dicts=True,
    )
    if ordinary:
        followup_actions = [ordinary, *followup_actions]
    return action, followup_actions, pointer
