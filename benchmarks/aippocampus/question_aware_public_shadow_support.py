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


def public_safe_local_calibration_readout(
    *,
    no_question_baseline: Mapping[str, Any],
    review_metrics: Mapping[str, Any],
    negative_controls: Sequence[Mapping[str, Any]],
    threshold_readout: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize #1368 calibration axes from the public shadow fixture.

    #1368 asks for broader private/local calibration, but the public repo should
    not require private history to make progress. This readout treats the
    checked-in public fixture as a local-history equivalent and records the
    false-positive/false-negative classes explicitly instead of burying them in
    answer-review and threshold subreports.
    """

    retrieval = no_question_baseline.get("retrieval_selection", {})
    no_question_selection = (
        retrieval.get("no_question_retrieval_answer", {})
        if isinstance(retrieval, Mapping)
        else {}
    )
    candidate_count = int(no_question_selection.get("candidate_count") or 0)
    no_question_selected_count = int(no_question_selection.get("selected_count") or 0)
    missed_resurfacing_count = max(0, candidate_count - no_question_selected_count)
    complete_cases = int(review_metrics.get("complete_comparison_case_count") or 0)
    wrong_hint_rate = parse_float(review_metrics.get("question_aware_wrong_hint_rate"))
    wrong_route_drag_count = round(wrong_hint_rate * complete_cases)
    dynamic_threshold = threshold_readout.get("dynamic_six_axis_threshold", {})
    dynamic_false_merge_count = int(dynamic_threshold.get("false_merge_count") or 0)
    dynamic_false_split_count = int(dynamic_threshold.get("false_split_count") or 0)
    negative_pass_count = sum(1 for item in negative_controls if item.get("passed"))
    negative_control_count = len(negative_controls)
    noise_false_positive_count = negative_control_count - negative_pass_count
    question_aware_metrics = (
        no_question_baseline.get("metrics", {})
        if isinstance(no_question_baseline.get("metrics"), Mapping)
        else {}
    )

    false_positive_classes = {
        "stale_question_carryover": {
            "observed_count": dynamic_false_merge_count,
            "metric_source": "dynamic_six_axis_threshold.false_merge_count",
        },
        "noise_or_code_promoted_to_question": {
            "observed_count": noise_false_positive_count,
            "metric_source": "negative_control_skip_reason_readout",
        },
        "wrong_route_drag": {
            "observed_count": wrong_route_drag_count,
            "metric_source": "question_aware_wrong_hint_rate",
        },
    }

    false_negative_classes = {
        "missed_resurfacing_without_question_tracking": {
            "observed_count": missed_resurfacing_count,
            "metric_source": "true_no_question_retrieval_answer_baseline",
        },
        "over_split_recurring_question": {
            "observed_count": dynamic_false_split_count,
            "metric_source": "dynamic_six_axis_threshold.false_split_count",
        },
    }
    safe_public_ready = bool(
        complete_cases > 0
        and negative_pass_count == negative_control_count
        and dynamic_false_merge_count == 0
        and dynamic_false_split_count == 0
        and wrong_route_drag_count == 0
        and parse_float(question_aware_metrics.get("retrieval_recall_delta")) > 0
    )
    maturity = (
        "public_safe_local_calibration_ready"
        if safe_public_ready
        else "public_safe_local_calibration_needs_review"
    )
    return {
        "kind": "question_aware_public_safe_local_calibration_readout",
        "status": maturity,
        "claim_level": "public_safe_extracted_fixture_calibration",
        "metrics": {
            "stale_question_carryover_count": dynamic_false_merge_count,
            "missed_resurfacing_without_question_tracking_count": missed_resurfacing_count,
            "wrong_route_drag_count": wrong_route_drag_count,
            "noise_false_positive_count": noise_false_positive_count,
            "over_split_false_negative_count": dynamic_false_split_count,
            "negative_control_pass_count": negative_pass_count,
            "negative_control_count": negative_control_count,
            "retrieval_recall_delta": question_aware_metrics.get("retrieval_recall_delta"),
            "answer_support_proxy_delta": question_aware_metrics.get(
                "answer_support_proxy_delta"
            ),
        },
        "false_positive_classes": false_positive_classes,
        "false_negative_classes": false_negative_classes,
        "privacy_and_deletion_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_refs_emitted": False,
            "deletion_or_no_recall_boundary": (
                "question rows are navigation only and must be dropped or reopened "
                "when source state is deleted, conflicted, or outside scope"
            ),
        },
        "issue_readouts": {
            "github_1368": {
                "sanitized_calibration_report": "public_safe_extracted_fixture",
                "false_positive_classes_recorded": sorted(false_positive_classes),
                "false_negative_classes_recorded": sorted(false_negative_classes),
                "maturity": maturity,
                "closeout_eligible": safe_public_ready,
            },
            "github_248": {
                "public_safe_calibration_maturity": maturity,
                "private_or_live_calibration_measured": False,
                "closeout_scope": "public_safe_owner_closeout_only",
                "owner_closeout_eligible": safe_public_ready,
            },
        },
        "can_claim": [
            "public_safe_question_tracking_calibration_classes_recorded",
            "public_safe_stale_carryover_missed_resurfacing_wrong_route_drag_readout_recorded",
        ],
        "cannot_claim": [
            "broad_private_history_calibration",
            "live_default_question_tracking_quality",
            "theme_resonance_calibration",
            "source_truth_from_question_tracking_rows",
        ],
    }


def public_shadow_metrics(
    *,
    metadata: Mapping[str, Any],
    review_rows: Sequence[Mapping[str, Any]],
    negative_controls: Sequence[Mapping[str, Any]],
    structural: Mapping[str, Any],
    review_metrics: Mapping[str, Any],
    no_question_baseline: Mapping[str, Any],
    calibration_readout: Mapping[str, Any],
    threshold_readout: Mapping[str, Any],
    negative_control_readout: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project the public-shadow report metrics without keeping them in the runner."""

    raw_structural_metrics = structural.get("metrics")
    structural_metrics: Mapping[str, Any] = (
        raw_structural_metrics if isinstance(raw_structural_metrics, Mapping) else {}
    )
    raw_no_question_metrics = no_question_baseline.get("metrics")
    no_question_metrics: Mapping[str, Any] = (
        raw_no_question_metrics if isinstance(raw_no_question_metrics, Mapping) else {}
    )
    raw_calibration_metrics = calibration_readout.get("metrics")
    calibration_metrics: Mapping[str, Any] = (
        raw_calibration_metrics if isinstance(raw_calibration_metrics, Mapping) else {}
    )
    dynamic_threshold = threshold_readout.get("dynamic_six_axis_threshold", {})
    threshold_metrics: Mapping[str, Any] = (
        dynamic_threshold if isinstance(dynamic_threshold, Mapping) else {}
    )
    public_case_count = int(
        metadata.get("public_case_count")
        or len({str(row.get("case_id") or "") for row in review_rows if row.get("case_id")})
        + len(negative_controls)
    )
    return {
        "public_case_count": public_case_count,
        "negative_control_count": len(negative_controls),
        "pack_count": structural_metrics["pack_count"],
        "source_ref_fidelity_rate": structural_metrics["source_ref_fidelity_rate"],
        "plain_term_coverage": structural_metrics["plain_term_coverage"],
        "question_blind_term_coverage": structural_metrics["question_blind_term_coverage"],
        "question_aware_term_coverage": structural_metrics["question_aware_term_coverage"],
        "question_aware_over_question_blind_delta": structural_metrics[
            "question_aware_over_question_blind_delta"
        ],
        "answer_usefulness_delta": review_metrics.get("answer_usefulness_delta"),
        "manual_query_reduction_delta": review_metrics.get("manual_query_reduction_delta"),
        "question_aware_wrong_hint_rate": review_metrics.get("question_aware_wrong_hint_rate"),
        "no_question_retrieval_recall": no_question_metrics["no_question_retrieval_recall"],
        "question_aware_retrieval_recall": no_question_metrics[
            "question_aware_retrieval_recall"
        ],
        "retrieval_recall_delta": no_question_metrics["retrieval_recall_delta"],
        "no_question_answer_support_proxy": no_question_metrics[
            "no_question_answer_support_proxy"
        ],
        "question_aware_answer_support_proxy": no_question_metrics[
            "question_aware_answer_support_proxy"
        ],
        "answer_support_proxy_delta": no_question_metrics["answer_support_proxy_delta"],
        "negative_control_pass_count": sum(
            1 for item in negative_control_readout if item.get("passed")
        ),
        "threshold_dynamic_false_split_count": threshold_metrics.get("false_split_count"),
        "threshold_dynamic_false_merge_count": threshold_metrics.get("false_merge_count"),
        "stale_question_carryover_count": calibration_metrics[
            "stale_question_carryover_count"
        ],
        "missed_resurfacing_without_question_tracking_count": calibration_metrics[
            "missed_resurfacing_without_question_tracking_count"
        ],
        "wrong_route_drag_count": calibration_metrics["wrong_route_drag_count"],
        "noise_false_positive_count": calibration_metrics["noise_false_positive_count"],
    }


def public_shadow_status(
    *,
    structural: Mapping[str, Any],
    metrics: Mapping[str, Any],
    negative_control_readout: Sequence[Mapping[str, Any]],
) -> str:
    answer_review = structural.get("answer_quality_review", {})
    answer_review_status = (
        answer_review.get("status") if isinstance(answer_review, Mapping) else None
    )
    ready = (
        str(structural.get("status") or "").startswith("structural_proxy_ready")
        and answer_review_status == "selected_source_reopened_answer_quality_review_ready"
        and all(item.get("passed") for item in negative_control_readout)
        and int(metrics["threshold_dynamic_false_split_count"] or 0) == 0
        and int(metrics["threshold_dynamic_false_merge_count"] or 0) == 0
    )
    return "public_shadow_ready" if ready else "public_shadow_needs_review"
