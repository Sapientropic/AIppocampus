from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypeAlias

from aippocampus_runtime.macro import momentum, perturbation, three_powers
from aippocampus_runtime.macro.hexagram import change_lines

RuntimeRole: TypeAlias = Literal[
    "recall_fanout",
    "recheck_timing",
    "dream_candidate_generation",
    "telepathy_handoff_compatibility",
    "aippo_clause_maturation",
    "compact_foreground_packet",
    "deepen_explain_only",
    "research_only",
]

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
SCHEMA_VERSION = "yi-runtime-interface-audit-v0"

DISCUSSION_LINKS = {
    "dynamics": "#1210",
    "topology": "#1262",
    "local_global_gluing": "#1270",
}


def _primitive(
    primitive_id: str,
    label: str,
    *,
    roles: tuple[RuntimeRole, ...],
    runtime_surface: tuple[str, ...],
    non_goals: tuple[str, ...],
    foreground_emitted: bool = False,
    interface_layer: str = "dynamics",
    usefulness_status: str = "fixture_supported",
) -> dict[str, object]:
    return {
        "primitive_id": primitive_id,
        "label": label,
        "roles": list(roles),
        "runtime_surface": list(runtime_surface),
        "interface_layer": interface_layer,
        "foreground_emitted": foreground_emitted,
        "usefulness_status": usefulness_status,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "non_goals": list(non_goals),
    }


def primitive_role_table() -> list[dict[str, object]]:
    """Return the canonical runtime-role audit for Yi macro primitives."""
    return [
        _primitive(
            "hexagram_state_six_bit",
            "hexagram state / six-bit bottom-to-top convention",
            roles=("deepen_explain_only",),
            runtime_surface=("macro.hexagram", "macro.state"),
            non_goals=("line_text_reading", "project_truth", "personality_or_fate_claim"),
        ),
        _primitive(
            "changing_lines",
            "changing lines",
            roles=("recall_fanout", "deepen_explain_only"),
            runtime_surface=("macro.hexagram.change_lines", "macro.perturbation"),
            non_goals=("symbolic_advice", "evidence_without_source_reopen"),
        ),
        _primitive(
            "hamming_perturbation_width",
            "Hamming distance / perturbation width",
            roles=("recall_fanout", "compact_foreground_packet"),
            runtime_surface=("macro.perturbation", "agent macro packet"),
            non_goals=("quality_score", "source_truth", "unbounded_candidate_expansion"),
            foreground_emitted=True,
        ),
        _primitive(
            "nuclear_opposite_reverse_transforms",
            "nuclear / opposite / reverse transforms",
            roles=("deepen_explain_only",),
            runtime_surface=("macro.hexagram.public_hexagram_projection",),
            non_goals=("foreground_symbolic_prose", "route_weight_change_without_fixture_lift"),
            usefulness_status="not_route_useful_yet",
        ),
        _primitive(
            "king_wen_sequence_movement",
            "King Wen sequence movement",
            roles=("recheck_timing", "deepen_explain_only"),
            runtime_surface=("macro.stage_tracker",),
            non_goals=("project_law", "automatic_stage_mutation", "claim_authority"),
        ),
        _primitive(
            "three_powers_route_facets",
            "Three Powers route facets",
            roles=("recall_fanout", "telepathy_handoff_compatibility"),
            runtime_surface=("macro.three_powers",),
            non_goals=("source_evidence", "hard_assignment", "identity_or_role_truth"),
            interface_layer="topology",
        ),
        _primitive(
            "shi_ying_role_positioning",
            "世 / 应 role positioning",
            roles=("telepathy_handoff_compatibility", "deepen_explain_only"),
            runtime_surface=("macro.state.relation_position", "macro.line_topology"),
            non_goals=("agent_personality_truth", "user_intent_inference"),
            interface_layer="topology",
        ),
        _primitive(
            "xiao_xi_momentum",
            "消息卦 momentum",
            roles=("recheck_timing", "compact_foreground_packet"),
            runtime_surface=("macro.momentum", "agent macro packet"),
            non_goals=("energy_score", "metaphysical_project_state", "evidence_score"),
            foreground_emitted=True,
        ),
        _primitive(
            "internal_line_topology",
            "乘 / 承 / 比 / 应 internal line topology",
            roles=("telepathy_handoff_compatibility", "deepen_explain_only"),
            runtime_surface=("macro.line_topology", "macro.three_powers"),
            non_goals=("ranking_weight_change", "source_support", "mathematical_topology_claim"),
            interface_layer="topology",
        ),
        _primitive(
            "proper_or_improper_position",
            "当位 / 不当位",
            roles=("research_only",),
            runtime_surface=("none",),
            non_goals=("foreground_signal", "route_control", "claim_support"),
            interface_layer="research",
            usefulness_status="unproven_concept",
        ),
    ]


