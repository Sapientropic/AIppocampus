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
from benchmarks.aippocampus.shared import provider_execution_budget
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref
from source_evidence.semantic_sidecars import (
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS,
    source_semantic_sidecar_materializer_contract,
)

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
    line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_timeout: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS
    ),
    source_semantic_sidecar_materializer: str = SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    source_semantic_sidecar_max_candidates: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES
    ),
    source_semantic_sidecar_max_provider_calls: int = 0,
    source_semantic_sidecar_workers: int = 1,
    source_semantic_sidecar_timeout: int = retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    source_semantic_sidecar_max_tokens: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS
    ),
    source_semantic_sidecar_min_confidence: float = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE
    ),
    rebuild_source_semantic_sidecars: bool = False,
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            source_semantic_sidecar_materializer=source_semantic_sidecar_materializer,
            source_semantic_sidecar_max_candidates=source_semantic_sidecar_max_candidates,
            source_semantic_sidecar_max_provider_calls=source_semantic_sidecar_max_provider_calls,
            source_semantic_sidecar_workers=source_semantic_sidecar_workers,
            source_semantic_sidecar_timeout=source_semantic_sidecar_timeout,
            source_semantic_sidecar_max_tokens=source_semantic_sidecar_max_tokens,
            source_semantic_sidecar_min_confidence=source_semantic_sidecar_min_confidence,
            rebuild_source_semantic_sidecars=rebuild_source_semantic_sidecars,
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


def evaluation_metadata(
    *,
    max_questions: int,
    min_questions: int,
    top_k: int,
    line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_timeout: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    source_semantic_sidecar_materializer: str = SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    source_semantic_sidecar_max_candidates: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES
    ),
    source_semantic_sidecar_max_provider_calls: int = 0,
    source_semantic_sidecar_workers: int = 1,
    source_semantic_sidecar_timeout: int = retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    source_semantic_sidecar_max_tokens: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS
    ),
    source_semantic_sidecar_min_confidence: float = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE
    ),
    rebuild_source_semantic_sidecars: bool = False,
) -> dict[str, Any]:
    resolved_line_reranker_mode = line_reranker_mode.strip().casefold()
    resolved_sidecar_materializer = (
        str(source_semantic_sidecar_materializer or "").strip().casefold()
    )
    metadata = {
        "mode": "retrieval_only",
        "retrieval_metric_scope": "session and source-line recall",
        "qa_generation": "not_run",
        "judge_model": None,
        "max_questions": int(max_questions),
        "min_questions": int(min_questions),
        "top_k": int(top_k),
        "line_reranker_mode": resolved_line_reranker_mode,
        "source_semantic_sidecar_materializer": resolved_sidecar_materializer,
        "rebuild_source_semantic_sidecars": bool(rebuild_source_semantic_sidecars),
        "runner": "benchmarks/aippocampus/benchmark_longmemeval.py",
        "underlying_adapter": (
            "benchmarks/aippocampus/benchmark_source_evidence_retrieval.py"
        ),
        "capability_provenance": (
            retrieval_benchmark.benchmark_capability_provenance(
                resolved_line_reranker_mode,
                source_semantic_sidecar_materializer=resolved_sidecar_materializer,
            )
        ),
    }
    if resolved_line_reranker_mode == "semantic":
        metadata["llm_rerank_arm"] = (
            retrieval_benchmark.semantic_line_reranker_public_contract(
                timeout=line_reranker_timeout,
                max_tokens=line_reranker_max_tokens,
            )
        )
    elif resolved_line_reranker_mode == "source_semantic_cache":
        metadata["source_semantic_cache_arm"] = (
            retrieval_benchmark.source_semantic_cache_public_contract()
        )
        if resolved_sidecar_materializer != SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF:
            metadata["source_semantic_sidecar_materializer_contract"] = (
                source_semantic_sidecar_materializer_contract(
                    materializer=resolved_sidecar_materializer,
                    max_candidates=source_semantic_sidecar_max_candidates,
                    max_provider_calls=source_semantic_sidecar_max_provider_calls,
                    workers=source_semantic_sidecar_workers,
                    timeout=source_semantic_sidecar_timeout,
                    max_tokens=source_semantic_sidecar_max_tokens,
                    min_confidence=source_semantic_sidecar_min_confidence,
                )
            )
    return metadata


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
    line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_timeout: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS
    ),
    source_semantic_sidecar_materializer: str = SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    source_semantic_sidecar_max_candidates: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES
    ),
    source_semantic_sidecar_max_provider_calls: int = 0,
    source_semantic_sidecar_workers: int = 1,
    source_semantic_sidecar_timeout: int = retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    source_semantic_sidecar_max_tokens: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS
    ),
    source_semantic_sidecar_min_confidence: float = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE
    ),
    rebuild_source_semantic_sidecars: bool = False,
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            source_semantic_sidecar_materializer=source_semantic_sidecar_materializer,
            source_semantic_sidecar_max_candidates=source_semantic_sidecar_max_candidates,
            source_semantic_sidecar_max_provider_calls=source_semantic_sidecar_max_provider_calls,
            source_semantic_sidecar_workers=source_semantic_sidecar_workers,
            source_semantic_sidecar_timeout=source_semantic_sidecar_timeout,
            source_semantic_sidecar_max_tokens=source_semantic_sidecar_max_tokens,
            source_semantic_sidecar_min_confidence=source_semantic_sidecar_min_confidence,
            rebuild_source_semantic_sidecars=rebuild_source_semantic_sidecars,
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


