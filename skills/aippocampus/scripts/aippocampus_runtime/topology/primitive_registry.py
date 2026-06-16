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
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("rendered_as_evidence", "output_mode"),
        "no_help_cases": ("explain_only_packet",),
    },
    "macro_as_decision": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:macro_packet+rendered_as_action_instruction",
        "reason_code": "reducer_macro_as_decision",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("packet_type", "rendered_as_action_instruction"),
    },
    "candidate_as_authority": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:candidate_boundary+rendered_as_certainty",
        "reason_code": "reducer_candidate_as_authority",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("packet_type", "rendered_as_certainty"),
    },
    "source_handle_as_fact": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:source_handle+rendered_as_fact",
        "reason_code": "reducer_source_handle_as_fact",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("source_handle", "rendered_as_fact"),
    },
    "explicit_route_cycle": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:route_state+reopen_attempt_count",
        "reason_code": "reducer_explicit_route_cycle",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("route_state", "reopen_attempt_count"),
    },
    "agency_suppression": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:useful_navigation_available+foreground_suppressed",
        "reason_code": "reducer_agency_suppression",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("useful_navigation_available", "foreground_suppressed"),
    },
    "knot_without_unlinking": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:obligation_count+unlinking_move_present",
        "reason_code": "reducer_knot_without_unlinking",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("obligation_count", "unlinking_move_present"),
    },
    "borromean_relation": {
        "provenance": REDUCER_BACKED,
        "reducer": "packet_fields:source_side+user_need_side+agent_agency_side",
        "reason_code": "reducer_borromean_relation",
        "action_time_effect": "load_bearing",
        "load_bearing_allowed": True,
        "required_fields": ("source_refs", "task_anchor", "agent_agency_room"),
    },
    "missing_middle_or_cut_point": {
        "provenance": ANNOTATION_BACKED,
        "annotation_fields": ("missing_middle", "pathlet_gap", "source_gap"),
        "reason_code": "producer_annotated_missing_middle",
        "next_reducer_candidate": True,
        "action_time_effect": "review_hint",
        "load_bearing_allowed": False,
        "producer_contract": "producer_must_mark_missing_middle_or_pathlet_gap",
        "required_fields": ("missing_middle", "pathlet_gap", "source_gap"),
        "no_help_cases": ("vocabulary_only_missing_middle", "single_annotation_without_source_refs"),
    },
    "weak_bridge": {
        "provenance": ANNOTATION_BACKED,
        "annotation_fields": ("shape",),
        "reason_code": "producer_annotated_weak_bridge",
        "next_reducer_candidate": True,
        "action_time_effect": "review_hint",
        "load_bearing_allowed": False,
        "producer_contract": "producer_must_mark_shape_weak_bridge_with_source_overlap",
        "required_fields": ("shape", "source_refs"),
        "no_help_cases": ("weak_bridge_without_independent_sources",),
    },
    "knot": {
        "provenance": VOCABULARY_ONLY,
        "reason_code": "vocabulary_only_knot",
        "action_time_effect": "research_only",
        "load_bearing_allowed": False,
    },
    "unlinking": {
        "provenance": VOCABULARY_ONLY,
        "reason_code": "vocabulary_only_unlinking",
        "action_time_effect": "research_only",
        "load_bearing_allowed": False,
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


def topology_promotion_gate_report() -> dict[str, Any]:
    primitives: list[dict[str, Any]] = []
    for primitive_id, row in sorted(_REGISTRY.items()):
        provenance = str(row.get("provenance") or VOCABULARY_ONLY)
        if provenance == REDUCER_BACKED:
            decision = "reducer_backed_load_bearing"
        elif primitive_id == "missing_middle_or_cut_point":
            decision = "producer_contract_backed_review_only"
        elif primitive_id == "weak_bridge":
            decision = "annotation_only_review"
        else:
            decision = "vocabulary_only_research"
        primitives.append(
            {
                "primitive_id": primitive_id,
                "provenance": provenance,
                "promotion_decision": decision,
                "action_time_effect": row.get("action_time_effect") or "research_only",
                "load_bearing_allowed": bool(row.get("load_bearing_allowed")),
                "required_fields": list(row.get("required_fields") or ()),
                "producer_contract": row.get("producer_contract") or "",
                "required_tests": [
                    "positive_action_time_or_review_case",
                    "no_help_negative_case",
                    "authority_boundary_zero_violation",
                ],
                "no_help_cases": list(row.get("no_help_cases") or ()),
                "reason_code": row.get("reason_code") or "",
            }
        )
    return {
        "kind": "aippocampus_topology_primitive_promotion_gate",
        "schema_version": 1,
        "primitives": primitives,
        "load_bearing_ids": [
            row["primitive_id"] for row in primitives if row["load_bearing_allowed"]
        ],
        "review_only_ids": [
            row["primitive_id"]
            for row in primitives
            if row["action_time_effect"] == "review_hint"
        ],
        "vocabulary_only_ids": [
            row["primitive_id"]
            for row in primitives
            if row["provenance"] == VOCABULARY_ONLY
        ],
        "boundary": {
            "producer_annotations_do_not_become_reducers": True,
            "vocabulary_labels_do_not_change_action_time_behavior": True,
            "topology_is_not_source_evidence": True,
        },
    }


__all__ = [
    "ANNOTATION_BACKED",
    "REDUCER_BACKED",
    "VOCABULARY_ONLY",
    "next_reducer_candidates",
    "primitive_provenance",
    "topology_promotion_gate_report",
    "topology_primitive_registry",
]
