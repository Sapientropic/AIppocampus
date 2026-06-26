#!/usr/bin/env python3
"""Validate coding sequence packets without turning them into truth.

This helper is deliberately a read-model validator for benchmark case packs.
Episode/Arc-like chains preserve ordered evidence and source refs; they do not
assert that an old route is still rejected today. Cognitive-load signals are
bounded routing hints derived from observable collaboration strain, never
emotion, personality, or user-trait facts.
"""

from __future__ import annotations

from typing import Any, Mapping

from aippocampus_runtime.core import dict_or_empty, list_or_empty

SEQUENCE_PACKET_KIND = "aippocampus_sequence_packet"
CHAIN_TRUTH_STATUS = "source_backed_chain_not_current_validity_fact"
LOAD_PROJECTION_BOUNDARY = "routing_caution_not_affect_or_personality_truth"

SAFE_THIN_SOURCE_USES = {"ask", "refresh_sources"}
SAFE_GAPPY_SEQUENCE_USES = {"ask", "refresh_sources"}
VISIBLE_ACTION_USES = {"remind", "warn"}
LOAD_BUCKET_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
FORBIDDEN_LOAD_TERMS = (
    "affect",
    "emotion",
    "emotional",
    "mood",
    "personality",
    "stress_narrative",
    "trait",
    "情绪",
    "人格",
    "性格",
)


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in list_or_empty(value) if str(item or "").strip()]


def _hash_count(values: Any) -> int:
    return sum(1 for value in _string_list(values) if value.startswith("sha256:"))


def _event_kind_sequence(timeline: list[Any]) -> list[str]:
    return [
        str(dict_or_empty(event).get("event_kind") or "").strip()
        for event in timeline
        if str(dict_or_empty(event).get("event_kind") or "").strip()
    ]


def _timeline_source_coverage(timeline: list[Any]) -> float:
    if not timeline:
        return 0.0
    covered = 0
    for event in timeline:
        event_map = dict_or_empty(event)
        if str(event_map.get("source_ref_hash") or "").startswith("sha256:"):
            covered += 1
    return round(covered / len(timeline), 6)


def _edge_order_errors(event_order: list[str], edges: list[Any]) -> list[str]:
    positions = {event: index for index, event in enumerate(event_order)}
    errors: list[str] = []
    for edge in edges:
        edge_map = dict_or_empty(edge)
        start = str(edge_map.get("from") or "").strip()
        end = str(edge_map.get("to") or "").strip()
        relation = str(edge_map.get("relation") or "").strip()
        if not start or not end or not relation:
            errors.append("sequence_edge_incomplete")
            continue
        if start not in positions or end not in positions:
            errors.append("sequence_edge_missing_event")
            continue
        if positions[start] >= positions[end]:
            errors.append("sequence_edge_reversed")
    return errors


def _contains_forbidden_load_term(value: Any) -> bool:
    if isinstance(value, Mapping):
        parts: list[Any] = list(value.keys()) + list(value.values())
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    material = " ".join(str(item) for item in parts if str(item or "").strip()).casefold()
    return any(term in material for term in FORBIDDEN_LOAD_TERMS)


def _total_strain_signals(counts: Mapping[str, Any]) -> int:
    total = 0
    for value in counts.values():
        try:
            total += max(0, int(value))
        except (TypeError, ValueError):
            continue
    return total


