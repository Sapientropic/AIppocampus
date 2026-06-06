#!/usr/bin/env python3
"""Materialize agent-fallback outputs through the existing staging gate.

The agent-fallback lane is allowed to produce candidate suggestions, but those
suggestions are not source truth. This module accepts only candidates that join
back to existing source-backed subconscious findings, then reuses the same
review output boundary as external-model review. Unsupported candidates stay
diagnostic-only so future host-agent executors cannot bypass source-ref gates by
inventing a nicer-looking JSON shape.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.subconscious import candidate_router, review

RESULT_KIND = "aippocampus_agent_fallback_result"
DEFAULT_RESULTS_NAME = "agent_fallback_results.jsonl"
DEFAULT_OUTPUT_NAME = "promotion_candidates.jsonl"
SOURCE = "agent_fallback_subconscious_review"
MODEL = "agent-fallback"


def default_results_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_RESULTS_NAME
    return candidate_router.default_jobs_path(None, registry_dir).parent / DEFAULT_RESULTS_NAME


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                rows.append({"kind": RESULT_KIND, "_line_number": line_number, "_invalid_json": True})
                continue
            if isinstance(item, dict):
                item["_line_number"] = line_number
                rows.append(item)
    return rows


def _candidate_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("candidates")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    candidate = row.get("candidate")
    if isinstance(candidate, dict):
        return [candidate]
    if any(key in row for key in ("candidate_type", "source_finding_ids", "title", "summary")):
        return [row]
    return []


def _has_source_refs(finding: dict[str, Any]) -> bool:
    return any(isinstance(ref, dict) for ref in finding.get("source_refs") or [])


def _normalize_candidate(
    item: dict[str, Any],
    *,
    findings_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    source_ids = unique_preserve(
        [str(value) for value in item.get("source_finding_ids") or [] if str(value).strip()],
        limit=12,
    )
    if not source_ids:
        return None, "missing_source_finding_ids"
    if any(source_id not in findings_by_id for source_id in source_ids):
        return None, "unresolved_source_finding_ids"
    if any(not _has_source_refs(findings_by_id[source_id]) for source_id in source_ids):
        return None, "source_finding_without_source_refs"
    candidate_type = str(item.get("candidate_type") or "project_memory").strip() or "project_memory"
    return (
        {
            "candidate_type": candidate_type,
            "title": str(item.get("title") or ""),
            "summary": str(item.get("summary") or ""),
            "recommendation": str(item.get("recommendation") or ""),
            "confidence": item.get("confidence"),
            "activation_cues": item.get("activation_cues") or [],
            "source_finding_ids": source_ids,
        },
        "accepted_for_review_gate",
    )


def build_review_from_results(
    *,
    results_path: Path,
    jobs_path: Path,
) -> dict[str, Any]:
    findings_by_id = candidate_router.load_findings_by_id(jobs_path)
    parsed: dict[str, Any] = {"promotion_candidates": [], "duplicate_groups": [], "weak_findings": []}
    rejections: Counter[str] = Counter()
    raw_candidate_count = 0
    result_rows = 0
    for row in iter_jsonl(results_path):
        if row.get("kind") != RESULT_KIND:
            continue
        result_rows += 1
        if row.get("_invalid_json"):
            rejections["invalid_json_result_row"] += 1
            continue
        candidates = _candidate_rows(row)
        if not candidates:
            rejections["missing_candidates"] += 1
            continue
        for item in candidates:
            raw_candidate_count += 1
            normalized, reason = _normalize_candidate(item, findings_by_id=findings_by_id)
            if normalized is None:
                rejections[reason] += 1
                continue
            parsed["promotion_candidates"].append(normalized)
    validated = review.validate_review(parsed, findings_by_id)
    validation_rejected = len(parsed["promotion_candidates"]) - len(validated["promotion_candidates"])
    if validation_rejected > 0:
        rejections["rejected_by_existing_review_gate"] += validation_rejected
    return {
        "review": validated,
        "stats": {
            "result_row_count": result_rows,
            "raw_candidate_count": raw_candidate_count,
            "accepted_candidate_count": len(validated["promotion_candidates"]),
            "diagnostic_only_count": sum(rejections.values()),
            "rejection_reasons": dict(sorted(rejections.items())),
        },
    }


def materialize_agent_fallback_results(
    *,
    results_path: Path,
    jobs_path: Path,
    output_path: Path,
    no_write: bool = False,
) -> dict[str, Any]:
    built = build_review_from_results(results_path=results_path, jobs_path=jobs_path)
    review_payload = built["review"]
    if not no_write:
        review.append_review_output(
            output_path,
            review_payload,
            model=MODEL,
            batch_id="agent_fallback",
            usage={},
            source=SOURCE,
            model_route={"provider": "agent_fallback"},
        )
    return {
        "schema_version": 1,
        "kind": "aippocampus_agent_fallback_materialization",
        "ok": True,
        "wrote": not no_write,
        "source": SOURCE,
        "output_boundary": "staging_only_source_joined_candidates",
        "promotion_candidate_count": len(review_payload["promotion_candidates"]),
        "duplicate_group_count": len(review_payload["duplicate_groups"]),
        "weak_finding_count": len(review_payload["weak_findings"]),
        **built["stats"],
        "safety": {
            "source_truth_unchanged": True,
            "source_finding_join_required": True,
            "foreground_hook_wait": False,
            "raw_agent_text_public": False,
            "promotion_or_adjudication": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-dir")
    parser.add_argument("--registry")
    parser.add_argument("--results")
    parser.add_argument("--jobs")
    parser.add_argument("--output")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry_path = Path(args.registry).resolve() if args.registry else None
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    results = (
        Path(args.results).resolve()
        if args.results
        else default_results_path(registry_path, registry_dir)
    )
    jobs = (
        Path(args.jobs).resolve()
        if args.jobs
        else candidate_router.default_jobs_path(registry_path, registry_dir)
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else candidate_router.default_candidates_path(registry_path, registry_dir)
    )
    report = materialize_agent_fallback_results(
        results_path=results,
        jobs_path=jobs,
        output_path=output,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("agent fallback materializer")
        print(f"- promotion candidates: {report['promotion_candidate_count']}")
        print(f"- diagnostic-only candidates: {report['diagnostic_only_count']}")
        print(f"- wrote: {str(report['wrote']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
