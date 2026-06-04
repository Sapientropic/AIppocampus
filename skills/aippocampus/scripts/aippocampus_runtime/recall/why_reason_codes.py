#!/usr/bin/env python3
"""Shared reason-code vocabulary for recall diagnostics."""

from __future__ import annotations

import hashlib
from typing import Any

DIAGNOSTIC_KIND = "aippocampus_recall_diagnostic"
SCHEMA_VERSION = 1
REASON_CODE_CATALOG_VERSION = 1
DEFAULT_MAX_ROUTES = 5

_REASON_ROWS = (
    (
        "route_returned",
        "surfaced",
        "recall_context",
        "A recall surface returned at least one navigation route.",
    ),
    (
        "source_reopen_required",
        "surfaced",
        "recall_context",
        "The route is navigation only and must reopen clean source before claims.",
    ),
    ("no_source_refs", "missing", "recall_context", "No reopenable source refs were found."),
    (
        "stale_handle",
        "degraded",
        "active_lock",
        "A handle or lock was invalidated by TTL or source freshness.",
    ),
    (
        "privacy_partition_block",
        "suppressed",
        "ambient_cache",
        "A privacy guard or partition blocked recall delivery.",
    ),
    (
        "anti_nag_source_already_visible",
        "suppressed",
        "ambient_cache",
        "Anti-nag/current-thread echo policy suppressed a nearby route.",
    ),
    (
        "semantic_provider_timeout",
        "degraded",
        "semantic_gate",
        "The semantic gate timed out or exceeded its explicit deadline.",
    ),
    (
        "semantic_degraded",
        "degraded",
        "semantic_gate",
        "The semantic gate returned an operator-safe degraded state.",
    ),
    (
        "semantic_unavailable_missing_auth",
        "degraded",
        "semantic_gate",
        "The semantic gate lacked required provider credentials.",
    ),
    (
        "semantic_disabled_by_operator",
        "missing",
        "semantic_gate",
        "The semantic gate was explicitly disabled for this diagnostic run.",
    ),
    (
        "source_thickness_thin",
        "degraded",
        "ambient_cache",
        "Only thin source support was available; reopen before claims.",
    ),
    ("ambient_cache_hit", "surfaced", "ambient_cache", "A warm/ambient cache entry matched."),
    ("ambient_cache_miss", "missing", "ambient_cache", "No warm/ambient cache entry matched."),
    (
        "active_lock_ready",
        "surfaced",
        "active_lock",
        "An active recall lock is ready and has reopenable refs.",
    ),
    ("active_lock_missing", "missing", "active_lock", "No active recall lock matched."),
    (
        "missing_clean_source",
        "missing",
        "recall_context",
        "Clean-source artifacts were unavailable for the selected workspace.",
    ),
    (
        "source_ref_not_found",
        "missing",
        "recall_context",
        "A source ref was present but did not resolve to clean source.",
    ),
    (
        "authority_level_block",
        "suppressed",
        "active_lock",
        "A higher-authority boundary blocked a weaker activation surface.",
    ),
    ("prewarm_miss", "missing", "ambient_cache", "Prewarm/cache lookup found no reusable route."),
    (
        "dream_candidate_not_adjudicated",
        "degraded",
        "ambient_cache",
        "A Dream/working-memory candidate exists only as a non-adjudicated hint.",
    ),
)

REASON_CODE_CATALOG = {
    code: {"decision": decision, "surface": surface, "meaning": meaning}
    for code, decision, surface, meaning in _REASON_ROWS
}

DECISION_SEVERITY = {"suppressed": 4, "degraded": 3, "surfaced": 2, "missing": 1, "unknown": 0}

NEXT_ACTION_BY_REASON = {
    "stale_handle": "rerun_recall_context",
    "source_ref_not_found": "refresh_index_or_rebuild_clean_source",
    "missing_clean_source": "run_onboard_or_build_clean_source",
    "privacy_partition_block": "ask_user_or_narrow_scope",
    "anti_nag_source_already_visible": "no_op",
    "source_reopen_required": "reopen_source",
    "route_returned": "reopen_source",
    "active_lock_ready": "reopen_source",
    "source_thickness_thin": "reopen_source_or_gather_more_source",
    "no_source_refs": "rerun_recall_context_or_search_clean_source",
    "semantic_provider_timeout": "rerun_recall_context_or_inspect_health",
    "semantic_degraded": "inspect_health",
    "semantic_unavailable_missing_auth": "inspect_health",
    "semantic_disabled_by_operator": "no_op",
    "ambient_cache_miss": "rerun_recall_context",
    "active_lock_missing": "rerun_recall_context",
}

CANNOT_CLAIM = [
    "diagnostic_reason_is_not_memory_evidence",
    "route_id_is_not_source_truth",
    "absence_of_route_is_not_absence_of_memory",
    "source_claim_requires_recall_deepen_or_clean_source_reopen",
]


def cue_hash(cue: str) -> str:
    return f"cue_{hashlib.sha256(str(cue or '').encode('utf-8')).hexdigest()[:24]}"


def safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def unique(values: list[str], *, limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def surface_report(
    surface: str,
    *,
    status: str,
    reason_codes: list[str] | None = None,
    route_ids: list[str] | None = None,
    counts: dict[str, int] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "surface": surface,
        "status": status,
        "reason_codes": unique(reason_codes or []),
    }
    if clean_route_ids := unique(route_ids or [], limit=12):
        report["route_ids"] = clean_route_ids
    if clean_counts := {key: safe_int(value) for key, value in (counts or {}).items()}:
        report["counts"] = clean_counts
    if details:
        report["details"] = details
    return report


def overall_decision(reason_codes: list[str]) -> str:
    if not reason_codes:
        return "unknown"
    decisions = [
        REASON_CODE_CATALOG.get(code, {}).get("decision", "unknown") for code in reason_codes
    ]
    return max(decisions, key=lambda item: DECISION_SEVERITY.get(item, 0), default="unknown")


def next_safe_action(reason_codes: list[str]) -> str:
    for code in reason_codes:
        if action := NEXT_ACTION_BY_REASON.get(code):
            return action
    return "inspect_health"
