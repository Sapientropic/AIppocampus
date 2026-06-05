#!/usr/bin/env python3
# ruff: noqa: F401
# Compatibility facade: keep old helper names importable while track logic lives
# in source_evidence modules.
"""Unify source-evidence retrieval benchmarks for AIppocampus Track B.

This runner deliberately reuses the mature retrieval evaluators instead of
inventing another scoring layer. Its job is report normalization: keep FTS5
source-line recall and selected source-evidence recall visible in one sanitized
shape, while preserving source refs as the authority.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

import smoke_source_evidence_recall_eval as source_evidence_eval

import benchmark_fts5_recall as fts5_benchmark
import sharegpt_sampling
from aippocampus_runtime.recall.index_builder import make_sqlite
from source_evidence.defaults import (
    DEFAULT_FTS5_CASES,
    DEFAULT_FTS5_MIN_CASES,
    DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    DEFAULT_SHAREGPT_PUBLIC_CASES,
    DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR,
    DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE,
    DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE,
    DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    DEFAULT_SOURCE_MAX_CASES,
    DEFAULT_SOURCE_MIN_CASES,
    DEFAULT_SOURCE_MIN_HIT_RATE,
    DEFAULT_STANDARD_DATASET,
    DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    DEFAULT_STANDARD_LINE_RERANKER_MODE,
    DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    DEFAULT_STANDARD_QA_CASES,
    DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    DEFAULT_STANDARD_QA_MIN_CASES,
    DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    DEFAULT_STANDARD_QA_TOP_K,
    SCHEMA_VERSION,
    STANDARD_DATASET_PATHS,
    STANDARD_LINE_RERANKER_MODES,
    LineRerankerFn,
    PublicSemanticLabelerFn,
)
from source_evidence.fts5_source_line import sanitize_fts5_case, summarize_fts5_payload
from source_evidence.public_semantic import (
    public_semantic_candidate_messages,
    public_semantic_claim_level,
    public_semantic_labeler_messages,
    public_semantic_sample_size_warning,
    public_semantic_source_ref,
    public_semantic_status,
    public_semantic_subset_messages,
    public_semantic_turn_rows,
    run_public_semantic_labeler,
    run_public_semantic_sidecar_benchmark,
    skipped_public_semantic_sidecar_payload,
    summarize_public_semantic_source_payload,
    write_public_semantic_subset_pack,
)
from source_evidence.reporting import (
    claim_boundary,
    now_utc,
    query_origin_summary,
    source_evidence_validation_guidance,
    summarize_sharegpt_public_payload,
    summarize_standard_retrieval_payload,
)
from source_evidence.selected_source import summarize_source_payload
from source_evidence.sharegpt_public import (
    add_sharegpt_public_case,
    build_sharegpt_public_cases,
    evaluate_sharegpt_public_case,
    load_sharegpt_conversations,
    normalize_sharegpt_rows,
    normalize_source_line,
    previous_assistant,
    previous_user,
    public_source_terms,
    rank_line,
    rank_turn,
    run_sharegpt_public_source_evidence_benchmark,
    sharegpt_conversation_is_eligible,
    sharegpt_message_for_sqlite,
    sharegpt_public_prompt,
    sharegpt_public_status,
    skipped_sharegpt_public_payload,
    summarize_sharegpt_public_results,
    turn_line_range,
)
from source_evidence.standard_public import (
    best_rank,
    build_locomo_messages,
    build_locomo_standard_cases,
    build_longmemeval_messages,
    build_longmemeval_v1_standard_cases,
    build_standard_line_reranker_candidates,
    evaluate_standard_retrieval_case,
    has_successful_standard_question_arm,
    iter_json_array_items,
    line_reranker_error_kind,
    load_standard_message_rows,
    locomo_session_sort_key,
    rank_expected_line,
    rank_expected_line_context,
    rank_expected_session,
    ranked_unique_lines,
    run_semantic_line_reranker,
    run_standard_retrieval_qa_benchmark,
    semantic_line_reranker_available,
    semantic_line_reranker_messages,
    skipped_standard_retrieval_payload,
    standard_content_query_terms,
    standard_message_for_sqlite,
    standard_retrieval_status,
    summarize_standard_retrieval_results,
)

__all__ = [
    "DEFAULT_FTS5_CASES",
    "DEFAULT_FTS5_MIN_CASES",
    "DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS",
    "DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES",
    "DEFAULT_PUBLIC_SEMANTIC_MAX_CASES",
    "DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES",
    "DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS",
    "DEFAULT_PUBLIC_SEMANTIC_MIN_CASES",
    "DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE",
    "DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE",
    "DEFAULT_PUBLIC_SEMANTIC_TIMEOUT",
    "DEFAULT_PUBLIC_SEMANTIC_TOP_K",
    "DEFAULT_SHAREGPT_PUBLIC_CASES",
    "DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS",
    "DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR",
    "DEFAULT_SHAREGPT_PUBLIC_MIN_CASES",
    "DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE",
    "DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE",
    "DEFAULT_SHAREGPT_PUBLIC_TOP_K",
    "DEFAULT_SOURCE_MAX_CASES",
    "DEFAULT_SOURCE_MIN_CASES",
    "DEFAULT_SOURCE_MIN_HIT_RATE",
    "DEFAULT_STANDARD_DATASET",
    "DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES",
    "DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS",
    "DEFAULT_STANDARD_LINE_RERANKER_MODE",
    "DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT",
    "DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS",
    "DEFAULT_STANDARD_LINE_RERANKER_WORKERS",
    "DEFAULT_STANDARD_QA_CASES",
    "DEFAULT_STANDARD_QA_CONTEXT_RADIUS",
    "DEFAULT_STANDARD_QA_MIN_CASES",
    "DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE",
    "DEFAULT_STANDARD_QA_TOP_K",
    "LineRerankerFn",
    "PublicSemanticLabelerFn",
    "SCHEMA_VERSION",
    "STANDARD_DATASET_PATHS",
    "STANDARD_LINE_RERANKER_MODES",
    "add_sharegpt_public_case",
    "best_rank",
    "build_locomo_messages",
    "build_locomo_standard_cases",
    "build_longmemeval_messages",
    "build_longmemeval_v1_standard_cases",
    "build_standard_line_reranker_candidates",
    "evaluate_sharegpt_public_case",
    "evaluate_standard_retrieval_case",
    "fts5_benchmark",
    "has_successful_standard_question_arm",
    "iter_json_array_items",
    "line_reranker_error_kind",
    "load_sharegpt_conversations",
    "load_standard_message_rows",
    "locomo_session_sort_key",
    "make_sqlite",
    "normalize_sharegpt_rows",
    "normalize_source_line",
    "previous_assistant",
    "previous_user",
    "public_semantic_candidate_messages",
    "public_semantic_claim_level",
    "public_semantic_labeler_messages",
    "public_semantic_sample_size_warning",
    "public_semantic_source_ref",
    "public_semantic_status",
    "public_semantic_subset_messages",
    "public_semantic_turn_rows",
    "public_source_terms",
    "rank_expected_line",
    "rank_expected_line_context",
    "rank_expected_session",
    "rank_line",
    "rank_turn",
    "ranked_unique_lines",
    "run_public_semantic_labeler",
    "run_public_semantic_sidecar_benchmark",
    "run_semantic_line_reranker",
    "run_sharegpt_public_source_evidence_benchmark",
    "run_source_evidence_retrieval_benchmark",
    "run_standard_retrieval_qa_benchmark",
    "semantic_line_reranker_available",
    "semantic_line_reranker_messages",
    "sharegpt_conversation_is_eligible",
    "sharegpt_message_for_sqlite",
    "sharegpt_public_prompt",
    "sharegpt_public_status",
    "sharegpt_sampling",
    "skipped_public_semantic_sidecar_payload",
    "skipped_sharegpt_public_payload",
    "skipped_standard_retrieval_payload",
    "source_evidence_eval",
    "standard_content_query_terms",
    "standard_message_for_sqlite",
    "standard_retrieval_status",
    "summarize_fts5_payload",
    "summarize_public_semantic_source_payload",
    "summarize_sharegpt_public_payload",
    "summarize_sharegpt_public_results",
    "summarize_source_payload",
    "summarize_standard_retrieval_payload",
    "summarize_standard_retrieval_results",
    "turn_line_range",
]

def cannot_claim(
    *,
    fts5_payload: dict[str, Any],
    source_payload: dict[str, Any],
    sharegpt_public_payload: dict[str, Any] | None = None,
    standard_public_payload: dict[str, Any] | None = None,
    public_semantic_sidecar_payload: dict[str, Any] | None = None,
) -> list[str]:
    claims = [
        "real_history_gate_quality",
        "live_semantic_model_quality",
        "end_to_end_payload_fidelity_on_private_real_history",
        "external_baseline_comparison",
    ]
    if not has_successful_standard_question_arm(standard_public_payload):
        claims.extend(
            [
                "natural_user_query_recall",
                "semantic_generalized_memory_recall",
                "paraphrase_or_cross_language_recall",
            ]
        )
    claims.extend(str(item) for item in source_payload.get("cannot_claim") or [])
    if not fts5_payload.get("ok"):
        claims.append("source_line_retrieval_quality")
    if not source_payload.get("ok"):
        claims.append("selected_source_evidence_recall")
    if sharegpt_public_payload:
        claims.extend(str(item) for item in sharegpt_public_payload.get("cannot_claim") or [])
        if not sharegpt_public_payload.get("ok") and sharegpt_public_payload.get(
            "status"
        ) != "skipped_missing_public_corpus":
            claims.append("sharegpt_public_source_evidence_recall")
    if standard_public_payload:
        claims.extend(str(item) for item in standard_public_payload.get("cannot_claim") or [])
        if not standard_public_payload.get("ok") and not str(
            standard_public_payload.get("status") or ""
        ).startswith("skipped_"):
            claims.append("standard_public_retrieval_qa_source_evidence")
    if public_semantic_sidecar_payload:
        claims.extend(str(item) for item in public_semantic_sidecar_payload.get("cannot_claim") or [])
        if not public_semantic_sidecar_payload.get("ok") and not str(
            public_semantic_sidecar_payload.get("status") or ""
        ).startswith("skipped_"):
            claims.append("public_semantic_sidecar_source_evidence")
    return sorted(set(claims))


def run_source_evidence_retrieval_benchmark(
    *,
    registry_path: Path | None = None,
    only_standard_public: bool = False,
    fts5_cases: int = DEFAULT_FTS5_CASES,
    fts5_min_cases: int = DEFAULT_FTS5_MIN_CASES,
    fts5_seed: int = fts5_benchmark.DEFAULT_SEED,
    fts5_top_k: int = fts5_benchmark.DEFAULT_TOP_K,
    fts5_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    source_max_cases: int = DEFAULT_SOURCE_MAX_CASES,
    source_min_cases: int = DEFAULT_SOURCE_MIN_CASES,
    source_top_k: int = 5,
    source_min_hit_rate: float = DEFAULT_SOURCE_MIN_HIT_RATE,
    source_ranking: str = "dynamic_source",
    source_require_semantic_sidecar: bool = True,
    source_max_term_frequency: int = 8,
    include_private_text: bool = False,
    include_sharegpt_public: bool = False,
    sharegpt_public_corpus_dir: Path | str | None = None,
    sharegpt_public_conversations: int = DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    sharegpt_public_max_cases: int = DEFAULT_SHAREGPT_PUBLIC_CASES,
    sharegpt_public_min_cases: int = DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    sharegpt_public_top_k: int = DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    sharegpt_public_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    sharegpt_public_min_message_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE,
    sharegpt_public_min_turn_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE,
    sharegpt_public_sampling_mode: str = sharegpt_sampling.SEEDED_STRATIFIED,
    sharegpt_public_seed: int = sharegpt_sampling.DEFAULT_SHAREGPT_SAMPLE_SEED,
    include_standard_public: bool = False,
    standard_dataset: str = DEFAULT_STANDARD_DATASET,
    standard_corpus_path: Path | str | None = None,
    standard_max_questions: int = DEFAULT_STANDARD_QA_CASES,
    standard_min_questions: int = DEFAULT_STANDARD_QA_MIN_CASES,
    standard_top_k: int = DEFAULT_STANDARD_QA_TOP_K,
    standard_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    standard_context_radius: int = DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    standard_min_session_hit_rate: float = DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    standard_line_reranker_mode: str = DEFAULT_STANDARD_LINE_RERANKER_MODE,
    standard_line_reranker_top_sessions: int = DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    standard_line_reranker_max_candidates: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    standard_line_reranker_timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    standard_line_reranker_max_tokens: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    standard_line_reranker_workers: int = DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    include_public_semantic_sidecar: bool = False,
    public_semantic_corpus_dir: Path | str | None = None,
    public_semantic_output_dir: Path | str | None = None,
    public_semantic_conversations: int = DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    public_semantic_max_messages: int = DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    public_semantic_max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    public_semantic_max_cases: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    public_semantic_min_cases: int = DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    public_semantic_top_k: int = DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    public_semantic_min_hit_rate: float = DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    public_semantic_min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    public_semantic_timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    public_semantic_max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
) -> dict[str, Any]:
    started = time.perf_counter()
    if only_standard_public:
        standard_public_payload = run_standard_retrieval_qa_benchmark(
            dataset=standard_dataset,
            corpus_path=standard_corpus_path,
            max_questions=standard_max_questions,
            min_questions=standard_min_questions,
            top_k=standard_top_k,
            candidate_limit=standard_candidate_limit,
            context_radius=standard_context_radius,
            min_session_hit_rate=standard_min_session_hit_rate,
            include_private_text=include_private_text,
            line_reranker_mode=standard_line_reranker_mode,
            line_reranker_top_sessions=standard_line_reranker_top_sessions,
            line_reranker_max_candidates=standard_line_reranker_max_candidates,
            line_reranker_timeout=standard_line_reranker_timeout,
            line_reranker_max_tokens=standard_line_reranker_max_tokens,
            line_reranker_workers=standard_line_reranker_workers,
        )
        standard_status = str(standard_public_payload.get("status") or "")
        standard_ok = bool(standard_public_payload.get("ok")) or standard_status.startswith(
            "skipped_"
        )
        if standard_status.startswith("skipped_"):
            status = "standard_public_only_skipped"
        elif standard_public_payload.get("ok"):
            status = "standard_public_only_sufficient"
        else:
            status = "standard_public_only_diagnostic"
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_source_evidence_retrieval_benchmark",
            "generated_at": now_utc(),
            "status": status,
            "ok": standard_ok,
            "config": {
                "only_standard_public": True,
                "include_standard_public": True,
                "standard_dataset": standard_dataset,
                "standard_max_questions": int(standard_max_questions),
                "standard_min_questions": int(standard_min_questions),
                "standard_top_k": int(standard_top_k),
                "standard_context_radius": int(standard_context_radius),
                "standard_line_reranker_mode": standard_line_reranker_mode,
                "standard_line_reranker_top_sessions": int(
                    standard_line_reranker_top_sessions
                ),
                "standard_line_reranker_max_candidates": int(
                    standard_line_reranker_max_candidates
                ),
                "standard_line_reranker_timeout": int(standard_line_reranker_timeout),
                "standard_line_reranker_max_tokens": int(
                    standard_line_reranker_max_tokens
                ),
                "standard_line_reranker_workers": int(standard_line_reranker_workers),
                "include_private_text": bool(include_private_text),
            },
            "tracks": {
                "standard_public_retrieval_qa": summarize_standard_retrieval_payload(
                    standard_public_payload
                )
            },
            "cases": {
                "standard_public_retrieval_qa": [
                    dict(case)
                    for case in standard_public_payload.get("cases") or []
                    if isinstance(case, dict)
                ]
            },
            "privacy_boundary": {
                "raw_text_emitted": bool(include_private_text),
                "snippets_emitted": bool(include_private_text),
                "titles_emitted": False,
                "source_reference_details_emitted": bool(include_private_text),
                "absolute_paths_emitted": bool(include_private_text),
                "case_ids_are_hashed": True,
                "output_shape": "sanitized_standard_public_retrieval_qa_only",
            },
            "cannot_claim": sorted(
                set(
                    [str(item) for item in standard_public_payload.get("cannot_claim") or []]
                    + [
                        "full_mixed_track_b_bundle",
                        "private_real_history_source_evidence_quality",
                    ]
                )
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        payload["query_origin_summary"] = query_origin_summary(payload["tracks"])
        if include_private_text:
            payload["private_debug_payloads"] = {
                "standard_public_retrieval_qa": standard_public_payload
            }
        return payload

    fts5_payload = fts5_benchmark.run_benchmark(
        registry_path=registry_path,
        sample_size=fts5_cases,
        seed=fts5_seed,
        top_k=fts5_top_k,
        candidate_limit=fts5_candidate_limit,
        min_cases=fts5_min_cases,
        include_private_text=include_private_text,
        compare_production=True,
    )
    source_payload = source_evidence_eval.run_source_evidence_recall_eval(
        registry_path=registry_path,
        max_cases=source_max_cases,
        min_cases=source_min_cases,
        top_k=source_top_k,
        min_hit_rate=source_min_hit_rate,
        require_semantic_sidecar=source_require_semantic_sidecar,
        max_term_frequency=source_max_term_frequency,
        ranking=source_ranking,
    )
    sharegpt_public_payload = None
    if include_sharegpt_public:
        sharegpt_public_payload = run_sharegpt_public_source_evidence_benchmark(
            corpus_dir=sharegpt_public_corpus_dir,
            conversations=sharegpt_public_conversations,
            max_cases=sharegpt_public_max_cases,
            min_cases=sharegpt_public_min_cases,
            top_k=sharegpt_public_top_k,
            candidate_limit=sharegpt_public_candidate_limit,
            min_message_hit_rate=sharegpt_public_min_message_hit_rate,
            min_turn_hit_rate=sharegpt_public_min_turn_hit_rate,
            sampling_mode=sharegpt_public_sampling_mode,
            seed=sharegpt_public_seed,
            include_private_text=include_private_text,
        )
    standard_public_payload = None
    if include_standard_public:
        standard_public_payload = run_standard_retrieval_qa_benchmark(
            dataset=standard_dataset,
            corpus_path=standard_corpus_path,
            max_questions=standard_max_questions,
            min_questions=standard_min_questions,
            top_k=standard_top_k,
            candidate_limit=standard_candidate_limit,
            context_radius=standard_context_radius,
            min_session_hit_rate=standard_min_session_hit_rate,
            include_private_text=include_private_text,
            line_reranker_mode=standard_line_reranker_mode,
            line_reranker_top_sessions=standard_line_reranker_top_sessions,
            line_reranker_max_candidates=standard_line_reranker_max_candidates,
            line_reranker_timeout=standard_line_reranker_timeout,
            line_reranker_max_tokens=standard_line_reranker_max_tokens,
            line_reranker_workers=standard_line_reranker_workers,
        )
    public_semantic_sidecar_payload = None
    if include_public_semantic_sidecar:
        public_semantic_sidecar_payload = run_public_semantic_sidecar_benchmark(
            corpus_dir=public_semantic_corpus_dir,
            output_dir=public_semantic_output_dir,
            conversations=public_semantic_conversations,
            max_messages=public_semantic_max_messages,
            max_candidates=public_semantic_max_candidates,
            max_cases=public_semantic_max_cases,
            min_cases=public_semantic_min_cases,
            top_k=public_semantic_top_k,
            min_hit_rate=public_semantic_min_hit_rate,
            min_confidence=public_semantic_min_confidence,
            timeout=public_semantic_timeout,
            max_tokens=public_semantic_max_tokens,
            include_private_text=include_private_text,
        )
    sharegpt_public_ok = (
        True
        if not sharegpt_public_payload
        else bool(sharegpt_public_payload.get("ok"))
        or sharegpt_public_payload.get("status") == "skipped_missing_public_corpus"
    )
    standard_public_ok = (
        True
        if not standard_public_payload
        else bool(standard_public_payload.get("ok"))
        or str(standard_public_payload.get("status") or "").startswith("skipped_")
    )
    public_semantic_ok = (
        True
        if not public_semantic_sidecar_payload
        else bool(public_semantic_sidecar_payload.get("ok"))
        or str(public_semantic_sidecar_payload.get("status") or "").startswith("skipped_")
    )
    ok = (
        bool(fts5_payload.get("ok"))
        and bool(source_payload.get("ok"))
        and sharegpt_public_ok
        and standard_public_ok
        and public_semantic_ok
    )
    status = "sufficient" if ok else "diagnostic_only"
    fts5_cases_payload = [
        sanitize_fts5_case(case, top_k=fts5_top_k)
        for case in fts5_payload.get("cases") or []
        if isinstance(case, dict)
    ]
    source_cases = [
        dict(case) for case in source_payload.get("cases") or [] if isinstance(case, dict)
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_source_evidence_retrieval_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": ok,
        "config": {
            "only_standard_public": bool(only_standard_public),
            "fts5_cases": int(fts5_cases),
            "fts5_min_cases": int(fts5_min_cases),
            "fts5_seed": int(fts5_seed),
            "fts5_top_k": int(fts5_top_k),
            "fts5_candidate_limit": int(fts5_candidate_limit),
            "source_max_cases": int(source_max_cases),
            "source_min_cases": int(source_min_cases),
            "source_top_k": int(source_top_k),
            "source_min_hit_rate": float(source_min_hit_rate),
            "source_ranking": source_ranking,
            "source_require_semantic_sidecar": bool(source_require_semantic_sidecar),
            "source_max_term_frequency": int(source_max_term_frequency),
            "include_private_text": bool(include_private_text),
            "include_sharegpt_public": bool(include_sharegpt_public),
            "sharegpt_public_conversations": int(sharegpt_public_conversations),
            "sharegpt_public_max_cases": int(sharegpt_public_max_cases),
            "sharegpt_public_min_cases": int(sharegpt_public_min_cases),
            "sharegpt_public_top_k": int(sharegpt_public_top_k),
            "sharegpt_public_sampling_mode": sharegpt_sampling.canonical_sampling_mode(
                sharegpt_public_sampling_mode
            ),
            "sharegpt_public_seed": int(sharegpt_public_seed),
            "include_standard_public": bool(include_standard_public),
            "standard_dataset": standard_dataset,
            "standard_max_questions": int(standard_max_questions),
            "standard_min_questions": int(standard_min_questions),
            "standard_top_k": int(standard_top_k),
            "standard_context_radius": int(standard_context_radius),
            "standard_line_reranker_mode": standard_line_reranker_mode,
            "standard_line_reranker_top_sessions": int(standard_line_reranker_top_sessions),
            "standard_line_reranker_max_candidates": int(standard_line_reranker_max_candidates),
            "standard_line_reranker_timeout": int(standard_line_reranker_timeout),
            "standard_line_reranker_max_tokens": int(standard_line_reranker_max_tokens),
            "standard_line_reranker_workers": int(standard_line_reranker_workers),
            "include_public_semantic_sidecar": bool(include_public_semantic_sidecar),
            "public_semantic_conversations": int(public_semantic_conversations),
            "public_semantic_max_messages": int(public_semantic_max_messages),
            "public_semantic_max_candidates": int(public_semantic_max_candidates),
            "public_semantic_max_cases": int(public_semantic_max_cases),
            "public_semantic_min_cases": int(public_semantic_min_cases),
            "public_semantic_top_k": int(public_semantic_top_k),
            "public_semantic_min_hit_rate": float(public_semantic_min_hit_rate),
            "public_semantic_min_confidence": float(public_semantic_min_confidence),
            "public_semantic_timeout": int(public_semantic_timeout),
            "public_semantic_max_tokens": int(public_semantic_max_tokens),
        },
        "tracks": {
            "fts5_source_line": summarize_fts5_payload(fts5_payload, top_k=fts5_top_k),
            "source_evidence": summarize_source_payload(source_payload),
        },
        "cases": {
            "fts5": fts5_cases_payload,
            "source_evidence": source_cases,
        },
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "titles_emitted": False,
            "source_reference_details_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_track_b_retrieval_aggregates",
        },
        "cannot_claim": cannot_claim(
            fts5_payload=fts5_payload,
            source_payload=source_payload,
            sharegpt_public_payload=sharegpt_public_payload,
            standard_public_payload=standard_public_payload,
            public_semantic_sidecar_payload=public_semantic_sidecar_payload,
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if sharegpt_public_payload:
        payload["tracks"]["sharegpt_public_source_evidence"] = (
            summarize_sharegpt_public_payload(sharegpt_public_payload)
        )
        payload["cases"]["sharegpt_public"] = [
            dict(case)
            for case in sharegpt_public_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    if standard_public_payload:
        payload["tracks"]["standard_public_retrieval_qa"] = (
            summarize_standard_retrieval_payload(standard_public_payload)
        )
        payload["cases"]["standard_public_retrieval_qa"] = [
            dict(case)
            for case in standard_public_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    if public_semantic_sidecar_payload:
        payload["tracks"]["public_semantic_sidecar"] = (
            summarize_public_semantic_source_payload(public_semantic_sidecar_payload)
        )
        payload["cases"]["public_semantic_sidecar"] = [
            dict(case)
            for case in public_semantic_sidecar_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    payload["query_origin_summary"] = query_origin_summary(payload["tracks"])
    source_guidance = source_evidence_validation_guidance(
        source_payload,
        require_semantic_sidecar=source_require_semantic_sidecar,
    )
    if source_guidance:
        payload["validation_guidance"] = {"track_b_source_evidence": source_guidance}
    if include_private_text:
        payload["private_debug_payloads"] = {
            "fts5": fts5_payload,
            "source_evidence": source_payload,
        }
        if sharegpt_public_payload:
            payload["private_debug_payloads"]["sharegpt_public"] = sharegpt_public_payload
        if standard_public_payload:
            payload["private_debug_payloads"]["standard_public_retrieval_qa"] = (
                standard_public_payload
            )
        if public_semantic_sidecar_payload:
            payload["private_debug_payloads"]["public_semantic_sidecar"] = (
                public_semantic_sidecar_payload
            )
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    fts5 = payload["tracks"].get("fts5_source_line")
    source = payload["tracks"].get("source_evidence")
    fts5_top_k = int(payload["config"].get("fts5_top_k") or 0)
    source_top_k = int(payload["config"].get("source_top_k") or 0)
    print("AIppocampus source-evidence retrieval benchmark")
    print(f"- status: {payload['status']}")
    if fts5:
        print(f"- fts5 cases: {fts5['total_cases']}")
        print(
            f"- fts5 top-{fts5_top_k}: "
            f"{fts5['fts5'].get(f'hit_top{fts5_top_k}', 0)} hit / "
            f"{fts5['fts5'].get(f'miss_top{fts5_top_k}', 0)} miss "
            f"({fts5['fts5'].get(f'hit_rate_top{fts5_top_k}', 0.0):.2%})"
        )
        hybrid = fts5.get("production_hybrid")
        if hybrid:
            print(
                f"- production hybrid top-{fts5_top_k}: "
                f"{hybrid.get(f'hit_top{fts5_top_k}', 0)} hit / "
                f"{hybrid.get(f'miss_top{fts5_top_k}', 0)} miss "
                f"({hybrid.get(f'hit_rate_top{fts5_top_k}', 0.0):.2%})"
            )
    if source:
        print(
            f"- selected source evidence top-{source_top_k}: "
            f"{source['passed_count']} hit / {source['failed_count']} miss "
            f"({source['top_k_hit_rate']:.2%})"
        )
        selection_explanation = source.get("selection_explanation") or {}
        if selection_explanation:
            print(
                "- selected source evidence selection: "
                f"{selection_explanation.get('mode')} "
                f"selected={selection_explanation.get('selected_case_count')} "
                f"min={selection_explanation.get('min_cases')}"
            )
    sharegpt_public = payload["tracks"].get("sharegpt_public_source_evidence")
    if sharegpt_public:
        metrics = sharegpt_public.get("metrics") or {}
        top_k = int((sharegpt_public.get("config") or {}).get("top_k") or 0)
        print(
            f"- ShareGPT public source evidence top-{top_k}: "
            f"message {metrics.get(f'message_hit_rate_top{top_k}', 0.0):.2%}, "
            f"turn {metrics.get(f'turn_hit_rate_top{top_k}', 0.0):.2%}"
        )
    standard_public = payload["tracks"].get("standard_public_retrieval_qa")
    if standard_public:
        metrics = standard_public.get("metrics") or {}
        config = standard_public.get("config") or {}
        top_k = int(config.get("top_k") or 0)
        dataset = config.get("dataset") or "standard"
        print(
            f"- {dataset} retrieval-QA top-{top_k}: "
            f"session {metrics.get(f'session_hit_rate_top{top_k}', 0.0):.2%}, "
            f"evidence exact {metrics.get(f'evidence_hit_rate_top{top_k}', 0.0):.2%}, "
            f"context-visible {metrics.get(f'evidence_context_hit_rate_top{top_k}', 0.0):.2%}"
        )
        if int(metrics.get("line_reranker_attempted_count") or 0):
            print(
                f"  line reranker exact MRR "
                f"{metrics.get('reranked_evidence_mrr', 0.0):.4f}, "
                f"top-{top_k} {metrics.get(f'reranked_evidence_hit_rate_top{top_k}', 0.0):.2%}"
            )
    public_semantic = payload["tracks"].get("public_semantic_sidecar")
    if public_semantic:
        metrics = public_semantic.get("metrics") or {}
        artifacts = public_semantic.get("artifacts") or {}
        config = public_semantic.get("config") or {}
        print(
            f"- public semantic sidecar top-{int(config.get('top_k') or 0)}: "
            f"{metrics.get('passed_count', 0)} hit / {metrics.get('failed_count', 0)} miss "
            f"({metrics.get('top_k_hit_rate', 0.0):.2%}); "
            f"sidecar rows {artifacts.get('reviewed_sidecar_row_count', 0)}; "
            f"claim {public_semantic.get('claim_level') or 'unknown'}"
        )
    guidance = (payload.get("validation_guidance") or {}).get("track_b_source_evidence")
    if isinstance(guidance, dict):
        print(f"- validation hint: {guidance.get('problem')}")
        print(f"  portable smoke: {guidance.get('portable_smoke_command')}")


def positive_track_b_case_count(option_name: str) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            count = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{option_name} must be a positive integer"
            ) from exc
        if count <= 0:
            raise argparse.ArgumentTypeError(
                f"{option_name} must be a positive integer; 0 does not disable "
                "internal Track B arms. Use --only-standard-public for the "
                "external public retrieval-QA-only path."
            )
        return count

    return parse


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument(
        "--only-standard-public",
        action="store_true",
        help=(
            "Run only the standard public retrieval-QA adapter and report its "
            "status separately from the mixed Track B bundle."
        ),
    )
    parser.add_argument(
        "--fts5-cases",
        type=positive_track_b_case_count("--fts5-cases"),
        default=DEFAULT_FTS5_CASES,
    )
    parser.add_argument(
        "--fts5-min-cases",
        type=positive_track_b_case_count("--fts5-min-cases"),
        default=DEFAULT_FTS5_MIN_CASES,
    )
    parser.add_argument("--fts5-seed", type=int, default=fts5_benchmark.DEFAULT_SEED)
    parser.add_argument("--fts5-top-k", type=int, default=fts5_benchmark.DEFAULT_TOP_K)
    parser.add_argument(
        "--fts5-candidate-limit",
        type=int,
        default=fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument(
        "--source-max-cases",
        type=positive_track_b_case_count("--source-max-cases"),
        default=DEFAULT_SOURCE_MAX_CASES,
    )
    parser.add_argument(
        "--source-min-cases",
        type=positive_track_b_case_count("--source-min-cases"),
        default=DEFAULT_SOURCE_MIN_CASES,
    )
    parser.add_argument("--source-top-k", type=int, default=5)
    parser.add_argument("--source-min-hit-rate", type=float, default=DEFAULT_SOURCE_MIN_HIT_RATE)
    parser.add_argument(
        "--source-ranking",
        choices=["dynamic_source", "registry"],
        default="dynamic_source",
    )
    parser.add_argument("--source-max-term-frequency", type=int, default=8)
    parser.add_argument(
        "--allow-deterministic-labels",
        action="store_true",
        help=(
            "Use deterministic clean-source labels as a source-evidence wiring baseline; "
            "this cannot claim semantic-sidecar sample coverage."
        ),
    )
    parser.add_argument("--include-sharegpt-public", action="store_true")
    parser.add_argument("--sharegpt-public-corpus-dir", type=Path, default=None)
    parser.add_argument(
        "--sharegpt-public-conversations",
        type=int,
        default=DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    )
    parser.add_argument("--sharegpt-public-cases", type=int, default=DEFAULT_SHAREGPT_PUBLIC_CASES)
    parser.add_argument(
        "--sharegpt-public-min-cases",
        type=int,
        default=DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    )
    parser.add_argument("--sharegpt-public-top-k", type=int, default=DEFAULT_SHAREGPT_PUBLIC_TOP_K)
    parser.add_argument(
        "--sharegpt-public-sampling-mode",
        choices=["seeded-stratified", "first-n"],
        default="seeded-stratified",
        help="ShareGPT public sampling. Use first-n only for explicit smoke/debug runs.",
    )
    parser.add_argument(
        "--sharegpt-public-seed",
        type=int,
        default=sharegpt_sampling.DEFAULT_SHAREGPT_SAMPLE_SEED,
    )
    parser.add_argument("--include-standard-public", action="store_true")
    parser.add_argument(
        "--standard-dataset",
        choices=sorted(STANDARD_DATASET_PATHS),
        default=DEFAULT_STANDARD_DATASET,
    )
    parser.add_argument("--standard-corpus-path", type=Path, default=None)
    parser.add_argument("--standard-questions", type=int, default=DEFAULT_STANDARD_QA_CASES)
    parser.add_argument(
        "--standard-min-questions",
        type=int,
        default=DEFAULT_STANDARD_QA_MIN_CASES,
    )
    parser.add_argument("--standard-top-k", type=int, default=DEFAULT_STANDARD_QA_TOP_K)
    parser.add_argument(
        "--standard-context-radius",
        type=int,
        default=DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    )
    parser.add_argument(
        "--standard-min-session-hit-rate",
        type=float,
        default=DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    )
    parser.add_argument(
        "--standard-line-reranker",
        choices=sorted(STANDARD_LINE_RERANKER_MODES - {"custom"}),
        default=DEFAULT_STANDARD_LINE_RERANKER_MODE,
    )
    parser.add_argument(
        "--standard-line-reranker-top-sessions",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    )
    parser.add_argument(
        "--standard-line-reranker-max-candidates",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--standard-line-reranker-timeout",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    )
    parser.add_argument(
        "--standard-line-reranker-max-tokens",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    )
    parser.add_argument(
        "--standard-line-reranker-workers",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    )
    parser.add_argument("--include-public-semantic-sidecar", action="store_true")
    parser.add_argument("--public-semantic-corpus-dir", type=Path, default=None)
    parser.add_argument("--public-semantic-output-dir", type=Path, default=None)
    parser.add_argument(
        "--public-semantic-conversations",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    )
    parser.add_argument(
        "--public-semantic-max-messages",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    )
    parser.add_argument(
        "--public-semantic-max-candidates",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--public-semantic-cases",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    )
    parser.add_argument(
        "--public-semantic-min-cases",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    )
    parser.add_argument(
        "--public-semantic-top-k",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    )
    parser.add_argument(
        "--public-semantic-min-hit-rate",
        type=float,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    )
    parser.add_argument(
        "--public-semantic-min-confidence",
        type=float,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    )
    parser.add_argument(
        "--public-semantic-timeout",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    )
    parser.add_argument(
        "--public-semantic-max-tokens",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    )
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    payload = run_source_evidence_retrieval_benchmark(
        registry_path=args.registry,
        only_standard_public=args.only_standard_public,
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
        source_require_semantic_sidecar=not args.allow_deterministic_labels,
        source_max_term_frequency=args.source_max_term_frequency,
        include_private_text=args.include_private_text,
        include_sharegpt_public=args.include_sharegpt_public,
        sharegpt_public_corpus_dir=args.sharegpt_public_corpus_dir,
        sharegpt_public_conversations=args.sharegpt_public_conversations,
        sharegpt_public_max_cases=args.sharegpt_public_cases,
        sharegpt_public_min_cases=args.sharegpt_public_min_cases,
        sharegpt_public_top_k=args.sharegpt_public_top_k,
        sharegpt_public_sampling_mode=args.sharegpt_public_sampling_mode,
        sharegpt_public_seed=args.sharegpt_public_seed,
        include_standard_public=args.include_standard_public,
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
        include_public_semantic_sidecar=args.include_public_semantic_sidecar,
        public_semantic_corpus_dir=args.public_semantic_corpus_dir,
        public_semantic_output_dir=args.public_semantic_output_dir,
        public_semantic_conversations=args.public_semantic_conversations,
        public_semantic_max_messages=args.public_semantic_max_messages,
        public_semantic_max_candidates=args.public_semantic_max_candidates,
        public_semantic_max_cases=args.public_semantic_cases,
        public_semantic_min_cases=args.public_semantic_min_cases,
        public_semantic_top_k=args.public_semantic_top_k,
        public_semantic_min_hit_rate=args.public_semantic_min_hit_rate,
        public_semantic_min_confidence=args.public_semantic_min_confidence,
        public_semantic_timeout=args.public_semantic_timeout,
        public_semantic_max_tokens=args.public_semantic_max_tokens,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
