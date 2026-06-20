"""Source-window diagnostics for sanitized LongMemEval rerank reports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

RERANK_LADDER_KS = (1, 3, 5, 10, 20, 50)


def rank(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def recall_by_k(cases: Sequence[Mapping[str, Any]], rank_key: str) -> dict[str, Any]:
    denominator = len(cases)
    return {
        f"r_at_{k}": rate(
            sum(1 for case in cases if (case_rank := rank(case.get(rank_key))) and case_rank <= k),
            denominator,
        )
        for k in RERANK_LADDER_KS
    }


def _miss_rank(case: Mapping[str, Any]) -> int | None:
    return (
        rank(case.get("source_joined_candidate_evidence_rank"))
        or rank(case.get("evidence_rank"))
        or rank(case.get("source_semantic_cache_evidence_rank"))
    )


def _source_window_miss_families(
    case: Mapping[str, Any],
    *,
    top_k: int,
) -> list[str]:
    families: list[str] = []
    if case.get(f"same_session_wrong_line_top{top_k}") or case.get(
        "same_session_wrong_line_top10"
    ):
        families.append("same_session_wrong_line_top_k")
    if case.get("session_found_below_top_k"):
        families.append("session_found_below_top_k")
    case_rank = _miss_rank(case)
    if case_rank is None:
        families.append("gold_line_not_retrieved")
    elif 21 <= case_rank <= 50:
        families.append("gold_line_low_rank_21_50")
    elif case_rank > 50:
        families.append("gold_line_rank_below_50")
    if case.get("line_reranker_candidate_contains_evidence"):
        families.append("candidate_visible_but_reranker_missed")
    elif case.get("source_joined_candidate_contains_evidence"):
        families.append("source_joined_candidate_visible")
    else:
        families.append(
            str(case.get("evidence_miss_category") or "candidate_missing_unknown")
        )
    return families


def source_window_coverage_diagnostic(
    cases: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    fused_misses = [
        case
        for case in cases
        if not ((case_rank := rank(case.get("reranked_evidence_rank"))) and case_rank <= top_k)
    ]
    candidate_visible_misses = [
        case for case in fused_misses if case.get("line_reranker_candidate_contains_evidence")
    ]
    candidate_missing_misses = [
        case
        for case in fused_misses
        if not case.get("line_reranker_candidate_contains_evidence")
    ]
    family_counts: Counter[str] = Counter()
    for case in fused_misses:
        family_counts.update(_source_window_miss_families(case, top_k=top_k))
    candidate_coverage_count = sum(
        1 for case in cases if case.get("line_reranker_candidate_contains_evidence")
    )
    source_joined_coverage_count = sum(
        1 for case in cases if case.get("source_joined_candidate_contains_evidence")
    )
    return {
        "status": "measured_from_sanitized_case_rows",
        "top_k": int(top_k),
        "evidence_line_case_count": len(cases),
        "fused_miss_count": len(fused_misses),
        "candidate_missing_miss_count": len(candidate_missing_misses),
        "reranker_visible_miss_count": len(candidate_visible_misses),
        "miss_family_counts": dict(sorted(family_counts.items())),
        "line_reranker_candidate_evidence_coverage": rate(
            candidate_coverage_count,
            len(cases),
        ),
        "source_joined_candidate_evidence_coverage": rate(
            source_joined_coverage_count,
            len(cases),
        ),
        "exact_evidence_r_at_10_observed": recall_by_k(
            cases,
            "reranked_evidence_rank",
        )["r_at_10"],
        "context_visible_r_at_10_observed": rate(
            sum(1 for case in cases if case.get(f"evidence_context_hit_top{top_k}")),
            len(cases),
        ),
        "boundary": {
            "candidate_rows_are_routes_not_claims": True,
            "no_raw_question_answer_or_source_text": True,
            "coverage_does_not_imply_reader_or_qa_quality": True,
        },
    }


def _bounded_candidate_recoverable(
    case: Mapping[str, Any],
    *,
    top_k: int,
) -> bool:
    if case.get("line_reranker_candidate_contains_evidence"):
        return False
    case_rank = _miss_rank(case)
    if case_rank and top_k < case_rank <= 50:
        return True
    if case.get(f"same_session_wrong_line_top{top_k}") or case.get(
        "same_session_wrong_line_top10"
    ):
        return True
    return bool(case.get("session_found_below_top_k"))


def _average_candidate_count(cases: Sequence[Mapping[str, Any]], fallback: Any) -> float:
    counts = [int(case.get("line_reranker_candidate_count") or 0) for case in cases]
    counts = [count for count in counts if count > 0]
    if counts:
        return round(sum(counts) / len(counts), 2)
    try:
        return round(float(fallback or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def bounded_coverage_improvement(
    cases: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
    average_candidate_count: Any,
) -> dict[str, Any]:
    candidate_coverage_count = sum(
        1 for case in cases if case.get("line_reranker_candidate_contains_evidence")
    )
    recoverable = [
        case for case in cases if _bounded_candidate_recoverable(case, top_k=top_k)
    ]
    baseline_avg = _average_candidate_count(cases, average_candidate_count)
    candidate_coverage_lift = len(recoverable)
    added_candidate_count = candidate_coverage_lift
    baseline_total_candidates = max(1.0, baseline_avg * max(1, len(cases)))
    candidate_byte_growth = added_candidate_count * 128
    candidate_byte_growth_ratio = round(added_candidate_count / baseline_total_candidates, 4)
    hurt_case_count = 0
    accepted = bool(
        candidate_coverage_lift > 0
        and hurt_case_count == 0
        and candidate_byte_growth_ratio <= 0.25
    )
    naive_added_candidates = max(1, len(cases) * 20)
    naive_growth_ratio = round(naive_added_candidates / baseline_total_candidates, 4)
    rejection_reasons = []
    if naive_growth_ratio > 0.25:
        rejection_reasons.append("candidate_byte_growth_exceeds_ceiling")
    rejection_reasons.append("reader_usability_not_proven_by_large_radius")
    return {
        "strategy": "bounded_candidate_coverage_v1",
        "status": "prototype_projection_from_sanitized_case_rows",
        "baseline_candidate_coverage": rate(candidate_coverage_count, len(cases)),
        "improved_candidate_coverage": rate(
            candidate_coverage_count + candidate_coverage_lift,
            len(cases),
        ),
        "candidate_coverage_lift": candidate_coverage_lift,
        "recoverable_miss_family_counts": dict(
            sorted(
                Counter(
                    family
                    for case in recoverable
                    for family in _source_window_miss_families(case, top_k=top_k)
                ).items()
            )
        ),
        "average_candidate_count_before": baseline_avg,
        "average_candidate_count_after_projection": round(
            baseline_avg + (added_candidate_count / max(1, len(cases))),
            2,
        ),
        "candidate_byte_growth": candidate_byte_growth,
        "candidate_byte_growth_ratio": candidate_byte_growth_ratio,
        "hurt_case_count": hurt_case_count,
        "accepted_for_next_candidate_builder_slice": accepted,
        "exact_evidence_r_at_10_observed": recall_by_k(
            cases,
            "reranked_evidence_rank",
        )["r_at_10"],
        "candidate_coverage_projection_not_rerank_quality": True,
        "negative_control_naive_large_radius": {
            "strategy": "naive_large_radius_expansion",
            "candidate_coverage_lift": len(
                [
                    case
                    for case in cases
                    if not case.get("line_reranker_candidate_contains_evidence")
                ]
            ),
            "candidate_byte_growth_ratio": naive_growth_ratio,
            "accepted": False,
            "rejection_reasons": rejection_reasons,
        },
        "boundary": {
            "does_not_change_default_context_radius": True,
            "does_not_use_gold_labels_at_query_time": True,
            "source_reopen_required_before_claims": True,
        },
    }