def write_provider_budget_checkpoint(path: Path, summary: dict[str, Any]) -> None:
    write_json_payload(
        path,
        {
            "schema_version": provider_execution_budget.SCHEMA_VERSION,
            "kind": "aippocampus_provider_execution_budget_checkpoint",
            "provider_execution_budget": summary,
        },
    )


def semantic_provider_budget_config(
    *,
    live_mode: bool,
    max_questions: int,
    line_reranker_timeout: int,
    line_reranker_max_tokens: int,
    max_provider_calls: int | None,
    max_provider_prompt_tokens: int | None,
    max_provider_completion_tokens: int | None,
    max_provider_total_tokens: int | None,
    max_provider_estimated_cost_usd: float | None,
    provider_cost_unknown: bool,
    provider_budget_checkpoint: Path | str | None,
    partial_output: Path | str | None,
) -> provider_execution_budget.ProviderExecutionBudget:
    contract = retrieval_benchmark.semantic_line_reranker_public_contract(
        timeout=line_reranker_timeout,
        max_tokens=line_reranker_max_tokens,
    )
    return provider_execution_budget.build_provider_execution_budget(
        benchmark_id="longmemeval_semantic_line_reranker",
        live_mode=live_mode,
        max_units=max_questions,
        per_case_timeout_seconds=line_reranker_timeout,
        max_provider_calls=max_provider_calls,
        max_prompt_tokens=max_provider_prompt_tokens,
        max_completion_tokens=max_provider_completion_tokens,
        max_total_tokens=max_provider_total_tokens,
        max_estimated_cost_usd=max_provider_estimated_cost_usd,
        cost_unknown=provider_cost_unknown,
        checkpoint_path=provider_budget_checkpoint,
        partial_output_path=partial_output,
        provider=str(contract.get("provider") or "unknown"),
        model=str(contract.get("model") or "unknown"),
        base_url_sha1=str(contract.get("base_url_sha1") or ""),
    )


