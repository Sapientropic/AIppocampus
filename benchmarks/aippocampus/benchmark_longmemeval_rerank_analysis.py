#!/usr/bin/env python3
"""Sanitized analysis for LongMemEval-S line-reranker reports.

This postprocessor is the #1092/#1193 decision layer over generated
LongMemEval rerank JSON. It does not rerun the benchmark or publish raw case
text. It recomputes richer ladder/taxonomy fields from already-sanitized case
rows, can compare a deterministic repair against a lexical baseline, and keeps
the semantic cache/product-path boundary explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1
DEFAULT_FULL_RUN_QUESTIONS = 500
RERANK_LADDER_KS = (1, 3, 5, 10, 20, 50)
SEMANTIC_CACHE_KEY_FIELDS = [
    "query_hash",
    "candidate_window_or_span_hashes",
    "reranker_prompt_version",
    "model_provider_id",
    "source_or_dataset_fingerprint",
    "policy_version",
]


def _load_report(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected object LongMemEval report")
    return payload


def _file_sha1(path: Path | str) -> str:
    digest = hashlib.sha1()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _as_cases(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [case for case in report.get("cases") or [] if isinstance(case, Mapping)]


def _rank(value: Any) -> int | None:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def _rank_bucket(rank: int | None) -> str:
    if rank is None:
        return "not_retrieved"
    if rank == 1:
        return "rank_1"
    if rank <= 3:
        return "rank_2_3"
    if rank <= 5:
        return "rank_4_5"
    if rank <= 10:
        return "rank_6_10"
    if rank <= 20:
        return "rank_11_20"
    if rank <= 50:
        return "rank_21_50"
    return "rank_below_50"


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def _recall_by_k(cases: Sequence[Mapping[str, Any]], rank_key: str) -> dict[str, Any]:
    denominator = len(cases)
    return {
        f"r_at_{k}": _rate(
            sum(1 for case in cases if (rank := _rank(case.get(rank_key))) and rank <= k),
            denominator,
        )
        for k in RERANK_LADDER_KS
    }


def _mrr(cases: Sequence[Mapping[str, Any]], rank_key: str) -> float:
    if not cases:
        return 0.0
    total = 0.0
    for case in cases:
        rank = _rank(case.get(rank_key))
        if rank:
            total += 1.0 / rank
    return round(total / len(cases), 4)


def _case_type_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case.get("case_type") or "unknown")].append(case)
    by_type: dict[str, Any] = {}
    for case_type, rows in sorted(grouped.items()):
        baseline_hit_top10 = sum(
            1
            for row in rows
            if (rank := _rank(row.get("evidence_rank"))) is not None and rank <= 10
        )
        reranked_hit_top10 = sum(
            1
            for row in rows
            if (rank := _rank(row.get("reranked_evidence_rank"))) is not None
            and rank <= 10
        )
        by_type[case_type] = {
            "case_count": len(rows),
            "baseline_evidence_hit_top10": baseline_hit_top10,
            "baseline_evidence_hit_rate_top10": _rate(baseline_hit_top10, len(rows))["rate"],
            "reranked_evidence_hit_top10": reranked_hit_top10,
            "reranked_evidence_hit_rate_top10": _rate(reranked_hit_top10, len(rows))["rate"],
            "reranked_evidence_mrr": _mrr(rows, "reranked_evidence_rank"),
            "semantic_bridge_lift_top10": sum(
                1 for row in rows if row.get("semantic_bridge_lift_top10")
            ),
            "rerank_regression_count_top10": _regression_count(rows, top_k=10),
            "line_reranker_error_count": sum(
                len(list(row.get("line_reranker_error_kinds") or [])) for row in rows
            ),
        }
    return by_type


def _miss_taxonomy_metrics(
    cases: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        category = str(case.get("evidence_miss_category") or "unknown")
        grouped[category].append(case)
    by_category: dict[str, Any] = {}
    for category, rows in sorted(grouped.items()):
        baseline_hits = sum(
            1
            for row in rows
            if (rank := _rank(row.get("evidence_rank"))) and rank <= top_k
        )
        reranked_hits = sum(
            1
            for row in rows
            if (rank := _rank(row.get("reranked_evidence_rank"))) and rank <= top_k
        )
        context_rescues = [row for row in rows if row.get(f"evidence_context_rescue_top{top_k}")]
        context_rescue_conversions = sum(
            1
            for row in context_rescues
            if (rank := _rank(row.get("reranked_evidence_rank"))) and rank <= top_k
        )
        candidate_contains = sum(
            1 for row in rows if row.get("line_reranker_candidate_contains_evidence")
        )
        by_category[category] = {
            "case_count": len(rows),
            "baseline_evidence_hit_top_k": baseline_hits,
            "baseline_evidence_hit_rate_top_k": _rate(baseline_hits, len(rows))["rate"],
            "reranked_evidence_hit_top_k": reranked_hits,
            "reranked_evidence_hit_rate_top_k": _rate(reranked_hits, len(rows))["rate"],
            "reranked_evidence_mrr": _mrr(rows, "reranked_evidence_rank"),
            "semantic_bridge_lift_top_k": sum(
                1 for row in rows if row.get(f"semantic_bridge_lift_top{top_k}")
            ),
            "context_visible_rescue_count": len(context_rescues),
            "context_visible_rescue_conversion_count": context_rescue_conversions,
            "context_visible_rescue_conversion_rate": _rate(
                context_rescue_conversions,
                len(context_rescues),
            )["rate"],
            "same_session_wrong_line_count": sum(
                1 for row in rows if row.get(f"same_session_wrong_line_top{top_k}")
            ),
            "candidate_contains_evidence_count": candidate_contains,
            "candidate_contains_evidence_rate": _rate(candidate_contains, len(rows))[
                "rate"
            ],
            "line_reranker_error_count": sum(
                len(list(row.get("line_reranker_error_kinds") or [])) for row in rows
            ),
        }
    return by_category


def _regression_count(cases: Sequence[Mapping[str, Any]], *, top_k: int) -> int:
    count = 0
    for case in cases:
        baseline_rank = _rank(case.get("evidence_rank"))
        reranked_rank = _rank(case.get("reranked_evidence_rank"))
        if baseline_rank and baseline_rank <= top_k and not (
            reranked_rank and reranked_rank <= top_k
        ):
            count += 1
    return count


def _rank_bucket_movement_counts(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        before = str(case.get("evidence_rank_bucket") or _rank_bucket(_rank(case.get("evidence_rank"))))
        after = _rank_bucket(_rank(case.get("reranked_evidence_rank")))
        counts[f"{before}->{after}"] += 1
    return dict(sorted(counts.items()))


def _error_kind_counts(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        for kind in case.get("line_reranker_error_kinds") or []:
            counts[str(kind)] += 1
    return dict(sorted(counts.items()))


def _project_full_run(
    *,
    metrics: Mapping[str, Any],
    pilot_question_count: int,
    full_run_questions: int,
) -> dict[str, Any]:
    usage = metrics.get("line_reranker_usage") or {}
    latency = metrics.get("line_reranker_latency_ms") or {}
    cache = metrics.get("line_reranker_cache") or {}
    metadata = metrics.get("line_reranker_metadata") or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    attempted = int(metrics.get("line_reranker_attempted_count") or pilot_question_count)
    per_question_tokens = round(total_tokens / attempted, 2) if attempted else 0.0
    avg_latency_ms = float(latency.get("avg") or 0.0)
    projected_total_tokens = int(round(per_question_tokens * full_run_questions))
    projected_single_worker_seconds = round(avg_latency_ms * full_run_questions / 1000, 2)
    return {
        "basis_question_count": int(pilot_question_count),
        "target_question_count": int(full_run_questions),
        "projected_total_tokens": projected_total_tokens,
        "projected_prompt_cache_hit_tokens": int(
            round((int(usage.get("prompt_cache_hit_tokens") or 0) / max(1, attempted)) * full_run_questions)
        ),
        "projected_prompt_cache_miss_tokens": int(
            round((int(usage.get("prompt_cache_miss_tokens") or 0) / max(1, attempted)) * full_run_questions)
        ),
        "projected_single_worker_seconds": projected_single_worker_seconds,
        "projected_single_worker_minutes": round(projected_single_worker_seconds / 60, 2),
        "average_available_call_latency_ms": avg_latency_ms,
        "cache_hit_rate": cache.get("hit_rate"),
        "cost_status": metadata.get("cost_status") or "provider_cost_not_reported",
        "decision": "not_run_by_default",
        "decision_reason": (
            "The semantic rerank arm is external-model-assisted, cost is not "
            "reported by the provider response, and the pilot already projects "
            "material token/latency spend at 500 questions. Run the full arm only "
            "when it answers a named claim-boundary question."
        ),
        "required_before_full_run": [
            "explicit_operator_budget_approval",
            "provider_cost_model_or_cost_ceiling",
            "privacy_review_for_external_candidate_source_text",
            "partial_output_path_kept_gitignored",
        ],
    }


def _line_reranker_mode(report: Mapping[str, Any]) -> str:
    evaluation = report.get("evaluation") or {}
    metrics = report.get("metrics") or {}
    metadata = metrics.get("line_reranker_metadata") or {}
    return str(
        evaluation.get("line_reranker_mode")
        or metadata.get("line_reranker_mode")
        or "unknown"
    )


def _comparison_metrics(
    current_cases: Sequence[Mapping[str, Any]],
    baseline_cases: Sequence[Mapping[str, Any]],
    *,
    current_report: Mapping[str, Any],
    baseline_report: Mapping[str, Any],
    baseline_report_path: Path | str,
    top_k: int,
) -> dict[str, Any]:
    current_r_at_10 = _recall_by_k(current_cases, "reranked_evidence_rank")["r_at_10"]
    baseline_r_at_10 = _recall_by_k(baseline_cases, "reranked_evidence_rank")["r_at_10"]
    current_mrr = _mrr(current_cases, "reranked_evidence_rank")
    baseline_mrr = _mrr(baseline_cases, "reranked_evidence_rank")
    context_current = [
        case for case in current_cases if case.get(f"evidence_context_rescue_top{top_k}")
    ]
    context_baseline = [
        case for case in baseline_cases if case.get(f"evidence_context_rescue_top{top_k}")
    ]
    current_context_conversions = sum(
        1
        for case in context_current
        if (rank := _rank(case.get("reranked_evidence_rank"))) and rank <= top_k
    )
    baseline_context_conversions = sum(
        1
        for case in context_baseline
        if (rank := _rank(case.get("reranked_evidence_rank"))) and rank <= top_k
    )
    current_wrong_lines = [
        case for case in current_cases if case.get(f"same_session_wrong_line_top{top_k}")
    ]
    baseline_wrong_lines = [
        case for case in baseline_cases if case.get(f"same_session_wrong_line_top{top_k}")
    ]
    current_wrong_reductions = sum(
        1
        for case in current_wrong_lines
        if (rank := _rank(case.get("reranked_evidence_rank"))) and rank <= top_k
    )
    baseline_wrong_reductions = sum(
        1
        for case in baseline_wrong_lines
        if (rank := _rank(case.get("reranked_evidence_rank"))) and rank <= top_k
    )
    lift = int(current_r_at_10["numerator"]) - int(baseline_r_at_10["numerator"])
    miss_families = _semantic_help_families(current_cases, top_k=top_k)
    improved = lift > 0 or current_mrr > baseline_mrr
    return {
        "baseline_mode": _line_reranker_mode(baseline_report),
        "current_mode": _line_reranker_mode(current_report),
        "baseline_report_sha1": _file_sha1(baseline_report_path),
        "question_count_match": len(current_cases) == len(baseline_cases),
        "reranked_evidence_r_at_10": {
            "baseline": baseline_r_at_10,
            "current": current_r_at_10,
        },
        "reranked_evidence_r_at_10_delta": {
            "numerator": lift,
            "rate": round(float(current_r_at_10["rate"]) - float(baseline_r_at_10["rate"]), 4),
        },
        "reranked_evidence_mrr": {
            "baseline": baseline_mrr,
            "current": current_mrr,
            "delta": round(current_mrr - baseline_mrr, 4),
        },
        "context_visible_rescue_conversion_delta": {
            "baseline": baseline_context_conversions,
            "current": current_context_conversions,
            "delta": current_context_conversions - baseline_context_conversions,
        },
        "same_session_wrong_line_reduction_delta": {
            "baseline": baseline_wrong_reductions,
            "current": current_wrong_reductions,
            "delta": current_wrong_reductions - baseline_wrong_reductions,
        },
        "miss_families_needing_semantic_or_model_help": miss_families,
        "decision": (
            "improved_over_baseline"
            if improved
            else "no_deterministic_improvement_failure_report"
        ),
    }


def _semantic_help_families(
    cases: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        reranked_rank = _rank(case.get("reranked_evidence_rank"))
        if reranked_rank and reranked_rank <= top_k:
            continue
        category = str(case.get("evidence_miss_category") or "unknown")
        if not case.get(f"evidence_context_hit_top{top_k}") and not case.get(
            "source_joined_candidate_contains_evidence"
        ):
            counts[f"{category}:source_window_not_visible"] += 1
        elif case.get("line_reranker_candidate_contains_evidence"):
            counts[f"{category}:candidate_visible_but_line_selection_failed"] += 1
        else:
            counts[f"{category}:candidate_packaging_or_source_join_failed"] += 1
    return dict(sorted(counts.items()))


def _semantic_cache_path_evaluation(
    report: Mapping[str, Any],
    *,
    semantic_pilot_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    pilot_metrics = (semantic_pilot_report or {}).get("metrics") or {}
    cold_latency = pilot_metrics.get("line_reranker_latency_ms") or {}
    cold_usage = pilot_metrics.get("line_reranker_usage") or {}
    cold_cache = pilot_metrics.get("line_reranker_cache") or {}
    return {
        "cold_online_semantic_latency": {
            "status": "measured_pilot" if cold_latency else "not_run_in_this_report",
            "avg_ms": cold_latency.get("avg"),
            "max_ms": cold_latency.get("max"),
            "available_call_count": cold_latency.get("count"),
            "total_tokens": cold_usage.get("total_tokens"),
            "boundary": "external provider call at query time; explicit opt-in only",
        },
        "warm_query_cache_latency": {
            "status": "contract_defined_not_measured",
            "cache_key_fields": SEMANTIC_CACHE_KEY_FIELDS,
            "boundary": (
                "valid only as warm query/candidate cache; do not report as cold online latency"
            ),
        },
        "source_side_cache_hot_path_latency": {
            "status": "not_measured_for_semantic_cache",
            "deterministic_report_elapsed_ms": report.get("elapsed_ms"),
            "boundary": (
                "source-side semantic warming must be built from source spans, not benchmark questions"
            ),
        },
        "source_side_cache_build_cost": {
            "status": "not_run",
            "token_count": None,
            "wall_clock_seconds": None,
            "boundary": "not claimable until a source-only warming job is measured",
        },
        "semantic_cache_hit_rate": {
            "status": "provider_prefix_cache_observed" if cold_cache else "not_measured",
            "hit_rate": cold_cache.get("hit_rate"),
            "hit_tokens": cold_cache.get("hit_tokens"),
            "miss_tokens": cold_cache.get("miss_tokens"),
        },
        "semantic_cache_invalidation_count": {
            "status": "not_measured",
            "count": None,
            "required_invalidation_inputs": [
                "source_fingerprint",
                "candidate_hashes",
                "prompt_version",
                "model_provider_id",
                "policy_version",
            ],
        },
        "foreground_default_decision": (
            "do_not_make_cold_online_semantic_rerank_default_hook_path"
        ),
    }


def _metadata(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") or {}
    metadata = metrics.get("line_reranker_metadata") or {}
    evaluation = report.get("evaluation") or {}
    arm = evaluation.get("llm_rerank_arm") or {}
    return {
        "line_reranker_mode": evaluation.get("line_reranker_mode"),
        "arm": metadata.get("arm") or arm.get("arm"),
        "prompt_version": metadata.get("prompt_version") or arm.get("prompt_version"),
        "provider": metadata.get("provider") or arm.get("provider"),
        "model": metadata.get("model") or arm.get("model"),
        "cost_status": metadata.get("cost_status") or "provider_cost_not_reported",
        "input_boundary": arm.get("input_boundary") or metadata.get("input_boundary") or {},
        "output_boundary": arm.get("output_boundary") or metadata.get("output_boundary") or {},
    }


def analyze_rerank_report(
    report_path: Path | str,
    *,
    baseline_report_path: Path | str | None = None,
    semantic_pilot_report_path: Path | str | None = None,
    full_run_questions: int = DEFAULT_FULL_RUN_QUESTIONS,
) -> dict[str, Any]:
    started = time.perf_counter()
    report = _load_report(report_path)
    baseline_report = _load_report(baseline_report_path) if baseline_report_path else None
    semantic_pilot_report = (
        _load_report(semantic_pilot_report_path) if semantic_pilot_report_path else None
    )
    cases = _as_cases(report)
    line_cases = [case for case in cases if case.get("has_line_evidence", True)]
    baseline_cases = (
        [
            case
            for case in _as_cases(baseline_report)
            if case.get("has_line_evidence", True)
        ]
        if baseline_report
        else []
    )
    metrics = report.get("metrics") or {}
    question_count = int(metrics.get("question_count") or len(cases))
    top_k = int((report.get("evaluation") or {}).get("top_k") or 10)
    context_rescue_cases = [
        case for case in line_cases if case.get("evidence_context_rescue_top10")
    ]
    same_session_wrong_line_cases = [
        case for case in line_cases if case.get("same_session_wrong_line_top10")
    ]
    reranked_top_k = f"reranked_evidence_hit_top{top_k}"
    semantic_bridge_lifts = sum(
        1 for case in line_cases if case.get("semantic_bridge_lift_top10")
    )
    context_rescue_conversions = sum(
        1
        for case in context_rescue_cases
        if (rank := _rank(case.get("reranked_evidence_rank"))) is not None
        and rank <= top_k
    )
    wrong_line_reductions = sum(
        1
        for case in same_session_wrong_line_cases
        if (rank := _rank(case.get("reranked_evidence_rank"))) is not None
        and rank <= top_k
    )
    error_counts = _error_kind_counts(line_cases)
    baseline_comparison = (
        _comparison_metrics(
            line_cases,
            baseline_cases,
            current_report=report,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
            top_k=top_k,
        )
        if baseline_report and baseline_report_path
        else None
    )
    status = "pilot_analyzed_full_run_not_default"
    source_issue = "https://github.com/Sapientropic/AIppocampus/issues/1092"
    if baseline_comparison:
        source_issue = "https://github.com/Sapientropic/AIppocampus/issues/1193"
        status = (
            "full_split_exact_line_repair_improved"
            if baseline_comparison["decision"] == "improved_over_baseline"
            else "full_split_exact_line_repair_failure_report"
        )
    projection_metrics = (
        (semantic_pilot_report or {}).get("metrics") if semantic_pilot_report else metrics
    ) or {}
    projection_question_count = int(
        projection_metrics.get("question_count")
        or (len(_as_cases(semantic_pilot_report)) if semantic_pilot_report else 0)
        or question_count
    )
    claim_boundary = (
        "This is a deterministic retrieval-only rerank repair analysis over "
        "candidate source lines, compared with the lexical 500Q baseline. It "
        "also carries semantic pilot cache/latency boundaries when a pilot "
        "report is supplied, but it does not score answer generation or "
        "judge-model QA."
        if baseline_comparison
        else (
            "This is an external-model-assisted retrieval-only rerank analysis "
            "over candidate lines. It is separate from deterministic retrieval "
            "and does not score answer generation or judge-model QA."
        )
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_rerank_analysis",
        "generated_at": now_utc(),
        "source_issue": source_issue,
        "source_report": {
            "kind": report.get("kind"),
            "status": report.get("status"),
            "generated_at": report.get("generated_at"),
            "input_report_sha1": _file_sha1(report_path),
            "local_path_emitted": False,
        },
        "status": status,
        "ok": bool(report.get("ok", True)),
        "benchmark": {
            "name": (report.get("benchmark") or {}).get("name"),
            "split": (report.get("benchmark") or {}).get("split"),
            "dataset_version": (report.get("benchmark") or {}).get("dataset_version"),
        },
        "reranker_metadata": _metadata(report),
        "metrics": {
            "question_count": question_count,
            "evidence_line_case_count": len(line_cases),
            "baseline_evidence_recall_by_k": _recall_by_k(line_cases, "evidence_rank"),
            "reranked_evidence_recall_by_k": _recall_by_k(
                line_cases,
                "reranked_evidence_rank",
            ),
            "semantic_only_evidence_recall_by_k": _recall_by_k(
                line_cases,
                "semantic_only_evidence_rank",
            ),
            "baseline_evidence_mrr": _mrr(line_cases, "evidence_rank"),
            "reranked_evidence_mrr": _mrr(line_cases, "reranked_evidence_rank"),
            "semantic_only_evidence_mrr": _mrr(line_cases, "semantic_only_evidence_rank"),
            "semantic_bridge_lift_top10": semantic_bridge_lifts,
            "rerank_regression_count_top10": _regression_count(line_cases, top_k=top_k),
            "context_visible_rescue_count": len(context_rescue_cases),
            "context_visible_rescue_conversion_count": context_rescue_conversions,
            "context_visible_rescue_conversion_rate": _rate(
                context_rescue_conversions,
                len(context_rescue_cases),
            )["rate"],
            "same_session_wrong_line_count": len(same_session_wrong_line_cases),
            "same_session_wrong_line_reduction_count": wrong_line_reductions,
            "same_session_wrong_line_reduction_rate": _rate(
                wrong_line_reductions,
                len(same_session_wrong_line_cases),
            )["rate"],
            "average_candidate_count": metrics.get("line_reranker_candidate_count_avg"),
            "rank_bucket_movement_counts": _rank_bucket_movement_counts(line_cases),
            "line_reranker_attempted_count": int(
                metrics.get("line_reranker_attempted_count") or 0
            ),
            "line_reranker_available_count": int(
                metrics.get("line_reranker_available_count") or 0
            ),
            "line_reranker_error_count": int(metrics.get("line_reranker_error_count") or 0),
            "line_reranker_error_kind_counts": error_counts,
            "line_reranker_usage": metrics.get("line_reranker_usage") or {},
            "line_reranker_latency_ms": metrics.get("line_reranker_latency_ms") or {},
            "line_reranker_cache": metrics.get("line_reranker_cache") or {},
            "per_case_type": _case_type_metrics(line_cases),
            "per_miss_taxonomy": _miss_taxonomy_metrics(line_cases, top_k=top_k),
            "reranked_reported_hit_top_k": int(metrics.get(reranked_top_k) or 0),
        },
        "baseline_comparison": baseline_comparison,
        "semantic_cache_path_evaluation": _semantic_cache_path_evaluation(
            report,
            semantic_pilot_report=semantic_pilot_report,
        ),
        "full_500_projection": _project_full_run(
            metrics=projection_metrics,
            pilot_question_count=projection_question_count,
            full_run_questions=full_run_questions,
        ),
        "commands": {
            "lexical_500": (
                "python benchmarks\\aippocampus\\benchmark_longmemeval.py --split "
                "longmemeval-v1-small --questions 500 --min-questions 100 "
                "--top-k 10 --line-reranker lexical --line-reranker-workers 8 "
                "--progress-every 50 --partial-output "
                "benchmark_corpus\\reports\\longmemeval-v1-small-lexical-500.partial.json "
                "--output benchmark_corpus\\reports\\longmemeval-v1-small-lexical-500.json"
            ),
            "structural_500": (
                "python benchmarks\\aippocampus\\benchmark_longmemeval.py --split "
                "longmemeval-v1-small --questions 500 --min-questions 100 "
                "--top-k 10 --line-reranker structural --line-reranker-workers 8 "
                "--progress-every 50 --partial-output "
                "benchmark_corpus\\reports\\longmemeval-v1-small-structural-500.partial.json "
                "--output benchmark_corpus\\reports\\longmemeval-v1-small-structural-500.json"
            ),
            "pilot": (
                "python benchmarks\\aippocampus\\benchmark_longmemeval.py --split "
                "longmemeval-v1-small --download --questions 25 --min-questions 25 "
                "--top-k 10 --line-reranker semantic --line-reranker-workers 1 "
                "--line-reranker-timeout 30 --progress-every 5 --output "
                "benchmark_corpus\\reports\\longmemeval-v1-small-semantic-pilot-25.json"
            ),
            "full_500_explicit_opt_in": (
                "python benchmarks\\aippocampus\\benchmark_longmemeval.py --split "
                "longmemeval-v1-small --download --questions 500 --min-questions 100 "
                "--top-k 10 --line-reranker semantic --line-reranker-workers 1 "
                "--line-reranker-timeout 30 --progress-every 25 --partial-output "
                "benchmark_corpus\\reports\\longmemeval-v1-small-semantic-500.partial.json "
                "--output benchmark_corpus\\reports\\longmemeval-v1-small-semantic-500.json"
            ),
            "analysis": (
                "python benchmarks\\aippocampus\\benchmark_longmemeval_rerank_analysis.py "
                "--report benchmark_corpus\\reports\\longmemeval-v1-small-structural-500.json "
                "--baseline-report "
                "benchmark_corpus\\reports\\longmemeval-v1-small-lexical-500.json "
                "--semantic-pilot-report "
                "benchmark_corpus\\reports\\longmemeval-v1-small-semantic-pilot-25.json "
                "--json"
            ),
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "case_ids_emitted": False,
            "local_paths_emitted": False,
            "absolute_paths_emitted": False,
            "dataset_url_emitted": False,
            "input_report_path_emitted": False,
            "external_model_raw_response_emitted": False,
            "output_shape": "sanitized_rerank_aggregate_analysis",
        },
        "claim_boundary": claim_boundary,
        "cannot_claim": sorted(
            {
                *(str(item) for item in report.get("cannot_claim") or []),
                "full_500_llm_reranker_quality",
                "default_exact_line_citation_quality",
                "longmemeval_qa_score",
                "answer_generation_quality",
                "judge_model_score",
                "sota_or_external_baseline_superiority",
                "provider_independent_quality",
                "broad_reranker_safety",
            }
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    return payload


def print_human_summary(payload: Mapping[str, Any]) -> None:
    metrics = payload["metrics"]
    projection = payload["full_500_projection"]
    print("AIppocampus LongMemEval rerank analysis")
    print(f"- status: {payload['status']}")
    print(f"- questions: {metrics['question_count']}")
    print(
        "- reranked R@10: "
        f"{metrics['reranked_evidence_recall_by_k']['r_at_10']['rate']:.2%}; "
        f"MRR {metrics['reranked_evidence_mrr']:.4f}"
    )
    print(
        "- bridge/regression: "
        f"{metrics['semantic_bridge_lift_top10']} lift, "
        f"{metrics['rerank_regression_count_top10']} regression"
    )
    print(
        "- full 500 decision: "
        f"{projection['decision']} ({projection['projected_total_tokens']} projected tokens)"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--semantic-pilot-report", type=Path)
    parser.add_argument("--full-run-questions", type=int, default=DEFAULT_FULL_RUN_QUESTIONS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = analyze_rerank_report(
        args.report,
        baseline_report_path=args.baseline_report,
        semantic_pilot_report_path=args.semantic_pilot_report,
        full_run_questions=args.full_run_questions,
    )
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
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
