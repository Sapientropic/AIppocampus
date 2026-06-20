"""Public projection for short-lived active-recall locks.

Active recall locks are route handles, not memory or evidence. This module owns
the foreground-safe projection so storage/lifecycle changes cannot accidentally
turn lock aliases or candidate refs into factual claim support.
"""

from __future__ import annotations

import time
from typing import Any

from aippocampus_runtime.question.source_refs import source_ref_key
from aippocampus_runtime.recall.active_recall_lock_lifecycle import roi_metrics

LOCK_SCHEMA_VERSION = 2
LOCK_STATES = {"pending", "ready", "expired", "failed"}


def _is_reopenable_ref(ref: dict[str, Any]) -> bool:
    if not isinstance(ref, dict):
        return False
    thread_key, message_id, turn_anchor, line = source_ref_key(ref)
    return bool(thread_key and (message_id or turn_anchor or line))


def reopenable_ref_count(refs: list[dict[str, Any]] | None) -> int:
    return sum(1 for ref in refs or [] if _is_reopenable_ref(ref))


def public_lock(entry: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    state = str(entry.get("state") or "pending")
    invalidated_by: list[str] = []
    expires_unix = float(entry.get("expires_unix") or 0.0)
    if expires_unix and current > expires_unix:
        invalidated_by.append("ttl_expired")
        state = "expired"
    if state not in LOCK_STATES:
        state = "failed"
    diagnostics = dict(entry.get("diagnostics") or {})
    candidate_refs = [
        dict(ref) for ref in entry.get("candidate_refs") or [] if isinstance(ref, dict)
    ]
    ref_count = reopenable_ref_count(candidate_refs)
    if state == "ready" and ref_count == 0:
        state = "pending"
        diagnostics["ready_downgraded_no_reopenable_refs"] = True
    age_ms = max(0, int((current - float(entry.get("created_unix") or current)) * 1000))
    diagnostics["lock_age_ms"] = age_ms
    if invalidated_by:
        diagnostics["invalidated_by"] = invalidated_by
    lock_version = max(1, int(entry.get("lock_version") or 1))
    enrichment_generation = max(0, int(entry.get("enrichment_generation") or 0))
    consumer_metrics = dict(entry.get("consumer_metrics") or {})
    first_generation = int(consumer_metrics.get("first_read_generation") or 0)
    consumer_metrics["read_generation_superseded"] = (
        bool(consumer_metrics.get("read_count")) and first_generation < enrichment_generation
    )
    return {
        "kind": "aippocampus_active_recall_lock",
        "schema_version": LOCK_SCHEMA_VERSION,
        "lock_id": entry.get("lock_id"),
        "lock_version": lock_version,
        "enrichment_generation": enrichment_generation,
        "state_transition": entry.get("state_transition") or f"{state}->{state}",
        "state": state,
        "support_level": "scent",
        "candidate_refs": candidate_refs,
        "candidate_ref_count": len(candidate_refs),
        "reopenable_ref_count": ref_count,
        "query_aliases": list(entry.get("query_aliases") or []),
        "route_reasons": list(entry.get("route_reasons") or []),
        "conflict_flags": list(entry.get("conflict_flags") or []),
        "source_reopen_required": True,
        "source_boundary": {
            "navigation_only_until_source_reopened": True,
            "model_aliases_are_not_facts": True,
            "candidate_refs_are_ids_only": True,
        },
        "suggested_next": "active_recall --mode reopen --lock-id <lock_id>",
        "thread_fingerprint": entry.get("thread_fingerprint"),
        "workspace_fingerprint": entry.get("workspace_fingerprint"),
        "prompt_fingerprint": entry.get("prompt_fingerprint"),
        "topic_epoch": entry.get("topic_epoch"),
        "registry_freshness_fingerprint": entry.get("registry_freshness_fingerprint"),
        "freshness_vector": dict(entry.get("freshness_vector") or {}),
        "consumer_metrics": consumer_metrics,
        "enrichment_timing": dict(entry.get("enrichment_timing") or {}),
        "roi_metrics": roi_metrics(entry.get("roi_metrics")),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "expires_at": entry.get("expires_at"),
        "diagnostics": diagnostics,
    }
