#!/usr/bin/env python3
"""Public-safe diagnostics for warm ambient recall results."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.warm_ambient.scout_profiles import (
    REQUIRED_GUARD_FAMILIES,
    scout_lane_parts,
)

SOURCE_VALIDATION_DROP_STATUSES = {"missing_source_ref", "unsupported"}
SUPPRESSION_REASON_BUCKET_ORDER = (
    "privacy_blocked",
    "evidence_sentinel_blocked",
    "guard_coverage_incomplete",
    "current_thread_echo",
    "source_validation_failed",
    "topic_epoch_suppressed",
    "quorum_not_met",
    "no_supported_cards",
)
GUARD_COVERAGE_STATES = {"resolved", "blocked", "missing", "timed_out", "not_requested"}
INCOMPLETE_GUARD_STATES = {"missing", "timed_out"}


def _public_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        counts[name] = max(0, int(count or 0))
    return {key: count for key, count in counts.items() if count > 0}


def _blocked_scout_families(blocked_by: Any) -> list[str]:
    families: list[str] = []
    for item in blocked_by or []:
        family, _ = scout_lane_parts(str(item or ""))
        if family:
            families.append(family)
    return unique_preserve(families, limit=8)


def _row_family(row: dict[str, Any]) -> str:
    family = str(row.get("scout_family") or "").strip()
    if family:
        return family
    family, _ = scout_lane_parts(str(row.get("scout") or ""))
    return family


def _row_error_kind(row: dict[str, Any]) -> str:
    return str(row.get("error_kind") or "").strip().casefold()


def _is_timeout_error(row: dict[str, Any]) -> bool:
    kind = _row_error_kind(row)
    reason = str(row.get("reason") or "").strip().casefold()
    return "timeout" in kind or "timeout" in reason or "timed out" in reason


def guard_coverage_status(
    *,
    scouts: tuple[str, ...] | list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report required guard coverage without exposing prompt or source text."""
    selected_by_family: dict[str, list[str]] = {family: [] for family in REQUIRED_GUARD_FAMILIES}
    for scout in scouts:
        family, _ = scout_lane_parts(str(scout or ""))
        if family in selected_by_family:
            selected_by_family[family].append(str(scout))

    rows_by_family: dict[str, list[dict[str, Any]]] = {
        family: [] for family in REQUIRED_GUARD_FAMILIES
    }
    for row in rows:
        family = _row_family(row)
        if family in rows_by_family:
            rows_by_family[family].append(row)

    family_status: dict[str, dict[str, Any]] = {}
    for family in REQUIRED_GUARD_FAMILIES:
        selected = selected_by_family[family]
        family_rows = rows_by_family[family]
        blocking_lanes = [
            str(row.get("scout") or "")
            for row in family_rows
            if row.get("ok") and row.get("block")
        ]
        error_kinds: dict[str, int] = {}
        for row in family_rows:
            if row.get("ok"):
                continue
            kind = _row_error_kind(row)
            if kind:
                error_kinds[kind] = error_kinds.get(kind, 0) + 1
        if not selected:
            state = "not_requested"
        elif blocking_lanes:
            state = "blocked"
        elif any(row.get("ok") for row in family_rows):
            state = "resolved"
        elif any(_is_timeout_error(row) for row in family_rows):
            state = "timed_out"
        else:
            state = "missing"
        details: dict[str, Any] = {
            "state": state,
            "selected_lane_count": len(selected),
            "observed_lane_count": len(family_rows),
        }
        if blocking_lanes:
            details["blocking_lanes"] = unique_preserve(blocking_lanes, limit=8)
        if error_kinds:
            details["error_kinds"] = error_kinds
        family_status[family] = details

    incomplete = [
        family
        for family, details in family_status.items()
        if details.get("state") in INCOMPLETE_GUARD_STATES
    ]
    requested = [
        family
        for family, details in family_status.items()
        if details.get("state") != "not_requested"
    ]
    blocked = [
        family for family, details in family_status.items() if details.get("state") == "blocked"
    ]
    status = "not_requested" if not requested else "incomplete" if incomplete else "complete"
    return {
        "status": status,
        "satisfied": not incomplete,
        "required_families": list(REQUIRED_GUARD_FAMILIES),
        "requested_families": requested,
        "blocked_families": blocked,
        "incomplete_families": incomplete,
        "families": family_status,
        "cache_write_policy": (
            "withhold_when_incomplete" if incomplete else "allow_when_quorum_met"
        ),
    }


def guard_coverage_incomplete(coverage: dict[str, Any] | None) -> bool:
    if not isinstance(coverage, dict):
        return False
    families = coverage.get("families") if isinstance(coverage.get("families"), dict) else {}
    return any(
        (details or {}).get("state") in INCOMPLETE_GUARD_STATES
        for details in families.values()
        if isinstance(details, dict)
    )


def suppression_reason_buckets(result: dict[str, Any]) -> list[str]:
    """Summarize warm-result gates without looking at prompt/source text."""
    buckets: list[str] = []
    cards = result.get("cards") or []
    card_count = len(cards) if isinstance(cards, list) else 0
    blocked_families = set(_blocked_scout_families(result.get("blocked_by")))
    source_status_counts = _public_count_map(result.get("source_validation_status_counts"))
    source_drop_count = sum(
        source_status_counts.get(status, 0) for status in SOURCE_VALIDATION_DROP_STATUSES
    )
    topic_epoch_decision = result.get("topic_epoch_decision") or {}
    topic_epoch_action = str(topic_epoch_decision.get("action") or "").strip().casefold()
    status = str(result.get("status") or "").strip().casefold()

    if "privacy_boundary_guard" in blocked_families:
        buckets.append("privacy_blocked")
    if "evidence_gap_sentinel" in blocked_families:
        buckets.append("evidence_sentinel_blocked")
    if guard_coverage_incomplete(result.get("guard_coverage")):
        buckets.append("guard_coverage_incomplete")
    if int(result.get("current_thread_echo_count") or 0) > 0 and card_count == 0:
        buckets.append("current_thread_echo")
    if source_drop_count > 0 and card_count == 0:
        buckets.append("source_validation_failed")
    if topic_epoch_decision.get("suppress_write") or topic_epoch_action == "suppress" or status == "suppressed":
        buckets.append("topic_epoch_suppressed")
    if status == "quorum_not_met":
        buckets.append("quorum_not_met")
    if buckets and card_count == 0:
        buckets.append("no_supported_cards")
    seen = set(buckets)
    return [bucket for bucket in SUPPRESSION_REASON_BUCKET_ORDER if bucket in seen]


def suppression_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    topic_epoch_decision = result.get("topic_epoch_decision") or {}
    diagnostics: dict[str, Any] = {
        "reason_buckets": suppression_reason_buckets(result),
        "card_count": len(result.get("cards") or []),
        "quorum_met": bool(result.get("quorum_met")),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
    }
    guard_coverage = result.get("guard_coverage")
    if isinstance(guard_coverage, dict):
        diagnostics["guard_coverage"] = guard_coverage
    blocked_families = _blocked_scout_families(result.get("blocked_by"))
    if blocked_families:
        diagnostics["blocked_scout_families"] = blocked_families
    source_status_counts = _public_count_map(result.get("source_validation_status_counts"))
    if source_status_counts:
        diagnostics["source_validation_status_counts"] = source_status_counts
    topic_epoch_action = str(topic_epoch_decision.get("action") or "").strip().casefold()
    if topic_epoch_action:
        diagnostics["topic_epoch_action"] = topic_epoch_action
    return diagnostics
