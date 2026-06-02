#!/usr/bin/env python3
"""Public-safe lifecycle helpers for active recall locks."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable

ROI_COUNTER_KEYS = (
    "reopen_attempt_count",
    "source_backed_hit_count",
    "wrong_or_stale_route_count",
)


def _sha(value: str, *, prefix: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _safe_freshness_kind(value: Any, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip())[:80]
    return text or fallback


def _file_freshness_fingerprint(path: Path | str | None, *, prefix: str) -> str:
    if path is None:
        return f"{prefix}_unknown"
    try:
        stat = Path(path).stat()
    except OSError:
        return f"{prefix}_missing"
    return _sha(f"{stat.st_mtime_ns}:{stat.st_size}", prefix=prefix)


def freshness_vector(
    *,
    registry_freshness_fingerprint_value: str,
    freshness_sources: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Build a public-safe freshness vector from registry and sidecar metadata."""
    vector = {"registry": registry_freshness_fingerprint_value}
    seen: dict[str, int] = {}
    for index, source in enumerate(freshness_sources or []):
        if not isinstance(source, dict):
            continue
        kind = _safe_freshness_kind(source.get("kind"), f"sidecar_{index + 1}")
        seen[kind] = seen.get(kind, 0) + 1
        key = kind if seen[kind] == 1 else f"{kind}_{seen[kind]}"
        vector[key] = _file_freshness_fingerprint(source.get("path"), prefix="sidecar")
    return vector


def nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def roi_metrics(value: Any = None) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    return {key: nonnegative_int(raw.get(key)) for key in ROI_COUNTER_KEYS}


def bump_roi_metrics(value: Any, **deltas: int) -> dict[str, int]:
    metrics = roi_metrics(value)
    for key, delta in deltas.items():
        if key in metrics:
            metrics[key] += nonnegative_int(delta)
    return metrics


def _safe_rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def summarize_lock_roi_entries(
    entries: list[dict[str, Any]],
    *,
    public_lock: Callable[[dict[str, Any]], dict[str, Any]],
    schema_version: int,
) -> dict[str, Any]:
    state_counts: dict[str, int] = {}
    lock_pull_count = 0
    read_while_pending_count = 0
    expired_before_consumption_count = 0
    never_read_count = 0
    enrichment_after_first_read_count = 0
    enrichment_after_expiry_count = 0
    counters = roi_metrics()
    for entry in entries:
        public = public_lock(entry)
        state = str(public.get("state") or "unknown")
        state_counts[state] = state_counts.get(state, 0) + 1
        consumer_metrics = dict(public.get("consumer_metrics") or {})
        read_count = nonnegative_int(consumer_metrics.get("read_count"))
        if read_count:
            lock_pull_count += 1
        else:
            never_read_count += 1
        if not read_count and state == "expired":
            expired_before_consumption_count += 1
        if consumer_metrics.get("first_read_state") == "pending":
            read_while_pending_count += 1
        timing = dict(public.get("enrichment_timing") or {})
        if timing.get("completed_after_first_read"):
            enrichment_after_first_read_count += 1
        if timing.get("completed_after_expiry"):
            enrichment_after_expiry_count += 1
        roi = roi_metrics(public.get("roi_metrics"))
        for key in ROI_COUNTER_KEYS:
            counters[key] += roi[key]
    lock_count = len(entries)
    reopen_attempt_count = counters["reopen_attempt_count"]
    return {
        "kind": "aippocampus_active_recall_lock_roi",
        "schema_version": schema_version,
        "lock_count": lock_count,
        "state_counts": dict(sorted(state_counts.items())),
        "lock_pull_count": lock_pull_count,
        "lock_reopen_attempt_count": reopen_attempt_count,
        "source_backed_hit_count": counters["source_backed_hit_count"],
        "wrong_or_stale_route_count": counters["wrong_or_stale_route_count"],
        "read_while_pending_count": read_while_pending_count,
        "expired_before_consumption_count": expired_before_consumption_count,
        "never_read_count": never_read_count,
        "enrichment_after_first_read_count": enrichment_after_first_read_count,
        "enrichment_after_expiry_count": enrichment_after_expiry_count,
        "rates": {
            "lock_pull_rate": _safe_rate(lock_pull_count, lock_count),
            "lock_reopen_rate": _safe_rate(reopen_attempt_count, lock_pull_count),
            "source_backed_hit_rate": _safe_rate(
                counters["source_backed_hit_count"], reopen_attempt_count
            ),
            "wrong_or_stale_route_rate": _safe_rate(
                counters["wrong_or_stale_route_count"], reopen_attempt_count
            ),
            "never_read_rate": _safe_rate(never_read_count, lock_count),
        },
        "source_boundary": {
            "aggregate_counts_only": True,
            "raw_prompts_omitted": True,
            "raw_source_text_omitted": True,
            "local_paths_omitted": True,
            "locks_are_navigation_only": True,
        },
        "cannot_claim": [
            "active_recall_lock_roi_proves_public_memory_quality",
            "lock_route_reasons_are_source_backed_facts_without_reopen",
        ],
    }
