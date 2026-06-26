"""Reviewed-background recovery promotion for compact agent recall cards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import normalize_foreground_action


def _action_id(action: Mapping[str, Any]) -> str:
    return str(action.get("id") or action.get("action_id") or "")


def _unique_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        normalized = core.strip_empty(normalize_foreground_action(action), drop_empty_dicts=True)
        if not normalized:
            continue
        key = (
            str(normalized.get("id") or ""),
            str(normalized.get("command") or normalized.get("command_template") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _compact_background_recovery(card: Mapping[str, Any]) -> dict[str, Any] | None:
    action = card.get("foreground_action")
    if not isinstance(action, Mapping):
        return None
    best = card.get("best_finding")
    best_map = best if isinstance(best, Mapping) else {}
    best_summary = {
        key: best_map[key]
        for key in (
            "finding_id",
            "finding_title",
            "matched_terms",
            "match_strength",
            "source_ref_count",
            "source_finding_count",
        )
        if key in best_map and best_map[key] not in (None, "", [], {})
    }
    return core.strip_empty(
        {
            "kind": "aippocampus_background_recall_recovery",
            "status": "background_finding_available",
            "summary": "Reviewed background finding can narrow this weak recall; reopen before claims.",
            "best_finding": best_summary or None,
            "primary_action": _action_id(action),
            "claim_boundary": "background_navigation_not_source_truth",
        },
        drop_empty_dicts=True,
    )


def _background_action(card: Mapping[str, Any]) -> dict[str, Any] | None:
    action = card.get("foreground_action")
    if not isinstance(action, Mapping):
        return None
    payload = core.strip_empty(normalize_foreground_action(action), drop_empty_dicts=True)
    if not payload:
        return None
    payload["id"] = _action_id(payload) or "reopen_background_finding_source_route"
    payload["label"] = payload.get("label") or "Reopen reviewed background route"
    payload["why"] = (
        payload.get("why")
        or "Reviewed background found a narrower scent; run recall on this finding/source id and deepen before claims."
    )
    payload["claim_boundary"] = payload.get("claim_boundary") or "background_navigation_not_source_truth"
    payload["mutation_risk"] = payload.get("mutation_risk") or "read_only"
    return payload


def _background_should_replace_primary(action: Mapping[str, Any]) -> bool:
    action_id = _action_id(action)
    if action_id in {
        "search_registry_sources_for_original_cue_anchors",
        "refine_low_specificity_recall_cue",
        "repair_last_recall_cache",
        "open_repo_familiarity_source",
    }:
        return True
    if action_id.startswith("recover_"):
        return True
    return str(action.get("tool_name") or "") == "search_memory"


def _background_should_follow_primary(action: Mapping[str, Any]) -> bool:
    return str(action.get("route_choice_posture") or "") == "labels_low_specificity"


def apply_background_recovery(
    *,
    payload: Mapping[str, Any],
    foreground_action: dict[str, Any],
    followup_actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    """Promote reviewed background before broad fallbacks for weak recall.

    Background cards are navigation, not source truth. This helper only moves a
    reviewed, source-linked finding ahead of broad search/repo-familiarity
    fallbacks when ordinary recall already needs recovery.
    """

    card = payload.get("background_recovery")
    card_map = card if isinstance(card, Mapping) else {}
    if card_map.get("status") != "ok":
        return foreground_action, followup_actions, None
    background_action = _background_action(card_map)
    background_recovery = _compact_background_recovery(card_map)
    if not background_action or not background_recovery:
        return foreground_action, followup_actions, None
    if _action_id(foreground_action) == _action_id(background_action):
        return foreground_action, followup_actions, background_recovery
    if _background_should_replace_primary(foreground_action):
        ordinary = core.strip_empty(
            normalize_foreground_action(foreground_action),
            drop_empty_dicts=True,
        )
        followup_actions = _unique_actions([ordinary, *followup_actions])
        return background_action, followup_actions, background_recovery
    if _background_should_follow_primary(foreground_action):
        followup_actions = _unique_actions([background_action, *followup_actions])
        return foreground_action, followup_actions, background_recovery
    return foreground_action, followup_actions, None
