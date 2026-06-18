"""Foreground action cards for storage governance plans."""

from __future__ import annotations

from typing import Any

CAPACITY_AGGREGATE_PLAN_ONLY_REASON = (
    "Capacity aggregate candidates need path-level retention candidates before apply or rebuild."
)
CAPACITY_AGGREGATE_REBUILD_NOTE = (
    "Rebuild generated index/vector/semantic caches from exact source for this "
    "registered thread; exact command depends on the cache class."
)


def storage_gc_foreground_actions(
    *,
    retention_report_available: bool,
) -> dict[str, list[dict[str, Any]] | list[str]]:
    if not retention_report_available:
        return {
            "safe_next_actions": [
                {
                    "id": "inspect_path_level_candidates",
                    "label": "Inspect path-level storage candidates",
                    "command": "aippocampus storage gc --dry-run --json --full --cwd .",
                    "mutation_risk": "read_only",
                    "claim_boundary": "operator_diagnostic_not_source_evidence",
                    "why": "Capacity aggregates are plan-only; path-level retention candidates are required before apply.",
                },
                {
                    "id": "preview_storage_gc_summary",
                    "label": "Preview compact storage summary",
                    "command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                    "mutation_risk": "read_only",
                    "claim_boundary": "operator_diagnostic_not_source_evidence",
                    "why": "Use this when a compact no-write pressure card is enough.",
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
                "command": "aippocampus storage gc --apply --class rebuildable --summary-json --cwd .",
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


def storage_gc_summary_actions(*, limit: int, include_apply: bool) -> list[dict[str, Any]]:
    """Return compact summary choices without making cleanup feel inevitable.

    Summary JSON is a foreground chooser, not an audit report. Keep
    stop/no-cleanup first because "do nothing" is the safest useful default
    when the user did not ask for storage work. Bounded audit remains one hop
    away for operator detail, and apply appears only when existing evidence can
    be audited and rebuilt.
    """

    top = max(1, int(limit))
    actions: list[dict[str, Any]] = [
        {
            "id": "stop_without_cleanup",
            "label": "Stop without cleanup",
            "command": "continue-without-cleanup",
            "message": "No cleanup is required from this summary; continue without mutating storage.",
            "mutation_risk": "read_only",
            "claim_boundary": "storage_pressure_summary_not_memory_quality_evidence",
            "why": "Storage GC is optional operator work unless the user explicitly chooses audit/apply.",
        },
        {
            "id": "bounded_storage_audit",
            "label": "Run bounded storage audit",
            "command": f"aippocampus storage gc --dry-run --json --top {top} --cwd .",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
            "why": "Open a small no-write candidate sample only when cleanup detail is worth inspecting.",
        },
    ]
    if include_apply:
        actions.append(
            {
                "id": "apply_rebuildable_after_audit",
                "label": "Apply rebuildable cleanup after audit",
                "command": "aippocampus storage gc --apply --class rebuildable --summary-json --cwd .",
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
    return actions
