#!/usr/bin/env python3
"""Synthetic question-tracking scale smoke.

This smoke creates synthetic `question_candidate` rows only. It does not read a
private registry and it does not write formal subconscious job output. Its job
is to make the O(N^2) baseline cost and optional sidecar source-join boundary
visible before `question_index.sqlite` is considered for the default path.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.question import index_sidecar as sidecar  # noqa: E402
from aippocampus_runtime.question import tracking  # noqa: E402


def synthetic_question_row(index: int, *, group_count: int) -> dict[str, Any]:
    group = index % max(1, group_count)
    day = 1 + (index % 28)
    return {
        "schema_version": 1,
        "kind": "aippocampus_subconscious_job_finding",
        "created_at": f"2026-05-{day:02d}T00:00:00Z",
        "job": "question_extraction",
        "finding_kind": "question_candidate",
        "fingerprint": f"sf_synthetic_question_{index:04d}",
        "title": f"Synthetic continuity group {group}",
        "summary": "Synthetic question-tracking scale smoke row.",
        "confidence": 0.86,
        "source_refs": [
            {
                "thread_key": f"synthetic:thread:{index:04d}",
                "message_id": f"synthetic-msg-{index:04d}",
                "turn_id": f"synthetic-turn-{index:04d}",
                "source_line": index + 1,
                "timestamp": f"2026-05-{day:02d}T00:00:00Z",
            }
        ],
        "question_text": f"How should continuity group {group} keep source refs across compaction?",
        "question_short": f"continuity group {group}",
        "intent_orientation": "implementation",
        "what_features": [f"continuity group {group}", "source refs", "compaction"],
        "where_context": ["AIppocampus synthetic smoke"],
        "phase_context": "scale_smoke",
        "collaboration_context": ["Codex"],
        "concepts": [f"continuity group {group}", "source refs"],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def elapsed_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


def run_question_tracking_scale_smoke(
    *,
    candidate_count: int = 48,
    group_count: int = 6,
    max_pairs: int = sidecar.DEFAULT_MAX_PAIRS,
) -> dict[str, Any]:
    candidate_total = max(0, int(candidate_count))
    group_total = max(1, int(group_count))
    rows = [
        synthetic_question_row(index, group_count=group_total)
        for index in range(candidate_total)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_path = root / "subconscious_jobs.jsonl"
        index_path = root / sidecar.DEFAULT_INDEX_NAME
        write_jsonl(jobs_path, rows)

        baseline_start = time.perf_counter()
        baseline = tracking.run_question_tracking(jobs_path=jobs_path, no_write=True)
        baseline_elapsed = elapsed_ms(baseline_start)

        sidecar_start = time.perf_counter()
        sidecar_result = sidecar.evaluate_question_index_sidecar(
            jobs_path=jobs_path,
            index_path=index_path,
            max_pairs=max_pairs,
            evidence_level="synthetic_scale_smoke",
        )
        sidecar_elapsed = elapsed_ms(sidecar_start)

    all_pair_count = candidate_total * max(0, candidate_total - 1) // 2
    warnings: list[str] = []
    if all_pair_count >= 10000:
        warnings.append("quadratic_pair_scan_large")
    if sidecar_result["baseline_strong_pair_coverage"] < 1.0:
        warnings.append("sidecar_candidate_coverage_gap")
    if not sidecar_result["source_ref_join_survived"]:
        warnings.append("sidecar_source_ref_join_gap")
    if not sidecar_result["source_ref_key_join_survived"]:
        warnings.append("sidecar_source_ref_key_join_gap")
    return {
        "ok": not any(warning.endswith("_gap") for warning in warnings),
        "kind": "aippocampus_question_tracking_scale_smoke",
        "synthetic_only": True,
        "candidate_count": candidate_total,
        "group_count": group_total,
        "all_pair_count": all_pair_count,
        "baseline": {
            "elapsed_ms": baseline_elapsed,
            "decision_pair_count": baseline["pair_count"],
            "accepted_pair_count": baseline["accepted_pair_count"],
            "link_count": baseline["link_count"],
            "low_salience_pair_skipped_count": baseline["low_salience_pair_skipped_count"],
        },
        "sidecar": {
            "elapsed_ms": sidecar_elapsed,
            "status": sidecar_result["question_index_status"],
            "sidecar_pair_count": sidecar_result["sidecar_pair_count"],
            "source_joined_pair_count": sidecar_result["source_joined_pair_count"],
            "source_ref_key_joined_pair_count": sidecar_result["source_ref_key_joined_pair_count"],
            "source_ref_key_mismatch_count": sidecar_result["source_ref_key_mismatch_count"],
            "baseline_strong_pair_coverage": sidecar_result["baseline_strong_pair_coverage"],
            "source_ref_join_survived": sidecar_result["source_ref_join_survived"],
            "source_ref_key_join_survived": sidecar_result["source_ref_key_join_survived"],
            "recommendation": sidecar_result["recommendation"],
            "adoption": sidecar_result["sidecar_adoption"],
            "default_enablement": sidecar_result["default_enablement"],
            "truth_boundary": sidecar_result["truth_boundary"],
        },
        "warnings": warnings,
        "privacy": {
            "reads_private_registry": False,
            "writes_formal_jobs": False,
            "raw_private_text_emitted": False,
        },
        "cannot_claim": [
            "real_registry_runtime_performance",
            "default_question_index_prefilter_is_safe",
            "vector_neighbors_are_truth",
            "private_history_question_recall_quality",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-count", type=int, default=48)
    parser.add_argument("--group-count", type=int, default=6)
    parser.add_argument("--max-pairs", type=int, default=sidecar.DEFAULT_MAX_PAIRS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_question_tracking_scale_smoke(
        candidate_count=args.candidate_count,
        group_count=args.group_count,
        max_pairs=args.max_pairs,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"candidate count: {result['candidate_count']}")
        print(f"all pairs: {result['all_pair_count']}")
        print(f"baseline elapsed ms: {result['baseline']['elapsed_ms']}")
        print(f"sidecar elapsed ms: {result['sidecar']['elapsed_ms']}")
        print(f"sidecar recommendation: {result['sidecar']['recommendation']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
