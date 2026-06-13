"""Cross-grain Yi/Macro projection helpers.

This module is deliberately explanatory: it names how existing deterministic
macro grains relate without adding symbolic advice, source support, ranking
weight, or macro-state mutation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.macro import hexagram, line_topology, transform_orbit
from aippocampus_runtime.macro.perturbation import build_perturbation_packet
from aippocampus_runtime.ops.route_readiness import safe_source_refs

AUTHORITY_LEVEL = "navigation_only"
CLAIM_PERMISSION = "no_claim_before_reopen"


def _three_powers_projection() -> list[dict[str, object]]:
    rows: dict[str, dict[str, Any]] = {
        "earth": {"layer": "earth", "line_span": [1, 2], "reason_codes": []},
        "human": {"layer": "human", "line_span": [3, 4], "reason_codes": []},
        "heaven": {"layer": "heaven", "line_span": [5, 6], "reason_codes": []},
    }
    for axis in line_topology.axis_mapping():
        layer = str(axis.get("layer") or "")
        if layer in rows:
            rows[layer]["reason_codes"].append(str(axis.get("axis_id") or ""))
    return [rows[layer] for layer in ("earth", "human", "heaven")]


def _six_line_projection(value: hexagram.HexagramRef) -> dict[str, object]:
    diagnostics = line_topology.build_line_topology_diagnostics(value)
    raw_broken = diagnostics.get("broken_couplings")
    broken_values = raw_broken if isinstance(raw_broken, Sequence) and not isinstance(raw_broken, str) else []
    broken = [item for item in broken_values if isinstance(item, Mapping)]
    return {
        "grain": "six_line_topology",
        "hexagram": diagnostics["hexagram"],
        "broken_couplings": broken,
        "reason_codes": diagnostics["reason_codes"],
        "projects_to_three_powers": [
            {
                "pair_id": item.get("pair_id"),
                "lower_layer": item.get("lower_layer"),
                "upper_layer": item.get("upper_layer"),
                "reason_code": item.get("diagnostic"),
            }
            for item in broken
        ],
        "ranking_weight_changes": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
    }


def _trigram_projection(value: hexagram.HexagramRef) -> dict[str, object]:
    item = hexagram.resolve_hexagram(value)
    return {
        "grain": "trigram_shape",
        "lower_trigram": item.lower_trigram,
        "upper_trigram": item.upper_trigram,
        "participation": "atmosphere_or_shape_hint_for_deepen_explain",
        "not_full_hexagram_state": True,
        "not_source_support": True,
        "foreground_emitted": False,
    }


def _orbit_projection(source: hexagram.HexagramRef, target: hexagram.HexagramRef | None) -> dict[str, object]:
    if target is None:
        item = hexagram.resolve_hexagram(source)
        return {
            "grain": "sixty_four_state_orbit",
            "source": {"name": item.name, "number": item.number},
            "orbit_members": transform_orbit.reversible_orbit_members(item),
            "relation": "source_orbit_inventory",
            "default_ranking_effect": "none",
        }
    diagnostic = transform_orbit.macro_transform_orbit_diagnostic(source, target)
    return {
        "grain": "sixty_four_state_orbit",
        "source": diagnostic["source"],
        "target": diagnostic["target"],
        "relation": diagnostic["relation"],
        "same_reversible_orbit": diagnostic["same_reversible_orbit"],
        "line_flip_adjacency": diagnostic["line_flip_adjacency"],
        "default_ranking_effect": diagnostic["default_ranking_effect"],
    }


def project_cross_grain_projection(
    source: hexagram.HexagramRef,
    *,
    target: hexagram.HexagramRef | None = None,
) -> dict[str, object]:
    """Return a public-safe cross-grain explain packet for #1391."""

    return {
        "kind": "yi_macro_cross_grain_projection",
        "three_powers_projection": _three_powers_projection(),
        "six_line_projection": _six_line_projection(source),
        "trigram_projection": _trigram_projection(source),
        "transform_orbit_projection": _orbit_projection(source, target),
        "consumer_contract": {
            "recall_deepen_explain_may_use_reason_codes": True,
            "foreground_symbolic_prose_allowed": False,
            "source_reopen_required_before_claim": True,
        },
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "ranking_weight_changes": False,
    }


def macro_transition_record(
    source: hexagram.HexagramRef,
    changing_lines: Iterable[int],
    *,
    source_refs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, object]:
    """Project 本卦 -> changing lines -> 之卦 as a lifecycle record."""

    positions = tuple(changing_lines)
    start = hexagram.resolve_hexagram(source)
    target = hexagram.change_lines(start, positions)
    packet = build_perturbation_packet(start, target)
    band = str(packet["band"])
    raw_reasons = packet.get("reason_codes")
    reason_codes = list(raw_reasons) if isinstance(raw_reasons, Sequence) and not isinstance(raw_reasons, str) else []
    return {
        "kind": "macro_change_line_transition",
        "source_hexagram": {"name": start.name, "number": start.number},
        "changed_lines": list(positions),
        "target_hexagram": {"name": target.name, "number": target.number},
        "perturbation_band": band,
        "source_refs": safe_source_refs(list(source_refs)),
        "reason_codes": reason_codes,
        "review_policy": {
            "requires_conflict_review_before_action": bool(packet.get("conflict_review_required")),
            "may_mutate_macro_state": False,
            "explicit_project_source_event_required_for_state_write": True,
        },
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "foreground_advice_allowed": False,
    }


def nuclear_basin_explain_policy(source: hexagram.HexagramRef) -> dict[str, object]:
    dynamics = transform_orbit.nuclear_dynamics(source)
    return {
        "kind": "macro_nuclear_basin_explain_policy",
        "decision": "explain_only_lock",
        "source": dynamics["source"],
        "basin_id": dynamics["basin_id"],
        "cycle": dynamics["cycle"],
        "projection_kind": dynamics["projection_kind"],
        "route_merge_allowed": False,
        "ranking_weight_changes": False,
        "source_support_from_basin_membership": False,
        "foreground_emitted": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
    }


__all__ = [
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "macro_transition_record",
    "nuclear_basin_explain_policy",
    "project_cross_grain_projection",
]
