"""Foreground action cards for storage governance plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.ops.storage_governance_contract import (
    CLASS_REBUILDABLE,
    TIER_REBUILDABLE_CACHE,
)

CAPACITY_AGGREGATE_PLAN_ONLY_REASON = (
    "Capacity aggregate candidates need path-level retention candidates before apply or rebuild."
)
CAPACITY_AGGREGATE_REBUILD_NOTE = (
    "Rebuild generated index/vector/semantic caches from exact source for this "
    "registered thread; exact command depends on the cache class."
)
GENERATION_CLEANUP_KINDS = {
    "rebuildable_old_index_generations",
    "rebuildable_old_segment_generations",
}


def _has_concrete_path(candidate: Mapping[str, Any]) -> bool:
    path = candidate.get("path")
    if not isinstance(path, Mapping):
        return False
    return bool(path.get("path_known") or path.get("path") or path.get("relative_path"))


def _has_known_blocked_precondition(candidate: Mapping[str, Any]) -> bool:
    preconditions = candidate.get("preconditions")
    if not isinstance(preconditions, Mapping):
        return False
    for item in preconditions.values():
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "")
        if status == "blocked":
            return True
    return False


def candidate_can_offer_compact_apply(candidate: Mapping[str, Any]) -> bool:
    """Return True only when compact summary may expose an apply lane.

    Compact storage summaries are foreground choosers. They must not infer
    "apply is probably fine" from a non-aggregate actionability flag: agents
    routinely mistake that for a safe deletion path. Keep the predicate tied to
    apply-owned candidate classes, path-level evidence, and non-blocked
    preconditions. `needs_apply_check` stays eligible because live lease/current
    thread checks are intentionally deferred to explicit apply mode.
    """

    if _has_known_blocked_precondition(candidate):
        return False
    if not _has_concrete_path(candidate):
        return False
    if (
        candidate.get("class") != CLASS_REBUILDABLE
        or candidate.get("tier") != TIER_REBUILDABLE_CACHE
    ):
        return False
    kind = str(candidate.get("kind") or "")
    candidate_id = str(candidate.get("id") or "")
    if kind in GENERATION_CLEANUP_KINDS:
        return True
    return kind == "rebuildable_generated_index" and candidate_id == "retention:rebuildable-main-sqlite"


def retention_report_generation_action() -> dict[str, Any]:
    """Return the discoverable pre-apply evidence step for storage GC.

    Storage apply must be backed by path-level retention evidence. Keep this as
    an explicit action instead of burying the lower-level module command in a
    warning string, so compact storage cards can route users toward evidence
    without making cleanup feel inevitable.
    """

    return {
        "id": "generate_retention_report",
        "label": "Generate retention report",
        "command": "python -m aippocampus_runtime.ops.retention_report --cwd . --write --json",
        "mutation_risk": "writes_local_retention_report_artifacts",
        "why": "Create path-level retention evidence before considering any storage cleanup apply.",
    }


def storage_gc_foreground_actions(
    *,
    retention_report_available: bool,
) -> dict[str, list[dict[str, Any]] | list[str]]:
    if not retention_report_available:
        return {
            "safe_next_actions": [
                {
                    "id": "preview_storage_gc_summary",
                    "label": "Preview compact storage summary",
                    "command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                    "mutation_risk": "read_only",
                    "claim_boundary": "operator_diagnostic_not_source_evidence",
                    "why": "Use the compact no-write pressure card before opening path-level storage detail.",
                },
                retention_report_generation_action(),
                {
                    "id": "bounded_storage_audit",
                    "label": "Run bounded storage audit",
                    "command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                    "mutation_risk": "read_only",
                    "claim_boundary": "operator_diagnostic_not_source_evidence",
                    "why": "Capacity aggregates are plan-only; path-level retention candidates are required before apply.",
                },
                {
                    "id": "open_full_storage_audit",
                    "label": "Open full storage audit",
                    "command": "aippocampus storage gc --dry-run --json --full --cwd .",
                    "mutation_risk": "read_only",
                    "claim_boundary": "operator_diagnostic_not_source_evidence",
                    "operator_only": True,
                    "why": "Use only when bounded detail is insufficient; full scans are operator diagnostics, not foreground defaults.",
                },
            ],
            "next_steps": [
                "Review candidate preconditions before any manual cleanup.",
                "Get path-level retention candidates before apply; capacity aggregates remain plan-only.",
                "Use --apply only after retention-report-backed path candidates pass apply-time checks.",
            ],
        }
    return {
        "safe_next_actions": [
            {
                "id": "preview_path_level_storage_candidates",
                "label": "Preview path-level storage candidates",
                "command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                "mutation_risk": "read_only",
                "claim_boundary": "operator_diagnostic_not_source_evidence",
                "why": "Review retention-report-backed candidates and preconditions before apply.",
            },
            {
                "id": "apply_rebuildable_storage_gc_after_review",
                "label": "Apply rebuildable cleanup after review",
                "command": "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
                "mutation_risk": "explicit_local_delete_of_rebuildable_cache",
                "claim_boundary": "operator_action_not_source_evidence",
                "why": "Apply only retention-report-backed rebuildable cache candidates whose checks pass.",
            },
        ],
        "next_steps": [
            "Review candidate preconditions before any manual cleanup.",
            "Use --apply only for rebuildable cache candidates with deterministic source, lease, active-thread, and manifest checks.",
        ],
    }


def storage_gc_summary_actions(
    *,
    limit: int,
    include_apply: bool,
    pressure_present: bool,
    needs_retention_report: bool = False,
) -> list[dict[str, Any]]:
    """Return compact summary choices without making cleanup feel inevitable.

    Summary JSON is a foreground chooser, not an audit report. Keep
    stop/no-cleanup available because "do nothing" is still a safe explicit
    choice. When computed pressure is present, put the bounded no-write review
    first so the foreground action does not contradict high reclaimable bytes.
    Apply appears only when existing evidence can be audited and rebuilt.
    """

    top = max(1, int(limit))
    stop_action = {
        "id": "stop_without_cleanup",
        "label": "Stop without cleanup",
        "continue_without_command": True,
        "no_command_needed": True,
        "message": (
            "Continue without mutating storage; cleanup remains optional unless "
            "the user chooses a storage review."
        )
        if pressure_present
        else "No cleanup is required from this summary; continue without mutating storage.",
        "mutation_risk": "read_only",
        "claim_boundary": "storage_pressure_summary_not_memory_quality_evidence",
        "why": "Storage GC is optional operator work unless the user explicitly chooses audit/apply.",
    }
    audit_action = {
        "id": "bounded_storage_audit",
        "label": "Run bounded storage audit",
        "command": f"aippocampus storage gc --dry-run --json --top {top} --cwd .",
        "mutation_risk": "read_only",
        "claim_boundary": "operator_diagnostic_not_source_evidence",
        "why": "Open a small no-write candidate sample when reclaimable storage pressure is worth inspecting.",
    }
    actions: list[dict[str, Any]] = (
        [audit_action]
        if pressure_present
        else [stop_action, audit_action]
    )
    if include_apply:
        actions.append(
            {
                "id": "apply_rebuildable_after_audit",
                "label": "Apply rebuildable cleanup after audit",
                "command": "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
                "mutation_risk": "explicit_local_delete_of_rebuildable_cache",
                "claim_boundary": "operator_action_not_source_evidence",
                "why": "Apply only after the bounded/full audit confirms rebuildable candidates and checks.",
                "requires_prior_audit": True,
                "deterministic_checks": [
                    "source_or_retention_report_available",
                    "active_thread_exclusion",
                    "reader_pin_or_ttl_contract",
                    "apply_time_manifest_or_rebuild_path",
                ],
                "rollback_or_rebuild_boundary": (
                    "Applies only to rebuildable cache classes; source history is protected "
                    "and the documented rebuild path must restore the cache."
                ),
            }
        )
    elif pressure_present and needs_retention_report:
        actions.append(retention_report_generation_action())
    if pressure_present:
        actions.append(stop_action)
    return actions
