#!/usr/bin/env python3
"""Produce agent-fallback result rows from queued source-backed tasks.

This is the executable bridge between the hook-safe fallback queue and the
existing materializer. It does not call an external model and it does not
promote memory. A host agent may use the queued task as its work order; this
local runner provides the conservative no-key path by emitting only candidates
joined to existing source-backed subconscious findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_payload
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.io_kernel import iter_jsonl_dict_rows_with_line_numbers
from aippocampus_runtime.subconscious import (
    agent_fallback_materializer,
    agent_fallback_queue,
    candidate_router,
    review,
)

RESULT_KIND = agent_fallback_materializer.RESULT_KIND
RESULT_PROVENANCE = "agent_fallback_executor"


def default_tasks_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / agent_fallback_queue.TASKS_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / agent_fallback_queue.TASKS_NAME


def default_jobs_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    return candidate_router.default_jobs_path(registry_path, registry_dir)


def default_results_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    return agent_fallback_materializer.default_results_path(registry_path, registry_dir)


def task_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, item in iter_jsonl_dict_rows_with_line_numbers(path):
        row = dict(item)
        row["_line_number"] = line_number
        rows.append(row)
    return rows


def _task_id(task: dict[str, Any]) -> str:
    explicit = str(task.get("task_id") or "").strip()
    if explicit:
        return explicit
    payload = {
        "project_label": task.get("project_label"),
        "reason": task.get("reason"),
        "created_at": task.get("created_at"),
        "line_number": task.get("_line_number"),
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return "aft_" + digest[:18]


def _processed_task_ids(results_path: Path) -> set[str]:
    return {
        str(row.get("task_id") or "")
        for row in task_rows(results_path)
        if row.get("kind") == RESULT_KIND and row.get("task_id")
    }


def _source_refs(finding: dict[str, Any]) -> list[dict[str, Any]]:
    return [ref for ref in finding.get("source_refs") or [] if isinstance(ref, dict)]


def _finding_project_labels(finding: dict[str, Any]) -> set[str]:
    labels = {str(finding.get("project_label") or "").strip()}
    for ref in _source_refs(finding):
        labels.add(str(ref.get("project_label") or "").strip())
    return {label for label in labels if label}


def _matches_task_project(finding: dict[str, Any], project_label: str) -> bool:
    if not project_label:
        return True
    labels = _finding_project_labels(finding)
    return not labels or project_label in labels


def _candidate_type_for_finding(finding: dict[str, Any]) -> str:
    kind = str(finding.get("finding_kind") or finding.get("kind") or "")
    job = str(finding.get("job") or "")
    if "question" in job or "question" in kind:
        return "question_candidate"
    if "theme" in job or "theme" in kind:
        return "theme_candidate"
    if "frontier" in kind:
        return "frontier_marker"
    if "contradiction" in job or "contradiction" in kind:
        return "contradiction_review"
    return "project_memory"


def _confidence_for_finding(finding: dict[str, Any]) -> float:
    quality_obj = finding.get("quality")
    quality: dict[str, Any] = quality_obj if isinstance(quality_obj, dict) else {}
    raw = (
        quality.get("promotion_readiness")
        or quality.get("heuristic_promotion_score")
        or finding.get("confidence")
        or 0.66
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.66
    return max(0.45, min(0.92, value))


def _candidate_from_finding(finding_id: str, finding: dict[str, Any]) -> dict[str, Any]:
    title = str(finding.get("title") or finding.get("summary") or "Agent fallback candidate")
    summary = str(finding.get("summary") or finding.get("why") or title)
    recommendation = str(
        finding.get("recommendation")
        or "Review through the existing source-backed promotion-candidate boundary."
    )
    candidate = {
        "candidate_type": _candidate_type_for_finding(finding),
        "title": compact_text(title, 160),
        "summary": compact_text(summary, 700),
        "recommendation": compact_text(recommendation, 360),
        "confidence": _confidence_for_finding(finding),
        "activation_cues": candidate_router.activation_cues_for(
            {"title": title, "summary": summary, "recommendation": recommendation}
        ),
        "source_finding_ids": [finding_id],
    }
    return sanitize_external_model_payload(candidate)


def _eligible_candidates(
    *,
    task: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    project_label = str(task.get("project_label") or "").strip()
    candidates: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    for finding_id, finding in sorted(findings_by_id.items()):
        if len(candidates) >= limit:
            break
        if str(finding.get("job") or "") in review.NAVIGATION_ONLY_JOBS:
            rejections["navigation_only_finding"] += 1
            continue
        if not _matches_task_project(finding, project_label):
            rejections["project_mismatch"] += 1
            continue
        if not _source_refs(finding):
            rejections["source_finding_without_source_refs"] += 1
            continue
        candidates.append(_candidate_from_finding(finding_id, finding))
    return candidates, rejections


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def produce_agent_fallback_results(
    *,
    tasks_path: Path,
    jobs_path: Path,
    results_path: Path,
    project: str | None = None,
    limit_per_task: int = 8,
    no_write: bool = False,
    reprocess: bool = False,
) -> dict[str, Any]:
    tasks = [
        row
        for row in task_rows(tasks_path)
        if row.get("kind") == "agent_fallback_subconscious_task"
        and (not project or str(row.get("project_label") or "") == project)
    ]
    findings_by_id = candidate_router.load_findings_by_id(jobs_path)
    processed = set() if reprocess else _processed_task_ids(results_path)
    rows: list[dict[str, Any]] = []
    all_rejections: Counter[str] = Counter()
    skipped_processed = 0
    for task in tasks:
        task_id = _task_id(task)
        if task_id in processed:
            skipped_processed += 1
            continue
        candidates, rejections = _eligible_candidates(
            task=task,
            findings_by_id=findings_by_id,
            limit=max(1, int(limit_per_task)),
        )
        all_rejections.update(rejections)
        if not candidates:
            continue
        rows.append(
            sanitize_external_model_payload(
                {
                    "schema_version": 1,
                    "kind": RESULT_KIND,
                    "created_at": now_utc(),
                    "task_id": task_id,
                    "project_label": task.get("project_label"),
                    "reason": task.get("reason"),
                    "provenance": RESULT_PROVENANCE,
                    "candidates": candidates,
                    "safety": {
                        "source_truth_unchanged": True,
                        "source_finding_join_required": True,
                        "foreground_hook_wait": False,
                        "external_model_call": False,
                        "promotion_or_adjudication": False,
                    },
                }
            )
        )

    if rows and not no_write:
        _append_jsonl(results_path, rows)
    candidate_count = sum(len(row.get("candidates") or []) for row in rows)
    return {
        "schema_version": 1,
        "kind": "aippocampus_agent_fallback_execution",
        "ok": True,
        "wrote": bool(rows and not no_write),
        "result_row_count": len(rows),
        "candidate_count": candidate_count,
        "diagnostic_only_count": sum(all_rejections.values()),
        "rejection_reasons": dict(sorted(all_rejections.items())),
        "task_count": len(tasks),
        "skipped_processed_task_count": skipped_processed,
        "results_file": results_path.name,
        "output_boundary": "local_private_agent_fallback_results",
        "safety": {
            "source_truth_unchanged": True,
            "source_finding_join_required": True,
            "foreground_hook_wait": False,
            "external_model_call": False,
            "promotion_or_adjudication": False,
            "public_report_includes_candidate_text": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-dir")
    parser.add_argument("--registry")
    parser.add_argument("--tasks")
    parser.add_argument("--jobs")
    parser.add_argument("--results")
    parser.add_argument("--project")
    parser.add_argument("--limit-per-task", type=int, default=8)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry_path = Path(args.registry).resolve() if args.registry else None
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    tasks = Path(args.tasks).resolve() if args.tasks else default_tasks_path(registry_path, registry_dir)
    jobs = Path(args.jobs).resolve() if args.jobs else default_jobs_path(registry_path, registry_dir)
    results = (
        Path(args.results).resolve()
        if args.results
        else default_results_path(registry_path, registry_dir)
    )
    report = produce_agent_fallback_results(
        tasks_path=tasks,
        jobs_path=jobs,
        results_path=results,
        project=args.project,
        limit_per_task=args.limit_per_task,
        no_write=args.no_write,
        reprocess=args.reprocess,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("agent fallback executor")
        print(f"- result rows: {report['result_row_count']}")
        print(f"- candidates: {report['candidate_count']}")
        print(f"- diagnostic-only findings: {report['diagnostic_only_count']}")
        print(f"- wrote: {str(report['wrote']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
