#!/usr/bin/env python3
"""Run the repeatable AIppocampus benchmark baseline suite.

The suite is a baseline capture tool, not a product-quality certificate. It
keeps "did the benchmark run reproducibly?" separate from "did every quality
target pass?" so unfinished recall upgrades can be measured without being
quietly reclassified as success.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import smoke_source_evidence_recall_eval as source_evidence_eval

import benchmark_compaction_continuity as compaction_benchmark
import benchmark_live_semantic_gate as live_semantic_benchmark
import benchmark_memory_decision_gate as gate_benchmark
import benchmark_payload_fidelity as payload_benchmark
import benchmark_source_evidence_retrieval as retrieval_benchmark

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BenchmarkSuiteConfig:
    registry_path: Path | None = None
    include_private_text: bool = False
    include_track_b: bool = True
    include_track_d: bool = True
    include_deterministic_source_labels: bool = True
    include_live_semantic: bool = False
    gate_case_limit: int | None = None
    payload_case_limit: int | None = None
    track_d_case_limit: int | None = None
    live_semantic_conversations: int = live_semantic_benchmark.DEFAULT_LIVE_CONVERSATIONS
    live_semantic_cases: int | None = None
    live_semantic_min_cases: int = live_semantic_benchmark.DEFAULT_MIN_LIVE_CASES
    live_semantic_min_surface_recall: float = (
        live_semantic_benchmark.DEFAULT_MIN_SURFACE_RECALL
    )
    live_semantic_mode: str | None = "auto"
    live_semantic_timeout: int = live_semantic_benchmark.DEFAULT_SEMANTIC_TIMEOUT
    live_semantic_workers: tuple[str, ...] = live_semantic_benchmark.DEFAULT_WORKERS
    live_semantic_cache_path: Path | None = None
    live_semantic_case_workers: int = live_semantic_benchmark.DEFAULT_CASE_WORKERS
    fts5_cases: int = retrieval_benchmark.DEFAULT_FTS5_CASES
    fts5_min_cases: int = retrieval_benchmark.DEFAULT_FTS5_MIN_CASES
    fts5_seed: int = retrieval_benchmark.fts5_benchmark.DEFAULT_SEED
    fts5_top_k: int = retrieval_benchmark.fts5_benchmark.DEFAULT_TOP_K
    fts5_candidate_limit: int = retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT
    source_max_cases: int = retrieval_benchmark.DEFAULT_SOURCE_MAX_CASES
    source_min_cases: int = retrieval_benchmark.DEFAULT_SOURCE_MIN_CASES
    source_top_k: int = 5
    source_min_hit_rate: float = retrieval_benchmark.DEFAULT_SOURCE_MIN_HIT_RATE
    source_ranking: str = "dynamic_source"
    source_max_term_frequency: int = 8
    include_sharegpt_public_track_b: bool = False
    sharegpt_public_corpus_dir: Path | None = None
    sharegpt_public_conversations: int = (
        retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS
    )
    sharegpt_public_max_cases: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CASES
    sharegpt_public_min_cases: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_MIN_CASES
    sharegpt_public_top_k: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_TOP_K
    include_standard_public_track_b: bool = False
    standard_dataset: str = retrieval_benchmark.DEFAULT_STANDARD_DATASET
    standard_corpus_path: Path | None = None
    standard_max_questions: int = retrieval_benchmark.DEFAULT_STANDARD_QA_CASES
    standard_min_questions: int = retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_CASES
    standard_top_k: int = retrieval_benchmark.DEFAULT_STANDARD_QA_TOP_K
    standard_context_radius: int = retrieval_benchmark.DEFAULT_STANDARD_QA_CONTEXT_RADIUS
    standard_min_session_hit_rate: float = (
        retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE
    )
    standard_line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE
    standard_line_reranker_top_sessions: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS
    )
    standard_line_reranker_max_candidates: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES
    )
    standard_line_reranker_timeout: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT
    )
    standard_line_reranker_max_tokens: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS
    )
    standard_line_reranker_workers: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_WORKERS
    )

    def sanitized_payload_config(self) -> dict[str, Any]:
        return {
            "suite_mode": "baseline",
            "registry_path_provided": self.registry_path is not None,
            "include_private_text": bool(self.include_private_text),
            "include_track_b": bool(self.include_track_b),
            "include_track_d": bool(self.include_track_d),
            "include_deterministic_source_labels": bool(
                self.include_deterministic_source_labels
            ),
            "include_live_semantic": bool(self.include_live_semantic),
            "gate_case_limit": self.gate_case_limit,
            "payload_case_limit": self.payload_case_limit,
            "track_d_case_limit": self.track_d_case_limit,
            "live_semantic_conversations": int(self.live_semantic_conversations),
            "live_semantic_cases": self.live_semantic_cases,
            "live_semantic_min_cases": int(self.live_semantic_min_cases),
            "live_semantic_min_surface_recall": float(self.live_semantic_min_surface_recall),
            "live_semantic_mode": self.live_semantic_mode or "auto",
            "live_semantic_timeout": int(self.live_semantic_timeout),
            "live_semantic_workers": list(self.live_semantic_workers),
            "live_semantic_case_workers": int(self.live_semantic_case_workers),
            "fts5_cases": int(self.fts5_cases),
            "fts5_min_cases": int(self.fts5_min_cases),
            "fts5_seed": int(self.fts5_seed),
            "fts5_top_k": int(self.fts5_top_k),
            "fts5_candidate_limit": int(self.fts5_candidate_limit),
            "source_max_cases": int(self.source_max_cases),
            "source_min_cases": int(self.source_min_cases),
            "source_top_k": int(self.source_top_k),
            "source_min_hit_rate": float(self.source_min_hit_rate),
            "source_ranking": self.source_ranking,
            "source_max_term_frequency": int(self.source_max_term_frequency),
            "include_sharegpt_public_track_b": bool(self.include_sharegpt_public_track_b),
            "sharegpt_public_conversations": int(self.sharegpt_public_conversations),
            "sharegpt_public_max_cases": int(self.sharegpt_public_max_cases),
            "sharegpt_public_min_cases": int(self.sharegpt_public_min_cases),
            "sharegpt_public_top_k": int(self.sharegpt_public_top_k),
            "include_standard_public_track_b": bool(self.include_standard_public_track_b),
            "standard_dataset": self.standard_dataset,
            "standard_max_questions": int(self.standard_max_questions),
            "standard_min_questions": int(self.standard_min_questions),
            "standard_top_k": int(self.standard_top_k),
            "standard_context_radius": int(self.standard_context_radius),
            "standard_min_session_hit_rate": float(self.standard_min_session_hit_rate),
            "standard_line_reranker_mode": self.standard_line_reranker_mode,
            "standard_line_reranker_top_sessions": int(
                self.standard_line_reranker_top_sessions
            ),
            "standard_line_reranker_max_candidates": int(
                self.standard_line_reranker_max_candidates
            ),
            "standard_line_reranker_timeout": int(self.standard_line_reranker_timeout),
            "standard_line_reranker_max_tokens": int(
                self.standard_line_reranker_max_tokens
            ),
            "standard_line_reranker_workers": int(self.standard_line_reranker_workers),
        }


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def track_status(name: str, payload: dict[str, Any]) -> str:
    if isinstance(payload.get("status"), str):
        return str(payload["status"])
    return "sufficient" if payload.get("ok") else f"{name}_failed"


def truthy_boundary(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    boundary = payload.get("privacy_boundary")
    if not isinstance(boundary, dict):
        return False
    return any(bool(boundary.get(key)) for key in keys)


def aggregate_privacy_boundary(tracks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw_text_keys = (
        "raw_text_emitted",
        "raw_prompt_emitted",
        "raw_context_emitted",
        "raw_correction_text_emitted",
        "raw_source_refs_emitted",
        "snippets_emitted",
        "source_reference_details_emitted",
    )
    return {
        "raw_text_emitted": any(
            truthy_boundary(payload, raw_text_keys) for payload in tracks.values()
        ),
        "absolute_paths_emitted": any(
            truthy_boundary(payload, ("absolute_paths_emitted",))
            for payload in tracks.values()
        ),
        "output_shape": "sanitized_aippocampus_benchmark_suite",
    }


def track_baseline_captured(name: str, payload: dict[str, Any]) -> bool:
    if name == "source_evidence_retrieval":
        fts5 = ((payload.get("tracks") or {}).get("fts5_source_line") or {})
        source = ((payload.get("tracks") or {}).get("source_evidence") or {})
        return bool(fts5.get("ok")) and int(source.get("case_count") or 0) > 0
    if name == "source_evidence_deterministic_labels":
        return int(payload.get("case_count") or 0) > 0
    return bool(payload.get("ok"))


def track_quality_ok(payload: dict[str, Any]) -> bool:
    if "quality_gate_ok" in payload:
        return bool(payload.get("quality_gate_ok"))
    return bool(payload.get("ok"))


def collect_cannot_claim(tracks: dict[str, dict[str, Any]], *, quality_gate_ok: bool) -> list[str]:
    claims: set[str] = set()
    for payload in tracks.values():
        claims.update(str(item) for item in payload.get("cannot_claim") or [])
    if not quality_gate_ok:
        claims.add("all_benchmark_quality_targets_met")
    return sorted(claims)


def collect_known_gaps(tracks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    gaps: dict[str, dict[str, Any]] = {}
    for name, payload in tracks.items():
        status = track_status(name, payload)
        if payload.get("ok") and status == "sufficient":
            continue
        if name == "source_evidence_retrieval":
            source = ((payload.get("tracks") or {}).get("source_evidence") or {})
            gaps[name] = {
                "status": status,
                "source_evidence_status": source.get("status"),
                "case_count": int(source.get("case_count") or 0),
                "top_k_hit_rate": float(source.get("top_k_hit_rate") or 0.0),
                "cannot_claim": payload.get("cannot_claim") or [],
            }
        else:
            gaps[name] = {
                "status": status,
                "cannot_claim": payload.get("cannot_claim") or [],
            }
            if "case_count" in payload:
                gaps[name]["case_count"] = int(payload.get("case_count") or 0)
            if "top_k_hit_rate" in payload:
                gaps[name]["top_k_hit_rate"] = float(payload.get("top_k_hit_rate") or 0.0)
    return gaps


def deterministic_source_label_slice(
    *,
    registry_path: Path | None,
    max_cases: int,
    min_cases: int,
    top_k: int,
    min_hit_rate: float,
    ranking: str,
    max_term_frequency: int,
) -> dict[str, Any]:
    payload = source_evidence_eval.run_source_evidence_recall_eval(
        registry_path=registry_path,
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=False,
        max_term_frequency=max_term_frequency,
        ranking=ranking,
    )
    summary = retrieval_benchmark.summarize_source_payload(payload)
    summary["cannot_claim"] = payload.get("cannot_claim") or []
    summary["selection"] = {
        "require_semantic_sidecar": False,
        "purpose": "broader deterministic source-label diagnostic baseline",
    }
    return summary


def run_benchmark_suite(
    *,
    registry_path: Path | None = None,
    include_private_text: bool = False,
    include_track_b: bool = True,
    include_track_d: bool = True,
    include_deterministic_source_labels: bool = True,
    include_live_semantic: bool = False,
    gate_case_limit: int | None = None,
    payload_case_limit: int | None = None,
    track_d_case_limit: int | None = None,
    live_semantic_conversations: int = live_semantic_benchmark.DEFAULT_LIVE_CONVERSATIONS,
    live_semantic_cases: int | None = None,
    live_semantic_min_cases: int = live_semantic_benchmark.DEFAULT_MIN_LIVE_CASES,
    live_semantic_min_surface_recall: float = (
        live_semantic_benchmark.DEFAULT_MIN_SURFACE_RECALL
    ),
    live_semantic_mode: str | None = "auto",
    live_semantic_timeout: int = live_semantic_benchmark.DEFAULT_SEMANTIC_TIMEOUT,
    live_semantic_workers: tuple[str, ...] = live_semantic_benchmark.DEFAULT_WORKERS,
    live_semantic_cache_path: Path | None = None,
    live_semantic_case_workers: int = live_semantic_benchmark.DEFAULT_CASE_WORKERS,
    fts5_cases: int = retrieval_benchmark.DEFAULT_FTS5_CASES,
    fts5_min_cases: int = retrieval_benchmark.DEFAULT_FTS5_MIN_CASES,
    fts5_seed: int = retrieval_benchmark.fts5_benchmark.DEFAULT_SEED,
    fts5_top_k: int = retrieval_benchmark.fts5_benchmark.DEFAULT_TOP_K,
    fts5_candidate_limit: int = retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    source_max_cases: int = retrieval_benchmark.DEFAULT_SOURCE_MAX_CASES,
    source_min_cases: int = retrieval_benchmark.DEFAULT_SOURCE_MIN_CASES,
    source_top_k: int = 5,
    source_min_hit_rate: float = retrieval_benchmark.DEFAULT_SOURCE_MIN_HIT_RATE,
    source_ranking: str = "dynamic_source",
    source_max_term_frequency: int = 8,
    include_sharegpt_public_track_b: bool = False,
    sharegpt_public_corpus_dir: Path | None = None,
    sharegpt_public_conversations: int = (
        retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS
    ),
    sharegpt_public_max_cases: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CASES,
    sharegpt_public_min_cases: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    sharegpt_public_top_k: int = retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    include_standard_public_track_b: bool = False,
    standard_dataset: str = retrieval_benchmark.DEFAULT_STANDARD_DATASET,
    standard_corpus_path: Path | None = None,
    standard_max_questions: int = retrieval_benchmark.DEFAULT_STANDARD_QA_CASES,
    standard_min_questions: int = retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_CASES,
    standard_top_k: int = retrieval_benchmark.DEFAULT_STANDARD_QA_TOP_K,
    standard_context_radius: int = retrieval_benchmark.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    standard_min_session_hit_rate: float = (
        retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE
    ),
    standard_line_reranker_mode: str = retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    standard_line_reranker_top_sessions: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS
    ),
    standard_line_reranker_max_candidates: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES
    ),
    standard_line_reranker_timeout: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT
    ),
    standard_line_reranker_max_tokens: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS
    ),
    standard_line_reranker_workers: int = (
        retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_WORKERS
    ),
) -> dict[str, Any]:
    return run_benchmark_suite_with_config(
        BenchmarkSuiteConfig(
            registry_path=registry_path,
            include_private_text=include_private_text,
            include_track_b=include_track_b,
            include_track_d=include_track_d,
            include_deterministic_source_labels=include_deterministic_source_labels,
            include_live_semantic=include_live_semantic,
            gate_case_limit=gate_case_limit,
            payload_case_limit=payload_case_limit,
            track_d_case_limit=track_d_case_limit,
            live_semantic_conversations=live_semantic_conversations,
            live_semantic_cases=live_semantic_cases,
            live_semantic_min_cases=live_semantic_min_cases,
            live_semantic_min_surface_recall=live_semantic_min_surface_recall,
            live_semantic_mode=live_semantic_mode,
            live_semantic_timeout=live_semantic_timeout,
            live_semantic_workers=live_semantic_workers,
            live_semantic_cache_path=live_semantic_cache_path,
            live_semantic_case_workers=live_semantic_case_workers,
            fts5_cases=fts5_cases,
            fts5_min_cases=fts5_min_cases,
            fts5_seed=fts5_seed,
            fts5_top_k=fts5_top_k,
            fts5_candidate_limit=fts5_candidate_limit,
            source_max_cases=source_max_cases,
            source_min_cases=source_min_cases,
            source_top_k=source_top_k,
            source_min_hit_rate=source_min_hit_rate,
            source_ranking=source_ranking,
            source_max_term_frequency=source_max_term_frequency,
            include_sharegpt_public_track_b=include_sharegpt_public_track_b,
            sharegpt_public_corpus_dir=sharegpt_public_corpus_dir,
            sharegpt_public_conversations=sharegpt_public_conversations,
            sharegpt_public_max_cases=sharegpt_public_max_cases,
            sharegpt_public_min_cases=sharegpt_public_min_cases,
            sharegpt_public_top_k=sharegpt_public_top_k,
            include_standard_public_track_b=include_standard_public_track_b,
            standard_dataset=standard_dataset,
            standard_corpus_path=standard_corpus_path,
            standard_max_questions=standard_max_questions,
            standard_min_questions=standard_min_questions,
            standard_top_k=standard_top_k,
            standard_context_radius=standard_context_radius,
            standard_min_session_hit_rate=standard_min_session_hit_rate,
            standard_line_reranker_mode=standard_line_reranker_mode,
            standard_line_reranker_top_sessions=standard_line_reranker_top_sessions,
            standard_line_reranker_max_candidates=standard_line_reranker_max_candidates,
            standard_line_reranker_timeout=standard_line_reranker_timeout,
            standard_line_reranker_max_tokens=standard_line_reranker_max_tokens,
            standard_line_reranker_workers=standard_line_reranker_workers,
        )
    )


def run_benchmark_suite_with_config(config: BenchmarkSuiteConfig) -> dict[str, Any]:
    registry_path = config.registry_path
    include_private_text = config.include_private_text
    include_track_b = config.include_track_b
    include_track_d = config.include_track_d
    include_deterministic_source_labels = config.include_deterministic_source_labels
    include_live_semantic = config.include_live_semantic
    gate_case_limit = config.gate_case_limit
    payload_case_limit = config.payload_case_limit
    track_d_case_limit = config.track_d_case_limit
    live_semantic_conversations = config.live_semantic_conversations
    live_semantic_cases = config.live_semantic_cases
    live_semantic_min_cases = config.live_semantic_min_cases
    live_semantic_min_surface_recall = config.live_semantic_min_surface_recall
    live_semantic_mode = config.live_semantic_mode
    live_semantic_timeout = config.live_semantic_timeout
    live_semantic_workers = config.live_semantic_workers
    live_semantic_cache_path = config.live_semantic_cache_path
    live_semantic_case_workers = config.live_semantic_case_workers
    fts5_cases = config.fts5_cases
    fts5_min_cases = config.fts5_min_cases
    fts5_seed = config.fts5_seed
    fts5_top_k = config.fts5_top_k
    fts5_candidate_limit = config.fts5_candidate_limit
    source_max_cases = config.source_max_cases
    source_min_cases = config.source_min_cases
    source_top_k = config.source_top_k
    source_min_hit_rate = config.source_min_hit_rate
    source_ranking = config.source_ranking
    source_max_term_frequency = config.source_max_term_frequency
    include_sharegpt_public_track_b = config.include_sharegpt_public_track_b
    sharegpt_public_corpus_dir = config.sharegpt_public_corpus_dir
    sharegpt_public_conversations = config.sharegpt_public_conversations
    sharegpt_public_max_cases = config.sharegpt_public_max_cases
    sharegpt_public_min_cases = config.sharegpt_public_min_cases
    sharegpt_public_top_k = config.sharegpt_public_top_k
    include_standard_public_track_b = config.include_standard_public_track_b
    standard_dataset = config.standard_dataset
    standard_corpus_path = config.standard_corpus_path
    standard_max_questions = config.standard_max_questions
    standard_min_questions = config.standard_min_questions
    standard_top_k = config.standard_top_k
    standard_context_radius = config.standard_context_radius
    standard_min_session_hit_rate = config.standard_min_session_hit_rate
    standard_line_reranker_mode = config.standard_line_reranker_mode
    standard_line_reranker_top_sessions = config.standard_line_reranker_top_sessions
    standard_line_reranker_max_candidates = config.standard_line_reranker_max_candidates
    standard_line_reranker_timeout = config.standard_line_reranker_timeout
    standard_line_reranker_max_tokens = config.standard_line_reranker_max_tokens
    standard_line_reranker_workers = config.standard_line_reranker_workers
    started = time.perf_counter()
    tracks: dict[str, dict[str, Any]] = {
        "gate_decision": gate_benchmark.run_benchmark(
            case_set="synthetic",
            case_limit=gate_case_limit,
            include_private_text=include_private_text,
        ),
        "payload_fidelity": payload_benchmark.run_benchmark(
            include_private_text=include_private_text,
            case_limit=payload_case_limit,
        ),
    }
    if include_track_d:
        tracks["compaction_continuity"] = compaction_benchmark.run_benchmark(
            include_private_text=include_private_text,
            case_limit=track_d_case_limit,
        )
    if include_track_b:
        tracks["source_evidence_retrieval"] = (
            retrieval_benchmark.run_source_evidence_retrieval_benchmark(
                registry_path=registry_path,
                fts5_cases=fts5_cases,
                fts5_min_cases=fts5_min_cases,
                fts5_seed=fts5_seed,
                fts5_top_k=fts5_top_k,
                fts5_candidate_limit=fts5_candidate_limit,
                source_max_cases=source_max_cases,
                source_min_cases=source_min_cases,
                source_top_k=source_top_k,
                source_min_hit_rate=source_min_hit_rate,
                source_ranking=source_ranking,
                source_require_semantic_sidecar=True,
                source_max_term_frequency=source_max_term_frequency,
                include_private_text=include_private_text,
                include_sharegpt_public=include_sharegpt_public_track_b,
                sharegpt_public_corpus_dir=sharegpt_public_corpus_dir,
                sharegpt_public_conversations=sharegpt_public_conversations,
                sharegpt_public_max_cases=sharegpt_public_max_cases,
                sharegpt_public_min_cases=sharegpt_public_min_cases,
                sharegpt_public_top_k=sharegpt_public_top_k,
                include_standard_public=include_standard_public_track_b,
                standard_dataset=standard_dataset,
                standard_corpus_path=standard_corpus_path,
                standard_max_questions=standard_max_questions,
                standard_min_questions=standard_min_questions,
                standard_top_k=standard_top_k,
                standard_context_radius=standard_context_radius,
                standard_min_session_hit_rate=standard_min_session_hit_rate,
                standard_line_reranker_mode=standard_line_reranker_mode,
                standard_line_reranker_top_sessions=standard_line_reranker_top_sessions,
                standard_line_reranker_max_candidates=standard_line_reranker_max_candidates,
                standard_line_reranker_timeout=standard_line_reranker_timeout,
                standard_line_reranker_max_tokens=standard_line_reranker_max_tokens,
                standard_line_reranker_workers=standard_line_reranker_workers,
            )
        )
        if include_deterministic_source_labels:
            tracks["source_evidence_deterministic_labels"] = (
                deterministic_source_label_slice(
                    registry_path=registry_path,
                    max_cases=source_max_cases,
                    min_cases=source_min_cases,
                    top_k=source_top_k,
                    min_hit_rate=source_min_hit_rate,
                    ranking=source_ranking,
                    max_term_frequency=source_max_term_frequency,
                )
            )
    if include_live_semantic:
        tracks["live_semantic_gate"] = live_semantic_benchmark.run_live_semantic_eval(
            sharegpt_conversations=live_semantic_conversations,
            case_limit=live_semantic_cases,
            min_cases=live_semantic_min_cases,
            min_surface_recall=live_semantic_min_surface_recall,
            semantic_mode=live_semantic_mode,
            semantic_timeout=live_semantic_timeout,
            semantic_workers=live_semantic_workers,
            semantic_cache_path=live_semantic_cache_path,
            case_workers=live_semantic_case_workers,
        )

    privacy_boundary = aggregate_privacy_boundary(tracks)
    quality_gate_ok = all(track_quality_ok(payload) for payload in tracks.values())
    baseline_captured = all(
        track_baseline_captured(name, payload) for name, payload in tracks.items()
    )
    if not include_private_text and (
        privacy_boundary["raw_text_emitted"] or privacy_boundary["absolute_paths_emitted"]
    ):
        baseline_captured = False

    if quality_gate_ok:
        status = "quality_gate_passed"
    elif baseline_captured:
        status = "baseline_captured_with_known_gaps"
    else:
        status = "baseline_capture_failed"

    track_statuses = {
        name: track_status(name, payload) for name, payload in tracks.items()
    }
    known_gaps = collect_known_gaps(tracks)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_benchmark_suite",
        "generated_at": now_utc(),
        "status": status,
        "ok": bool(baseline_captured),
        "quality_gate_ok": bool(quality_gate_ok),
        "config": config.sanitized_payload_config(),
        "track_statuses": track_statuses,
        "known_gaps": known_gaps,
        "tracks": tracks,
        "privacy_boundary": privacy_boundary,
        "cannot_claim": collect_cannot_claim(
            tracks, quality_gate_ok=quality_gate_ok
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus benchmark suite")
    print(f"- status: {payload['status']}")
    print(f"- baseline captured: {payload['ok']}")
    print(f"- quality gate ok: {payload['quality_gate_ok']}")
    print("- tracks:")
    for name, status in payload["track_statuses"].items():
        print(f"  - {name}: {status}")
    if payload["known_gaps"]:
        print("- known gaps:")
        for name, gap in payload["known_gaps"].items():
            print(f"  - {name}: {gap.get('status')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--skip-track-b", action="store_true")
    parser.add_argument("--skip-track-d", action="store_true")
    parser.add_argument("--skip-deterministic-source-labels", action="store_true")
    parser.add_argument("--include-live-semantic", action="store_true")
    parser.add_argument("--include-sharegpt-public-track-b", action="store_true")
    parser.add_argument("--include-standard-public-track-b", action="store_true")
    parser.add_argument("--gate-cases", type=int, default=None)
    parser.add_argument("--payload-cases", type=int, default=None)
    parser.add_argument("--track-d-cases", type=int, default=None)
    parser.add_argument(
        "--live-semantic-conversations",
        type=int,
        default=live_semantic_benchmark.DEFAULT_LIVE_CONVERSATIONS,
    )
    parser.add_argument("--live-semantic-cases", type=int, default=None)
    parser.add_argument(
        "--live-semantic-min-cases",
        type=int,
        default=live_semantic_benchmark.DEFAULT_MIN_LIVE_CASES,
    )
    parser.add_argument(
        "--live-semantic-min-surface-recall",
        type=float,
        default=live_semantic_benchmark.DEFAULT_MIN_SURFACE_RECALL,
    )
    parser.add_argument(
        "--live-semantic-mode",
        choices=["auto", "on", "off"],
        default="auto",
    )
    parser.add_argument(
        "--live-semantic-timeout",
        type=int,
        default=live_semantic_benchmark.DEFAULT_SEMANTIC_TIMEOUT,
    )
    parser.add_argument(
        "--live-semantic-workers",
        default=",".join(live_semantic_benchmark.DEFAULT_WORKERS),
    )
    parser.add_argument(
        "--live-semantic-case-workers",
        type=int,
        default=live_semantic_benchmark.DEFAULT_CASE_WORKERS,
    )
    parser.add_argument("--live-semantic-cache", type=Path, default=None)
    parser.add_argument("--fts5-cases", type=int, default=retrieval_benchmark.DEFAULT_FTS5_CASES)
    parser.add_argument(
        "--fts5-min-cases",
        type=int,
        default=retrieval_benchmark.DEFAULT_FTS5_MIN_CASES,
    )
    parser.add_argument(
        "--fts5-seed",
        type=int,
        default=retrieval_benchmark.fts5_benchmark.DEFAULT_SEED,
    )
    parser.add_argument(
        "--fts5-top-k",
        type=int,
        default=retrieval_benchmark.fts5_benchmark.DEFAULT_TOP_K,
    )
    parser.add_argument(
        "--fts5-candidate-limit",
        type=int,
        default=retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument(
        "--source-max-cases",
        type=int,
        default=retrieval_benchmark.DEFAULT_SOURCE_MAX_CASES,
    )
    parser.add_argument(
        "--source-min-cases",
        type=int,
        default=retrieval_benchmark.DEFAULT_SOURCE_MIN_CASES,
    )
    parser.add_argument("--source-top-k", type=int, default=5)
    parser.add_argument(
        "--source-min-hit-rate",
        type=float,
        default=retrieval_benchmark.DEFAULT_SOURCE_MIN_HIT_RATE,
    )
    parser.add_argument(
        "--source-ranking",
        choices=["dynamic_source", "registry"],
        default="dynamic_source",
    )
    parser.add_argument("--source-max-term-frequency", type=int, default=8)
    parser.add_argument(
        "--sharegpt-public-corpus-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--sharegpt-public-conversations",
        type=int,
        default=retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    )
    parser.add_argument(
        "--sharegpt-public-cases",
        type=int,
        default=retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_CASES,
    )
    parser.add_argument(
        "--sharegpt-public-min-cases",
        type=int,
        default=retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    )
    parser.add_argument(
        "--sharegpt-public-top-k",
        type=int,
        default=retrieval_benchmark.DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    )
    parser.add_argument(
        "--standard-dataset",
        choices=sorted(retrieval_benchmark.STANDARD_DATASET_PATHS),
        default=retrieval_benchmark.DEFAULT_STANDARD_DATASET,
    )
    parser.add_argument("--standard-corpus-path", type=Path, default=None)
    parser.add_argument(
        "--standard-questions",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_CASES,
    )
    parser.add_argument(
        "--standard-min-questions",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_CASES,
    )
    parser.add_argument(
        "--standard-top-k",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_TOP_K,
    )
    parser.add_argument(
        "--standard-context-radius",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    )
    parser.add_argument(
        "--standard-min-session-hit-rate",
        type=float,
        default=retrieval_benchmark.DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    )
    parser.add_argument(
        "--standard-line-reranker",
        choices=sorted(retrieval_benchmark.STANDARD_LINE_RERANKER_MODES - {"custom"}),
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MODE,
    )
    parser.add_argument(
        "--standard-line-reranker-top-sessions",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    )
    parser.add_argument(
        "--standard-line-reranker-max-candidates",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--standard-line-reranker-timeout",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    )
    parser.add_argument(
        "--standard-line-reranker-max-tokens",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    )
    parser.add_argument(
        "--standard-line-reranker-workers",
        type=int,
        default=retrieval_benchmark.DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def benchmark_suite_config_from_args(args: argparse.Namespace) -> BenchmarkSuiteConfig:
    return BenchmarkSuiteConfig(
        registry_path=args.registry,
        include_private_text=args.include_private_text,
        include_track_b=not args.skip_track_b,
        include_track_d=not args.skip_track_d,
        include_deterministic_source_labels=not args.skip_deterministic_source_labels,
        include_live_semantic=args.include_live_semantic,
        gate_case_limit=args.gate_cases,
        payload_case_limit=args.payload_cases,
        track_d_case_limit=args.track_d_cases,
        live_semantic_conversations=args.live_semantic_conversations,
        live_semantic_cases=args.live_semantic_cases,
        live_semantic_min_cases=args.live_semantic_min_cases,
        live_semantic_min_surface_recall=args.live_semantic_min_surface_recall,
        live_semantic_mode=args.live_semantic_mode,
        live_semantic_timeout=args.live_semantic_timeout,
        live_semantic_workers=live_semantic_benchmark.parse_workers(args.live_semantic_workers),
        live_semantic_cache_path=args.live_semantic_cache,
        live_semantic_case_workers=args.live_semantic_case_workers,
        fts5_cases=args.fts5_cases,
        fts5_min_cases=args.fts5_min_cases,
        fts5_seed=args.fts5_seed,
        fts5_top_k=args.fts5_top_k,
        fts5_candidate_limit=args.fts5_candidate_limit,
        source_max_cases=args.source_max_cases,
        source_min_cases=args.source_min_cases,
        source_top_k=args.source_top_k,
        source_min_hit_rate=args.source_min_hit_rate,
        source_ranking=args.source_ranking,
        source_max_term_frequency=args.source_max_term_frequency,
        include_sharegpt_public_track_b=args.include_sharegpt_public_track_b,
        sharegpt_public_corpus_dir=args.sharegpt_public_corpus_dir,
        sharegpt_public_conversations=args.sharegpt_public_conversations,
        sharegpt_public_max_cases=args.sharegpt_public_cases,
        sharegpt_public_min_cases=args.sharegpt_public_min_cases,
        sharegpt_public_top_k=args.sharegpt_public_top_k,
        include_standard_public_track_b=args.include_standard_public_track_b,
        standard_dataset=args.standard_dataset,
        standard_corpus_path=args.standard_corpus_path,
        standard_max_questions=args.standard_questions,
        standard_min_questions=args.standard_min_questions,
        standard_top_k=args.standard_top_k,
        standard_context_radius=args.standard_context_radius,
        standard_min_session_hit_rate=args.standard_min_session_hit_rate,
        standard_line_reranker_mode=args.standard_line_reranker,
        standard_line_reranker_top_sessions=args.standard_line_reranker_top_sessions,
        standard_line_reranker_max_candidates=args.standard_line_reranker_max_candidates,
        standard_line_reranker_timeout=args.standard_line_reranker_timeout,
        standard_line_reranker_max_tokens=args.standard_line_reranker_max_tokens,
        standard_line_reranker_workers=args.standard_line_reranker_workers,
    )


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    payload = run_benchmark_suite_with_config(benchmark_suite_config_from_args(args))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