def evaluate_case_evidence(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return sanitized sequence/load contract flags for one E2E50 case."""

    chain = dict_or_empty(case.get("episode_chain"))
    packet = dict_or_empty(case.get("sequence_packet"))
    sequence_present = bool(chain or packet)
    sequence_codes: set[str] = set()
    sequence_raw_valid = True
    expected_sequence_valid = bool(chain.get("expected_valid", True))

    timeline = list_or_empty(packet.get("timeline"))
    timeline_order = _event_kind_sequence(timeline)
    chain_order = _string_list(chain.get("event_order"))
    current_assessment = dict_or_empty(packet.get("current_assessment"))
    proposed_use = str(current_assessment.get("proposed_use") or "").strip()
    source_thickness = str(current_assessment.get("source_thickness") or "thin").strip()
    sequence_gaps = _string_list(chain.get("sequence_gaps")) + _string_list(packet.get("sequence_gaps"))

    if sequence_present:
        if not chain:
            sequence_codes.add("sequence_missing_episode_chain")
        if not packet:
            sequence_codes.add("sequence_missing_packet")
        if str(packet.get("kind") or "") != SEQUENCE_PACKET_KIND:
            sequence_codes.add("sequence_packet_kind_invalid")
        if str(chain.get("truth_status") or "") != CHAIN_TRUTH_STATUS:
            sequence_codes.add("sequence_truth_status_invalid")
        if not timeline_order or not chain_order:
            sequence_codes.add("sequence_missing_order")
        elif timeline_order != chain_order:
            sequence_codes.add("sequence_order_mismatch")
        if len(timeline_order) < 2:
            sequence_codes.add("sequence_single_point_trap")
            if proposed_use in VISIBLE_ACTION_USES:
                sequence_codes.add("sequence_single_point_overclaim")
        if sequence_gaps:
            sequence_codes.add("sequence_middle_event_gap")
            if proposed_use not in SAFE_GAPPY_SEQUENCE_USES:
                sequence_codes.add("sequence_gap_overclaim")
        if source_thickness == "thin" and proposed_use not in SAFE_THIN_SOURCE_USES:
            sequence_codes.add("sequence_source_thin_overclaim")
        if str(current_assessment.get("truth_boundary") or "") != "derived_weather_not_source_fact":
            sequence_codes.add("sequence_weather_boundary_missing")
        if _hash_count(chain.get("source_ref_hashes")) <= 0:
            sequence_codes.add("sequence_missing_chain_source_hash")
        if _timeline_source_coverage(timeline) < 1.0:
            sequence_codes.add("sequence_missing_timeline_source_hash")
        sequence_codes.update(_edge_order_errors(timeline_order, list_or_empty(chain.get("causal_edges"))))

        cannot_claim = set(_string_list(packet.get("cannot_claim")))
        if "current_validity_requires_source_reopen" not in cannot_claim:
            sequence_codes.add("sequence_current_validity_boundary_missing")
        sequence_raw_valid = not sequence_codes

    sequence_contract_ok = (sequence_raw_valid == expected_sequence_valid) if sequence_present else True
    sequence_blockers = sorted(sequence_codes if not sequence_contract_ok else set())

    episode_kind = str(chain.get("episode_kind") or "")
    current_validity = str(chain.get("current_validity") or "")
    behavior_only_rejection_applicable = (
        sequence_present
        and episode_kind == "rejected_route_arc"
        and str(chain.get("origin") or "") == "behavior_event"
    )
    behavior_only_rejection_passed = (
        behavior_only_rejection_applicable
        and sequence_contract_ok
        and any(kind in {"failed_check", "tool_failure"} for kind in timeline_order)
    )
    supersession_applicable = sequence_present and episode_kind in {
        "supersession_arc",
        "temporary_concern_arc",
    }
    supersession_passed = (
        supersession_applicable
        and sequence_contract_ok
        and current_validity in {"superseded", "local_only", "needs_reopen"}
        and proposed_use != "warn"
    )

    load = dict_or_empty(case.get("cognitive_load"))
    load_present = bool(load)
    load_codes: set[str] = set()
    bucket = str(load.get("load_boost_bucket") or "none").strip()
    bucket_rank = LOAD_BUCKET_RANK.get(bucket, -1)
    counts = dict_or_empty(load.get("strain_signal_counts"))
    strain_total = _total_strain_signals(counts)
    false_positive = False
    decay = dict_or_empty(load.get("decay"))
    decay_applied = bool(decay.get("applied") or decay.get("invalidated_by_supersession"))
    overpersonalization_count = 0
    load_source_truth_override = False

    if load_present:
        if bucket_rank < 0:
            load_codes.add("load_boost_bucket_invalid")
        false_positive = strain_total <= 0 and bucket_rank >= LOAD_BUCKET_RANK["medium"]
        if false_positive:
            load_codes.add("load_weight_false_positive")
        if not decay_applied:
            load_codes.add("load_decay_missing")
        if str(load.get("projection_boundary") or "") != LOAD_PROJECTION_BOUNDARY:
            load_codes.add("load_projection_boundary_missing")
        if _contains_forbidden_load_term(load.get("load_reason_codes")) or _contains_forbidden_load_term(
            load.get("projection_claims")
        ):
            overpersonalization_count = 1
            load_codes.add("overpersonalization_from_load_signal")
        load_source_truth_override = (
            sequence_present
            and source_thickness == "thin"
            and proposed_use not in SAFE_THIN_SOURCE_USES
            and bucket_rank > 0
        )
        if load_source_truth_override:
            load_codes.add("load_source_truth_override")

    return {
        "sequence_packet_present": sequence_present,
        "sequence_contract_ok": sequence_contract_ok,
        "sequence_blocker_codes": sequence_blockers,
        "order_sensitivity_applicable": sequence_present,
        "order_sensitivity_passed": sequence_contract_ok,
        "middle_event_gap_applicable": bool(sequence_gaps),
        "middle_event_gap_detected": "sequence_middle_event_gap" in sequence_codes,
        "single_point_trap_applicable": sequence_present and len(timeline_order) < 2,
        "single_point_overclaim": "sequence_single_point_overclaim" in sequence_codes,
        "supersession_applicable": supersession_applicable,
        "supersession_passed": supersession_passed,
        "source_ref_chain_coverage": _timeline_source_coverage(timeline),
        "behavior_only_rejection_applicable": behavior_only_rejection_applicable,
        "behavior_only_rejection_passed": behavior_only_rejection_passed,
        "cognitive_load_sidecar_present": load_present,
        "load_contract_ok": not load_codes,
        "load_blocker_codes": sorted(load_codes),
        "load_boost_bucket": bucket,
        "strain_signal_count_total": strain_total,
        "load_reason_code_count": len(_string_list(load.get("load_reason_codes"))),
        "load_weight_false_positive": false_positive,
        "load_decay_applied": decay_applied,
        "overpersonalization_from_load_signal_count": overpersonalization_count,
        "load_source_truth_override": load_source_truth_override,
    }
