"""Public-shadow projection helpers for the question-aware benchmark."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

NO_QUESTION_RETRIEVAL_FORBIDDEN_FIELDS = [
    "question_text",
    "question_short",
    "linked_question_short",
    "linked_questions",
    "theme_short",
    "theme_label",
    "theme_cluster_id",
]


def baseline_preregistration(*, fixture: Mapping[str, Any]) -> dict[str, Any]:
    raw_metadata = fixture.get("metadata")
    metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, Mapping) else {}
    return {
        "kind": "question_aware_public_shadow_baseline_preregistration",
        "cohort": {
            "fixture_id": metadata.get("id", "question_aware_public_shadow_v1"),
            "source_family_counts": metadata.get("source_family_counts", {}),
            "case_family_counts": metadata.get("case_family_counts", {}),
            "public_case_count": metadata.get("public_case_count"),
        },
        "arms": {
            "question_blind_structural": {
                "description": "same selected source-backed rows with question/theme labels removed",
                "question_metadata_visible": False,
                "true_retrieval_baseline": False,
            },
            "plain_baseline_answer_review": {
                "description": "selected public review arm without question-aware source reopen",
                "question_metadata_visible": False,
                "true_retrieval_baseline": False,
            },
            "no_question_retrieval_answer": {
                "description": (
                    "deterministic public retrieval and answer-proxy arm scored without "
                    "question/theme text or labels"
                ),
                "question_metadata_visible": False,
                "true_retrieval_baseline": True,
            },
            "question_aware_source_reopen": {
                "description": "selected public review arm with question-aware route and source reopen",
                "question_metadata_visible": True,
                "source_reopen_required": True,
            },
        },
        "primary_readouts": [
            "question_aware_over_question_blind_delta",
            "answer_usefulness_delta",
            "retrieval_recall_delta",
            "answer_support_proxy_delta",
            "manual_query_reduction_delta",
            "question_aware_wrong_hint_rate",
        ],
        "regression_guards": [
            "negative_controls_all_pass",
            "dynamic_threshold_false_merge_count_zero",
            "dynamic_threshold_false_split_count_zero",
            "raw_private_or_source_text_not_emitted",
        ],
        "claim_boundary": (
            "public selected-fixture plus deterministic no-question retrieval baseline shape, "
            "not broad private-history calibration"
        ),
    }


def source_ref_count(row: Mapping[str, Any]) -> int:
    refs = row.get("source_refs")
    return len(refs) if isinstance(refs, Sequence) and not isinstance(refs, str) else 0


def parse_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def true_no_question_retrieval_answer_baseline(
    *,
    fixture: Mapping[str, Any],
    structural: Mapping[str, Any],
    review_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the public fair-baseline shape without reading question/theme labels.

    The no-question arm intentionally scores only generic source-backed features
    that a question-blind retriever could know before question tracking exists.
    Do not add question/theme labels, linked question payloads, or theme ids to
    the sort key: that would turn this back into the selected structural proxy
    #1367 was opened to replace.
    """

    rows = [row for row in fixture.get("job_rows") or [] if isinstance(row, Mapping)]
    source_backed_rows = [row for row in rows if source_ref_count(row) > 0]
    complete_cases = int(review_metrics.get("complete_comparison_case_count") or 0)
    retrieval_budget = max(1, complete_cases)
    no_question_rows = sorted(
        source_backed_rows,
        key=lambda row: (
            -source_ref_count(row),
            -parse_float(row.get("confidence")),
            str(row.get("created_at") or ""),
        ),
    )[:retrieval_budget]
    raw_structural_metrics = structural.get("metrics")
    structural_metrics: Mapping[str, Any] = (
        raw_structural_metrics if isinstance(raw_structural_metrics, Mapping) else {}
    )
    raw_kind_counts = structural_metrics.get("source_seed_kind_counts")
    kind_counts: Mapping[str, Any] = raw_kind_counts if isinstance(raw_kind_counts, Mapping) else {}
    question_aware_count = int(kind_counts.get("question_candidate") or 0)
    selected_count = sum(
        int(value or 0)
        for value in kind_counts.values()
    )
    total_candidates = max(1, len(source_backed_rows))
    no_question_recall = round(len(no_question_rows) / total_candidates, 4)
    question_aware_recall = round(selected_count / total_candidates, 4)
    question_aware_supported_rate = parse_float(
        review_metrics.get("question_aware_answer_supported_rate")
    )
    no_question_answer_support_proxy = round(
        no_question_recall * question_aware_supported_rate,
        4,
    )
    question_aware_answer_support_proxy = round(
        question_aware_recall * question_aware_supported_rate,
        4,
    )
    return {
        "kind": "question_aware_public_shadow_no_question_retrieval_answer_baseline",
        "status": "fair_baseline_shape_ready"
        if source_backed_rows and complete_cases
        else "fair_baseline_shape_needs_review",
        "arms": {
            "no_question_retrieval_answer": {
                "question_metadata_visible": False,
                "true_retrieval_baseline": True,
                "answer_measurement": "deterministic_answer_support_proxy",
            },
            "question_aware_retrieval_answer": {
                "question_metadata_visible": True,
                "source_reopen_required": True,
                "answer_measurement": "selected_source_reopened_review",
            },
        },
        "retrieval_selection": {
            "no_question_retrieval_answer": {
                "strategy": "generic_source_backed_public_rows_by_ref_count_confidence_time",
                "retrieval_budget": retrieval_budget,
                "candidate_count": len(source_backed_rows),
                "selected_count": len(no_question_rows),
                "allowed_scoring_fields": [
                    "source_refs_count",
                    "confidence",
                    "created_at",
                ],
                "forbidden_fields": NO_QUESTION_RETRIEVAL_FORBIDDEN_FIELDS,
            },
            "question_aware_retrieval_answer": {
                "strategy": "existing_question_aware_public_shadow_pack_selection",
                "selected_count": selected_count,
                "question_candidate_count": question_aware_count,
            },
        },
        "metrics": {
            "no_question_retrieval_recall": no_question_recall,
            "question_aware_retrieval_recall": question_aware_recall,
            "retrieval_recall_delta": round(question_aware_recall - no_question_recall, 4),
            "no_question_answer_support_proxy": no_question_answer_support_proxy,
            "question_aware_answer_support_proxy": question_aware_answer_support_proxy,
            "answer_support_proxy_delta": round(
                question_aware_answer_support_proxy - no_question_answer_support_proxy,
                4,
            ),
        },
        "privacy": {
            "raw_source_text_emitted": False,
            "raw_answer_text_emitted": False,
            "raw_source_refs_emitted": False,
            "question_or_theme_labels_used_for_no_question_scoring": False,
        },
        "can_claim": [
            "public_shadow_true_no_question_retrieval_baseline_shape_recorded",
            "no_question_arm_scoring_excludes_question_theme_labels",
        ],
        "cannot_claim": [
            "private_history_retrieval_quality",
            "broad_no_question_aware_retrieval_baseline",
            "live_model_answer_quality",
            "user_visible_recall_improvement",
        ],
    }


