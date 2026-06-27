"""APW meta-echo recovery for compact recall foreground actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices

META_ECHO_REASON_CODE = "memory_product_meta_echo_demoted"


def maybe_promote_original_anchor_search(
    *,
    associative_path_fallback: Mapping[str, Any] | None,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    recovery_cue: str,
    source_open_primary_action: Callable[[Mapping[str, Any]], bool],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prefer source search when APW found a memory-product quote echo.

    Current clean-source discussion about AIppocampus often quotes older user
    wording while debating recall UX. Deepening that quote is technically
    source-backed but product-wrong; compact recall should search registered
    sources for the original anchor before offering lower-confidence routes.
    """

    if not _meta_echo_search_action_needed(associative_path_fallback):
        return foreground_action, safe_next_actions
    registry_fallback = recall_choices.registry_source_search_fallback_action(recovery_cue)
    if not registry_fallback or source_open_primary_action(foreground_action):
        return foreground_action, safe_next_actions
    ordinary_recovery_action = core.strip_empty(
        normalize_foreground_action(foreground_action),
        drop_empty_dicts=True,
    )
    if ordinary_recovery_action:
        safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
    safe_next_actions = _without_action_duplicate(safe_next_actions, registry_fallback)
    registry_fallback["route_choice_posture"] = (
        "apw_meta_echo_demoted_original_source_search_first"
    )
    registry_fallback["why"] = (
        "APW found a current clean-source echo of the cue inside memory-product "
        "discussion; search registered sources for the original anchor before "
        "deepening lower-confidence routes."
    )
    if isinstance(associative_path_fallback, dict):
        associative_path_fallback["primary_action"] = registry_fallback.get("id")
        associative_path_fallback["echo_source_demoted"] = True
    return registry_fallback, safe_next_actions


def promote_original_anchor_search_from_safe_actions(
    *,
    source_anchor_gate: Mapping[str, Any] | None,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Promote an already-built original-anchor search over weak echo paths."""

    if not isinstance(source_anchor_gate, Mapping) or source_anchor_gate.get("status") != "blocked":
        return foreground_action, safe_next_actions
    foreground_id = str(foreground_action.get("id") or foreground_action.get("action_id") or "")
    if foreground_id == "search_registry_sources_for_original_cue_anchors":
        return foreground_action, safe_next_actions
    if foreground_id not in {
        "deepen_top_route_low_confidence",
        "open_discussion_atlas_pointer",
        "reopen_background_finding_source_route",
    }:
        return foreground_action, safe_next_actions
    for index, action in enumerate(safe_next_actions):
        action_id = str(action.get("id") or action.get("action_id") or "")
        if action_id != "search_registry_sources_for_original_cue_anchors":
            continue
        promoted = dict(action)
        promoted["route_choice_posture"] = "original_anchor_search_first"
        promoted["why"] = (
            str(promoted.get("why") or "").rstrip(".")
            + "; promoted because the current primary route may be a weak deepen or quote echo."
        )
        remaining = [*safe_next_actions[:index], *safe_next_actions[index + 1 :]]
        ordinary_action = core.strip_empty(normalize_foreground_action(foreground_action))
        return promoted, [ordinary_action, *remaining] if ordinary_action else remaining
    return foreground_action, safe_next_actions


def _without_action_duplicate(
    actions: list[dict[str, Any]],
    primary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    primary_id = str(primary.get("id") or primary.get("action_id") or "")
    primary_command = str(primary.get("command") or primary.get("command_template") or "")
    return [
        action
        for action in actions
        if (
            str(action.get("id") or action.get("action_id") or ""),
            str(action.get("command") or action.get("command_template") or ""),
        )
        != (primary_id, primary_command)
    ]


def _meta_echo_search_action_needed(
    associative_path_fallback: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(associative_path_fallback, Mapping):
        return False
    if str(associative_path_fallback.get("status") or "") != "abstained":
        return False
    reason_codes = {
        str(code).strip()
        for code in associative_path_fallback.get("reason_codes") or []
        if str(code).strip()
    }
    return META_ECHO_REASON_CODE in reason_codes
