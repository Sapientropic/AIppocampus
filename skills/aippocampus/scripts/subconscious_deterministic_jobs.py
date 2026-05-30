#!/usr/bin/env python3
"""Deterministic follow-up jobs for the subconscious runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DETERMINISTIC_QUESTION_TRACKING_RUNNER = "deterministic_question_tracking"
DETERMINISTIC_THEME_EMERGENCE_RUNNER = "deterministic_theme_emergence"
DETERMINISTIC_QUESTION_RESOLUTION_RUNNER = "deterministic_question_resolution"
DETERMINISTIC_RUNNERS = {
    DETERMINISTIC_QUESTION_TRACKING_RUNNER,
    DETERMINISTIC_THEME_EMERGENCE_RUNNER,
    DETERMINISTIC_QUESTION_RESOLUTION_RUNNER,
}


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


def run_theme_emergence_job(
    *,
    registry_path: Path | None,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    no_write: bool,
    dry_run: bool,
) -> dict[str, Any]:
    del registry_path
    import theme_emergence

    theme_result = theme_emergence.run_theme_emergence(
        jobs_path=jobs_output_path,
        concept_graph_path=concept_graph_path,
        output_path=jobs_output_path,
        no_write=no_write or dry_run,
    )
    finding_count = (
        int(theme_result.get("fresh_theme_count") or 0)
        if not no_write and not dry_run
        else int(theme_result.get("theme_count") or 0)
    )
    return {
        "ok": True,
        "dry_run": dry_run,
        "job": "theme_emergence",
        "sample_index": 1,
        "sample_count": 1,
        "model": "deterministic",
        "model_route": {"provider": "deterministic"},
        "turn_count": 0,
        "finding_count": finding_count,
        "edge_count": 0,
        "findings": theme_result.get("themes") or [],
        "tool_steps": [],
        "final_attempts": [],
        "usage": {},
        "cache": {"available": False, "kind": "none"},
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": bool(theme_result.get("wrote")),
        "deferred_write": False,
        "batch_id": theme_result.get("batch_id"),
        "theme_emergence": {key: value for key, value in theme_result.items() if key not in {"themes"}},
    }


def run_question_resolution_job(
    *,
    registry_path: Path | None,
    jobs_output_path: Path,
    edges_output_path: Path,
    no_write: bool,
    dry_run: bool,
) -> dict[str, Any]:
    import question_resolution

    resolution = question_resolution.run_question_resolution(
        jobs_path=jobs_output_path,
        registry_path=registry_path,
        output_path=jobs_output_path,
        no_write=no_write or dry_run,
    )
    finding_count = (
        int(resolution.get("fresh_signal_count") or 0)
        if not no_write and not dry_run
        else int(resolution.get("candidate_signal_count") or 0)
    )
    return {
        "ok": True,
        "dry_run": dry_run,
        "job": "question_resolution",
        "sample_index": 1,
        "sample_count": 1,
        "model": "deterministic",
        "model_route": {"provider": "deterministic"},
        "turn_count": 0,
        "finding_count": finding_count,
        "edge_count": 0,
        "findings": resolution.get("signals") or [],
        "tool_steps": [],
        "final_attempts": [],
        "usage": {},
        "cache": {"available": False, "kind": "none"},
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": bool(resolution.get("wrote_count")),
        "deferred_write": False,
        "batch_id": "",
        "question_resolution": {
            key: value for key, value in resolution.items() if key not in {"signals"}
        },
    }


def run_deterministic_job(
    job: str,
    *,
    registry_path: Path | None,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    no_write: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if job == "question_tracking":
        return run_question_tracking_job(
            registry_path=registry_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            no_write=no_write,
            dry_run=dry_run,
        )
    if job == "theme_emergence":
        return run_theme_emergence_job(
            registry_path=registry_path,
            concept_graph_path=concept_graph_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            no_write=no_write,
            dry_run=dry_run,
        )
    if job == "question_resolution":
        return run_question_resolution_job(
            registry_path=registry_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            no_write=no_write,
            dry_run=dry_run,
        )
    raise ValueError(f"unknown deterministic job {job!r}")
