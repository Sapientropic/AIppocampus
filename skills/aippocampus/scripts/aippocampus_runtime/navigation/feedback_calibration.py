"""Public-safe feedback calibration adapter for attention route ranking.

Feedback calibration is navigation metadata. This helper deliberately keeps
score deltas bounded, emits only route ids / route kinds / reason codes, and
never upgrades a route into source evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import list_or_empty

SCORE_SCALE = 0.22


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def append_codes(existing: object, codes: Sequence[str], *, limit: int = 6) -> list[str]:
    base = list(existing) if isinstance(existing, list | tuple) else []
    result: list[str] = []
    for code in [*base, *codes]:
        clean = str(code or "").strip()
        if clean and clean not in result:
            result.append(clean)
        if len(result) >= limit:
            break
    return result


def route_kind_for_route(route: Mapping[str, Any]) -> str:
    return str(route.get("route_kind") or route.get("kind") or "active_path").strip() or "active_path"


def payload(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get("calibration")
    if isinstance(nested, Mapping):
        return nested
    return value


def by_route(
    calibration: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for item in payload(calibration).get("deltas") or []:
        if not isinstance(item, Mapping):
            continue
        route_id = str(item.get("route_id") or "").strip()
        route_kind = str(item.get("route_kind") or "").strip()
        if route_id and route_kind:
            rows[(route_id, route_kind)] = dict(item)
    return rows


def bounded_delta(row: Mapping[str, Any] | None) -> float:
    if not row:
        return 0.0
    if row.get("sparse_feedback_fallback") or row.get("conflicting_feedback_fallback"):
        return 0.0
    return max(-1.0, min(1.0, _float(row.get("route_weight_delta"))))


def score_adjustment(row: Mapping[str, Any] | None) -> float:
    return bounded_delta(row) * SCORE_SCALE


def reason_codes(row: Mapping[str, Any] | None, delta: float | None = None) -> list[str]:
    if not row:
        return []
    bounded = bounded_delta(row) if delta is None else delta
    raw = [str(code) for code in list_or_empty(row.get("reason_codes")) if str(code).strip()]
    codes: list[str] = []
    if bounded > 0:
        codes.append("feedback_calibration_lift")
    elif bounded < 0:
        codes.append("feedback_calibration_demote")
    elif row.get("sparse_feedback_fallback"):
        codes.append("feedback_calibration_sparse_no_delta")
    elif row.get("conflicting_feedback_fallback"):
        codes.append("feedback_calibration_conflict_no_delta")
    for code in raw:
        if code not in codes:
            codes.append(code)
    return codes[:6]


def annotate_route(route: dict[str, Any], row: Mapping[str, Any] | None) -> bool:
    delta = bounded_delta(row)
    codes = reason_codes(row, delta)
    if not codes:
        return False
    route["triage_rank_reason_codes"] = append_codes(
        route.get("triage_rank_reason_codes"),
        codes,
    )
    route["_route_delta_reason_codes"] = append_codes(
        route.get("_route_delta_reason_codes"),
        codes,
    )
    route["_recommended_next"] = "deepen_this_route_first"
    route["feedback_calibration_delta"] = delta
    return True


def diagnostics(
    *,
    calibration: Mapping[str, Any] | None,
    matched: Sequence[Mapping[str, Any]],
    ignored_delta_count: int,
) -> dict[str, Any]:
    calibration_payload = payload(calibration)
    matched_rows = [
        {
            "route_id": str(row.get("route_id") or ""),
            "route_kind": str(row.get("route_kind") or ""),
            "route_weight_delta": bounded_delta(row),
            "reason_codes": reason_codes(row),
        }
        for row in matched
    ]
    positive = sum(1 for row in matched_rows if _float(row.get("route_weight_delta")) > 0)
    negative = sum(1 for row in matched_rows if _float(row.get("route_weight_delta")) < 0)
    return {
        "applied": bool(matched_rows),
        "consumer": "attention_route_projection",
        "load_status": calibration_payload.get("load_status"),
        "event_count_loaded": calibration_payload.get("event_count_loaded"),
        "matched_route_count": len(matched_rows),
        "positive_delta_count": positive,
        "negative_delta_count": negative,
        "ignored_delta_count": ignored_delta_count,
        "matched_routes": matched_rows[:8],
        "reason_codes": append_codes(
            [],
            [
                *(["feedback_calibration_consumed"] if matched_rows else []),
                *(
                    ["feedback_calibration_no_matching_route"]
                    if calibration_payload and not matched_rows
                    else []
                ),
            ],
            limit=4,
        ),
        "policy_boundary": {
            "feedback_is_navigation_metadata_only": True,
            "feedback_score_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "clean_source_mutation_allowed": False,
            "source_open_claim_allowed": False,
        },
        "cannot_claim": list_or_empty(calibration_payload.get("cannot_claim"))
        or [
            "feedback_event_is_source_truth",
            "feedback_calibration_can_emit_source_open",
            "feedback_calibration_mutates_clean_source",
        ],
    }
