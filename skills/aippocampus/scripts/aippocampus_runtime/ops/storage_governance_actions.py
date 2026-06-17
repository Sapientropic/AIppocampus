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
