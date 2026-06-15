"""Topology primitive provenance registry.

The topology layer has two safe jobs: run small reducers where a relation can
be derived from packet fields, and preserve producer annotations where the
producer already named a shape. Annotation-backed rows are useful, but they are
not independent topology discovery and should not be reported with reducer
reason codes.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

REDUCER_BACKED = "reducer_backed"
ANNOTATION_BACKED = "annotation_backed"
VOCABULARY_ONLY = "vocabulary_only"

_REGISTRY: dict[str, dict[str, Any]] = {
    "navigation_as_claim": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:rendered_as_evidence+navigation_boundary",
        "reason_code": "reducer_navigation_as_claim",
    },
    "macro_as_decision": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:macro_packet+rendered_as_action_instruction",
        "reason_code": "reducer_macro_as_decision",
    },
    "candidate_as_authority": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:candidate_boundary+rendered_as_certainty",
        "reason_code": "reducer_candidate_as_authority",
    },
    "source_handle_as_fact": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:source_handle+rendered_as_fact",
        "reason_code": "reducer_source_handle_as_fact",
    },
    "explicit_route_cycle": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:route_state+reopen_attempt_count",
        "reason_code": "reducer_explicit_route_cycle",
    },
    "agency_suppression": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:useful_navigation_available+foreground_suppressed",
        "reason_code": "reducer_agency_suppression",
    },
    "knot_without_unlinking": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:obligation_count+unlinking_move_present",
        "reason_code": "reducer_knot_without_unlinking",
    },
    "borromean_relation": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:source_side+user_need_side+agent_agency_side",
        "reason_code": "reducer_borromean_relation",
    },
    "missing_middle_or_cut_point": {
        "provenance": ANNOTATION_BACKED,
        "annotation_fields": ("missing_middle", "pathlet_gap", "source_gap"),
        "reason_code": "producer_annotated_missing_middle",
        "next_reducer_candidate": True,
    },
    "weak_bridge": {
        "provenance": ANNOTATION_BACKED,
        "annotation_fields": ("shape",),
        "reason_code": "producer_annotated_weak_bridge",
        "next_reducer_candidate": True,
    },
    "knot": {
        "provenance": VOCABULARY_ONLY,
        "reason_code": "vocabulary_only_knot",
    },
    "unlinking": {
        "provenance": VOCABULARY_ONLY,
        "reason_code": "vocabulary_only_unlinking",
    },
}


def topology_primitive_registry() -> dict[str, dict[str, Any]]:
    return deepcopy(_REGISTRY)


def primitive_provenance(primitive_id: str) -> str:
    row = _REGISTRY.get(primitive_id)
    return str(row.get("provenance")) if row else VOCABULARY_ONLY


def next_reducer_candidates() -> list[str]:
    return sorted(
        primitive_id
        for primitive_id, row in _REGISTRY.items()
        if row.get("next_reducer_candidate")
    )


__all__ = [
    "ANNOTATION_BACKED",
    "REDUCER_BACKED",
    "VOCABULARY_ONLY",
    "next_reducer_candidates",
    "primitive_provenance",
    "topology_primitive_registry",
]
