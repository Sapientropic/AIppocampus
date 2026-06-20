"""Public warm ambient job-result summaries."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.subconscious.runtime import compact_usage
from aippocampus_runtime.warm_ambient.diagnostics import (
    suppression_diagnostics,
    suppression_reason_buckets,
)
from aippocampus_runtime.warm_ambient.error_classification import scout_error_kind

WARM_JOB_SCHEMA_VERSION = 1


def _cache_write_summary(cache_write: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cache_write, dict):
        return None
    summary = {
        "status": cache_write.get("status"),
        "reason": cache_write.get("reason"),
        "topic_epoch": cache_write.get("topic_epoch"),
        "card_count": cache_write.get("card_count"),
        "source_ref_fingerprint_count": len(cache_write.get("source_ref_fingerprints") or []),
    }
    guard_coverage = cache_write.get("guard_coverage")
    if isinstance(guard_coverage, dict):
        summary["guard_coverage"] = guard_coverage
    residue = cache_write.get("residue_export")
    if isinstance(residue, dict):
        summary["residue_export"] = {
            "status": residue.get("status"),
            "topic_epoch": residue.get("topic_epoch"),
            "residue_count": residue.get("residue_count"),
            "residue_id": residue.get("residue_id"),
        }
    return {key: value for key, value in summary.items() if value is not None}


def warm_job_result_summary(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    error_kinds: dict[str, int] = {}
    for row in result.get("scouts") or []:
        if row.get("ok"):
            continue
        kind = str(row.get("error_kind") or scout_error_kind(row.get("reason")))
        error_kinds[kind] = error_kinds.get(kind, 0) + 1
    summary = {
        "kind": "aippocampus_warm_ambient_recall_job_result",
        "schema_version": WARM_JOB_SCHEMA_VERSION,
        "job_id": job.get("job_id"),
        "prompt_hash": job.get("prompt_hash") or job.get("prompt_sha1"),
        "created_at": now_utc(),
        "ok": bool(result.get("ok")),
        "available": bool(result.get("available")),
        "status": result.get("status"),
        "reason": result.get("reason") or "",
        "quorum_met": bool(result.get("quorum_met")),
        "useful_signal_quorum_met": bool(result.get("useful_signal_quorum_met")),
        "batch_end_reason": result.get("batch_end_reason"),
        "configured_scout_count": int(result.get("scout_count") or 0),
        "observed_scout_result_count": len(result.get("scouts") or []),
        "prefix_cache_warmup_scout_count": int(result.get("prefix_cache_warmup_scout_count") or 0),
        "accepted_scout_count": int(result.get("accepted_scout_count") or 0),
        "failed_scout_count": int(result.get("failed_scout_count") or 0),
        "scout_error_kinds": error_kinds,
        "card_count": len(result.get("cards") or []),
        "topic_epoch": result.get("topic_epoch"),
        "topic_epoch_action": (result.get("topic_epoch_decision") or {}).get("action"),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
        "suppression_reason_buckets": suppression_reason_buckets(result),
        "suppression_diagnostics": suppression_diagnostics(result),
        "guard_coverage": result.get("guard_coverage") or {},
        "cache_write": _cache_write_summary(result.get("cache_write")),
        "active_recall_lock": {
            "lock_id": (result.get("active_recall_lock") or {}).get("lock_id"),
            "state": (result.get("active_recall_lock") or {}).get("state"),
            "support_level": "scent",
            "source_reopen_required": True,
        }
        if isinstance(result.get("active_recall_lock"), dict)
        else None,
        "usage": compact_usage(result.get("usage") or {}),
        "cache": result.get("cache") or {},
        "model_route": result.get("model_route") or {},
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "late_update_policy": "detached_wait_all_writes_thread_cache",
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_prompt_trace_emitted": False,
            "raw_cards_emitted": False,
            "absolute_paths_emitted": False,
        },
    }
    if job.get("prompt_sha1"):
        summary["legacy_prompt_sha1"] = job.get("prompt_sha1")
    return summary
