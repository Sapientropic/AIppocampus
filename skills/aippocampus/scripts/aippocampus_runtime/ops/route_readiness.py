#!/usr/bin/env python3
"""Public-safe route-readiness diagnostics for speculative prewarm rows.

Route readiness is an observability surface, not a cache writer and not source
evidence. It may tell an agent that a route handle is worth reopening, but exact
claims still have to reopen clean source. Keep this module sidecar-shaped: do
not promote ROI, freshness, or prewarm status into clean-source fields.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.privacy_taxonomy import (
    privacy_action_is_local_route,
    privacy_boundary_reason_bucket,
    public_codes,
)
from aippocampus_runtime.recall.active_recall_lock_lifecycle import (
    nonnegative_int,
)

ROUTE_READINESS_KIND = "aippocampus_route_readiness_report"
ROUTE_READINESS_SCHEMA_VERSION = 1

SOURCE_REF_KEYS = (
    "source_id",
    "stable_source_id",
    "thread_key",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "source_line",
)

SECRETISH_PREFIXES = ("sk-", "ghp_", "AKIA")
STALE_FRESHNESS = {
    "stale",
    "expired",
    "superseded",
    "unknown",
    "conflicted",
    "refuted",
    "uncertain",
}
BLOCKED_PRIVACY_STATES = {"blocked", "private", "sensitive", "partition_blocked"}


def _sha(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _safe_ref_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if any(text.startswith(prefix) for prefix in SECRETISH_PREFIXES):
        return "<redacted-sensitive-label>"
    if "\\" in text or "/" in text or (len(text) > 2 and text[1:3] == ":\\"):
        return "<redacted-sensitive-label>"
    return text[:160]


def safe_source_refs(value: Any) -> list[dict[str, Any]]:
    """Return source refs as ids/anchors only, never as raw source material."""
    if isinstance(value, Mapping):
        items: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref: dict[str, Any] = {}
        for key in SOURCE_REF_KEYS:
            item_value = item.get(key)
            if item_value in {None, ""}:
                continue
            out_key = "line" if key == "source_line" else key
            if out_key == "stable_source_id":
                out_key = "source_id"
            safe_value = _safe_ref_value(item_value)
            if safe_value in {None, ""}:
                continue
            ref[out_key] = safe_value
        if not ref:
            continue
        marker = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
    return refs


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ttl_remaining(row: Mapping[str, Any], *, now_unix: float) -> int:
    explicit = row.get("ttl_remaining_seconds")
    if explicit not in {None, ""}:
        return int(_float(explicit))
    expires = row.get("expires_unix")
    if expires not in {None, ""}:
        return int(_float(expires) - now_unix)
    ttl = row.get("ttl_seconds")
    if ttl not in {None, ""}:
        created = _float(row.get("created_unix"), now_unix)
        return int(created + _float(ttl) - now_unix)
    return 0


def _freshness(row: Mapping[str, Any]) -> str:
    value = row.get("freshness") or row.get("freshness_state") or row.get("state")
    text = str(value or "unknown").strip().casefold()
    return text or "unknown"


def _privacy_state(row: Mapping[str, Any]) -> str:
    bucket = privacy_boundary_reason_bucket(
        privacy_action=row.get("privacy_action"),
        reason_codes=row.get("privacy_reason_codes"),
    )
    if bucket and bucket != "local_route_handle_only":
        return bucket
    if privacy_action_is_local_route(row.get("privacy_action")):
        return "local_route_handle"
    if row.get("privacy_blocked") or row.get("blocked_by_privacy"):
        return "blocked"
    text = str(row.get("privacy_state") or row.get("privacy") or "allowed").strip().casefold()
    return text or "allowed"


def _roi_score(row: Mapping[str, Any]) -> float:
    explicit = row.get("roi_score")
    if explicit not in {None, ""}:
        return round(_float(explicit), 4)
    expected_value = _float(row.get("expected_value"), 0.0)
    cost = _float(row.get("estimated_cost"), 1.0)
    if cost <= 0:
        return round(expected_value, 4)
    return round(expected_value / cost, 4)


def normalize_route_candidate(
    row: Mapping[str, Any],
    *,
    now_unix: float | None = None,
    min_roi_score: float = 1.0,
) -> dict[str, Any]:
    """Project one candidate into a public-safe ready/suppressed row."""
    now_value = time.time() if now_unix is None else now_unix
    refs = safe_source_refs(row.get("source_refs"))
    freshness = _freshness(row)
    privacy_state = _privacy_state(row)
    ttl_remaining = _ttl_remaining(row, now_unix=now_value)
    ttl_seconds = nonnegative_int(row.get("ttl_seconds"))
    score = _roi_score(row)
    output_authority = str(row.get("output_authority") or "navigation_only").strip()

    reason_codes: list[str] = []
    privacy_bucket = privacy_boundary_reason_bucket(
        privacy_action=row.get("privacy_action"),
        reason_codes=row.get("privacy_reason_codes"),
        blocked=privacy_state in BLOCKED_PRIVACY_STATES,
    )
    if output_authority != "navigation_only" or row.get("navigation_only") is False:
        reason_codes.append("output_authority_not_navigation_only")
    if not refs:
        reason_codes.append("no_source_refs")
    if freshness in STALE_FRESHNESS:
        reason_codes.append("stale_or_unknown_freshness")
    if ttl_remaining <= 0:
        reason_codes.append("ttl_expired")
    if privacy_bucket == "local_route_handle_only":
        reason_codes.append("local_route_handle_only")
    elif privacy_bucket:
        reason_codes.append(privacy_bucket)
    if score < min_roi_score:
        reason_codes.append("low_expected_value")

    blocking_codes = [code for code in reason_codes if code != "local_route_handle_only"]
    ready = not blocking_codes
    suppression_reason = "" if ready else blocking_codes[0]
    route_id = row.get("route_id") or row.get("lock_id") or row.get("candidate_id")
    return {
        "route_id_hash": _sha(route_id or row, prefix="route"),
        "surface_kind": str(row.get("surface_kind") or row.get("candidate_kind") or "prewarm_candidate")[:80],
        "status": "ready" if ready else "suppressed",
        "readiness_class": "source_reopen_ready" if ready else "silent",
        "output_authority": "navigation_only",
        "navigation_only": True,
        "source_reopen_required_before_claim": True,
        "source_refs": refs,
        "source_ref_count": len(refs),
        "freshness": freshness,
        "ttl_seconds": ttl_seconds,
        "ttl_remaining_seconds": max(0, ttl_remaining),
        "roi_score": score,
        "reason_codes": reason_codes or ["ready_for_source_reopen"],
        "suppression_reason": suppression_reason,
        "privacy_action": str(row.get("privacy_action") or ""),
        "privacy_reason_codes": public_codes(row.get("privacy_reason_codes")),
    }


def _active_lock_roi_metrics(active_lock_roi: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(active_lock_roi, Mapping):
        return {
            "lock_pull_count": 0,
            "lock_reopen_attempt_count": 0,
            "source_backed_hit_count": 0,
            "wrong_or_stale_route_count": 0,
            "expired_before_consumption_count": 0,
            "never_read_count": 0,
            "rates": {},
        }
    return {
        "lock_pull_count": nonnegative_int(active_lock_roi.get("lock_pull_count")),
        "lock_reopen_attempt_count": nonnegative_int(active_lock_roi.get("lock_reopen_attempt_count")),
        "source_backed_hit_count": nonnegative_int(active_lock_roi.get("source_backed_hit_count")),
        "wrong_or_stale_route_count": nonnegative_int(active_lock_roi.get("wrong_or_stale_route_count")),
        "expired_before_consumption_count": nonnegative_int(
            active_lock_roi.get("expired_before_consumption_count")
        ),
        "never_read_count": nonnegative_int(active_lock_roi.get("never_read_count")),
        "rates": dict(active_lock_roi.get("rates") or {}),
    }


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def route_readiness_report(
    candidates: Iterable[Mapping[str, Any]],
    *,
    active_lock_roi: Mapping[str, Any] | None = None,
    now_unix: float | None = None,
    min_roi_score: float = 1.0,
) -> dict[str, Any]:
    rows = [
        normalize_route_candidate(
            candidate,
            now_unix=now_unix,
            min_roi_score=min_roi_score,
        )
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    ready_rows = [row for row in rows if row["status"] == "ready"]
    suppressed_rows = [row for row in rows if row["status"] == "suppressed"]
    suppression_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for row in suppressed_rows:
        reason = str(row.get("suppression_reason") or "unknown")
        suppression_counts[reason] = suppression_counts.get(reason, 0) + 1
        for code in row.get("reason_codes") or []:
            reason_code = str(code or "unknown")
            reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
    roi = _active_lock_roi_metrics(active_lock_roi)
    reopen_attempts = roi["lock_reopen_attempt_count"]
    source_hits = roi["source_backed_hit_count"]
    wrong_or_stale = roi["wrong_or_stale_route_count"]
    metrics = {
        "candidate_count": len(rows),
        "ready_count": len(ready_rows),
        "suppressed_count": len(suppressed_rows),
        "source_ref_ready_count": sum(1 for row in ready_rows if row["source_ref_count"] > 0),
        "stale_suppression_count": reason_counts.get("stale_or_unknown_freshness", 0),
        "ttl_suppression_count": reason_counts.get("ttl_expired", 0),
        "privacy_suppression_count": sum(
            reason_counts.get(code, 0)
            for code in (
                "privacy_blocked",
                "external_payload_blocked",
                "secret_or_property_risk_blocked",
            )
        ),
        "external_payload_suppression_count": reason_counts.get("external_payload_blocked", 0),
        "secret_or_property_risk_suppression_count": reason_counts.get(
            "secret_or_property_risk_blocked", 0
        ),
        "low_value_suppression_count": reason_counts.get("low_expected_value", 0),
        "no_source_refs_suppression_count": reason_counts.get("no_source_refs", 0),
        "output_authority_suppression_count": reason_counts.get(
            "output_authority_not_navigation_only", 0
        ),
        "prewarm_consumed_count": roi["lock_pull_count"],
        "source_reopen_after_prewarm_count": source_hits,
        "wrong_or_stale_route_count": wrong_or_stale,
        "expired_before_consumption_count": roi["expired_before_consumption_count"],
        "never_read_count": roi["never_read_count"],
    }
    metrics["rates"] = {
        "ready_rate": _rate(metrics["ready_count"], metrics["candidate_count"]),
        "source_reopen_after_prewarm_rate": _rate(source_hits, reopen_attempts),
        "wrong_or_stale_route_rate": _rate(wrong_or_stale, reopen_attempts),
        "wasted_prewarm_rate": _rate(
            metrics["expired_before_consumption_count"] + metrics["never_read_count"],
            metrics["candidate_count"],
        ),
    }
    report = {
        "kind": ROUTE_READINESS_KIND,
        "schema_version": ROUTE_READINESS_SCHEMA_VERSION,
        "no_write": True,
        "navigation_only": True,
        "rows": rows,
        "suppression_counts": dict(sorted(suppression_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "metrics": metrics,
        "active_lock_roi": roi,
        "contract": {
            "no_write_report_only": True,
            "clean_source_mutation_allowed": False,
            "owner_surface_mutation_allowed": False,
            "foreground_hook_mutation_allowed": False,
            "route_readiness_is_not_source_truth": True,
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "sensitive_values_serialized": False,
        },
        "cannot_claim": [
            "prewarm_route_is_source_backed_evidence",
            "route_readiness_proves_memory_quality",
            "suppressed_row_deletes_clean_source",
        ],
    }
    return redact_sensitive_values(redact_private_paths(report))


def fixture_route_readiness_report() -> dict[str, Any]:
    fixed_now = 1_780_000_000.0
    candidates = [
        {
            "route_id": "ready-route",
            "surface_kind": "active_recall_lock",
            "freshness": "current",
            "created_unix": fixed_now - 120,
            "ttl_seconds": 900,
            "expected_value": 4,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:route-ready", "message_id": "m1", "line": 4}],
        },
        {
            "route_id": "stale-route",
            "surface_kind": "ambient_card",
            "freshness": "stale",
            "created_unix": fixed_now - 2_000,
            "ttl_seconds": 600,
            "expected_value": 4,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:old", "message_id": "m2"}],
        },
        {
            "route_id": "privacy-route",
            "surface_kind": "semantic_trigger",
            "freshness": "current",
            "created_unix": fixed_now - 30,
            "ttl_seconds": 900,
            "privacy_state": "blocked",
            "expected_value": 3,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:private", "thread_key": "E:\\private\\thread.jsonl"}],
        },
        {
            "route_id": "low-roi-route",
            "surface_kind": "warm_ambient_candidate",
            "freshness": "current",
            "created_unix": fixed_now - 30,
            "ttl_seconds": 900,
            "expected_value": 0.2,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:weak", "message_id": "m3"}],
        },
        {
            "route_id": "sensitive-label-redaction-route",
            "surface_kind": "prewarm_candidate",
            "freshness": "current",
            "created_unix": fixed_now - 30,
            "ttl_seconds": 900,
            "expected_value": 3,
            "estimated_cost": 1,
            "source_refs": [],
            "raw_prompt": "this field must never be serialized",
        },
    ]
    active_lock_roi = {
        "lock_pull_count": 1,
        "lock_reopen_attempt_count": 1,
        "source_backed_hit_count": 1,
        "wrong_or_stale_route_count": 0,
        "expired_before_consumption_count": 1,
        "never_read_count": 1,
        "rates": {
            "lock_pull_rate": 0.5,
            "source_backed_hit_rate": 1.0,
            "wrong_or_stale_route_rate": 0.0,
        },
    }
    return route_readiness_report(
        candidates,
        active_lock_roi=active_lock_roi,
        now_unix=fixed_now,
    )
