"""Compact foreground projection for Cognitive Observatory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.foreground_compact_language import (
    compact_details_flag,
    strip_compact_policy_vocabulary,
)
from aippocampus_runtime.ops.cognitive_observatory_actions import (
    foreground_action,
    readout_next_actions,
)


def panel_previews(report: Mapping[str, Any], *, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
    raw_panels = report.get("campus_usefulness_panels")
    panel_container = raw_panels if isinstance(raw_panels, Mapping) else {}
    panels = panel_container.get("panels")
    panel_map = panels if isinstance(panels, Mapping) else {}
    previews: dict[str, list[dict[str, Any]]] = {}
    for name in ("useful_now", "wasted_motion", "quiet_for_a_reason", "needs_ripening"):
        rows: list[dict[str, Any]] = []
        for item in list(panel_map.get(name) or [])[:limit]:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "surface": str(item.get("surface") or "unknown"),
                    "label": str(item.get("label") or "row"),
                    "next_action": str(item.get("next_action") or "reopen_source_before_claim"),
                    "reason_codes": [str(code) for code in item.get("reason_codes") or []][:4],
                }
            )
        previews[name] = rows
    return previews


def compact_claim_boundary() -> dict[str, Any]:
    return {
        "can_use_for": ["route_readiness_triage", "observability_review"],
        "must_reopen_for": ["source_backed_claims", "control_state_changes"],
        "detail_available_with": "aippocampus observatory --operator-json",
    }


def summary_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") or {}
    readout_state = report.get("readout_state")
    no_rows = (
        isinstance(readout_state, Mapping)
        and str(readout_state.get("status") or "") == "no_rows"
    )
    action = foreground_action(no_rows=no_rows)
    safe_next_actions = readout_next_actions(no_rows=no_rows)
    payload = {
        "kind": "aippocampus_cognitive_observatory_summary",
        **canonical_foreground_action_fields(action, safe_next_actions=safe_next_actions),
        "ok": bool(report.get("ok")),
        "read_only": bool(report.get("no_write")),
        "not_control_plane": bool((report.get("contract") or {}).get("not_control_plane")),
        "route_ready_count": metrics.get("route_ready_count", 0),
        "route_suppressed_count": metrics.get("route_suppressed_count", 0),
        "activation_surface_count": metrics.get("activation_surface_count", 0),
        "useful_now_count": metrics.get("campus_useful_now_count", 0),
        "wasted_motion_count": metrics.get("campus_wasted_motion_count", 0),
        "quiet_for_a_reason_count": metrics.get("campus_quiet_for_a_reason_count", 0),
        "needs_ripening_count": metrics.get("campus_needs_ripening_count", 0),
        "panel_previews": panel_previews(report),
        "surfaces": list(report.get("surfaces") or [])[:12],
        "full_audit_flag": "--operator-json",
        "html_flag": "--html",
        "operator_json_available": True,
        "operator_json_command": "aippocampus observatory --operator-json",
        "privacy_boundary": report.get("privacy_boundary"),
        "claim_boundary": compact_claim_boundary(),
    }
    payload.update(compact_details_flag(payload))
    return strip_compact_policy_vocabulary(
        payload,
        extra_denied_keys=frozenset({"full_audit_flag"}),
    )
