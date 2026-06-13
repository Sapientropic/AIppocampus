#!/usr/bin/env python3
"""LoCoMo text-QA answer and latency harness.

This runner keeps LoCoMo answer generation separate from the existing
retrieval-only control. It registers public LoCoMo conversations through the
standard source-backed retrieval adapter, then optionally asks a fixed reader to
answer from the bounded source lines that retrieval surfaced. Reports are
sanitized by default: raw dialogue, question, answer, local paths, and provider
responses stay out of the serialized benchmark payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import benchmark_locomo_answer_usefulness as answer_eval
import benchmark_locomo_public_users as locomo
import benchmark_source_evidence_retrieval as retrieval_benchmark
from benchmarks.aippocampus.shared import provider_execution_budget
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref
from source_evidence import standard_public

SCHEMA_VERSION = 1
READER_PROMPT_VERSION = "locomo-text-qa-fixed-reader-v1"
DETERMINISTIC_JUDGE_MODEL = "deterministic_locomo_text_qa_overlap_v1"
DEFAULT_READER_MODE = "dry-run"
DEFAULT_READER_API_KEY_ENV = "AIPPOCAMPUS_LOCOMO_READER_API_KEY"
DEFAULT_READER_MODEL = (
    os.environ.get("AIPPOCAMPUS_LOCOMO_READER_MODEL")
    or standard_public.DEFAULT_MODEL
)
DEFAULT_READER_BASE_URL = (
    os.environ.get("AIPPOCAMPUS_LOCOMO_READER_BASE_URL")
    or standard_public.DEFAULT_BASE_URL
)
DEFAULT_READER_TIMEOUT = 30
DEFAULT_READER_MAX_TOKENS = 512
DEFAULT_READER_CACHE_POLICY = "provider_prefix_cache_if_available"


@dataclass(frozen=True)
class ReaderConfig:
    mode: str
    provider: str
    model: str
    base_url: str
    api_key_env: str
    timeout: int
    max_tokens: int | None
    cache_policy: str
    input_cost_per_million: float | None
    output_cost_per_million: float | None


@dataclass(frozen=True)
class ReaderPrediction:
    attempted: bool
    status: str
    answer_text: str = ""
    abstained: bool = False
    citation_lines: tuple[int, ...] = ()
    confidence: float | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] | None = None
    cache: dict[str, Any] | None = None
    error_kind: str | None = None


def sha1_text(text: str) -> str:
    return standard_public.sha1_text(str(text))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "fixture": locomo.public_path_label(path),
            "expected": "download LoCoMo locomo10.json into benchmark_corpus/locomo/",
        }
    if not path.is_file():
        return {
            "ok": False,
            "status": "not_file",
            "fixture": locomo.public_path_label(path),
        }
    size_bytes = path.stat().st_size
    return {
        "ok": True,
        "status": "verified",
        "fixture": locomo.public_path_label(path),
        "fingerprint": {
            "sha256": sha256_file(path),
            "size_bytes": size_bytes,
        },
    }


def reader_provider(model: str, base_url: str) -> str:
    return standard_public.semantic_line_reranker_provider(
        model=model,
        base_url=base_url,
    )


def cache_contract(provider: str) -> str:
    return standard_public.semantic_line_reranker_cache_contract(provider)


def cache_metrics(usage: dict[str, Any], *, provider: str) -> dict[str, Any]:
    return standard_public.semantic_line_reranker_cache_metrics(
        usage,
        provider=provider,
    )


def reader_config_metadata(config: ReaderConfig) -> dict[str, Any]:
    return {
        "mode": config.mode,
        "prompt_version": READER_PROMPT_VERSION,
        "provider": config.provider,
        "model": config.model,
        "base_url_sha1": sha1_text(config.base_url)[:16],
        "api_key_env": config.api_key_env,
        "cache_policy": config.cache_policy,
        "cache_contract": cache_contract(config.provider),
        "timeout": int(config.timeout),
        "max_tokens": config.max_tokens,
        "temperature": 0.0,
        "live_provider_call": config.mode == "provider",
        "input_boundary": {
            "visible_to_model": [
                "question_text",
                "bounded_candidate_source_lines",
                "line_number",
                "role",
                "session_rank",
                "nearest_hit_rank",
                "context_distance",
            ],
            "withheld_from_model": [
                "gold_answer",
                "gold_evidence_ids",
                "expected_lines",
                "expected_sessions",
                "retrieval_labels",
                "judge_labels",
                "raw_report_cases",
            ],
        },
        "output_boundary": {
            "raw_answer_text_serialized": False,
            "raw_source_text_serialized": False,
            "citation_lines_serialized": True,
            "answer_text_sha1_serialized": True,
        },
    }


def benchmark_metadata(data_path: Path, verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": "locomo",
        "dataset_id": "locomo_public_longitudinal_users_v1",
        "role": "public long-conversation text QA diagnostic",
        "source": "https://github.com/snap-research/locomo",
        "license": "CC BY-NC 4.0 per upstream LoCoMo repository",
        "fixture": verification.get("fixture") or locomo.public_path_label(data_path),
        "verification": verification,
        "manifest": "benchmark_corpus/locomo_manifest.json",
        "runner": "benchmarks/aippocampus/benchmark_locomo_qa.py",
        "underlying_retrieval_adapter": (
            "benchmarks/aippocampus/source_evidence/standard_public.py"
        ),
    }


def evaluation_metadata(
    *,
    max_questions: int,
    min_questions: int,
    top_k: int,
    candidate_limit: int,
    context_radius: int,
    min_session_hit_rate: float,
    reader_top_sessions: int,
    reader_max_candidates: int,
    reader_config: ReaderConfig,
) -> dict[str, Any]:
    return {
        "mode": "locomo_text_qa_with_fixed_reader",
        "retrieval_metric_scope": "session, source-line, and source-window recall",
        "answer_metric_scope": "fixed-reader answer usefulness with local deterministic judge",
        "judge_model": DETERMINISTIC_JUDGE_MODEL,
        "official_locomo_judge": "not_run",
        "question_type_boundary": (
            "LoCoMo category values are preserved as dataset-provided category "
            "ids; this runner does not remap them to semantic labels."
        ),
        "max_questions": int(max_questions),
        "min_questions": int(min_questions),
        "top_k": int(top_k),
        "candidate_limit": int(candidate_limit),
        "context_radius": int(context_radius),
        "min_session_hit_rate": float(min_session_hit_rate),
        "reader_top_sessions": int(reader_top_sessions),
        "reader_max_candidates": int(reader_max_candidates),
        "reader": reader_config_metadata(reader_config),
    }


def privacy_boundary() -> dict[str, Any]:
    return {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "raw_dialogue_text_emitted": False,
        "raw_question_text_emitted": False,
        "raw_answer_text_emitted": False,
        "raw_source_text_emitted": False,
        "raw_model_response_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": True,
        "output_shape": "sanitized_locomo_text_qa_metrics",
    }


def cannot_claim(status: str) -> list[str]:
    claims = {
        "official_locomo_leaderboard_score",
        "official_locomo_judge_score",
        "multimodal_locomo_quality",
        "longmemeval_quality",
        "personamem_quality",
        "sota_or_external_baseline_superiority",
        "model_independent_memory_superiority",
        "private_real_history_quality",
        "default_reader_or_provider_adoption",
        "general_life_wide_memory_quality",
    }
    if status.startswith("skipped_") or status == "dry_run_schema_ready":
        claims.add("answer_generation_quality")
    return sorted(claims)


def locomo_case_id(source_id: str, qa_index: int, question: str) -> str:
    return sha1_text("\n".join(["locomo", source_id, f"{source_id}:{qa_index}", question]))[:16]


def load_gold_answer_map(
    *,
    corpus_path: Path,
    max_questions: int,
) -> dict[str, dict[str, Any]]:
    answers: dict[str, dict[str, Any]] = {}
    eligible_count = 0
    for sample in standard_public.iter_json_array_items(corpus_path):
        if eligible_count >= max_questions:
            break
        if not isinstance(sample, dict):
            continue
        source_id = str(sample.get("sample_id") or "locomo-sample")
        messages, dialogue_to_line, _line_to_session = standard_public.build_locomo_messages(sample)
        if not messages:
            continue
        for qa_index, qa in enumerate(sample.get("qa") or []):
            if eligible_count >= max_questions:
                break
            if not isinstance(qa, dict):
                continue
            question = str(qa.get("question") or "").strip()
            evidence_ids = [str(item) for item in qa.get("evidence") or []]
            expected_lines = [
                dialogue_to_line[item]
                for item in evidence_ids
                if item in dialogue_to_line
            ]
            if not question or not expected_lines:
                continue
            category = str(qa.get("category") or "unknown")
            case_id = locomo_case_id(source_id, qa_index, question)
            answers[case_id] = {
                "answer": str(qa.get("answer") or ""),
                "category": category,
                "evidence_id_count": len(set(evidence_ids)),
            }
            eligible_count += 1
    return answers


def build_content_hits(
    case: dict[str, Any],
    *,
    top_k: int,
    candidate_limit: int,
) -> list[dict[str, Any]]:
    content_terms = standard_public.standard_content_query_terms(str(case.get("query") or ""))
    if not content_terms or content_terms == list(case.get("query_terms") or []):
        return []
    hits, _warnings = retrieval_benchmark.fts5_benchmark.search_fts5_only(
        case["sqlite_path"],
        content_terms,
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    return hits


def build_reader_candidates(
    case: dict[str, Any],
    *,
    top_k: int,
    candidate_limit: int,
    context_radius: int,
    reader_top_sessions: int,
    reader_max_candidates: int,
) -> tuple[list[dict[str, Any]], float, int]:
    started = time.perf_counter()
    hits, warnings = retrieval_benchmark.fts5_benchmark.search_fts5_only(
        case["sqlite_path"],
        case["query_terms"],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    content_hits = build_content_hits(
        case,
        top_k=top_k,
        candidate_limit=candidate_limit,
    )
    expected = case.get("expected") or {}
    candidates = standard_public.build_standard_line_reranker_candidates(
        case["sqlite_path"],
        hits,
        extra_hit_lists=[("content", content_hits)] if content_hits else None,
        line_to_session={str(k): str(v) for k, v in (expected.get("line_to_session") or {}).items()},
        top_k=top_k,
        context_radius=context_radius,
        top_sessions=reader_top_sessions,
        max_candidates=reader_max_candidates,
    )
    return candidates, round((time.perf_counter() - started) * 1000, 2), len(warnings)


def reader_messages(question: str, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidate_rows = [
        {
            "line": int(candidate["line"]),
            "role": str(candidate.get("role") or ""),
            "session_rank": int(candidate.get("session_rank") or 0),
            "nearest_hit_rank": int(candidate.get("nearest_hit_rank") or 0),
            "context_distance": int(candidate.get("context_distance") or 0),
            "text": str(candidate.get("text") or ""),
        }
        for candidate in candidates
    ]
    payload = {
        "prompt_version": READER_PROMPT_VERSION,
        "question": question,
        "candidate_source_lines": candidate_rows,
        "output_schema": {
            "answer": "string; answer only from candidate_source_lines",
            "abstained": "boolean; true when evidence is insufficient",
            "citation_lines": "array of cited candidate line numbers",
            "confidence": "number between 0 and 1",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the fixed LoCoMo text-QA reader for AIppocampus. "
                "Use only the provided source lines. Return strict JSON. "
                "If the source lines do not support an answer, abstain."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def parse_citation_lines(value: Any) -> tuple[int, ...]:
    lines: list[int] = []
    for item in value or []:
        try:
            lines.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(set(lines)))


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "y",
        "abstain",
        "abstained",
    }


def provider_error_kind(exc: BaseException) -> str:
    text = str(exc).casefold()
    name = type(exc).__name__.lower()
    if "timeout" in name or "timeout" in text:
        return "provider_timeout"
    if "key" in text or "auth" in text:
        return "provider_auth_error"
    return "provider_error"


def run_reader(
    *,
    question: str,
    candidates: list[dict[str, Any]],
    config: ReaderConfig,
    api_key: str | None,
) -> ReaderPrediction:
    if config.mode == "dry-run":
        return ReaderPrediction(attempted=False, status="reader_not_run")
    if not api_key:
        return ReaderPrediction(
            attempted=False,
            status="skipped_missing_reader_key",
            error_kind="missing_reader_key",
        )
    started = time.perf_counter()
    try:
        response = standard_public.call_chat_json(
            reader_messages(question, candidates),
            api_key=api_key,
            model=config.model,
            base_url=config.base_url,
            max_tokens=config.max_tokens,
            timeout=float(config.timeout),
            temperature=0.0,
            service_name=(
                "DeepSeek LoCoMo reader API"
                if config.provider == "deepseek"
                else "OpenAI-compatible LoCoMo reader API"
            ),
            cache_contract=cache_contract(config.provider),
        )
        parsed = standard_public.parse_model_json(response)
        usage = standard_public.compact_usage(response.get("usage") or {})
        return ReaderPrediction(
            attempted=True,
            status="answered",
            answer_text=str(parsed.get("answer") or ""),
            abstained=bool_value(parsed.get("abstained")),
            citation_lines=parse_citation_lines(parsed.get("citation_lines")),
            confidence=standard_public.clamp_confidence(parsed.get("confidence")),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            usage=usage,
            cache=cache_metrics(usage, provider=config.provider),
        )
    except Exception as exc:  # pragma: no cover - live provider failures vary
        return ReaderPrediction(
            attempted=True,
            status="reader_error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error_kind=provider_error_kind(exc),
        )


def classify_failure(
    *,
    retrieval_row: dict[str, Any],
    prediction: ReaderPrediction,
    quality: dict[str, Any],
    context_sufficient: bool,
    answer_correct: bool,
    top_k: int,
) -> str:
    if answer_correct:
        return "answered_correctly"
    if not prediction.attempted:
        return prediction.status
    if not context_sufficient:
        return "retrieval_miss"
    if prediction.abstained or not prediction.answer_text.strip():
        return "abstention_unanswerable_boundary"
    if "temporal" in str(retrieval_row.get("case_type") or "").casefold():
        return "temporal_confusion"
    if float(quality.get("token_overlap_rate") or 0.0) >= 0.45:
        return "evaluation_mismatch"
    if retrieval_row.get(f"evidence_context_hit_top{top_k}"):
        return "evidence_visible_reader_miss"
    return "retrieval_miss"


def score_answer_case(
    *,
    case: dict[str, Any],
    retrieval_row: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_latency_ms: float,
    candidate_warning_count: int,
    gold: dict[str, Any],
    prediction: ReaderPrediction,
    top_k: int,
) -> dict[str, Any]:
    gold_answer = str(gold.get("answer") or "")
    quality = answer_eval.answer_quality(prediction.answer_text, gold_answer)
    has_line_evidence = bool(retrieval_row.get("has_line_evidence"))
    context_sufficient = bool(
        retrieval_row.get(f"evidence_context_hit_top{top_k}")
        if has_line_evidence
        else retrieval_row.get(f"session_hit_top{top_k}")
    )
    answer_correct = bool(
        prediction.attempted
        and context_sufficient
        and not prediction.abstained
        and quality["strong_match"]
        and not quality["negation_trap"]
    )
    candidate_lines = {int(candidate["line"]) for candidate in candidates}
    expected_lines = {int(line) for line in case.get("expected", {}).get("lines") or []}
    cited_candidate_lines = sorted(set(prediction.citation_lines) & candidate_lines)
    cited_expected_lines = sorted(set(prediction.citation_lines) & expected_lines)
    correct_source_citation = bool(expected_lines and expected_lines.issubset(set(cited_candidate_lines)))
    failure_category = classify_failure(
        retrieval_row=retrieval_row,
        prediction=prediction,
        quality=quality,
        context_sufficient=context_sufficient,
        answer_correct=answer_correct,
        top_k=top_k,
    )
    return {
        "case_id": case["case_id"],
        "case_type": retrieval_row["case_type"],
        "question_type": retrieval_row["case_type"],
        "question_type_source": "locomo_dataset_category_id",
        "source_id_sha1": retrieval_row["source_id_sha1"],
        "question_id_sha1": retrieval_row["question_id_sha1"],
        "query_sha1": retrieval_row["query_sha1"],
        "answer_sha1": sha1_text(gold_answer)[:16] if gold_answer else None,
        "gold_evidence_id_count": int(gold.get("evidence_id_count") or 0),
        "retrieval": {
            "session_rank": retrieval_row.get("session_rank"),
            "evidence_rank": retrieval_row.get("evidence_rank"),
            "evidence_context_rank": retrieval_row.get("evidence_context_rank"),
            f"session_hit_top{top_k}": bool(retrieval_row.get(f"session_hit_top{top_k}")),
            f"evidence_hit_top{top_k}": bool(retrieval_row.get(f"evidence_hit_top{top_k}")),
            f"evidence_context_hit_top{top_k}": bool(
                retrieval_row.get(f"evidence_context_hit_top{top_k}")
            ),
            "evidence_miss_category": retrieval_row.get("evidence_miss_category"),
            "candidate_count": len(candidates),
            "candidate_contains_evidence": bool(expected_lines & candidate_lines),
            "candidate_latency_ms": candidate_latency_ms,
            "warning_count": int(retrieval_row.get("warning_count") or 0)
            + int(candidate_warning_count),
        },
        "reader": {
            "attempted": prediction.attempted,
            "status": prediction.status,
            "abstained": prediction.abstained,
            "confidence": prediction.confidence,
            "latency_ms": prediction.latency_ms,
            "usage": prediction.usage or {},
            "cache": prediction.cache or {},
            "answer_text_sha1": sha1_text(prediction.answer_text)[:16]
            if prediction.answer_text
            else None,
            "citation_line_count": len(prediction.citation_lines),
            "cited_candidate_line_count": len(cited_candidate_lines),
            "cited_expected_line_count": len(cited_expected_lines),
            "invalid_citation_line_count": len(set(prediction.citation_lines) - candidate_lines),
            "error_kind": prediction.error_kind,
        },
        "answer": {
            "context_sufficient": context_sufficient,
            "answer_quality": quality,
            "answer_correct": answer_correct,
            "correct_source_citation": correct_source_citation,
            "failure_category": failure_category,
        },
    }


def summarize_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    for row in rows:
        standard_public.add_usage(usage, row.get("reader", {}).get("usage") or {})
    return usage


def summarize_reader_latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["reader"]["latency_ms"])
        for row in rows
        if isinstance(row.get("reader", {}).get("latency_ms"), int | float)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
    }


def summarize_candidate_latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["retrieval"]["candidate_latency_ms"])
        for row in rows
        if isinstance(row.get("retrieval", {}).get("candidate_latency_ms"), int | float)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
    }


def summarize_cache(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hit_tokens = 0
    miss_tokens = 0
    available_count = 0
    kind_counts: dict[str, int] = {}
    for row in rows:
        cache = row.get("reader", {}).get("cache") or {}
        if not cache:
            continue
        kind = str(cache.get("kind") or "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if cache.get("available"):
            available_count += 1
        hit_tokens += int(cache.get("hit_tokens") or 0)
        miss_tokens += int(cache.get("miss_tokens") or 0)
    total = hit_tokens + miss_tokens
    return {
        "available_count": available_count,
        "kind_counts": kind_counts,
        "hit_tokens": hit_tokens,
        "miss_tokens": miss_tokens,
        "hit_rate": round(hit_tokens / total, 4) if total else 0.0,
    }


def summarize_answer_cases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    attempted = sum(1 for row in rows if row.get("reader", {}).get("attempted"))
    abstained = sum(1 for row in rows if row.get("reader", {}).get("abstained"))
    context_sufficient = sum(
        1 for row in rows if row.get("answer", {}).get("context_sufficient")
    )
    correct = sum(1 for row in rows if row.get("answer", {}).get("answer_correct"))
    cited = sum(1 for row in rows if row.get("answer", {}).get("correct_source_citation"))
    taxonomy_counts: dict[str, int] = {}
    by_question_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = str(row.get("answer", {}).get("failure_category") or "unknown")
        taxonomy_counts[category] = taxonomy_counts.get(category, 0) + 1
        question_type = str(row.get("question_type") or "unknown")
        bucket = by_question_type.setdefault(
            question_type,
            {
                "case_count": 0,
                "reader_attempted_count": 0,
                "context_sufficient_count": 0,
                "answer_correct_count": 0,
                "correct_source_citation_count": 0,
            },
        )
        bucket["case_count"] += 1
        bucket["reader_attempted_count"] += int(bool(row.get("reader", {}).get("attempted")))
        bucket["context_sufficient_count"] += int(
            bool(row.get("answer", {}).get("context_sufficient"))
        )
        bucket["answer_correct_count"] += int(
            bool(row.get("answer", {}).get("answer_correct"))
        )
        bucket["correct_source_citation_count"] += int(
            bool(row.get("answer", {}).get("correct_source_citation"))
        )
    for bucket in by_question_type.values():
        bucket["answer_correct_rate"] = locomo.safe_rate(
            bucket["answer_correct_count"],
            bucket["case_count"],
        )
        bucket["context_sufficient_rate"] = locomo.safe_rate(
            bucket["context_sufficient_count"],
            bucket["case_count"],
        )
    return {
        "case_count": total,
        "reader_attempted_count": attempted,
        "reader_not_run_count": total - attempted,
        "context_sufficient_count": context_sufficient,
        "context_sufficient_rate": locomo.safe_rate(context_sufficient, total),
        "answer_correct_count": correct,
        "answer_correct_rate": locomo.safe_rate(correct, total),
        "correct_source_citation_count": cited,
        "correct_source_citation_rate": locomo.safe_rate(cited, total),
        "abstention_count": abstained,
        "abstention_rate": locomo.safe_rate(abstained, attempted),
        "failure_taxonomy_counts": taxonomy_counts,
        "by_question_type": dict(sorted(by_question_type.items())),
    }


def estimate_cost(
    usage: dict[str, Any],
    *,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> dict[str, Any]:
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    if input_cost_per_million is None or output_cost_per_million is None:
        return {
            "status": "not_estimated_without_price_table",
            "estimated_usd": None,
            "tracked_fields": ["usage", "latency", "cache"],
        }
    estimate = (
        (prompt_tokens / 1_000_000.0) * float(input_cost_per_million)
        + (completion_tokens / 1_000_000.0) * float(output_cost_per_million)
    )
    return {
        "status": "estimated_from_user_supplied_token_prices",
        "estimated_usd": round(estimate, 6),
        "input_cost_per_million": float(input_cost_per_million),
        "output_cost_per_million": float(output_cost_per_million),
    }


def forbidden_local_path_matches(text: str) -> list[str]:
    patterns = [
        r"[A-Za-z]:\\[^\s\"']+",
        r"/(?:Users|home|tmp|var|mnt)/[^\s\"']+",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    return matches


def credential_like_matches(text: str) -> list[str]:
    patterns = [
        r"sk-[A-Za-z0-9_-]{20,}",
        r"(?:api|token|secret)[-_]?[A-Za-z0-9]{24,}",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return matches


def validate_sanitized_report(
    payload: dict[str, Any],
    *,
    forbidden_texts: list[str] | None = None,
) -> dict[str, Any]:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    errors: list[dict[str, Any]] = []
    path_matches = forbidden_local_path_matches(dumped)
    if path_matches:
        errors.append(
            {
                "kind": "absolute_path_leak",
                "count": len(path_matches),
                "examples_sha1": [sha1_text(item)[:12] for item in path_matches[:3]],
            }
        )
    credential_matches = credential_like_matches(dumped)
    if credential_matches:
        errors.append(
            {
                "kind": "credential_like_string",
                "count": len(credential_matches),
                "examples_sha1": [
                    sha1_text(item)[:12] for item in credential_matches[:3]
                ],
            }
        )
    leaked_texts = [
        text
        for text in forbidden_texts or []
        if text and len(text) >= 6 and text in dumped
    ]
    if leaked_texts:
        errors.append(
            {
                "kind": "raw_text_leak",
                "count": len(leaked_texts),
                "examples_sha1": [sha1_text(item)[:12] for item in leaked_texts[:3]],
            }
        )
    return {
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "checks": [
            "absolute_path_leak",
            "credential_like_string",
            "raw_question_answer_or_source_text_leak",
        ],
    }


def skipped_payload(
    *,
    data_path: Path,
    reason: str,
    verification: dict[str, Any],
    started: float,
    max_questions: int,
    min_questions: int,
    top_k: int,
    candidate_limit: int,
    context_radius: int,
    min_session_hit_rate: float,
    reader_top_sessions: int,
    reader_max_candidates: int,
    reader_config: ReaderConfig,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_text_qa_benchmark",
        "generated_at": locomo.now_utc(),
        "status": reason,
        "ok": True,
        "report_generation_ok": True,
        "benchmark": benchmark_metadata(data_path, verification),
        "evaluation": evaluation_metadata(
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            reader_top_sessions=reader_top_sessions,
            reader_max_candidates=reader_max_candidates,
            reader_config=reader_config,
        ),
        "retrieval": {"metrics": {"question_count": 0}},
        "answer": {"metrics": {"case_count": 0, "reader_attempted_count": 0}},
        "latency": {"retrieval_ms": {"count": 0}, "reader_ms": {"count": 0}},
        "token_usage": {},
        "reader_cache": summarize_cache([]),
        "cost": estimate_cost(
            {},
            input_cost_per_million=reader_config.input_cost_per_million,
            output_cost_per_million=reader_config.output_cost_per_million,
        ),
        "cases": [],
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": cannot_claim(reason),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    validation = validate_sanitized_report(payload)
    payload["sanitized_report_validation"] = validation
    payload["report_generation_ok"] = validation["ok"]
    payload["ok"] = bool(payload["ok"] and validation["ok"])
    return payload


def write_json_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def reader_provider_budget_config(
    *,
    live_mode: bool,
    max_questions: int,
    reader_config: ReaderConfig,
    max_provider_calls: int | None,
    max_provider_prompt_tokens: int | None,
    max_provider_completion_tokens: int | None,
    max_provider_total_tokens: int | None,
    max_provider_estimated_cost_usd: float | None,
    provider_cost_unknown: bool,
    provider_budget_checkpoint: Path | str | None,
    partial_output: Path | str | None,
) -> provider_execution_budget.ProviderExecutionBudget:
    return provider_execution_budget.build_provider_execution_budget(
        benchmark_id="locomo_text_qa_fixed_reader",
        live_mode=live_mode,
        max_units=max_questions,
        per_case_timeout_seconds=reader_config.timeout,
        max_provider_calls=max_provider_calls,
        max_prompt_tokens=max_provider_prompt_tokens,
        max_completion_tokens=max_provider_completion_tokens,
        max_total_tokens=max_provider_total_tokens,
        max_estimated_cost_usd=max_provider_estimated_cost_usd,
        cost_unknown=provider_cost_unknown,
        checkpoint_path=provider_budget_checkpoint,
        partial_output_path=partial_output,
        provider=reader_config.provider,
        model=reader_config.model,
        base_url=reader_config.base_url,
    )


def provider_failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    failures = [
        row.get("reader", {})
        for row in rows
        if row.get("reader", {}).get("attempted")
        and row.get("reader", {}).get("error_kind")
    ]
    return {
        "failed_units": len(failures),
        "timed_out_units": sum(
            1 for row in failures if row.get("error_kind") == "provider_timeout"
        ),
    }


def provider_budget_summary_for_rows(
    config: provider_execution_budget.ProviderExecutionBudget,
    *,
    rows: list[dict[str, Any]],
    usage: dict[str, Any],
    cache_usage: dict[str, Any],
    cost: dict[str, Any],
    elapsed_ms: float,
    stop_reason: str,
) -> dict[str, Any]:
    failures = provider_failure_counts(rows)
    estimated_cost = cost.get("estimated_usd")
    return provider_execution_budget.provider_execution_budget_summary(
        config,
        completed_units=sum(1 for row in rows if row.get("reader", {}).get("attempted")),
        failed_units=failures["failed_units"],
        timed_out_units=failures["timed_out_units"],
        elapsed_ms=elapsed_ms,
        usage=usage,
        cache_usage=cache_usage,
        estimated_cost_usd=estimated_cost
        if isinstance(estimated_cost, int | float)
        else None,
        cost_unavailable_reason=(
            "provider_reader_cost_estimated_from_user_prices"
            if isinstance(estimated_cost, int | float)
            else "provider_reader_cost_not_estimated_without_price_table"
        ),
        stop_reason=stop_reason,
        validation_errors=[],
    )


def attach_budget_and_validate(
    payload: dict[str, Any],
    budget_summary: dict[str, Any],
) -> None:
    payload["provider_execution_budget"] = budget_summary
    validation = validate_sanitized_report(payload)
    payload["sanitized_report_validation"] = validation
    payload["report_generation_ok"] = validation["ok"]
    payload["ok"] = bool(payload["ok"] and validation["ok"])


def run_locomo_qa_benchmark(
    *,
    dataset_path: Path | str = locomo.DEFAULT_DATASET,
    max_questions: int = standard_public.DEFAULT_STANDARD_QA_CASES,
    min_questions: int = standard_public.DEFAULT_STANDARD_QA_MIN_CASES,
    top_k: int = standard_public.DEFAULT_STANDARD_QA_TOP_K,
    candidate_limit: int = retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    context_radius: int = standard_public.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    min_session_hit_rate: float = standard_public.DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    reader_mode: str = DEFAULT_READER_MODE,
    reader_model: str = DEFAULT_READER_MODEL,
    reader_base_url: str = DEFAULT_READER_BASE_URL,
    reader_api_key_env: str = DEFAULT_READER_API_KEY_ENV,
    reader_timeout: int = DEFAULT_READER_TIMEOUT,
    reader_max_tokens: int = DEFAULT_READER_MAX_TOKENS,
    reader_cache_policy: str = DEFAULT_READER_CACHE_POLICY,
    reader_top_sessions: int = standard_public.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    reader_max_candidates: int = standard_public.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    reader_input_cost_per_million: float | None = None,
    reader_output_cost_per_million: float | None = None,
    partial_output: Path | str | None = None,
    provider_budget_checkpoint: Path | str | None = None,
    max_provider_calls: int | None = None,
    max_provider_prompt_tokens: int | None = None,
    max_provider_completion_tokens: int | None = None,
    max_provider_total_tokens: int | None = None,
    max_provider_estimated_cost_usd: float | None = None,
    provider_cost_unknown: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    data_path = Path(dataset_path).resolve()
    partial_path = Path(partial_output).resolve() if partial_output else None
    checkpoint_path = (
        Path(provider_budget_checkpoint).resolve()
        if provider_budget_checkpoint
        else None
    )
    verification = verify_dataset_file(data_path)
    resolved_reader_mode = reader_mode.strip().casefold()
    if resolved_reader_mode not in {"dry-run", "provider"}:
        raise ValueError(f"unsupported reader mode: {reader_mode}")
    provider = reader_provider(reader_model, reader_base_url)
    reader_config = ReaderConfig(
        mode=resolved_reader_mode,
        provider=provider,
        model=reader_model,
        base_url=reader_base_url,
        api_key_env=reader_api_key_env,
        timeout=int(reader_timeout),
        max_tokens=None if int(reader_max_tokens) <= 0 else int(reader_max_tokens),
        cache_policy=reader_cache_policy,
        input_cost_per_million=reader_input_cost_per_million,
        output_cost_per_million=reader_output_cost_per_million,
    )
    if not verification["ok"]:
        reason = (
            "skipped_missing_dataset"
            if verification.get("status") == "missing"
            else "skipped_dataset_verification_failed"
        )
        payload = skipped_payload(
            data_path=data_path,
            reason=reason,
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            reader_top_sessions=reader_top_sessions,
            reader_max_candidates=reader_max_candidates,
            reader_config=reader_config,
        )
        if partial_path is not None:
            write_json_payload(partial_path, payload)
        return payload
    live_provider_mode = resolved_reader_mode == "provider"
    provider_budget = reader_provider_budget_config(
        live_mode=live_provider_mode,
        max_questions=max_questions,
        reader_config=reader_config,
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
            data_path=data_path,
            reason="skipped_provider_budget_not_declared",
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            reader_top_sessions=reader_top_sessions,
            reader_max_candidates=reader_max_candidates,
            reader_config=reader_config,
        )
        payload["ok"] = False
        budget_summary = provider_execution_budget.provider_execution_budget_summary(
            provider_budget,
            stop_reason="provider_budget_preflight_failed",
            validation_errors=budget_errors,
        )
        attach_budget_and_validate(payload, budget_summary)
        if checkpoint_path is not None:
            provider_execution_budget.write_provider_budget_checkpoint(
                checkpoint_path,
                budget_summary,
            )
        if partial_path is not None:
            write_json_payload(partial_path, payload)
        return payload
    api_key = os.environ.get(reader_api_key_env)
    if resolved_reader_mode == "provider" and not api_key:
        payload = skipped_payload(
            data_path=data_path,
            reason="skipped_missing_reader_key",
            verification=verification,
            started=started,
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            reader_top_sessions=reader_top_sessions,
            reader_max_candidates=reader_max_candidates,
            reader_config=reader_config,
        )
        budget_summary = provider_execution_budget.provider_execution_budget_summary(
            provider_budget,
            stop_reason="provider_key_missing_before_start",
            validation_errors=[],
        )
        attach_budget_and_validate(payload, budget_summary)
        if checkpoint_path is not None:
            provider_execution_budget.write_provider_budget_checkpoint(
                checkpoint_path,
                budget_summary,
            )
        if partial_path is not None:
            write_json_payload(partial_path, payload)
        return payload

    gold_by_case = load_gold_answer_map(
        corpus_path=data_path,
        max_questions=max_questions,
    )
    forbidden_texts: list[str] = []
    rows: list[dict[str, Any]] = []
    retrieval_rows: list[dict[str, Any]] = []
    corpus: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="aippocampus-locomo-qa-") as tmp:
        cases, corpus = standard_public.build_locomo_standard_cases(
            Path(tmp),
            corpus_path=data_path,
            max_questions=max_questions,
        )
        for case in cases:
            retrieval_row = standard_public.evaluate_standard_retrieval_case(
                case,
                top_k=top_k,
                candidate_limit=candidate_limit,
                context_radius=context_radius,
                include_private_text=False,
                line_reranker_mode="off",
            )
            candidates, candidate_latency_ms, candidate_warning_count = build_reader_candidates(
                case,
                top_k=top_k,
                candidate_limit=candidate_limit,
                context_radius=context_radius,
                reader_top_sessions=reader_top_sessions,
                reader_max_candidates=reader_max_candidates,
            )
            prediction = run_reader(
                question=str(case.get("query") or ""),
                candidates=candidates,
                config=reader_config,
                api_key=api_key,
            )
            gold = gold_by_case.get(case["case_id"]) or {"answer": ""}
            forbidden_texts.extend(
                [
                    str(case.get("query") or ""),
                    str(gold.get("answer") or ""),
                    *[str(candidate.get("text") or "") for candidate in candidates],
                ]
            )
            retrieval_rows.append(retrieval_row)
            rows.append(
                score_answer_case(
                    case=case,
                    retrieval_row=retrieval_row,
                    candidates=candidates,
                    candidate_latency_ms=candidate_latency_ms,
                    candidate_warning_count=candidate_warning_count,
                    gold=gold,
                    prediction=prediction,
                    top_k=top_k,
                )
            )

    retrieval_metrics = standard_public.summarize_standard_retrieval_results(
        retrieval_rows,
        top_k=top_k,
        context_radius=context_radius,
    )
    retrieval_status = standard_public.standard_retrieval_status(
        retrieval_metrics,
        min_questions=min_questions,
        top_k=top_k,
        min_session_hit_rate=min_session_hit_rate,
    )
    answer_metrics = summarize_answer_cases(rows)
    usage = summarize_usage(rows)
    reader_cache = summarize_cache(rows)
    cost = estimate_cost(
        usage,
        input_cost_per_million=reader_config.input_cost_per_million,
        output_cost_per_million=reader_config.output_cost_per_million,
    )
    status = (
        "dry_run_schema_ready"
        if resolved_reader_mode == "dry-run"
        else "answer_scored"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_text_qa_benchmark",
        "generated_at": locomo.now_utc(),
        "status": status,
        "ok": True,
        "report_generation_ok": True,
        "quality_gate_status": "not_a_gate",
        "benchmark": benchmark_metadata(data_path, verification),
        "evaluation": evaluation_metadata(
            max_questions=max_questions,
            min_questions=min_questions,
            top_k=top_k,
            candidate_limit=candidate_limit,
            context_radius=context_radius,
            min_session_hit_rate=min_session_hit_rate,
            reader_top_sessions=reader_top_sessions,
            reader_max_candidates=reader_max_candidates,
            reader_config=reader_config,
        ),
        "retrieval": {
            "status": retrieval_status,
            "metrics": retrieval_metrics,
            "corpus": corpus,
        },
        "answer": {
            "status": "not_run" if resolved_reader_mode == "dry-run" else "scored",
            "metrics": answer_metrics,
        },
        "latency": {
            "retrieval_ms": summarize_candidate_latency(rows),
            "reader_ms": summarize_reader_latency(rows),
            "total_elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        },
        "token_usage": usage,
        "reader_cache": reader_cache,
        "cost": cost,
        "cases": rows,
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": cannot_claim(status),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if live_provider_mode:
        budget_summary = provider_budget_summary_for_rows(
            provider_budget,
            rows=rows,
            usage=usage,
            cache_usage=reader_cache,
            cost=cost,
            elapsed_ms=float(payload["elapsed_ms"]),
            stop_reason=status,
        )
        payload["provider_execution_budget"] = budget_summary
        if checkpoint_path is not None:
            provider_execution_budget.write_provider_budget_checkpoint(
                checkpoint_path,
                budget_summary,
            )
    validation = validate_sanitized_report(payload, forbidden_texts=forbidden_texts)
    payload["sanitized_report_validation"] = validation
    payload["report_generation_ok"] = validation["ok"]
    payload["ok"] = bool(validation["ok"])
    if not validation["ok"]:
        payload["status"] = "sanitized_report_validation_failed"
    if partial_path is not None:
        write_json_payload(partial_path, payload)
    return payload


CLI_STDOUT_BOUNDARY = {
    "kind": "aippocampus_locomo_text_qa_cli",
    "stdout_boundary": "static_only",
    "full_report": "use --output for the sanitized JSON report",
}


def print_human_summary() -> None:
    print("AIppocampus LoCoMo text-QA benchmark")
    print("- stdout: static boundary only")
    print("- full report: use --output for sanitized JSON")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=locomo.DEFAULT_DATASET)
    parser.add_argument("--questions", type=int, default=standard_public.DEFAULT_STANDARD_QA_CASES)
    parser.add_argument("--min-questions", type=int, default=standard_public.DEFAULT_STANDARD_QA_MIN_CASES)
    parser.add_argument("--top-k", type=int, default=standard_public.DEFAULT_STANDARD_QA_TOP_K)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=retrieval_benchmark.fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument(
        "--context-radius",
        type=int,
        default=standard_public.DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    )
    parser.add_argument(
        "--min-session-hit-rate",
        type=float,
        default=standard_public.DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    )
    parser.add_argument("--reader-mode", choices=["dry-run", "provider"], default=DEFAULT_READER_MODE)
    parser.add_argument("--reader-model", default=DEFAULT_READER_MODEL)
    parser.add_argument("--reader-base-url", default=DEFAULT_READER_BASE_URL)
    parser.add_argument("--reader-api-key-env", default=DEFAULT_READER_API_KEY_ENV)
    parser.add_argument("--reader-timeout", type=int, default=DEFAULT_READER_TIMEOUT)
    parser.add_argument("--reader-max-tokens", type=int, default=DEFAULT_READER_MAX_TOKENS)
    parser.add_argument("--reader-cache-policy", default=DEFAULT_READER_CACHE_POLICY)
    parser.add_argument(
        "--reader-top-sessions",
        type=int,
        default=standard_public.DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    )
    parser.add_argument(
        "--reader-max-candidates",
        type=int,
        default=standard_public.DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    )
    parser.add_argument("--reader-input-cost-per-million", type=float, default=None)
    parser.add_argument("--reader-output-cost-per-million", type=float, default=None)
    parser.add_argument("--partial-output", type=Path, default=None)
    parser.add_argument("--provider-budget-checkpoint", type=Path, default=None)
    parser.add_argument("--max-provider-calls", type=int, default=None)
    parser.add_argument("--max-provider-prompt-tokens", type=int, default=None)
    parser.add_argument("--max-provider-completion-tokens", type=int, default=None)
    parser.add_argument("--max-provider-total-tokens", type=int, default=None)
    parser.add_argument("--max-provider-estimated-cost-usd", type=float, default=None)
    parser.add_argument("--provider-cost-unknown", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_locomo_qa_benchmark(
        dataset_path=args.dataset,
        max_questions=args.questions,
        min_questions=args.min_questions,
        top_k=args.top_k,
        candidate_limit=args.candidate_limit,
        context_radius=args.context_radius,
        min_session_hit_rate=args.min_session_hit_rate,
        reader_mode=args.reader_mode,
        reader_model=args.reader_model,
        reader_base_url=args.reader_base_url,
        reader_api_key_env=args.reader_api_key_env,
        reader_timeout=args.reader_timeout,
        reader_max_tokens=args.reader_max_tokens,
        reader_cache_policy=args.reader_cache_policy,
        reader_top_sessions=args.reader_top_sessions,
        reader_max_candidates=args.reader_max_candidates,
        reader_input_cost_per_million=args.reader_input_cost_per_million,
        reader_output_cost_per_million=args.reader_output_cost_per_million,
        partial_output=args.partial_output,
        provider_budget_checkpoint=args.provider_budget_checkpoint,
        max_provider_calls=args.max_provider_calls,
        max_provider_prompt_tokens=args.max_provider_prompt_tokens,
        max_provider_completion_tokens=args.max_provider_completion_tokens,
        max_provider_total_tokens=args.max_provider_total_tokens,
        max_provider_estimated_cost_usd=args.max_provider_estimated_cost_usd,
        provider_cost_unknown=args.provider_cost_unknown,
    )
    if args.output:
        write_json_payload(args.output, payload)
    if args.json_output:
        print(json.dumps(CLI_STDOUT_BOUNDARY, ensure_ascii=False, indent=2))
    else:
        print_human_summary()
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
