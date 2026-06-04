#!/usr/bin/env python3
"""Private-safe question prefilter parity smoke.

This runner evaluates whether the optional question-index sidecar can reproduce
the current pair-scan strong-pair surface and rejoin candidates to current
source refs. It deliberately does not enable the sidecar as the default
question_tracking prefilter: source-joined parity is necessary evidence, not
answer-quality or user-visible recall proof.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.question import index_sidecar as sidecar  # noqa: E402
from aippocampus_runtime.question.tracking import (  # noqa: E402
    default_jobs_path,
    default_registry_path,
)

SCHEMA_VERSION = 1
KIND = "aippocampus_question_prefilter_parity_smoke"
CLAIM_LEVEL = "selected_registry_structural_parity"


def elapsed_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


def _warning_codes(result: dict[str, Any], *, min_candidates: int) -> list[str]:
    warnings: list[str] = []
    if int(result.get("candidate_count") or 0) < max(0, int(min_candidates)):
        warnings.append("insufficient_question_candidates")
    if float(result.get("baseline_strong_pair_coverage") or 0.0) < 1.0:
        warnings.append("sidecar_candidate_coverage_gap")
    if not result.get("source_ref_join_survived"):
        warnings.append("sidecar_source_ref_join_gap")
    if not result.get("source_ref_key_join_survived"):
        warnings.append("sidecar_source_ref_key_join_gap")
    return warnings


def _status_for_warnings(warnings: list[str]) -> str:
    if "insufficient_question_candidates" in warnings:
        return "insufficient_question_candidates"
    if warnings:
        return "structural_parity_gap"
    return "structural_parity_ready"


def _default_prefilter_report(result: dict[str, Any]) -> dict[str, Any]:
    adoption = dict(result.get("sidecar_adoption") or {})
    return {
        "enabled": False,
        "recommended": bool(adoption.get("default_prefilter_recommended")),
        "safe_to_enable_by_default": bool(adoption.get("safe_to_enable_by_default")),
        "decision": str(adoption.get("decision") or ""),
        "recommendation": str(result.get("recommendation") or adoption.get("recommendation") or ""),
        "reason_codes": list(adoption.get("reason_codes") or []),
        "required_before_default": list(adoption.get("required_before_default") or []),
    }


def _sanitized_payload(
    result: dict[str, Any],
    *,
    elapsed: int,
    min_candidates: int,
) -> dict[str, Any]:
    warnings = _warning_codes(result, min_candidates=min_candidates)
    status = _status_for_warnings(warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not warnings,
        "kind": KIND,
        "status": status,
        "claim_level": CLAIM_LEVEL,
        "metrics": {
            "elapsed_ms": elapsed,
            "candidate_count": int(result.get("candidate_count") or 0),
            "record_count": int(result.get("record_count") or 0),
            "stale_candidate_count": int(result.get("stale_candidate_count") or 0),
            "all_pair_count": int(result.get("all_pair_count") or 0),
            "trackable_pair_count": int(result.get("trackable_pair_count") or 0),
            "baseline_strong_pair_count": int(result.get("baseline_strong_pair_count") or 0),
            "sidecar_pair_count": int(result.get("sidecar_pair_count") or 0),
            "source_joined_pair_count": int(result.get("source_joined_pair_count") or 0),
            "source_ref_key_joined_pair_count": int(
                result.get("source_ref_key_joined_pair_count") or 0
            ),
            "source_ref_key_mismatch_count": int(
                result.get("source_ref_key_mismatch_count") or 0
            ),
        },
        "parity": {
            "baseline_strong_pair_coverage": float(
                result.get("baseline_strong_pair_coverage") or 0.0
            ),
            "source_ref_join_survived": bool(result.get("source_ref_join_survived")),
            "source_ref_key_join_survived": bool(result.get("source_ref_key_join_survived")),
            "truth_boundary": str(result.get("truth_boundary") or ""),
        },
        "sidecar": {
            "status": str(result.get("question_index_status") or ""),
            "wrote_temporary_index": bool(result.get("wrote")),
            "max_pairs": int(result.get("max_pairs") or 0),
            "error": str(result.get("question_index_error") or ""),
        },
        "default_prefilter": _default_prefilter_report(result),
        "privacy": {
            "private_text_emitted": False,
            "raw_source_refs_emitted": False,
            "registry_paths_emitted": False,
            "source_signature_emitted": False,
            "persistent_index_written": False,
        },
        "warnings": warnings,
        "can_claim": [
            "sidecar_structural_candidate_parity_against_current_pair_scan",
            "sidecar_candidates_rejoin_current_source_ref_keys_when_parity_passes",
            "default_prefilter_boundary_is_reported_without_private_text",
        ],
        "cannot_claim": [
            "answer_quality",
            "user_visible_recall_improvement",
            "private_history_question_recall_quality",
            "default_question_index_prefilter_is_safe",
            "vector_neighbors_are_truth",
            "full_history_coverage",
        ],
    }


def run_question_prefilter_parity_smoke(
    *,
    jobs_path: Path | None = None,
    registry_path: Path | None = None,
    max_pairs: int = sidecar.DEFAULT_MAX_PAIRS,
    min_candidates: int = 1,
) -> dict[str, Any]:
    jobs = jobs_path or default_jobs_path(None, None)
    registry = registry_path
    with tempfile.TemporaryDirectory() as tmp:
        index_path = Path(tmp) / sidecar.DEFAULT_INDEX_NAME
        start = time.perf_counter()
        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=jobs,
            registry_path=registry,
            index_path=index_path,
            max_pairs=max_pairs,
            evidence_level=CLAIM_LEVEL,
        )
        elapsed = elapsed_ms(start)
    return _sanitized_payload(
        result,
        elapsed=elapsed,
        min_candidates=min_candidates,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a private-safe question prefilter parity smoke."
    )
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--max-pairs", type=int, default=sidecar.DEFAULT_MAX_PAIRS)
    parser.add_argument("--min-candidates", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    registry = default_registry_path(args.registry, args.registry_dir)
    jobs = args.jobs.resolve() if args.jobs else default_jobs_path(args.registry, args.registry_dir)
    payload = run_question_prefilter_parity_smoke(
        jobs_path=jobs,
        registry_path=registry,
        max_pairs=args.max_pairs,
        min_candidates=args.min_candidates,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2 if args.json_output else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json_output:
        print(text)
    else:
        print(f"status: {payload['status']}")
        print(f"candidates: {payload['metrics']['candidate_count']}")
        print(f"baseline strong pairs: {payload['metrics']['baseline_strong_pair_count']}")
        print(f"coverage: {payload['parity']['baseline_strong_pair_coverage']}")
        print(f"default prefilter recommended: {payload['default_prefilter']['recommended']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
