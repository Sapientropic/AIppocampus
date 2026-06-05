#!/usr/bin/env python3
"""No-write anticipatory prewarm planner projection.

This is a planner report, not a worker and not a cache writer. It accepts
already-proposed next-context domains, runs them through the existing
route-readiness gates, and returns public-safe navigation rows that a later
foreground action may pull and reopen from source.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.ops.route_readiness import route_readiness_report, safe_source_refs

PREWARM_PLANNER_KIND = "aippocampus_prewarm_planner_report"
PREWARM_PLANNER_SCHEMA_VERSION = 1
MAX_ALIASES = 6
MAX_INVALIDATION_TRIGGERS = 6

SECRETISH_MARKERS = ("secret", "token", "password", "credential", "api_key")


def _sha(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _safe_text(value: Any, chars: int = 160) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _looks_sensitive_text(text: str) -> bool:
    lowered = text.casefold()
    if any(marker in lowered for marker in SECRETISH_MARKERS):
        return True
    return "\\" in text or "/" in text or (len(text) > 2 and text[1:3] == ":\\")


def _safe_terms(value: Any, *, limit: int, chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _safe_text(item, chars)
        if not text or _looks_sensitive_text(text):
            continue
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _route_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_id": candidate.get("domain_id")
        or candidate.get("route_id")
        or candidate.get("candidate_id"),
        "surface_kind": candidate.get("owner_surface")
        or candidate.get("surface_kind")
        or "anticipatory_prewarm",
        "freshness": candidate.get("freshness") or candidate.get("currentness") or "unknown",
        "created_unix": candidate.get("created_unix"),
        "expires_unix": candidate.get("expires_unix"),
        "ttl_seconds": candidate.get("ttl_seconds"),
        "ttl_remaining_seconds": candidate.get("ttl_remaining_seconds"),
        "expected_value": candidate.get("expected_value"),
        "estimated_cost": candidate.get("estimated_cost"),
        "roi_score": candidate.get("roi_score"),
        "privacy_state": candidate.get("privacy_state") or candidate.get("privacy"),
        "privacy_blocked": candidate.get("privacy_blocked"),
        "blocked_by_privacy": candidate.get("blocked_by_privacy"),
        "output_authority": "navigation_only",
        "navigation_only": True,
        "source_refs": candidate.get("source_refs") or [],
    }


def _domain_row(candidate: Mapping[str, Any], readiness_row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(readiness_row.get("status") or "suppressed")
    ready = status == "ready"
    title = _safe_text(
        candidate.get("title")
        or candidate.get("domain")
        or candidate.get("owner_surface")
        or "prewarm domain",
        140,
    )
    refs = safe_source_refs(candidate.get("source_refs") or [])
    reason_codes = [
        str(reason)
        for reason in readiness_row.get("reason_codes") or []
        if str(reason or "").strip()
    ]
    row = {
        "domain_id_hash": _sha(
            candidate.get("domain_id") or candidate.get("route_id") or title,
            prefix="prewarm",
        ),
        "title": title,
        "owner_surface": _safe_text(candidate.get("owner_surface") or "anticipatory_prewarm", 80),
        "status": status,
        "readiness_class": readiness_row.get("readiness_class") or "silent",
        "navigation_only": True,
        "next_action": "source_reopen" if ready else "stay_silent",
        "source_refs": refs,
        "source_ref_count": len(refs),
        "freshness": readiness_row.get("freshness") or "unknown",
        "ttl_seconds": _int(readiness_row.get("ttl_seconds")),
        "ttl_remaining_seconds": _int(readiness_row.get("ttl_remaining_seconds")),
        "roi_score": _float(readiness_row.get("roi_score")),
        "query_aliases": _safe_terms(
            candidate.get("query_aliases") or candidate.get("aliases") or [],
            limit=MAX_ALIASES,
            chars=80,
        ),
        "invalidation_triggers": _safe_terms(
            candidate.get("invalidation_triggers") or [],
            limit=MAX_INVALIDATION_TRIGGERS,
            chars=80,
        ),
        "reason_codes": reason_codes,
        "source_boundary": {
            "prewarm_is_navigation_only": True,
            "source_reopen_required_before_claim": True,
            "ready_row_is_not_evidence": True,
            "suppressed_row_stays_silent": not ready,
        },
    }
    if ready:
        row["source_reopen_path"] = {"tool": "source_reopen", "source_refs": refs[:3]}
    return row


def _latency_saved_estimate(
    candidates: list[Mapping[str, Any]],
    rows: list[Mapping[str, Any]],
) -> int:
    total = 0
    for candidate, row in zip(candidates, rows, strict=False):
        if row.get("status") != "ready":
            continue
        total += max(0, _int(candidate.get("latency_saved_ms_estimate")))
    return total


def _metrics(
    *,
    candidates: list[Mapping[str, Any]],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    raw_metrics = readiness.get("metrics")
    route_metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    raw_rates = route_metrics.get("rates")
    rates: Mapping[str, Any] = raw_rates if isinstance(raw_rates, Mapping) else {}
    rows = [row for row in readiness.get("rows") or [] if isinstance(row, Mapping)]
    source_reopen_rate = _float(rates.get("source_reopen_after_prewarm_rate"), 0.0)
    return {
        "prewarm_candidate_count": len(candidates),
        "prewarm_ready_count": _int(route_metrics.get("ready_count")),
        "prewarm_suppressed_count": _int(route_metrics.get("suppressed_count")),
        "prewarm_consumed_count": _int(route_metrics.get("prewarm_consumed_count")),
        "prewarm_hit_rate": source_reopen_rate,
        "wasted_prewarm_rate": _float(rates.get("wasted_prewarm_rate"), 0.0),
        "stale_prewarm_suppression_count": _int(route_metrics.get("stale_suppression_count")),
        "privacy_suppression_count": _int(route_metrics.get("privacy_suppression_count")),
        "low_value_suppression_count": _int(route_metrics.get("low_value_suppression_count")),
        "foreground_latency_saved_ms_estimate": _latency_saved_estimate(candidates, rows),
        "model_visible_claim_from_prewarm_violation_count": 0,
        "source_reopen_after_prewarm_rate": source_reopen_rate,
    }


def prewarm_planner_report(
    candidates: Iterable[Mapping[str, Any]],
    *,
    active_lock_roi: Mapping[str, Any] | None = None,
    now_unix: float | None = None,
    min_roi_score: float = 1.0,
) -> dict[str, Any]:
    """Emit a no-write anticipatory prewarm report over candidate domains."""

    clean_candidates = [candidate for candidate in candidates if isinstance(candidate, Mapping)]
    readiness = route_readiness_report(
        [_route_candidate(candidate) for candidate in clean_candidates],
        active_lock_roi=active_lock_roi,
        now_unix=now_unix,
        min_roi_score=min_roi_score,
    )
    readiness_rows = [row for row in readiness.get("rows") or [] if isinstance(row, Mapping)]
    predicted_domains = [
        _domain_row(candidate, row)
        for candidate, row in zip(clean_candidates, readiness_rows, strict=False)
    ]
    return {
        "kind": PREWARM_PLANNER_KIND,
        "schema_version": PREWARM_PLANNER_SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "navigation_only": True,
        "predicted_domains": predicted_domains,
        "route_readiness": readiness,
        "metrics": _metrics(candidates=clean_candidates, readiness=readiness),
        "contract": {
            "no_write_report_only": True,
            "reuses_route_readiness": True,
            "clean_source_mutation_allowed": False,
            "owner_surface_mutation_allowed": False,
            "foreground_hook_mutation_allowed": False,
            "prewarm_output_authority": "navigation_only",
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
            "answer_text_serialized": False,
        },
        "can_claim": [
            "roi_gated_prewarm_planner_fixture_exists",
            "prewarm_candidates_reuse_route_readiness",
            "suppressed_prewarm_reason_codes_are_reported",
        ],
        "cannot_claim": [
            "prewarm_candidate_is_source_truth",
            "prewarm_route_is_source_backed_evidence",
            "full_sleep_cycle_planner_is_live",
            "foreground_hooks_consume_prewarm_by_default",
            "live_latency_savings_are_proven",
        ],
    }


def fixture_prewarm_planner_report() -> dict[str, Any]:
    fixed_now = 1_780_000_000.0
    return prewarm_planner_report(
        [
            {
                "domain_id": "ready-active-path",
                "title": "Active path packet follow-up",
                "owner_surface": "warm_ambient",
                "freshness": "current",
                "created_unix": fixed_now - 120,
                "ttl_seconds": 900,
                "expected_value": 4,
                "estimated_cost": 1,
                "latency_saved_ms_estimate": 160,
                "query_aliases": ["active path packet", "task-start route"],
                "invalidation_triggers": ["registry_fingerprint_changed"],
                "source_refs": [{"source_id": "clean:route-ready", "message_id": "m1"}],
                "raw_prompt": "SECRET_TOKEN=abc123 must not serialize",
            },
            {
                "domain_id": "stale-route",
                "title": "Stale route",
                "owner_surface": "dream",
                "freshness": "stale",
                "created_unix": fixed_now - 2_000,
                "ttl_seconds": 600,
                "expected_value": 4,
                "estimated_cost": 1,
                "source_refs": [{"source_id": "clean:old", "message_id": "m2"}],
            },
            {
                "domain_id": "privacy-route",
                "title": "Privacy route",
                "owner_surface": "warm_ambient",
                "freshness": "current",
                "created_unix": fixed_now - 30,
                "ttl_seconds": 900,
                "privacy_state": "blocked",
                "expected_value": 3,
                "estimated_cost": 1,
                "source_refs": [{"source_id": "clean:private", "thread_key": "E:\\private\\thread.jsonl"}],
            },
            {
                "domain_id": "low-roi-route",
                "title": "Low ROI route",
                "owner_surface": "semantic_trigger",
                "freshness": "current",
                "created_unix": fixed_now - 30,
                "ttl_seconds": 900,
                "expected_value": 0.2,
                "estimated_cost": 1,
                "source_refs": [{"source_id": "clean:weak", "message_id": "m3"}],
            },
        ],
        active_lock_roi={
            "lock_pull_count": 1,
            "lock_reopen_attempt_count": 1,
            "source_backed_hit_count": 1,
            "wrong_or_stale_route_count": 0,
            "expired_before_consumption_count": 1,
            "never_read_count": 1,
        },
        now_unix=fixed_now,
    )
