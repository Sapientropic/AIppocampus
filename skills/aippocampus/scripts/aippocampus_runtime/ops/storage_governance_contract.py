"""Shared contract constants for storage governance planning."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.ops import storage_capacity_report

SCHEMA_VERSION = 1

CLASS_ALL = "all"
CLASS_REBUILDABLE = "rebuildable"
CLASS_REVIEW_ARTIFACT = "review-artifact"
SUPPORTED_CLASSES = {CLASS_ALL, CLASS_REBUILDABLE, CLASS_REVIEW_ARTIFACT}

TIER_CANONICAL_SOURCE = "canonical_source"
TIER_REBUILDABLE_CACHE = "rebuildable_cache"
TIER_REVIEW_ARTIFACT = "navigation_review_artifact"

REBUILDABLE_ACTIONS = {"rebuildable_delete_under_disk_pressure"}
REVIEW_ARTIFACT_ACTIONS = {
    "archive_or_delete_after_human_review",
    "delete_when_no_export_is_running",
}
PROTECTED_SOURCE_ACTIONS = {
    "do_not_modify_live_file",
    "keep_and_version",
    "compress_in_cold_archive_only",
    "compress_copy_with_cold_archive.py",
}


def human_bytes(size: int) -> str:
    return storage_capacity_report.human_bytes(size)


def candidate_class_for_tier(tier: str) -> str:
    if tier == TIER_REBUILDABLE_CACHE:
        return CLASS_REBUILDABLE
    if tier == TIER_REVIEW_ARTIFACT:
        return CLASS_REVIEW_ARTIFACT
    return TIER_CANONICAL_SOURCE


def matches_class(candidate: dict[str, Any], class_filter: str) -> bool:
    if class_filter == CLASS_ALL:
        return True
    return candidate.get("class") == class_filter


def status(status_name: str, *, evidence: str, requirement: str) -> dict[str, str]:
    return {
        "status": status_name,
        "requirement": requirement,
        "evidence": evidence,
    }


def capacity_preconditions(thread: dict[str, Any], *, include_active: bool) -> dict[str, Any]:
    clean_bytes = int(thread.get("canonical_clean_source_bytes") or 0)
    raw_bytes = int(thread.get("raw_audit_source_bytes") or 0)
    source_ok = clean_bytes > 0 or raw_bytes > 0
    return {
        "raw_or_clean_source": status(
            "passed" if source_ok else "blocked",
            evidence=(
                f"capacity thread clean={clean_bytes} raw={raw_bytes}"
                if source_ok
                else "capacity report has no raw or clean-source bytes for this thread"
            ),
            requirement="Exact raw or clean source must remain available before cache eviction.",
        ),
        "clean_source_manifest": status(
            "passed" if clean_bytes > 0 else "needs_apply_check",
            evidence=(
                f"capacity thread canonical_clean_source_bytes={clean_bytes}"
                if clean_bytes > 0
                else "capacity report cannot prove clean-source manifest bytes"
            ),
            requirement="Clean-source manifest must exist for caches derived from clean source.",
        ),
        "active_thread_exclusion": status(
            "needs_apply_check" if include_active else "blocked_by_default",
            evidence=(
                "--include-active was passed; apply mode must still prove the thread is safe."
                if include_active
                else "Active-thread matching requires apply-time thread identity checks."
            ),
            requirement="Do not evict the current active thread unless explicitly requested.",
        ),
        "writer_or_export_lease": status(
            "needs_apply_check",
            evidence="Capacity report does not inspect live leases.",
            requirement="No active writer/build/export lease may own the target path.",
        ),
    }


def generation_gc_candidates_from_capacity_thread(
    thread: dict[str, Any],
    *,
    include_active: bool,
) -> list[dict[str, Any]]:
    generations = thread.get("index_generations") or {}
    if not isinstance(generations, dict):
        return []

    preconditions = capacity_preconditions(thread, include_active=include_active)
    preconditions["reader_pin_or_ttl_contract"] = status(
        "blocked",
        evidence=(
            "Old source-index generations are only reportable until reader-pin/TTL cleanup "
            "is implemented."
        ),
        requirement="Do not delete generation directories while foreground readers may still pin them.",
    )
    preconditions["last_known_good_pointer"] = status(
        "passed",
        evidence=(
            "Candidate excludes current_generation and last_known_good_generation from "
            "source_index.pointer.json."
        ),
        requirement="Generation cleanup must preserve current and last-known-good pointer targets.",
    )

    candidates: list[dict[str, Any]] = []
    for item in generations.get("generation_gc_candidates") or []:
        if not isinstance(item, dict):
            continue
        generation_id = str(item.get("generation") or "generation")
        size = int(item.get("bytes") or 0)
        if size <= 0:
            continue
        relative_path = item.get("relative_path")
        path: dict[str, Any] = {
            "path_known": bool(relative_path),
            "relative_path": relative_path,
            "relative_to": "registry",
        }
        if item.get("path"):
            path["path"] = item["path"]
        candidates.append(
            {
                "id": f"capacity:{thread.get('thread_dir')}:old-index-generation:{generation_id}",
                "class": CLASS_REBUILDABLE,
                "tier": TIER_REBUILDABLE_CACHE,
                "label": f"Old source-index generation {generation_id}",
                "kind": "rebuildable_old_index_generations",
                "bytes": size,
                "human_bytes": human_bytes(size),
                "path": path,
                "source_report": {
                    "kind": "storage_capacity_report",
                    "schema_version": SCHEMA_VERSION,
                    "section": "index_generations",
                    "thread_key": thread.get("thread_key"),
                    "thread_dir": thread.get("thread_dir"),
                    "current_generation": generations.get("current_generation"),
                    "last_known_good_generation": generations.get("last_known_good_generation"),
                    "generation": generation_id,
                },
                "evidence": [
                    f"generation={generation_id}",
                    f"old_generation_bytes={size}",
                    f"pointer_status={generations.get('status')}",
                    "current and last-known-good generations are excluded from this candidate",
                ],
                "preconditions": dict(preconditions),
                "rebuild_command": (
                    "Generation GC is plan-only until reader-pin/TTL cleanup lands; rebuild the "
                    "main index with python -m aippocampus_runtime.recall.index_builder "
                    "--cwd <workspace>."
                ),
                "expected_rebuild_cost": {"class": "medium", "seconds": None},
            }
        )
    return candidates


def rebuild_command_for_retention_item(item: dict[str, Any]) -> str | None:
    item_id = str(item.get("id") or "")
    kind = str(item.get("kind") or "")
    if item_id == "rebuildable-main-sqlite" or kind == "rebuildable_generated_index":
        return "python -m aippocampus_runtime.recall.index_builder --cwd <workspace>"
    if item_id == "rebuildable-segment-sqlite":
        return "python -m aippocampus_runtime.recall.segment_builder --cwd <workspace>"
    if item_id == "rebuildable-graphify-corpus" or kind == "rebuildable_generated_corpus":
        return "python -m aippocampus_runtime.ops.graphify_corpus --cwd <workspace>"
    return None


def metric_int(report: dict[str, Any], *path: str) -> int:
    value: Any = report
    for key in path:
        if not isinstance(value, dict):
            return 0
        value = value.get(key)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def plan_metrics(
    *,
    capacity_report: dict[str, Any],
    retention_report: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    protected = metric_int(capacity_report, "totals", "raw_audit_source_bytes") + metric_int(
        capacity_report,
        "totals",
        "canonical_clean_source_bytes",
    )
    if protected <= 0 and retention_report is not None:
        protected = sum(
            int(item.get("bytes") or 0)
            for item in retention_report.get("items") or []
            if str(item.get("action") or "") in PROTECTED_SOURCE_ACTIONS
        )

    reclaimable_rebuildable = metric_int(
        capacity_report,
        "totals",
        "generated_index_bytes",
    ) + metric_int(capacity_report, "totals", "semantic_sidecar_bytes")
    if reclaimable_rebuildable <= 0:
        reclaimable_rebuildable = sum(
            int(item.get("bytes") or 0)
            for item in candidates
            if item.get("tier") == TIER_REBUILDABLE_CACHE
        )

    reclaimable_review = sum(
        int(item.get("bytes") or 0)
        for item in candidates
        if item.get("tier") == TIER_REVIEW_ARTIFACT
    )

    return {
        "protected_source_bytes": protected,
        "protected_source_human": human_bytes(protected),
        "reclaimable_rebuildable_bytes": reclaimable_rebuildable,
        "reclaimable_rebuildable_human": human_bytes(reclaimable_rebuildable),
        "reclaimable_review_artifact_bytes": reclaimable_review,
        "reclaimable_review_artifact_human": human_bytes(reclaimable_review),
        "generated_index_amplification_ratio": (capacity_report.get("totals") or {}).get(
            "index_amplification_ratio",
            0.0,
        ),
        "archive_verified": False,
        "archive_verification_status": "not_checked_in_dry_run",
        "eviction_candidate_count": len(candidates),
        "eviction_applied_count": 0,
        "expected_rebuild_seconds": None,
        "expected_rebuild_cost_class": "medium" if candidates else "none",
        "post_eviction_recall_surface_ok": None,
        "post_eviction_recall_surface_status": "not_checked_in_dry_run",
    }
