"""Result assembly helpers for compact agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _without_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [])}


def hidden_route_count_fields(
    *,
    route_receipts: Sequence[Mapping[str, Any]],
    memory_packets: Sequence[Mapping[str, Any]],
    labels_low_specificity: bool,
) -> dict[str, int]:
    displayed_route_count = len(route_receipts)
    omitted_route_count = max(0, len(memory_packets) - displayed_route_count)
    if not omitted_route_count and not labels_low_specificity:
        return {}
    fields = {"displayed_route_count": displayed_route_count}
    if omitted_route_count:
        fields["omitted_route_count"] = omitted_route_count
    return fields


def sorted_duplicate_label_omissions(
    duplicate_label_omissions: Mapping[str, Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return sorted(
        duplicate_label_omissions.values(),
        key=lambda row: (int(row["kept_route_index"]), str(row["route_label"])),
    )


def low_specificity_weak_route_recovery_card(
    *,
    weak_route_recovery_card: Mapping[str, Any] | None,
    safe_next_actions: Sequence[Mapping[str, Any]],
    foreground_action: Mapping[str, Any],
    memory_packets: Sequence[Mapping[str, Any]],
    displayed_route_count: int,
) -> dict[str, Any]:
    safe_action_ids = [
        str(action.get("id") or action.get("action_id") or "") for action in safe_next_actions
    ]
    refine_action_id = next(
        (action_id for action_id in safe_action_ids if action_id.startswith("refine")),
        None,
    )
    deepen_action_id = next(
        (action_id for action_id in safe_action_ids if action_id.startswith("deepen")),
        None,
    )
    primary_action = foreground_action.get("id") or foreground_action.get("action_id")
    return _without_empty(
        {
            **(weak_route_recovery_card or {}),
            "posture": "labels_low_specificity",
            "route_count": len(memory_packets),
            "displayed_as_choices": displayed_route_count,
            "primary_action": primary_action,
            "source_search_fallback_action_id": primary_action,
            "refine_action_id": refine_action_id,
            "deepen_action_id": deepen_action_id,
        }
    )
