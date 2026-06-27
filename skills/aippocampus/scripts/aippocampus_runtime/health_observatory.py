"""Cheap Observatory readiness projection for health/pulse surfaces."""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def cognitive_observatory_readiness_summary() -> dict[str, Any]:
    try:
        from aippocampus_runtime.ops import cognitive_observatory  # noqa: PLC0415

        summary = cognitive_observatory.summary_projection(
            cognitive_observatory.cognitive_observatory_readout()
        )
    except Exception as exc:
        return {
            "state": "installed",
            "status": "unavailable",
            "usefulness_counts": {
                "useful_now": 0,
                "wasted_motion": 0,
                "quiet_for_a_reason": 0,
                "needs_ripening": 0,
            },
            "error_type": type(exc).__name__,
            "claim_boundary": "observatory_summary_not_source_evidence",
        }
    useful_now = _safe_int(summary.get("useful_now_count"))
    return {
        "state": "useful" if useful_now else "callable",
        "status": "usefulness_rows_available" if useful_now else "no_rows_loaded",
        "usefulness_counts": {
            "useful_now": useful_now,
            "wasted_motion": _safe_int(summary.get("wasted_motion_count")),
            "quiet_for_a_reason": _safe_int(summary.get("quiet_for_a_reason_count")),
            "needs_ripening": _safe_int(summary.get("needs_ripening_count")),
        },
        "read_only": True,
        "not_control_plane": True,
        "summary_command": "aippocampus observatory --summary-json",
        "claim_boundary": "observatory_summary_not_source_evidence",
    }
