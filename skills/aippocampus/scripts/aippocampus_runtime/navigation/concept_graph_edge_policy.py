"""Edge-quality policy for concept graph navigation."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.navigation.concept_lifecycle import normalize_graph_status

MIN_AUTO_COOCCURS_THREAD_COUNT = 2
BIDIRECTIONAL_EDGE_TYPES = {
    "alias",
    "same_decision_space",
    "contrasts_with",
    "co_occurs",
    "project_topic",
    "related",
}


def automatic_co_occurs_expansion_status(
    *,
    edge_type: str,
    status: str,
    thread_count: int,
) -> tuple[str, str | None]:
    """Park one-off automatic co-occurrence edges before recall expansion."""

    normalized_status = normalize_graph_status(status)
    if (
        edge_type == "co_occurs"
        and normalized_status == "staging"
        and int(thread_count or 0) < MIN_AUTO_COOCCURS_THREAD_COUNT
    ):
        return "parked", "low_source_diversity_auto_co_occurs"
    return normalized_status, None


def quality_gate_bucket(gate: dict[str, Any], edge_type: str, status: str) -> None:
    by_edge_type = gate.setdefault("edge_type_status_counts", {})
    bucket = by_edge_type.setdefault(edge_type, {})
    bucket[status] = int(bucket.get(status, 0)) + 1


def quality_gate_reason(gate: dict[str, Any], reason: str) -> None:
    reasons = gate.setdefault("reason_counts", {})
    reasons[reason] = int(reasons.get(reason, 0)) + 1


def concept_lifecycle_for_edge(*, status: str, lifecycle_reason: str) -> tuple[str, str]:
    if (
        normalize_graph_status(status) == "parked"
        and lifecycle_reason == "low_source_diversity_auto_co_occurs"
    ):
        return "staging", "association_staging_edge_parked_low_source_diversity"
    return status, lifecycle_reason


__all__ = [
    "MIN_AUTO_COOCCURS_THREAD_COUNT",
    "BIDIRECTIONAL_EDGE_TYPES",
    "automatic_co_occurs_expansion_status",
    "concept_lifecycle_for_edge",
    "quality_gate_bucket",
    "quality_gate_reason",
]
