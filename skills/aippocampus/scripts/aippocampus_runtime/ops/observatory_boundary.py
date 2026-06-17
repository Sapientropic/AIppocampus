"""Compact-boundary helpers for cognitive observatory readouts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CAN_CLAIM = [
    "public_safe_route_readiness_diagnostic_exists",
    "read_only_observatory_readout_exists",
    "public_safe_static_observatory_export_exists",
    "suppressed_prewarm_reason_codes_are_reported",
    "public_safe_query_pattern_route_observability_exists",
    "public_safe_cognitive_load_calibration_observability_exists",
    "campus_usefulness_panels_show_safe_but_useless_routes",
]

CANNOT_CLAIM = [
    "complete_cognitive_observatory_ui_exists",
    "prewarm_route_is_source_backed_evidence",
    "sleep_cycle_anticipatory_planner_is_live",
    "observatory_rows_can_mutate_control_state",
    "diagnostic_roi_proves_memory_quality",
    "query_pattern_route_is_source_truth",
    "cognitive_load_calibration_proves_user_visible_lift",
    "cognitive_load_signal_is_source_truth",
    "campus_panels_are_control_or_truth_surface",
]


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def with_boundary_detail(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(payload)
    cannot_claim = string_list(projected.pop("cannot_claim", []))
    if cannot_claim:
        boundary_detail = dict(projected.get("boundary_detail") or {})
        boundary_detail["cannot_claim"] = cannot_claim
        boundary_detail.setdefault(
            "operator_note",
            "Compact observatory embeds keep claim limits drillable without making them the foreground card.",
        )
        projected["boundary_detail"] = boundary_detail
    return projected


def readout_state(route_readiness: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    route_rows = len(route_readiness.get("rows") or [])
    activation_count = int(metrics.get("activation_surface_count") or 0)
    useful_now_count = int(metrics.get("campus_useful_now_count") or 0)
    has_rows = bool(route_rows or activation_count or useful_now_count)
    return {
        "status": "rows_available" if has_rows else "no_rows",
        "route_readiness_rows": route_rows,
        "activation_surface_count": activation_count,
        "useful_now_count": useful_now_count,
    }


def boundary_detail(
    *,
    route_readiness: Mapping[str, Any],
    control_authority: Mapping[str, Any],
) -> dict[str, Any]:
    route_detail = route_readiness.get("boundary_detail")
    control_detail = control_authority.get("boundary_detail")
    return {
        "can_claim": list(CAN_CLAIM),
        "cannot_claim": list(CANNOT_CLAIM),
        "nested_cannot_claim": {
            "route_readiness": string_list(
                (route_detail if isinstance(route_detail, Mapping) else {}).get("cannot_claim")
            ),
            "control_authority_audit": string_list(
                (control_detail if isinstance(control_detail, Mapping) else {}).get("cannot_claim")
            ),
        },
        "operator_note": (
            "These limits remain active; compact foreground output keeps them behind "
            "boundary_detail so the readout can lead with safe next actions."
        ),
    }