def _roles_by_id() -> dict[str, dict[str, object]]:
    return {str(item["primitive_id"]): item for item in primitive_role_table()}


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _roles(row: Mapping[str, object]) -> tuple[str, ...]:
    value = row.get("roles")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _truthy(value: object) -> bool:
    return bool(value)


def _int(value: object) -> int:
    if not isinstance(value, (str, bytes, int, float)):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _foreground_guardrail_violations(rows: Sequence[Mapping[str, object]]) -> list[str]:
    violations: list[str] = []
    for row in rows:
        if not row.get("foreground_emitted"):
            continue
        primitive_id = str(row.get("primitive_id"))
        if row.get("action_grammar") != ACTION_GRAMMAR:
            violations.append(f"{primitive_id}:missing_direction_only_action_grammar")
        if row.get("authority_level") != AUTHORITY_LEVEL:
            violations.append(f"{primitive_id}:authority_upgrade")
        if row.get("claim_permission") != CLAIM_PERMISSION:
            violations.append(f"{primitive_id}:claim_permission_upgrade")
        if row.get("fact_claim_allowed") is not False:
            violations.append(f"{primitive_id}:fact_claim_allowed")
    return violations


def _hamming_and_momentum_fixture() -> dict[str, object]:
    local_shift = perturbation.build_perturbation_packet("乾", change_lines("乾", (1,)))
    large_shift = perturbation.build_perturbation_packet("乾", change_lines("乾", (1, 2, 3, 4)))
    rising = momentum.build_momentum_block({"support_delta": 0.2})
    decaying = momentum.build_momentum_block({"staleness_delta": 0.2})
    local_fanout = _as_mapping(local_shift.get("fanout_hint"))
    large_fanout = _as_mapping(large_shift.get("fanout_hint"))
    local_limit = _int(local_fanout.get("recommended_candidate_limit"))
    large_limit = _int(large_fanout.get("recommended_candidate_limit"))
    return {
        "kind": "yi_hamming_momentum_behavior_fixture",
        "local_shift": {
            "band": local_shift["band"],
            "candidate_limit": local_limit,
            "authority_level": local_shift["authority_level"],
            "fact_claim_allowed": local_shift["fact_claim_allowed"],
        },
        "large_shift": {
            "band": large_shift["band"],
            "candidate_limit": large_limit,
            "authority_level": large_shift["authority_level"],
            "fact_claim_allowed": large_shift["fact_claim_allowed"],
        },
        "rising_momentum": {
            "phase": rising["phase"],
            "recheck_on": rising["recheck_on"],
            "stale_after_days": momentum.stale_after_days_for_momentum(rising, default=30),
            "authority_level": rising["authority_level"],
            "fact_claim_allowed": rising["fact_claim_allowed"],
        },
        "decaying_momentum": {
            "phase": decaying["phase"],
            "recheck_on": decaying["recheck_on"],
            "stale_after_days": momentum.stale_after_days_for_momentum(decaying, default=30),
            "authority_level": decaying["authority_level"],
            "fact_claim_allowed": decaying["fact_claim_allowed"],
        },
        "hamming_changes_fanout": large_limit > local_limit,
        "momentum_changes_recheck": bool(decaying["recheck_on"]) and not rising["recheck_on"],
        "authority_level": AUTHORITY_LEVEL,
        "fact_claim_allowed": False,
    }


def _topology_sheaf_consumption_fixture() -> dict[str, object]:
    large_shift = perturbation.build_perturbation_packet("乾", change_lines("乾", (1, 2, 3, 4)))
    fanout = three_powers.apply_three_powers_fanout(
        "handoff current workflow route",
        (
            {"route_id": "source-route", "source_family": "source"},
            {"route_id": "workflow-route", "source_family": "handoff"},
            {"route_id": "claim-route", "source_family": "product_claim"},
        ),
        active_layer="human",
        perturbation_packet=large_shift,
        topology_hexagram="坎",
        base_candidate_limit=1,
    )
    topology = fanout.get("topology_diagnostics")
    topology_fact_claim = (
        bool(topology.get("fact_claim_allowed"))
        if isinstance(topology, Mapping)
        else True
    )
    return {
        "kind": "yi_topology_sheaf_consumption_fixture",
        "input_signals": {
            "yi_active_layer": fanout["active_layer"],
            "yi_perturbation_band": large_shift["band"],
            "topology_reason_codes": topology.get("reason_codes") if isinstance(topology, Mapping) else [],
        },
        "consumer_contract": {
            "topology_discussion": DISCUSSION_LINKS["topology"],
            "sheaf_discussion": DISCUSSION_LINKS["local_global_gluing"],
            "local_view_signal": "active_layer_human",
            "global_glue_boundary": "source_reopen_required_before_claim",
        },
        "selected_route_ids": fanout["selected_route_ids"],
        "authority_level": fanout["authority_level"],
        "claim_permission": fanout["claim_permission"],
        "fact_claim_allowed": bool(fanout["fact_claim_allowed"]) or topology_fact_claim,
    }


