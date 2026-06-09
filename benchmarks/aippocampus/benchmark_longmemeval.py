#!/usr/bin/env python3
"""Dedicated LongMemEval benchmark adapter for AIppocampus.

This runner intentionally measures retrieval/source-evidence behavior first.
LongMemEval QA judging is an LLM-evaluator path, so it must remain explicit and
separate from deterministic retrieval metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

import benchmark_source_evidence_retrieval as retrieval_benchmark
from claim_boundary_refs import claim_boundary_ref

SCHEMA_VERSION = 1
DEFAULT_SPLIT = "longmemeval-v1-small"
DEFAULT_MAX_QUESTIONS = 50
DEFAULT_MIN_QUESTIONS = 20
DEFAULT_TOP_K = 10
DEFAULT_MIN_SESSION_HIT_RATE = 0.5
LONGMEMEVAL_DATASET_BASE = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main"
)
LONGMEMEVAL_REPO_URL = "https://github.com/xiaowu0162/LongMemEval"
LONGMEMEVAL_PAPER_URL = "https://arxiv.org/abs/2410.10813"


@dataclass(frozen=True)
class LongMemEvalSplit:
    dataset: str
    filename: str
    expected_sha256: str
    expected_bytes: int
    benchmark_label: str
    default_role: str

    @property
    def url(self) -> str:
        return f"{LONGMEMEVAL_DATASET_BASE}/{self.filename}"


LONGMEMEVAL_SPLITS: dict[str, LongMemEvalSplit] = {
    "longmemeval-v1-oracle": LongMemEvalSplit(
        dataset="longmemeval-v1-oracle",
        filename="longmemeval_oracle.json",
        expected_sha256="821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c",
        expected_bytes=15_388_478,
        benchmark_label="LongMemEval cleaned oracle",
        default_role="bounded smoke and oracle-evidence debugging",
    ),
    "longmemeval-v1-small": LongMemEvalSplit(
        dataset="longmemeval-v1-small",
        filename="longmemeval_s_cleaned.json",
        expected_sha256="d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
        expected_bytes=277_383_467,
        benchmark_label="LongMemEval-S cleaned",
        default_role="first comparable public split",
    ),
    "longmemeval-v1-medium": LongMemEvalSplit(
        dataset="longmemeval-v1-medium",
        filename="longmemeval_m_cleaned.json",
        expected_sha256="9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f",
        expected_bytes=2_737_100_077,
        benchmark_label="LongMemEval-M cleaned",
        default_role="large-context stress split",
    ),
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_data_path(split: LongMemEvalSplit) -> Path:
    return (_paths.REPO_ROOT / "benchmark_corpus" / "longmemeval" / split.filename).resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_file(path: Path, split: LongMemEvalSplit) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "path_sha1": hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16],
            "expected_bytes": split.expected_bytes,
            "expected_sha256": split.expected_sha256,
        }
    size = path.stat().st_size
    digest = file_sha256(path)
    return {
        "ok": size == split.expected_bytes and digest == split.expected_sha256,
        "status": "verified" if size == split.expected_bytes and digest == split.expected_sha256 else "mismatch",
        "path_sha1": hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16],
        "bytes": size,
        "sha256": digest,
        "expected_bytes": split.expected_bytes,
        "expected_sha256": split.expected_sha256,
    }


def download_dataset(path: Path, split: LongMemEvalSplit) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with urllib.request.urlopen(split.url, timeout=60) as response:
        with path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    verified = verify_dataset_file(path, split)
    verified["downloaded"] = True
    verified["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return verified


def skipped_payload(
    *,
    split: LongMemEvalSplit,
    data_path: Path,
    reason: str,
    verification: dict[str, Any],
    started: float,
    max_questions: int,
    min_questions: int,
    top_k: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_benchmark",
        "generated_at": now_utc(),
        "status": reason,
        "ok": True,
        "benchmark": benchmark_metadata(split, data_path, verification),
        "evaluation": evaluation_metadata(
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
        ),
        "metrics": {"question_count": 0},
        "cases": [],
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": cannot_claim(reason),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def benchmark_metadata(
    split: LongMemEvalSplit,
    data_path: Path,
    verification: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": "LongMemEval",
        "paper_url": LONGMEMEVAL_PAPER_URL,
        "official_repo_url": LONGMEMEVAL_REPO_URL,
        "dataset_url": split.url,
        "dataset_version": "longmemeval-cleaned 2025-09",
        "split": split.dataset,
        "split_label": split.benchmark_label,
        "split_role": split.default_role,
        "local_path_sha1": hashlib.sha1(str(data_path).encode("utf-8")).hexdigest()[:16],
        "verification": verification,
        "v2_boundary": (
            "LongMemEval-V2 is a separate 2026 agentic-context benchmark and is not "
            "scored by this V1 source-evidence adapter."
        ),
    }


def evaluation_metadata(*, max_questions: int, min_questions: int, top_k: int) -> dict[str, Any]:
    return {
        "mode": "retrieval_only",
        "retrieval_metric_scope": "session and source-line recall",
        "qa_generation": "not_run",
        "judge_model": None,
        "max_questions": int(max_questions),
        "min_questions": int(min_questions),
        "top_k": int(top_k),
        "runner": "benchmarks/aippocampus/benchmark_longmemeval.py",
        "underlying_adapter": (
            "benchmarks/aippocampus/benchmark_source_evidence_retrieval.py"
        ),
    }


def privacy_boundary() -> dict[str, Any]:
    return {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": True,
        "output_shape": "sanitized_longmemeval_retrieval_metrics",
    }


def cannot_claim(status: str) -> list[str]:
    claims = {
        "longmemeval_qa_score",
        "answer_generation_quality",
        "judge_model_score",
        "longmemeval_v2_score",
        "sota_or_external_baseline_superiority",
    }
    if status.startswith("skipped_") or status.startswith("partial_"):
        claims.add("longmemeval_retrieval_score")
    return sorted(claims)


def progress_metrics(progress_events: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "question_count": max(
            [int(event.get("cases_evaluated") or 0) for event in progress_events]
            or [0]
        ),
        "cases_built": max(
            [int(event.get("cases_built") or 0) for event in progress_events] or [0]
        ),
        "cases_evaluated": max(
            [int(event.get("cases_evaluated") or 0) for event in progress_events]
            or [0]
        ),
    }


def progress_snapshot(progress_events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "event_count": len(progress_events),
        "last_event": progress_events[-1] if progress_events else {},
        "recent_events": progress_events[-10:],
    }


def partial_diagnostic_payload(
    *,
    split: LongMemEvalSplit,
    data_path: Path,
    verification: dict[str, Any],
    started: float,
    max_questions: int,
    min_questions: int,
    top_k: int,
    status: str,
    reason: str,
    progress_events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": False,
        "benchmark": benchmark_metadata(split, data_path, verification),
        "evaluation": evaluation_metadata(
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
        ),
        "metrics": progress_metrics(progress_events),
        "cases": [],
        "standard_adapter": {"status": "incomplete", "config": {}, "corpus": {}},
        "progress": progress_snapshot(progress_events),
        "partial_diagnostic": {
            "reason": reason,
            "promotable_retrieval_evidence": False,
        },
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": cannot_claim(status),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def write_json_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_longmemeval_benchmark(
    *,
    split_name: str = DEFAULT_SPLIT,
    data_file: Path | str | None = None,
    download: bool = False,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    min_questions: int = DEFAULT_MIN_QUESTIONS,
    top_k: int = DEFAULT_TOP_K,
    candidate_limit: int = retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    context_radius: int = retrieval_benchmark.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    min_session_hit_rate: float = DEFAULT_MIN_SESSION_HIT_RATE,
    progress_every: int = 0,
    partial_output: Path | str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    split = LONGMEMEVAL_SPLITS[split_name]
    data_path = Path(data_file).resolve() if data_file else default_data_path(split)
    partial_path = Path(partial_output).resolve() if partial_output else None
    progress_events: list[dict[str, Any]] = []
    verification = download_dataset(data_path, split) if download else verify_dataset_file(data_path, split)
    if not verification["ok"]:
        reason = (
            "skipped_missing_dataset"
            if verification.get("status") == "missing"
            else "skipped_dataset_verification_failed"
        )
        return skipped_payload(
            split=split,
            data_path=data_path,
            reason=reason,
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
        )

    def handle_progress(event: dict[str, Any]) -> None:
        long_event = {
            "kind": "aippocampus_longmemeval_progress",
            "generated_at": now_utc(),
            "split": split.dataset,
            "phase": event.get("phase"),
            "cases_built": int(event.get("cases_built") or 0),
            "cases_evaluated": int(event.get("cases_evaluated") or 0),
            "elapsed_ms": float(event.get("elapsed_ms") or 0.0),
        }
        for key in (
            "total_cases",
            "max_questions",
            "average_seconds_per_case",
            "corpus",
        ):
            if key in event:
                long_event[key] = event[key]
        progress_events.append(long_event)
        if partial_path is not None:
            write_json_payload(
                partial_path,
                partial_diagnostic_payload(
                    split=split,
                    data_path=data_path,
                    verification=verification,
                    started=started,
                    max_questions=max_questions,
                    min_questions=min_questions,
                    top_k=top_k,
                    status="partial_diagnostic_running",
                    reason="checkpoint",
                    progress_events=progress_events,
                ),
            )
        if progress_callback is not None:
            progress_callback(long_event)

    track_progress = (
        int(progress_every) > 0
        or progress_callback is not None
        or partial_path is not None
    )
    try:
        retrieval = retrieval_benchmark.run_standard_retrieval_qa_benchmark(
            dataset=split.dataset,
            corpus_path=data_path,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            progress_every=progress_every,
            progress_callback=handle_progress if track_progress else None,
        )
    except KeyboardInterrupt:
        if partial_path is None:
            raise
        payload = partial_diagnostic_payload(
            split=split,
            data_path=data_path,
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            status="partial_diagnostic_interrupted",
            reason="keyboard_interrupt",
            progress_events=progress_events,
        )
        write_json_payload(partial_path, payload)
        return payload
    status = "retrieval_sufficient" if retrieval.get("ok") else "retrieval_diagnostic"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": bool(retrieval.get("ok")),
        "benchmark": benchmark_metadata(split, data_path, verification),
        "evaluation": evaluation_metadata(
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
        ),
        "metrics": retrieval.get("metrics") or {},
        "cases": retrieval.get("cases") or [],
        "standard_adapter": {
            "status": retrieval.get("status"),
            "config": retrieval.get("config") or {},
            "corpus": retrieval.get("corpus") or {},
        },
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": sorted(set(cannot_claim(status)) | set(retrieval.get("cannot_claim") or [])),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if progress_events:
        payload["progress"] = progress_snapshot(progress_events)
    if partial_path is not None:
        write_json_payload(partial_path, payload)
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics") or {}
    benchmark = payload.get("benchmark") or {}
    evaluation = payload.get("evaluation") or {}
    top_k = int(evaluation.get("top_k") or DEFAULT_TOP_K)
    print("AIppocampus LongMemEval benchmark")
    print(f"- status: {payload.get('status')}")
    print(f"- split: {benchmark.get('split')} ({benchmark.get('split_label')})")
    print(f"- mode: {evaluation.get('mode')}")
    print(f"- questions: {metrics.get('question_count', 0)}")
    print(
        f"- session top-{top_k}: "
        f"{metrics.get(f'session_hit_rate_top{top_k}', 0.0):.2%}; "
        f"evidence top-{top_k}: {metrics.get(f'evidence_hit_rate_top{top_k}', 0.0):.2%}; "
        f"context-visible: {metrics.get(f'evidence_context_hit_rate_top{top_k}', 0.0):.2%}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=sorted(LONGMEMEVAL_SPLITS), default=DEFAULT_SPLIT)
    parser.add_argument("--data-file", type=Path, default=None)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--questions", type=int, default=DEFAULT_MAX_QUESTIONS)
    parser.add_argument("--min-questions", type=int, default=DEFAULT_MIN_QUESTIONS)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument(
        "--context-radius",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    )
    parser.add_argument("--min-session-hit-rate", type=float, default=DEFAULT_MIN_SESSION_HIT_RATE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Emit sanitized JSONL progress to stderr every N evaluated cases.",
    )
    parser.add_argument(
        "--partial-output",
        type=Path,
        default=None,
        help="Write a sanitized checkpoint/partial diagnostic JSON file during the run.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    def stderr_progress(event: dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)

    payload = run_longmemeval_benchmark(
        split_name=args.split,
        data_file=args.data_file,
        download=args.download,
        max_questions=args.questions,
        min_questions=args.min_questions,
        top_k=args.top_k,
        candidate_limit=args.candidate_limit,
        context_radius=args.context_radius,
        min_session_hit_rate=args.min_session_hit_rate,
        progress_every=args.progress_every,
        partial_output=args.partial_output,
        progress_callback=stderr_progress if int(args.progress_every) > 0 else None,
    )
    if args.output:
        write_json_payload(args.output, payload)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
