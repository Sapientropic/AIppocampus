#!/usr/bin/env python3
"""Compatibility shim for the packaged dream retrospective lifecycle."""

from __future__ import annotations

from aippocampus_runtime.dream.retrospective_lifecycle import (
    ELIGIBLE_DREAM_FUNCTIONS,
    LIFECYCLE_KIND,
    REGISTRY_LATER_ROW_FILES,
    SUMMARY_KIND,
    eligible_later_rows_for_probe,
    evidence_kind_counts,
    is_retrospective_probe,
    iter_jsonl,
    lifecycle_item,
    load_registry_rows,
    main,
    probe_created_at,
    probe_id,
    public_lifecycle_summary,
    review_due,
    row_created_at,
    row_mentions_project,
    run_retrospective_lifecycle,
    term_overlap_without_target,
)

__all__ = [
    "ELIGIBLE_DREAM_FUNCTIONS",
    "LIFECYCLE_KIND",
    "REGISTRY_LATER_ROW_FILES",
    "SUMMARY_KIND",
    "eligible_later_rows_for_probe",
    "evidence_kind_counts",
    "is_retrospective_probe",
    "iter_jsonl",
    "lifecycle_item",
    "load_registry_rows",
    "main",
    "probe_created_at",
    "probe_id",
    "public_lifecycle_summary",
    "review_due",
    "row_created_at",
    "row_mentions_project",
    "run_retrospective_lifecycle",
    "term_overlap_without_target",
]


if __name__ == "__main__":
    raise SystemExit(main())
