"""Public-shadow projection helpers for the question-aware benchmark."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


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
            "question_aware_source_reopen": {
                "description": "selected public review arm with question-aware route and source reopen",
                "source_reopen_required": True,
            },
        },
        "primary_readouts": [
            "question_aware_over_question_blind_delta",
            "answer_usefulness_delta",
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
            "public selected-fixture baseline, not broad private-history calibration "
            "or true no-question-aware retrieval baseline"
        ),
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