def _deepen_only_fixture(rows_by_id: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    row = rows_by_id["nuclear_opposite_reverse_transforms"]
    return {
        "kind": "yi_deepen_explain_only_fixture",
        "primitive_id": row["primitive_id"],
        "roles": row["roles"],
        "foreground_emitted": row["foreground_emitted"],
        "why": "structural transforms are available for source-open explanation, but no route-usefulness fixture justifies foreground or ranking use",
        "authority_level": row["authority_level"],
        "fact_claim_allowed": row["fact_claim_allowed"],
    }


def _research_only_fixture(rows_by_id: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    row = rows_by_id["proper_or_improper_position"]
    return {
        "kind": "yi_research_only_fixture",
        "primitive_id": row["primitive_id"],
        "roles": row["roles"],
        "why": "proper-position semantics are not runtime-ready until a fixture proves they improve route usefulness without adding symbolic foreground prose",
        "authority_level": row["authority_level"],
        "fact_claim_allowed": row["fact_claim_allowed"],
    }


def build_yi_runtime_interface_audit_report() -> dict[str, object]:
    rows = primitive_role_table()
    rows_by_id = _roles_by_id()
    foreground_violations = _foreground_guardrail_violations(rows)
    hamming_momentum = _hamming_and_momentum_fixture()
    topology_sheaf = _topology_sheaf_consumption_fixture()
    deepen_only = _deepen_only_fixture(rows_by_id)
    research_only = _research_only_fixture(rows_by_id)
    role_counts = {
        role: sum(1 for row in rows if role in _roles(row))
        for role in (
            "recall_fanout",
            "recheck_timing",
            "dream_candidate_generation",
            "telepathy_handoff_compatibility",
            "aippo_clause_maturation",
            "compact_foreground_packet",
            "deepen_explain_only",
            "research_only",
        )
    }
    metrics = {
        "primitive_count": len(rows),
        "foreground_guardrail_violation_count": len(foreground_violations),
        "deepen_explain_only_fixture_count": int(
            "deepen_explain_only" in _roles(deepen_only)
            and deepen_only["foreground_emitted"] is False
        ),
        "research_only_fixture_count": int("research_only" in _roles(research_only)),
        "hamming_changes_fanout_count": int(
            _truthy(hamming_momentum["hamming_changes_fanout"])
        ),
        "momentum_changes_recheck_count": int(
            _truthy(hamming_momentum["momentum_changes_recheck"])
        ),
        "topology_sheaf_authority_upgrade_count": int(
            topology_sheaf["authority_level"] != AUTHORITY_LEVEL
            or topology_sheaf["fact_claim_allowed"] is not False
        ),
    }
    return {
        "kind": "yi_runtime_interface_audit_report",
        "schema_version": SCHEMA_VERSION,
        "ok": (
            metrics["primitive_count"] >= 10
            and metrics["foreground_guardrail_violation_count"] == 0
            and metrics["deepen_explain_only_fixture_count"] >= 1
            and metrics["research_only_fixture_count"] >= 1
            and metrics["hamming_changes_fanout_count"] >= 1
            and metrics["momentum_changes_recheck_count"] >= 1
            and metrics["topology_sheaf_authority_upgrade_count"] == 0
        ),
        "discussion_links": dict(DISCUSSION_LINKS),
        "design_rule": (
            "Yi says how the situation moves; topology says whether relations hold; "
            "sheaf-style local/global gluing decides whether local views can compose."
        ),
        "primitives": rows,
        "role_counts": role_counts,
        "fixtures": {
            "deepen_explain_only": deepen_only,
            "research_only": research_only,
            "hamming_and_momentum": hamming_momentum,
            "topology_sheaf_consumption": topology_sheaf,
        },
        "metrics": metrics,
        "violations": foreground_violations,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "cannot_claim": [
            "macro_orientation_as_source_evidence",
            "divination_reading",
            "personality_or_fate_inference",
            "route_weight_change_from_research_only_concept",
        ],
    }


__all__ = [
    "ACTION_GRAMMAR",
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "DISCUSSION_LINKS",
    "RuntimeRole",
    "SCHEMA_VERSION",
    "build_yi_runtime_interface_audit_report",
    "primitive_role_table",
]
