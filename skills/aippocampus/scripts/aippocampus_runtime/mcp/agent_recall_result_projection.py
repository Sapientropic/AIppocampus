"""Result assembly helpers for compact agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime import core


def sorted_duplicate_label_omissions(
    duplicate_label_omissions: Mapping[str, Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return sorted(
        duplicate_label_omissions.values(),
        key=lambda row: (int(row["kept_route_index"]), str(row["route_label"])),
    )


def low_specificity_route_guidance_card(
    *,
    base_card: Mapping[str, Any] | None,
    action_options: Sequence[Mapping[str, Any]],
    foreground_action: Mapping[str, Any],
) -> dict[str, Any]:
    safe_action_ids = [
        str(action.get("id") or action.get("action_id") or "") for action in action_options
    ]
    refine_action_id = next(
        (action_id for action_id in safe_action_ids if action_id.startswith("refine")),
        None,
    )
    deepen_action_id = next(
        (action_id for action_id in safe_action_ids if action_id.startswith("deepen")),
        None,
    )
    source_search_action_id = next(
        (
            action_id
            for action_id in safe_action_ids
            if action_id == "search_registry_sources_for_original_cue_anchors"
        ),
        None,
    )
    primary_action = foreground_action.get("id") or foreground_action.get("action_id")
    return core.strip_empty(
        {
            **(base_card or {}),
            "posture": "labels_low_specificity",
            "summary": (
                "Recall has route-shaped context, but compact labels are weak; "
                "open the route before relying on it."
            ),
            "primary_action": primary_action,
            "source_search_fallback_action_id": source_search_action_id,
            "refine_action_id": refine_action_id,
            "deepen_action_id": deepen_action_id,
            "claim_boundary": "no_claim_before_reopen",
        }
    )
