"""Public-safe semantic sidecar evidence diagnostics.

The real-history smoke needs to explain sparse semantic-label funnels without
turning model sidecars into source truth. Keep this helper aggregate-only: no
raw text, paths, thread ids, message ids, source refs, or snippets.
"""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.semantic_scope_labels import label_evidence_is_sufficient


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_label_counts(values: Any) -> dict[str, int]:
    if not isinstance(values, dict):
        return {}
    return {
        label: public_count(values.get(label))
        for label in SCOPE_LABEL_ORDER
        if label in values
    }


def public_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_present_count(*values: Any) -> int:
    for value in values:
        if value is not None:
            return public_count(value)
    return 0


def public_ordered_label_list(values: Any) -> list[str]:
    present = {str(value) for value in values or []}
    return [label for label in SCOPE_LABEL_ORDER if label in present]


def compact_label_evidence_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Report aggregate per-label evidence completeness without leaking source text."""

    label_counts: dict[str, int] = {}
    sufficient_label_counts: dict[str, int] = {}
    weak_or_missing_label_counts: dict[str, int] = {}
    label_count = 0
    sufficient_evidence_count = 0
    weak_or_missing_count = 0
    findings_with_labels = 0
    for job in result.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        for finding in job.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            labels = [
                str(label) for label in finding.get("scope_labels") or [] if str(label).strip()
            ]
            if not labels:
                continue
            findings_with_labels += 1
            evidence_by_label = {
                str(item.get("label") or ""): item
                for item in finding.get("label_evidence") or []
                if isinstance(item, dict) and item.get("label")
            }
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
                label_count += 1
                evidence = evidence_by_label.get(label)
                if label_evidence_is_sufficient(label, evidence):
                    sufficient_evidence_count += 1
                    sufficient_label_counts[label] = sufficient_label_counts.get(label, 0) + 1
                else:
                    weak_or_missing_count += 1
                    weak_or_missing_label_counts[label] = (
                        weak_or_missing_label_counts.get(label, 0) + 1
                    )
    return {
        "finding_count_with_labels": findings_with_labels,
        "accepted_label_count": label_count,
        "labels_with_sufficient_evidence": sufficient_evidence_count,
        "weak_or_missing_evidence_label_count": weak_or_missing_count,
        "label_evidence_complete": label_count > 0 and sufficient_evidence_count == label_count,
        "label_coverage": sorted(label_counts),
        "per_label_count": {label: label_counts[label] for label in sorted(label_counts)},
        "per_label_sufficient_evidence_count": {
            label: sufficient_label_counts[label] for label in sorted(sufficient_label_counts)
        },
        "per_label_weak_or_missing_evidence_count": {
            label: weak_or_missing_label_counts[label]
            for label in sorted(weak_or_missing_label_counts)
        },
    }


def semantic_evidence_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    """Explain candidate -> finding -> materialized rows using counts only."""

    job = public_dict(result.get("job"))
    label_evidence = public_dict(job.get("label_evidence"))
    materialization_result = result.get("materialization")
    materialization_counts_available = isinstance(materialization_result, dict)
    materialization = public_dict(materialization_result)
    candidate_coverage = public_dict(result.get("candidate_coverage"))
    candidate_source = public_dict(result.get("semantic_candidate_source"))
    after = public_dict(result.get("after"))

    selected_candidate_count = first_present_count(
        candidate_coverage.get("candidate_turn_count"),
        candidate_source.get("candidate_turn_count"),
    )
    evaluated_candidate_count = first_present_count(
        candidate_coverage.get("evaluated_candidate_turn_count")
    )
    finding_count = public_count(job.get("finding_count"))
    materialized_row_count = public_count(materialization.get("row_count"))
    materialized_thread_count = (
        public_count(after.get("semantic_sidecar_threads")) if materialized_row_count else 0
    )

    finding_label_counts = public_label_counts(label_evidence.get("per_label_count"))
    sufficient_label_counts = public_label_counts(
        label_evidence.get("per_label_sufficient_evidence_count")
    )
    weak_label_counts = public_label_counts(
        label_evidence.get("per_label_weak_or_missing_evidence_count")
    )
    materialized_label_counts = public_label_counts(materialization.get("per_label_row_count"))
    per_label = {
        label: {
            "finding_label_count": public_count(finding_label_counts.get(label)),
            "sufficient_evidence_label_count": public_count(
                sufficient_label_counts.get(label)
            ),
            "weak_or_missing_evidence_label_count": public_count(
                weak_label_counts.get(label)
            ),
            "materialized_label_count": public_count(materialized_label_counts.get(label)),
        }
        for label in SCOPE_LABEL_ORDER
    }

    missing_after_materialization = (
        [
            label
            for label, stats in per_label.items()
            if stats["materialized_label_count"] == 0
        ]
        if materialization_counts_available
        else []
    )
    finding_not_materialized = [
        label
        for label, stats in per_label.items()
        if stats["finding_label_count"] > 0 and stats["materialized_label_count"] == 0
    ]
    return {
        "funnel": {
            "selected_candidate_count": selected_candidate_count,
            "candidate_thread_count": first_present_count(
                candidate_source.get("candidate_thread_count")
            ),
            "evaluated_candidate_turn_count": evaluated_candidate_count,
            "unevaluated_candidate_turn_count": public_count(
                candidate_coverage.get("unevaluated_candidate_turn_count")
            ),
            "batch_count": public_count(candidate_coverage.get("batch_count")),
            "successful_batch_count": public_count(
                candidate_coverage.get("successful_batch_count")
            ),
            "failed_batch_count": public_count(candidate_coverage.get("failed_batch_count")),
            "finding_count": finding_count,
            "finding_count_with_labels": public_count(
                label_evidence.get("finding_count_with_labels")
            ),
            "materialized_row_count": materialized_row_count,
            "materialized_thread_count": materialized_thread_count,
        },
        "per_label": per_label,
        "high_risk_label_families": {
            "families": list(SCOPE_LABEL_ORDER),
            "per_label_materialized_counts_available": materialization_counts_available,
            "missing_after_materialization": missing_after_materialization,
            "finding_not_materialized": finding_not_materialized,
            "classification": (
                "still_unsafe_to_restore_without_stronger_source_backed_evidence"
                if materialization_counts_available
                else "not_classified_without_materialization_run"
            ),
        },
        "materialization_reason_buckets": {
            "model_abstained_or_no_finding": max(0, evaluated_candidate_count - finding_count),
            "unevaluated_candidate_turn_count": public_count(
                candidate_coverage.get("unevaluated_candidate_turn_count")
            ),
            "skipped_without_refs": public_count(candidate_source.get("skipped_without_refs")),
            "already_had_semantic_sidecar": public_count(
                candidate_source.get("skipped_already_semantic")
            ),
            "weak_or_missing_label_evidence": public_count(
                label_evidence.get("weak_or_missing_evidence_label_count")
            ),
            "strict_materializer_suppressed_or_merged": max(
                0, finding_count - materialized_row_count
            ),
            "no_write_materialization_not_run": (
                finding_count
                if finding_count
                and not materialization
                and not bool(result.get("sidecars_written"))
                else 0
            ),
        },
        "strict_gate_relaxed": False,
        "boundary": (
            "aggregate_diagnostic_only_semantic_sidecars_are_navigation_hints_clean_source_is_truth"
        ),
    }


def public_semantic_evidence_diagnostics(diagnostics: Any) -> dict[str, Any]:
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    funnel = diagnostics.get("funnel") if isinstance(diagnostics.get("funnel"), dict) else {}
    reason_buckets = (
        diagnostics.get("materialization_reason_buckets")
        if isinstance(diagnostics.get("materialization_reason_buckets"), dict)
        else {}
    )
    labels = diagnostics.get("per_label") if isinstance(diagnostics.get("per_label"), dict) else {}
    high_risk = (
        diagnostics.get("high_risk_label_families")
        if isinstance(diagnostics.get("high_risk_label_families"), dict)
        else {}
    )
    materialized_counts_available = bool(
        high_risk.get("per_label_materialized_counts_available")
    )
    return {
        "funnel": {
            "selected_candidate_count": public_count(funnel.get("selected_candidate_count")),
            "candidate_thread_count": public_count(funnel.get("candidate_thread_count")),
            "evaluated_candidate_turn_count": public_count(
                funnel.get("evaluated_candidate_turn_count")
            ),
            "unevaluated_candidate_turn_count": public_count(
                funnel.get("unevaluated_candidate_turn_count")
            ),
            "batch_count": public_count(funnel.get("batch_count")),
            "successful_batch_count": public_count(funnel.get("successful_batch_count")),
            "failed_batch_count": public_count(funnel.get("failed_batch_count")),
            "finding_count": public_count(funnel.get("finding_count")),
            "finding_count_with_labels": public_count(funnel.get("finding_count_with_labels")),
            "materialized_row_count": public_count(funnel.get("materialized_row_count")),
            "materialized_thread_count": public_count(funnel.get("materialized_thread_count")),
        },
        "per_label": {
            label: public_semantic_label_diagnostics(labels.get(label))
            for label in SCOPE_LABEL_ORDER
        },
        "high_risk_label_families": {
            "families": list(SCOPE_LABEL_ORDER),
            "per_label_materialized_counts_available": materialized_counts_available,
            "missing_after_materialization": public_ordered_label_list(
                high_risk.get("missing_after_materialization")
            ),
            "finding_not_materialized": public_ordered_label_list(
                high_risk.get("finding_not_materialized")
            ),
            "classification": (
                "still_unsafe_to_restore_without_stronger_source_backed_evidence"
                if materialized_counts_available
                else "not_classified_without_materialization_run"
            ),
        },
        "materialization_reason_buckets": {
            "model_abstained_or_no_finding": public_count(
                reason_buckets.get("model_abstained_or_no_finding")
            ),
            "unevaluated_candidate_turn_count": public_count(
                reason_buckets.get("unevaluated_candidate_turn_count")
            ),
            "skipped_without_refs": public_count(reason_buckets.get("skipped_without_refs")),
            "already_had_semantic_sidecar": public_count(
                reason_buckets.get("already_had_semantic_sidecar")
            ),
            "weak_or_missing_label_evidence": public_count(
                reason_buckets.get("weak_or_missing_label_evidence")
            ),
            "strict_materializer_suppressed_or_merged": public_count(
                reason_buckets.get("strict_materializer_suppressed_or_merged")
            ),
            "no_write_materialization_not_run": public_count(
                reason_buckets.get("no_write_materialization_not_run")
            ),
        },
        "strict_gate_relaxed": False,
        "boundary": (
            "aggregate_diagnostic_only_semantic_sidecars_are_navigation_hints_clean_source_is_truth"
        ),
    }


def public_semantic_label_diagnostics(item: Any) -> dict[str, int]:
    if not isinstance(item, dict):
        item = {}
    return {
        "finding_label_count": public_count(item.get("finding_label_count")),
        "sufficient_evidence_label_count": public_count(
            item.get("sufficient_evidence_label_count")
        ),
        "weak_or_missing_evidence_label_count": public_count(
            item.get("weak_or_missing_evidence_label_count")
        ),
        "materialized_label_count": public_count(item.get("materialized_label_count")),
    }


def with_semantic_evidence_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    result["semantic_evidence_diagnostics"] = semantic_evidence_diagnostics(result)
    return result
