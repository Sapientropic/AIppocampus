"""Diagnostics for progressive recall source-reopen follow-through."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

FAIL_CLOSED_CLASSES = {
    "stale_recall_handle": "stale_handle_rejected_before_source_use",
    "continuity_domain_blocked": "blocked_handle_rejected_before_source_use",
}


def no_reopen_diagnostics(failure_class: str = "") -> dict[str, Any]:
    return {
        "route_handle_present": False,
        "source_join_present": False,
        "reopen_landed": False,
        "source_reopen_follow_through_eligible": False,
        "expected_fail_closed": False,
        "failure_class": failure_class,
    }


def _failure_class(
    *,
    success: bool,
    error_code: str,
    source_refs: Sequence[Any],
) -> str:
    if success:
        return ""
    if error_code in FAIL_CLOSED_CLASSES:
        return FAIL_CLOSED_CLASSES[error_code]
    if error_code == "source_ref_not_found":
        return "source_ref_not_found"
    if source_refs:
        return "wrong_source_ref_landed"
    if error_code:
        return f"deepen_error:{error_code}"
    return "no_source_refs_returned"


def reopen_diagnostics(
    *,
    route_handle_present: bool,
    source_join_present: bool,
    source_reopen_attempted: bool,
    success: bool,
    error_code: str,
    source_refs: Sequence[Any],
) -> dict[str, Any]:
    failure_class = _failure_class(
        success=success,
        error_code=error_code,
        source_refs=source_refs,
    )
    expected_fail_closed = failure_class in set(FAIL_CLOSED_CLASSES.values())
    return {
        "route_handle_present": route_handle_present,
        "source_join_present": source_join_present,
        "reopen_landed": bool(source_refs) and not error_code,
        "source_reopen_follow_through_eligible": bool(
            source_reopen_attempted and not expected_fail_closed
        ),
        "expected_fail_closed": expected_fail_closed,
        "failure_class": failure_class,
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def aggregate_follow_through(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    attempted = [row for row in rows if row.get("source_reopen_attempted")]
    eligible = [
        row
        for row in attempted
        if row.get("source_reopen_follow_through_eligible", True)
    ]
    failure_classes = Counter(
        str(row.get("failure_class") or "")
        for row in attempted
        if row.get("failure_class")
    )
    follow_count = sum(1 for row in eligible if row.get("source_reopen_follow_through"))
    return {
        "source_reopen_follow_through_count": follow_count,
        "source_reopen_follow_through_eligible_count": len(eligible),
        "source_reopen_follow_through_rate": _ratio(follow_count, len(eligible)),
        "source_reopen_landed_count": sum(
            1 for row in attempted if row.get("reopen_landed")
        ),
        "source_reopen_fail_closed_count": sum(
            1 for row in attempted if row.get("expected_fail_closed")
        ),
        "source_reopen_failure_classes": dict(sorted(failure_classes.items())),
    }


def issue_readout_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_reopen_follow_through_measured": True,
        "source_reopen_follow_through_rate": row.get(
            "source_reopen_follow_through_rate", 0
        ),
        "source_reopen_follow_through_count": row.get(
            "source_reopen_follow_through_count", 0
        ),
        "source_reopen_follow_through_eligible_count": row.get(
            "source_reopen_follow_through_eligible_count", 0
        ),
        "source_reopen_landed_count": row.get("source_reopen_landed_count", 0),
        "source_reopen_fail_closed_count": row.get(
            "source_reopen_fail_closed_count", 0
        ),
        "source_reopen_failure_classes": row.get("source_reopen_failure_classes", {}),
    }


def render_aggregate_summary(row: Mapping[str, Any]) -> str:
    rate = row.get("source_reopen_follow_through_rate", 0)
    if not row.get("source_reopen_attempt_count"):
        return str(rate)
    follow_count = row.get("source_reopen_follow_through_count", 0)
    eligible_count = row.get("source_reopen_follow_through_eligible_count", 0)
    fail_closed_count = row.get("source_reopen_fail_closed_count", 0)
    return (
        f"{rate} ({follow_count}/{eligible_count} eligible, "
        f"{fail_closed_count} fail-closed)"
    )
