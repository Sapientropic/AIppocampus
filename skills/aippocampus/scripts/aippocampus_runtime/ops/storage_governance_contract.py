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


def rebuild_command_for_retention_item(item: dict[str, Any]) -> str | None:
    item_id = str(item.get("id") or "")
    kind = str(item.get("kind") or "")
    if item_id == "rebuildable-main-sqlite" or kind == "rebuildable_generated_index":
        return "python ...\\build_index.py --cwd <workspace>"
    if item_id == "rebuildable-segment-sqlite":
        return "python ...\\build_segments.py --cwd <workspace>"
    if item_id == "rebuildable-graphify-corpus" or kind == "rebuildable_generated_corpus":
        return "python ...\\prepare_graphify_corpus.py --cwd <workspace>"
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
