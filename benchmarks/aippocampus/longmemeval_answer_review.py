from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def mapping_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def refined_failure_category(row: dict[str, Any]) -> str:
    answer = mapping_value(row.get("answer"))
    reader = mapping_value(row.get("reader"))
    retrieval = mapping_value(row.get("retrieval"))
    category = str(answer.get("failure_category") or "unknown")
    if category == "answered_correctly":
        return category
    if reader.get("status") == "reader_error" or reader.get("error_kind"):
        return "reader_provider_error"
    if not answer.get("context_sufficient"):
        return "retrieval_evidence_unavailable"
    if (
        bool(retrieval.get("has_line_evidence", True))
        and not retrieval.get("candidate_contains_evidence")
    ):
        return "insufficient_evidence_packaging"
    if reader.get("abstained"):
        return "over_abstention_boundary_false_negative"
    if category == "evaluation_mismatch":
        return "deterministic_judge_mismatch"
    if category == "abstention_unanswerable_boundary":
        return "reader_empty_answer"
    if category == "evidence_visible_reader_miss":
        return "true_reader_miss"
    return category


def failure_review_next_action(category: str) -> str:
    return {
        "reader_provider_error": "rerun_or_inspect_provider_response_shape",
        "deterministic_judge_mismatch": "review_normalization_or_official_judge_equivalence",
        "over_abstention_boundary_false_negative": "tighten_reader_prompt_against_false_abstention",
        "insufficient_evidence_packaging": "raise_source_line_salience_before_reader",
        "true_reader_miss": "improve_reader_prompt_or_model_route",
        "retrieval_evidence_unavailable": "fix_retrieval_before_reader_eval",
        "reader_empty_answer": "inspect_reader_output_schema_and_prompt",
        "stale_update_confusion": "review_temporal_update_prompting",
    }.get(category, "review_case_before_scaling")


def reader_public_outcome(reader: dict[str, Any]) -> str:
    if reader.get("status") == "reader_error" or reader.get("error_kind"):
        return "reader_error"
    if reader.get("abstained"):
        return "abstained"
    if reader.get("answer_text_sha1"):
        return "answered"
    if reader.get("status") == "answered":
        return "empty_answer"
    return str(reader.get("status") or "unknown")


def build_failure_review(payload: dict[str, Any]) -> dict[str, Any]:
    review_rows: list[dict[str, Any]] = []
    for row in payload.get("cases") or []:
        if not isinstance(row, dict):
            continue
        answer = mapping_value(row.get("answer"))
        if answer.get("failure_category") == "answered_correctly":
            continue
        reader = mapping_value(row.get("reader"))
        retrieval = mapping_value(row.get("retrieval"))
        quality = mapping_value(answer.get("answer_quality"))
        refined = refined_failure_category(row)
        review_rows.append(
            {
                "case_id": str(row.get("case_id") or ""),
                "case_type": str(row.get("case_type") or "unknown"),
                "source_id_sha1": row.get("source_id_sha1"),
                "question_id_sha1": row.get("question_id_sha1"),
                "answer_sha1": row.get("answer_sha1"),
                "answer_text_sha1": reader.get("answer_text_sha1"),
                "original_failure_category": answer.get("failure_category"),
                "refined_failure_category": refined,
                "context_sufficient": bool(answer.get("context_sufficient")),
                "candidate_contains_evidence": bool(
                    retrieval.get("candidate_contains_evidence")
                ),
                "reader_status": reader.get("status"),
                "reader_error_kind": reader.get("error_kind"),
                "reader_abstained": bool(reader.get("abstained")),
                "reader_outcome": reader_public_outcome(reader),
                "token_overlap_rate": quality.get("token_overlap_rate"),
                "evidence_rank": retrieval.get("evidence_rank"),
                "evidence_context_rank": retrieval.get("evidence_context_rank"),
                "evidence_miss_category": retrieval.get("evidence_miss_category"),
                "next_safe_action": failure_review_next_action(refined),
            }
        )
    taxonomy_counts: dict[str, int] = {}
    for row in review_rows:
        category = str(row["refined_failure_category"])
        taxonomy_counts[category] = taxonomy_counts.get(category, 0) + 1
    return {
        "kind": "aippocampus_longmemeval_answer_failure_review",
        "schema_version": SCHEMA_VERSION,
        "review_scope": "sanitized_non_correct_cases_only",
        "non_correct_case_count": len(review_rows),
        "taxonomy_counts": taxonomy_counts,
        "cases": review_rows,
        "privacy_boundary": {
            "raw_question_text_emitted": False,
            "raw_answer_text_emitted": False,
            "raw_source_text_emitted": False,
            "raw_model_response_emitted": False,
            "case_ids_are_hashed": True,
        },
    }


def expansion_go_no_go(review: dict[str, Any]) -> dict[str, Any]:
    taxonomy = mapping_value(review.get("taxonomy_counts"))
    blocker_keys = [
        "reader_provider_error",
        "deterministic_judge_mismatch",
        "over_abstention_boundary_false_negative",
        "insufficient_evidence_packaging",
        "retrieval_evidence_unavailable",
        "reader_empty_answer",
        "stale_update_confusion",
    ]
    blockers = [key for key in blocker_keys if int(taxonomy.get(key) or 0) > 0]
    true_reader_miss_count = int(taxonomy.get("true_reader_miss") or 0)
    if blockers:
        status = "no_go"
        next_action = "fix_blockers_before_100q_or_500q"
    elif true_reader_miss_count:
        status = "go_100q_before_500q"
        next_action = "scale_to_100q_with_reader_miss_monitoring"
    else:
        status = "go_100q"
        next_action = "run_100q_before_500q"
    return {
        "kind": "aippocampus_longmemeval_answer_expansion_gate",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "blockers": blockers,
        "true_reader_miss_count": true_reader_miss_count,
        "gate_policy": {
            "no_unexplained_judge_mismatch": taxonomy.get(
                "deterministic_judge_mismatch", 0
            )
            == 0,
            "no_reader_provider_errors": taxonomy.get("reader_provider_error", 0)
            == 0,
            "no_over_abstention_false_negatives": taxonomy.get(
                "over_abstention_boundary_false_negative",
                0,
            )
            == 0,
            "no_packaging_failures": taxonomy.get(
                "insufficient_evidence_packaging", 0
            )
            == 0,
            "retrieval_available_for_answer_cases": taxonomy.get(
                "retrieval_evidence_unavailable",
                0,
            )
            == 0,
            "no_stale_update_confusion": taxonomy.get("stale_update_confusion", 0)
            == 0,
        },
        "next_action": next_action,
    }
