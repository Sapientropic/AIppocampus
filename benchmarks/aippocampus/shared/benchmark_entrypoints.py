"""Small CLI contracts for benchmark helper modules.

Benchmark submodules often live beside public runners because aggregate
benchmarks import them directly. If one of those helpers is executed by a
second user, it should explain the supported runner instead of failing with an
import traceback or succeeding with empty output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

HEAVY_JSON_ENTRYPOINTS = {
    "benchmark_longmemeval_answer.py": "fixed_reader_answer_latency_harness_can_use_provider_or_large_retrieval",
    "benchmark_source_evidence_retrieval.py": "track_b_aggregate_can_build_indexes_and_optional_public_corpora",
    "benchmark_suite.py": "aggregate_suite_runner_not_a_zero_arg_json_smoke",
}


def library_only_payload(
    *,
    module_path: str,
    supported_runner: str,
    summary: str,
) -> dict[str, object]:
    return {
        "kind": "aippocampus_benchmark_helper_entrypoint_contract",
        "ok": True,
        "status": "library_only",
        "module": module_path,
        "supported_runner": supported_runner,
        "summary": summary,
    }


def library_only_main(
    *,
    module_path: str,
    supported_runner: str,
    summary: str,
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog=module_path,
        description=(
            f"{module_path} is library-only. {summary} "
            f"Run {supported_runner} for the supported public benchmark surface."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print a machine-readable library-only contract.",
    )
    args = parser.parse_args(argv)
    payload = library_only_payload(
        module_path=module_path,
        supported_runner=supported_runner,
        summary=summary,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"{module_path} is library-only; run {supported_runner} "
            "for the supported public benchmark surface."
        )
    return 0


def json_report_exit_code(*, json_output: bool, report_generation_ok: bool = True, ok: bool) -> int:
    """Exit-code policy for benchmark JSON report collectors.

    In `--json` mode, a valid machine-readable report is a successful command
    even when the benchmark quality gate inside the report is false. CI paths
    that want nonzero on quality failure should use an explicit strict wrapper
    instead of making report collectors guess whether stdout is trustworthy.
    """

    if json_output and report_generation_ok:
        return 0
    return 0 if ok else 1


def missing_required_input_payload(
    *,
    kind: str,
    missing: Sequence[str],
    supported_runner: str,
    summary: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "ok": False,
        "report_generation_ok": True,
        "benchmark_ok": False,
        "status": "missing_required_input",
        "missing_required_input": list(missing),
        "supported_runner": supported_runner,
        "summary": summary,
        "exit_code_policy": (
            "json_report_generation_success_returns_zero; benchmark status lives in JSON"
        ),
    }


def benchmark_entrypoint_manifest(benchmark_dir: Path | str) -> dict[str, object]:
    root = Path(benchmark_dir)
    scripts = sorted(path.name for path in root.glob("benchmark_*.py") if path.is_file())
    entrypoints: list[dict[str, object]] = []
    for script in scripts:
        heavy_reason = HEAVY_JSON_ENTRYPOINTS.get(script)
        heavy = heavy_reason is not None
        entrypoints.append(
            {
                "script": script,
                "entrypoint_class": "heavy_local_eval" if heavy else "public_fast_json_candidate",
                "execution_status": "not_run",
                "classification_basis": "static_manifest_only",
                "execution_status_reason": (
                    "entrypoint manifest classifies expected CLI shape without running benchmarks"
                ),
                "public_fast_json_default": not heavy,
                "safe_sweep_modes": ["json_contract"] if heavy else ["json"],
                "classification_reason": heavy_reason or "default_json_expected_to_return_quickly",
            }
        )
    return {
        "kind": "aippocampus_benchmark_entrypoint_manifest",
        "schema_version": 1,
        "ok": True,
        "scanned_count": len(entrypoints),
        "heavy_local_eval_count": sum(
            1 for row in entrypoints if row["entrypoint_class"] == "heavy_local_eval"
        ),
        "entrypoints": entrypoints,
        "contract": {
            "manifest_classification_does_not_run_benchmarks": True,
            "entrypoint_class_is_static_expected_shape_not_measured_result": True,
            "heavy_local_eval_is_not_broken_json": True,
            "real_benchmark_runs_keep_their_existing_quality_behavior": True,
        },
    }
