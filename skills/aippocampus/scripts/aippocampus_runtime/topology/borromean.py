"""Borromean source/user-need/agent-agency reducer for packet topology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SOURCE_SIDE_KEYS = (
    "source_ref_available",
    "source_refs",
    "source_ids",
    "source_ref_ids",
    "source_anchors",
    "source_handle",
    "source_handles",
    "route_handle",
    "route_handles",
    "route_id",
    "deepen_route_id",
    "reopen_path",
    "source_reopen_route",
    "source_reopen_routes",
)
USER_NEED_KEYS = (
    "task",
    "current_task",
    "user_need",
    "user_intent",
    "intent_anchor",
    "task_anchor",
    "user_need_anchor",
    "request_scope",
    "task_boundary",
)
AGENCY_TRUE_KEYS = ("agent_agency_room", "foreground_judgment_room", "agency_room")
AGENCY_FALSE_KEYS = (
    "rendered_as_action_instruction",
    "rendered_as_fact",
    "rendered_as_certainty",
    "foreground_suppressed",
    "force_action",
    "must_follow",
    "source_repetition_required",
    "over_suppression",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _has_value(value: Any) -> bool:
    if value in (None, "", [], {}, ()):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_value(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_value(item) for item in value)
    return bool(value)


def _boundary_mapping(row: Mapping[str, Any]) -> Mapping[str, Any]:
    boundary = row.get("boundary") or row.get("packet_boundary") or row.get("source_boundary")
    return boundary if isinstance(boundary, Mapping) else {}


def _source_side_present(row: Mapping[str, Any]) -> bool:
    for key in SOURCE_SIDE_KEYS:
        if key == "source_ref_available":
            if row.get(key) is True:
                return True
            continue
        if _has_value(row.get(key)):
            return True
    return False


def _user_need_side_present(row: Mapping[str, Any]) -> bool:
    if any(_has_value(row.get(key)) for key in USER_NEED_KEYS):
        return True
    boundary = _boundary_mapping(row)
    return any(_has_value(boundary.get(key)) for key in USER_NEED_KEYS)


def _agent_agency_side_present(row: Mapping[str, Any]) -> bool:
    if any(_safe_bool(row.get(key)) for key in AGENCY_FALSE_KEYS):
        return False
    for key in AGENCY_TRUE_KEYS:
        if key in row:
            return row.get(key) is True
    action = _text(row.get("action_grammar") or row.get("action")).casefold()
    claim = _text(row.get("claim_permission")).casefold()
    authority = _text(row.get("authority_level") or row.get("authority")).casefold()
    return (
        action in {"direction_only", "reopenable_route", "bounded_evidence"}
        or claim in {"no_claim_before_reopen", "navigation_only_not_fact"}
        or authority in {"navigation_only", "direction_only", "candidate_not_fact"}
    )


def borromean_relation_diagnostic(row: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce packet-visible fields into a compact Borromean relation diagnostic.

    The reducer only evaluates foreground-visible or action-shaping packets. It
    never infers hidden user intent; the user-need side must be explicit in the
    packet or boundary fields.
    """

    visible = _safe_bool(row.get("foreground_visible")) or _safe_bool(row.get("action_shaping"))
    annotation_break = row.get("borromean_break") is True
    sides = {
        "source": _source_side_present(row),
        "user_need": _user_need_side_present(row),
        "agent_agency": _agent_agency_side_present(row),
    }
    missing_sides = [side for side, present in sides.items() if not present]
    derived_break = visible and bool(missing_sides)
    break_counted = visible and (derived_break or annotation_break)
    reason_codes = [f"borromean_missing_{side}_side" for side in missing_sides] if visible else []
    if annotation_break:
        reason_codes.append("producer_annotated_borromean_break")
    if visible and not reason_codes:
        reason_codes.append("borromean_relation_preserved")
    status = "not_evaluated"
    if visible:
        status = "break" if break_counted else "preserved"

    return {
        "kind": "borromean_relation_diagnostic",
        "status": status,
        "evaluated": visible,
        "foreground_or_action_shaping": visible,
        "sides_present": sides,
        "missing_sides": missing_sides if visible else [],
        "derived_break": derived_break,
        "annotation_break": annotation_break,
        "break_counted": break_counted,
        "reason_codes": reason_codes,
        "authority_level": "navigation_only",
        "claim_permission": "navigation_only_not_fact",
        "source_reopen_required_before_claim": True,
        "topology_truth_source": False,
    }


__all__ = ["borromean_relation_diagnostic"]
