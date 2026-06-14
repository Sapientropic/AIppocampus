#!/usr/bin/env python3
"""Public-safe fixture catalog for local/global compatibility."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.aippo import working_contract
from aippocampus_runtime.dream import topology_scout
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.navigation import macro_router_interface
from aippocampus_runtime.ops import (
    packet_topology_diagnostic,
    telepathy_coordination_packet,
)


def _successful_glue_sections() -> list[dict[str, Any]]:
    entry = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="蹇",
        changing_lines=(3,),
        source_refs=({"source_id": "issue:#1272"},),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="人",
        momentum={"basis": {"support_delta": 0.2}},
    )
    macro = macro_router_interface.build_macro_router_context(entry)
    macro.update(
        {
            "scope": "project:AIppocampus#issue:1272",
            "source_ids": ["issue:#1272"],
            "topic_epoch": "2026w24",
        }
    )
    telepathy = telepathy_coordination_packet.normalize_coordination_packet(
        {
            "case_id": "macro_handoff",
            "scope": "project:AIppocampus#issue:1272",
            "coordination_mode": "handoff",
            "status": "ready_for_handoff",
            "source_support": "reopenable_route",
            "handoff_readiness": "route_ready",
            "owner": "codex-public",
        }
    )
    telepathy.update({"source_ids": ["issue:#1272"], "topic_epoch": "2026w24"})
    memory = {
        "case_id": "route_packet_1272",
        "kind": "memory_packet",
        "scope": "project:AIppocampus#issue:1272",
        "source_ids": ["issue:#1272"],
        "topic_epoch": "2026w24",
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
    }
    return [memory, macro, telepathy]


def _dream_partial_sections() -> list[dict[str, Any]]:
    dream = topology_scout.candidate_or_rejection(
        {
            "case_id": "weak_bridge_between_issues",
            "shape": "weak_bridge",
            "source_anchors": ["issue:#1263", "issue:#1270"],
        }
    )
    dream["scope"] = "project:AIppocampus#issue:1270"
    memory = {
        "case_id": "route_packet_1270",
        "kind": "memory_packet",
        "scope": "project:AIppocampus#issue:1270",
        "source_ids": ["issue:#1285"],
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
    }
    return [dream, memory]


def _stale_obstruction_sections() -> list[dict[str, Any]]:
    topology = packet_topology_diagnostic.evaluate_packet(
        {
            "case_id": "repeated_failed_route_cycle",
            "packet_type": "route_packet",
            "route_state": "rejected",
            "reopen_attempt_count": 3,
            "repeated_failed_route": True,
        }
    )
    topology.update(
        {
            "scope": "project:AIppocampus#issue:1188",
            "source_ids": ["issue:#1188"],
            "status": "rejected",
        }
    )
    memory = {
        "case_id": "stale_route_1188",
        "kind": "memory_packet",
        "scope": "project:AIppocampus#issue:1188",
        "source_ids": ["issue:#1188"],
        "route_state": "stale",
        "authority_level": "navigation_only",
    }
    return [topology, memory]


def _privacy_blocked_sections() -> list[dict[str, Any]]:
    private_packet = telepathy_coordination_packet.normalize_coordination_packet(
        {
            "case_id": "privacy_blocked_packet",
            "scope": "private_scope_fixture",
            "coordination_mode": "blocked",
            "status": "blocked",
            "source_support": "ignore_or_blocked",
            "boundary_flags": ["no_private_source", "no_shared_cot"],
            "owner": "codex-private",
        }
    )
    private_packet.update({"privacy_domain": "private", "source_ids": ["issue:#1264"]})
    public_packet = {
        "case_id": "public_route_1264",
        "kind": "memory_packet",
        "scope": "project:AIppocampus#issue:1264",
        "source_ids": ["issue:#1264"],
        "privacy_domain": "public",
        "authority_level": "navigation_only",
    }
    return [private_packet, public_packet]


def _authority_escalation_sections() -> list[dict[str, Any]]:
    contract = working_contract.build_project_workflow_public_safe_contract()
    activation = working_contract.activation_packet_from_working_contract(
        contract, task="issue closeout"
    )
    activation.update(
        {
            "case_id": "aippo_activation_escalation_attempt",
            "scope": "project:AIppocampus#issue:1285",
            "source_ids": ["issue:#1285"],
            "requested_claim_permission": "source_open",
        }
    )
    dream = topology_scout.candidate_or_rejection(
        {
            "case_id": "dream_candidate_escalation_guard",
            "shape": "knot",
            "source_anchors": ["issue:#1285"],
            "obligation_count": 3,
            "unlinking_move_present": False,
        }
    )
    dream.update(
        {
            "scope": "project:AIppocampus#issue:1285",
            "requested_claim_permission": "bounded_claim_allowed",
        }
    )
    return [activation, dream]


def _shared_vocabulary_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "vocab_memory",
            "kind": "memory_packet",
            "scope": "project:AIppocampus",
            "route_topic": "dream topology bridge",
            "source_ids": [],
            "authority_level": "navigation_only",
        },
        {
            "case_id": "vocab_dream",
            "kind": "dream_topology_candidate",
            "scope": "project:Different",
            "route_topic": "dream topology bridge",
            "source_anchors": [],
            "authority": "dream_synthesized_candidate_not_fact",
        },
    ]


def _broad_obstruction_with_narrowed_glue_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "dream_broad",
            "kind": "dream_topology_candidate",
            "scope": "project:AIppocampus#area:dream",
            "restriction_path": [
                "project:AIppocampus",
                "project:AIppocampus#thread_family:runtime",
            ],
            "source_ids": ["issue:#1270"],
            "shape": "weak_bridge",
        },
        {
            "case_id": "macro_broad",
            "kind": "macro_router_context",
            "scope": "project:AIppocampus#area:macro",
            "restriction_path": [
                "project:AIppocampus",
                "project:AIppocampus#thread_family:runtime",
            ],
            "source_ids": ["issue:#1270"],
            "shape": "weak_bridge",
        },
    ]


def _narrowing_failed_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "agent_a",
            "kind": "memory_packet",
            "scope": "project:AIppocampus#agent:a",
            "restriction_path": ["project:AIppocampus#agent:a"],
            "source_ids": ["issue:#1270-a"],
            "shape": "weak_bridge",
        },
        {
            "case_id": "agent_b",
            "kind": "telepathy_coordination_packet",
            "scope": "project:AIppocampus#agent:b",
            "restriction_path": ["project:AIppocampus#agent:b"],
            "source_ids": ["issue:#1270-b"],
            "shape": "weak_bridge",
        },
    ]


def _time_window_mismatch_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "old_window",
            "kind": "memory_packet",
            "scope": "project:AIppocampus#issue:1270",
            "source_ids": ["issue:#1270"],
            "section_time_window": {
                "start": "2026-06-13T00:00:00Z",
                "end": "2026-06-13T01:00:00Z",
            },
        },
        {
            "case_id": "new_window",
            "kind": "macro_router_context",
            "scope": "project:AIppocampus#issue:1270",
            "source_ids": ["issue:#1270"],
            "source_coverage_time": {
                "start": "2026-06-14T00:00:00Z",
                "end": "2026-06-14T01:00:00Z",
            },
        },
    ]


def _missing_middle_cut_point_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "cut_a",
            "kind": "dream_topology_candidate",
            "scope": "project:AIppocampus#thread:a",
            "source_ids": [],
            "shape": "cut_point",
        },
        {
            "case_id": "cut_b",
            "kind": "memory_packet",
            "scope": "project:AIppocampus#thread:b",
            "source_ids": [],
            "shape": "cut_point",
        },
    ]


def _conflict_obstruction_sections() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "conflict_a",
            "kind": "dream_topology_candidate",
            "scope": "project:AIppocampus#issue:1270",
            "source_ids": ["issue:#1270"],
            "shape": "cut_point",
            "obstruction_kind": "conflict",
        },
        {
            "case_id": "conflict_b",
            "kind": "memory_packet",
            "scope": "project:AIppocampus#issue:1270",
            "source_ids": [],
            "shape": "cut_point",
            "obstruction_kind": "conflict",
        },
    ]


def fixture_compatibility_cases() -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        ("successful_macro_telepathy_glue", _successful_glue_sections()),
        ("dream_topology_partial_glue", _dream_partial_sections()),
        ("stale_topology_obstruction", _stale_obstruction_sections()),
        ("privacy_blocked_boundary", _privacy_blocked_sections()),
        ("authority_escalation_attempt", _authority_escalation_sections()),
        ("shared_vocabulary_only", _shared_vocabulary_sections()),
        (
            "broad_obstruction_with_narrowed_glue",
            _broad_obstruction_with_narrowed_glue_sections(),
        ),
        ("restriction_narrowing_failed", _narrowing_failed_sections()),
        ("time_window_mismatch", _time_window_mismatch_sections()),
        ("missing_middle_cut_point", _missing_middle_cut_point_sections()),
        ("conflict_obstruction", _conflict_obstruction_sections()),
    ]


def fixture_adjudication_rows() -> list[dict[str, str]]:
    return [
        {
            "case_id": "useful_obstruction",
            "diagnostic_result": "obstruction",
            "adjudication_label": "useful_obstruction",
        },
        {
            "case_id": "false_glue",
            "diagnostic_result": "glued_route",
            "adjudication_label": "false_glue",
        },
        {
            "case_id": "no_help",
            "diagnostic_result": "obstruction",
            "adjudication_label": "no_help",
        },
        {
            "case_id": "ambiguous",
            "diagnostic_result": "partial_glue",
            "adjudication_label": "ambiguous_correlation",
        },
    ]