def materialization_review_evidence(
    *,
    structural: Mapping[str, Any],
    review_metrics: Mapping[str, Any],
    manual_query_reduction_delta: float,
    negative_controls: Sequence[Mapping[str, Any]],
    threshold_readout: Mapping[str, Any],
) -> dict[str, Any]:
    selection = structural.get("pack_selection", {})
    selected_counts = (
        selection.get("selected_source_seed_kind_counts", {})
        if isinstance(selection, Mapping)
        else {}
    )
    dynamic_threshold = threshold_readout.get("dynamic_six_axis_threshold", {})
    false_merge_count = int(dynamic_threshold.get("false_merge_count") or 0)
    false_split_count = int(dynamic_threshold.get("false_split_count") or 0)
    negative_pass_count = sum(1 for item in negative_controls if item.get("passed"))
    complete_cases = int(review_metrics.get("complete_comparison_case_count") or 0)
    usefulness_delta = review_metrics.get("answer_usefulness_delta")
    wrong_hint_rate = review_metrics.get("question_aware_wrong_hint_rate")
    categories: dict[str, dict[str, Any]] = {
        "source_reopen_usefulness": {
            "status": "observed" if complete_cases and (usefulness_delta or 0) > 0 else "not_observed",
            "metric": "answer_usefulness_delta",
            "value": usefulness_delta,
        },
        "manual_search_reduction": {
            "status": "observed" if manual_query_reduction_delta > 0 else "not_observed",
            "metric": "manual_query_reduction_delta",
            "value": manual_query_reduction_delta,
        },
        "wrong_route_drag": {
            "status": "bounded"
            if wrong_hint_rate == 0.0 and negative_pass_count == len(negative_controls)
            else "needs_review",
            "question_aware_wrong_hint_rate": wrong_hint_rate,
            "negative_control_pass_count": negative_pass_count,
            "negative_control_count": len(negative_controls),
        },
        "candidate_link_theme_materialization": {
            "status": "observed"
            if int(selected_counts.get("question_link") or 0) > 0
            and int(selected_counts.get("theme_candidate") or 0) > 0
            else "missing_link_or_theme",
            "selected_source_seed_kind_counts": selected_counts,
        },
        "threshold_regression_guard": {
            "status": "passed" if false_merge_count == 0 and false_split_count == 0 else "needs_review",
            "dynamic_false_merge_count": false_merge_count,
            "dynamic_false_split_count": false_split_count,
        },
    }
    return {
        "kind": "question_aware_public_shadow_materialization_review_evidence",
        "status": "public_shadow_review_evidence_ready"
        if all(item["status"] in {"observed", "bounded", "passed"} for item in categories.values())
        else "public_shadow_review_evidence_needs_review",
        "reviewer_usefulness_categories": categories,
        "source_reachability_boundary": (
            "question/theme/link rows are route material, not source truth; "
            "final factual claims still require source reopen"
        ),
        "can_claim": [
            "selected_public_fixture_materializes_question_link_and_theme_candidate",
            "selected_public_fixture_records_manual_search_and_wrong_route_readouts",
        ],
        "cannot_claim": [
            "theme_resonance_calibration",
            "private_history_materialization_quality",
            "live_user_review_lift",
        ],
    }
