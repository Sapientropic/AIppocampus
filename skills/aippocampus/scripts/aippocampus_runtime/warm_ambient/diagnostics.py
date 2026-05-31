#!/usr/bin/env python3
"""Public-safe diagnostics for warm ambient recall results."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.warm_ambient.scout_profiles import scout_lane_parts

SOURCE_VALIDATION_DROP_STATUSES = {"missing_source_ref", "unsupported"}
SUPPRESSION_REASON_BUCKET_ORDER = (
    "privacy_blocked",
    "evidence_sentinel_blocked",
    "current_thread_echo",
    "source_validation_failed",
    "topic_epoch_suppressed",
    "quorum_not_met",
    "no_supported_cards",
)


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