def provider_budget_summary_for_metrics(
    config: provider_execution_budget.ProviderExecutionBudget,
    *,
    metrics: dict[str, Any],
    elapsed_ms: float,
    stop_reason: str,
) -> dict[str, Any]:
    error_counts = metrics.get("line_reranker_error_kind_counts") or {}
    timed_out = int(error_counts.get("timeout") or 0) if isinstance(error_counts, dict) else 0
    return provider_execution_budget.provider_execution_budget_summary(
        config,
        completed_units=int(metrics.get("line_reranker_available_count") or 0),
        failed_units=int(metrics.get("line_reranker_error_count") or 0),
        timed_out_units=timed_out,
        elapsed_ms=elapsed_ms,
        usage=metrics.get("line_reranker_usage") or {},
        cache_usage=metrics.get("line_reranker_cache") or {},
        estimated_cost_usd=None,
        cost_unavailable_reason="provider_cost_not_reported_by_chat_completions_response",
        stop_reason=stop_reason,
        validation_errors=[],
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
    line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_top_sessions: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS
    ),
    line_reranker_max_candidates: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES
    ),
    line_reranker_timeout: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS
    ),
    line_reranker_workers: int = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    progress_every: int = 0,
    partial_output: Path | str | None = None,
    provider_budget_checkpoint: Path | str | None = None,
    max_provider_calls: int | None = None,
    max_provider_prompt_tokens: int | None = None,
    max_provider_completion_tokens: int | None = None,
    max_provider_total_tokens: int | None = None,
    max_provider_estimated_cost_usd: float | None = None,
    provider_cost_unknown: bool = False,
    standard_cache_dir: Path | str | None = None,
    use_standard_cache: bool = True,
    rebuild_standard_cache: bool = False,
    source_semantic_sidecar_materializer: str = SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    source_semantic_sidecar_max_candidates: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES
    ),
    source_semantic_sidecar_max_provider_calls: int = 0,
    source_semantic_sidecar_workers: int = 1,
    source_semantic_sidecar_timeout: int = retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    source_semantic_sidecar_max_tokens: int = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS
    ),
    source_semantic_sidecar_min_confidence: float = (
        retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE
    ),
    rebuild_source_semantic_sidecars: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    split = LONGMEMEVAL_SPLITS[split_name]
    data_path = Path(data_file).resolve() if data_file else default_data_path(split)
    partial_path = Path(partial_output).resolve() if partial_output else None
    checkpoint_path = (
        Path(provider_budget_checkpoint).resolve()
        if provider_budget_checkpoint
        else None
    )
    progress_events: list[dict[str, Any]] = []
    sidecar_config: dict[str, Any] = {
        "source_semantic_sidecar_materializer": source_semantic_sidecar_materializer,
        "source_semantic_sidecar_max_candidates": source_semantic_sidecar_max_candidates,
        "source_semantic_sidecar_max_provider_calls": (
            source_semantic_sidecar_max_provider_calls
        ),
        "source_semantic_sidecar_workers": source_semantic_sidecar_workers,
        "source_semantic_sidecar_timeout": source_semantic_sidecar_timeout,
        "source_semantic_sidecar_max_tokens": source_semantic_sidecar_max_tokens,
        "source_semantic_sidecar_min_confidence": (
            source_semantic_sidecar_min_confidence
        ),
        "rebuild_source_semantic_sidecars": rebuild_source_semantic_sidecars,
    }
    verification = (
        download_dataset(data_path, split)
        if download
        else verify_dataset_file(data_path, split)
    )
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            **sidecar_config,
        )
    live_provider_mode = line_reranker_mode.strip().casefold() == "semantic"
    provider_budget = semantic_provider_budget_config(
        live_mode=live_provider_mode,
        max_questions=max_questions,
        line_reranker_timeout=line_reranker_timeout,
        line_reranker_max_tokens=line_reranker_max_tokens,
        max_provider_calls=max_provider_calls,
        max_provider_prompt_tokens=max_provider_prompt_tokens,
        max_provider_completion_tokens=max_provider_completion_tokens,
        max_provider_total_tokens=max_provider_total_tokens,
        max_provider_estimated_cost_usd=max_provider_estimated_cost_usd,
        provider_cost_unknown=provider_cost_unknown,
        provider_budget_checkpoint=checkpoint_path,
        partial_output=partial_path,
    )
    budget_errors = provider_execution_budget.validate_provider_execution_budget(
        provider_budget
    )
    if budget_errors:
        payload = skipped_payload(
            split=split,
            data_path=data_path,
            reason="skipped_provider_budget_not_declared",
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            **sidecar_config,
        )
        payload["ok"] = False
        budget_summary = provider_execution_budget.provider_execution_budget_summary(
            provider_budget,
            stop_reason="provider_budget_preflight_failed",
            validation_errors=budget_errors,
        )
        payload["provider_execution_budget"] = budget_summary
        if checkpoint_path is not None:
            write_provider_budget_checkpoint(checkpoint_path, budget_summary)
        if partial_path is not None:
            write_json_payload(partial_path, payload)
        return payload

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
                    line_reranker_mode=line_reranker_mode,
                    line_reranker_timeout=line_reranker_timeout,
                    line_reranker_max_tokens=line_reranker_max_tokens,
                    **sidecar_config,
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_top_sessions=line_reranker_top_sessions,
            line_reranker_max_candidates=line_reranker_max_candidates,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            line_reranker_workers=line_reranker_workers,
            progress_every=progress_every,
            progress_callback=handle_progress if track_progress else None,
            standard_cache_dir=standard_cache_dir,
            use_standard_cache=use_standard_cache,
            rebuild_standard_cache=rebuild_standard_cache,
            **sidecar_config,
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            **sidecar_config,
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
            line_reranker_mode=line_reranker_mode,
            line_reranker_timeout=line_reranker_timeout,
            line_reranker_max_tokens=line_reranker_max_tokens,
            **sidecar_config,
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
    if live_provider_mode:
        budget_summary = provider_budget_summary_for_metrics(
            provider_budget,
            metrics=payload["metrics"],
            elapsed_ms=payload["elapsed_ms"],
            stop_reason=status,
        )
        payload["provider_execution_budget"] = budget_summary
        if checkpoint_path is not None:
            write_provider_budget_checkpoint(checkpoint_path, budget_summary)
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
    reranked_key = f"reranked_evidence_hit_rate_top{top_k}"
    if reranked_key in metrics:
        print(f"- reranked evidence top-{top_k}: {metrics.get(reranked_key, 0.0):.2%}")


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
    parser.add_argument(
        "--line-reranker",
        choices=sorted(retrieval_benchmark.STANDARD_LINE_RERANKER_MODES - {"custom"}),
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    )
    parser.add_argument(
        "--line-reranker-top-sessions",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    )
    parser.add_argument(
        "--line-reranker-max-candidates",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--line-reranker-timeout",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    )
    parser.add_argument(
        "--line-reranker-max-tokens",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    )
    parser.add_argument(
        "--line-reranker-workers",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    )
    parser.add_argument(
        "--standard-cache-dir",
        type=Path,
        default=None,
        help="Directory for reusable prepared standard cases/source indexes.",
    )
    parser.add_argument(
        "--no-standard-cache",
        action="store_true",
        help="Disable reusable standard case/source-index cache and use a temporary build.",
    )
    parser.add_argument(
        "--rebuild-standard-cache",
        action="store_true",
        help="Force rebuild of cached standard cases/source indexes.",
    )
    parser.add_argument(
        "--rebuild-source-semantic-sidecars",
        action="store_true",
        help=(
            "Force source semantic sidecar re-materialization; standard cache rebuilds "
            "reuse existing sidecars unless this is set."
        ),
    )
    parser.add_argument(
        "--source-semantic-sidecar-materializer",
        choices=sorted(SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS),
        default=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
        help=(
            "Opt-in cold-fill materializer for canonical semantic-scope sidecars "
            "before source_semantic_cache prewarm."
        ),
    )
    parser.add_argument(
        "--source-semantic-sidecar-max-candidates",
        type=int,
        default=retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
        help=(
            "Candidate selector width for public_semantic_labeler, or source-message "
            "batch size for public_semantic_labeler_full_source."
        ),
    )
    parser.add_argument(
        "--max-source-semantic-sidecar-calls",
        type=int,
        default=0,
        help=(
            "Hard cap for source-side semantic sidecar materializer provider calls; "
            "in full-source mode this caps source-message batches globally."
        ),
    )
    parser.add_argument(
        "--source-semantic-sidecar-workers",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--source-semantic-sidecar-timeout",
        type=int,
        default=retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    )
    parser.add_argument(
        "--source-semantic-sidecar-max-tokens",
        type=int,
        default=retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    )
    parser.add_argument(
        "--source-semantic-sidecar-min-confidence",
        type=float,
        default=retrieval_benchmark.DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    )
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
    parser.add_argument(
        "--provider-budget-checkpoint",
        type=Path,
        default=None,
        help="Write a sanitized provider-budget checkpoint for live/provider runs.",
    )
    parser.add_argument("--max-provider-calls", type=int, default=None)
    parser.add_argument("--max-provider-prompt-tokens", type=int, default=None)
    parser.add_argument("--max-provider-completion-tokens", type=int, default=None)
    parser.add_argument("--max-provider-total-tokens", type=int, default=None)
    parser.add_argument("--max-provider-estimated-cost-usd", type=float, default=None)
    parser.add_argument(
        "--provider-cost-unknown",
        action="store_true",
        help="Acknowledge that provider dollar cost is unavailable for this run.",
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
        line_reranker_mode=args.line_reranker,
        line_reranker_top_sessions=args.line_reranker_top_sessions,
        line_reranker_max_candidates=args.line_reranker_max_candidates,
        line_reranker_timeout=args.line_reranker_timeout,
        line_reranker_max_tokens=args.line_reranker_max_tokens,
        line_reranker_workers=args.line_reranker_workers,
        progress_every=args.progress_every,
        partial_output=args.partial_output,
        provider_budget_checkpoint=args.provider_budget_checkpoint,
        max_provider_calls=args.max_provider_calls,
        max_provider_prompt_tokens=args.max_provider_prompt_tokens,
        max_provider_completion_tokens=args.max_provider_completion_tokens,
        max_provider_total_tokens=args.max_provider_total_tokens,
        max_provider_estimated_cost_usd=args.max_provider_estimated_cost_usd,
        provider_cost_unknown=args.provider_cost_unknown,
        standard_cache_dir=args.standard_cache_dir,
        use_standard_cache=not args.no_standard_cache,
        rebuild_standard_cache=args.rebuild_standard_cache,
        rebuild_source_semantic_sidecars=args.rebuild_source_semantic_sidecars,
        source_semantic_sidecar_materializer=args.source_semantic_sidecar_materializer,
        source_semantic_sidecar_max_candidates=args.source_semantic_sidecar_max_candidates,
        source_semantic_sidecar_max_provider_calls=args.max_source_semantic_sidecar_calls,
        source_semantic_sidecar_workers=args.source_semantic_sidecar_workers,
        source_semantic_sidecar_timeout=args.source_semantic_sidecar_timeout,
        source_semantic_sidecar_max_tokens=args.source_semantic_sidecar_max_tokens,
        source_semantic_sidecar_min_confidence=args.source_semantic_sidecar_min_confidence,
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
