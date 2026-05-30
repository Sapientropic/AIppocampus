#!/usr/bin/env python3
"""Deterministic follow-up jobs for the subconscious runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DETERMINISTIC_QUESTION_TRACKING_RUNNER = "deterministic_question_tracking"


def run_question_tracking_job(
    *,
    registry_path: Path | None,
    jobs_output_path: Path,
    edges_output_path: Path,
    no_write: bool,
    dry_run: bool,
) -> dict[str, Any]:
    import question_tracking

    tracking = question_tracking.run_question_tracking(
        jobs_path=jobs_output_path,
        registry_path=registry_path,
        output_path=jobs_output_path,
        no_write=no_write or dry_run,
    )
    finding_count = (
        int(tracking.get("fresh_link_count") or 0)
        if not no_write and not dry_run
        else int(tracking.get("link_count") or 0)
    )
    return {
        "ok": True,
        "dry_run": dry_run,
        "job": "question_tracking",
        "sample_index": 1,
        "sample_count": 1,
        "model": "deterministic",
        "model_route": {"provider": "deterministic"},
        "turn_count": 0,
        "finding_count": finding_count,
        "edge_count": 0,
        "findings": tracking.get("links") or [],
        "tool_steps": [],
        "final_attempts": [],
        "usage": {},
        "cache": {"available": False, "kind": "none"},
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": bool(tracking.get("wrote")),
        "deferred_write": False,
        "batch_id": tracking.get("batch_id"),
        "tracking": {key: value for key, value in tracking.items() if key not in {"links"}},
    }
