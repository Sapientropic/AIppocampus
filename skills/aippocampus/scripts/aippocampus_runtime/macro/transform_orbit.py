"""Deterministic transform-orbit diagnostics for macro hexagram states."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any, Literal

from aippocampus_runtime.macro import hexagram

ReversibleOperation = Literal["opposite", "reverse"]
RelationLabel = Literal[
    "same_state",
    "same_reversible_orbit",
    "adjacent_flip",
    "different_route_family",
]

REVERSIBLE_OPERATION_SETS: dict[str, tuple[ReversibleOperation, ...]] = {
    "cr_reversible": ("opposite", "reverse"),
    "opposite_reverse_v4": ("opposite", "reverse"),
}


def apply_operation(
    value: hexagram.HexagramRef,
    operation: ReversibleOperation,
) -> hexagram.Hexagram:
    item = hexagram.resolve_hexagram(value)
    if operation == "opposite":
        return item.opposite
    if operation == "reverse":
        return item.reverse
    raise ValueError(f"unsupported reversible transform operation: {operation!r}")


def _operation_set(name: str) -> tuple[ReversibleOperation, ...]:
    try:
        return REVERSIBLE_OPERATION_SETS[name]
    except KeyError as exc:
        raise ValueError(f"unknown reversible operation set: {name!r}") from exc


def reversible_orbit(
    value: hexagram.HexagramRef,
    *,
    operation_set: str = "cr_reversible",
) -> tuple[hexagram.Hexagram, ...]:
    operations = _operation_set(operation_set)
    seen: dict[hexagram.Lines6, hexagram.Hexagram] = {}
    frontier = [hexagram.resolve_hexagram(value)]
    while frontier:
        current = frontier.pop()
        if current.lines in seen:
            continue
        seen[current.lines] = current
        frontier.extend(apply_operation(current, operation) for operation in operations)
    return tuple(sorted(seen.values(), key=lambda item: item.number))


def reversible_orbit_members(
    value: hexagram.HexagramRef,
    *,
    operation_set: str = "cr_reversible",
) -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "number": item.number,
            "bitstring_bottom_to_top": item.bitstring_bottom_to_top,
        }
        for item in reversible_orbit(value, operation_set=operation_set)
    ]


def orbit_id(
    value: hexagram.HexagramRef,
    *,
    operation_set: str = "cr_reversible",
) -> str:
    members = reversible_orbit(value, operation_set=operation_set)
    canonical = min(item.bitstring_bottom_to_top for item in members)
    return f"{operation_set}:{canonical}"


def reversible_orbit_inventory(
    *,
    operation_set: str = "cr_reversible",
) -> dict[str, Any]:
    grouped: dict[str, tuple[hexagram.Hexagram, ...]] = {}
    for item in hexagram.HEXAGRAMS:
        grouped.setdefault(
            orbit_id(item, operation_set=operation_set),
            reversible_orbit(item, operation_set=operation_set),
        )
    size_distribution = Counter(len(members) for members in grouped.values())
    return {
        "operation_set": operation_set,
        "operation_names": list(_operation_set(operation_set)),
        "orbit_count": len(grouped),
        "size_distribution": dict(sorted(size_distribution.items())),
        "member_count": sum(len(members) for members in grouped.values()),
        "nuclear_included": False,
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
    }


def _state_payload(value: hexagram.Hexagram) -> dict[str, Any]:
    return {
        "name": value.name,
        "number": value.number,
        "bitstring_bottom_to_top": value.bitstring_bottom_to_top,
    }


def _opposite_reverse(value: hexagram.Hexagram) -> hexagram.Hexagram:
    return apply_operation(apply_operation(value, "opposite"), "reverse")


def _group_relation(source: hexagram.Hexagram, target: hexagram.Hexagram) -> str:
    if source.lines == target.lines:
        return "same"
    if apply_operation(source, "opposite").lines == target.lines:
        return "opposite"
    if apply_operation(source, "reverse").lines == target.lines:
        return "reverse"
    if _opposite_reverse(source).lines == target.lines:
        return "opposite_reverse"
    if hexagram.hamming_distance(source, target) == 1:
        return "one_line_perturbation"
    return "outside"


def yi_group_action_invariant_diagnostic(
    source: hexagram.HexagramRef,
    target: hexagram.HexagramRef,
    *,
    source_refs: Sequence[dict[str, Any]] | None = None,
    scope: str = "macro_transform",
) -> dict[str, Any]:
    """Diagnose reversible Yi group relations without granting evidence.

    The reducer is intentionally navigation-only. It says which structural
    transform connects two macro states, but source reopen still owns whether
    an agent may use the relation as a claim about real work.
    """

    left = hexagram.resolve_hexagram(source)
    right = hexagram.resolve_hexagram(target)
    operation_set = "opposite_reverse_v4"
    source_orbit = reversible_orbit(left, operation_set=operation_set)
    target_orbit = reversible_orbit(right, operation_set=operation_set)
    relation = _group_relation(left, right)
    refs = [dict(ref) for ref in source_refs or [] if isinstance(ref, dict)]
    return {
        "kind": "yi_group_action_invariant_diagnostic",
        "operation_group": operation_set,
        "operation_names": list(_operation_set(operation_set)),
        "source": _state_payload(left),
        "target": _state_payload(right),
        "source_orbit_id": orbit_id(left, operation_set=operation_set),
        "target_orbit_id": orbit_id(right, operation_set=operation_set),
        "source_orbit_size": len(source_orbit),
        "target_orbit_size": len(target_orbit),
        "source_self_reverse": apply_operation(left, "reverse").lines == left.lines,
        "target_self_reverse": apply_operation(right, "reverse").lines == right.lines,
        "relation": relation,
        "same_orbit": right.lines in {member.lines for member in source_orbit},
        "changed_lines": list(hexagram.changed_lines(left, right)),
        "hamming_distance": hexagram.hamming_distance(left, right),
        "perturbation_not_orbit": relation == "one_line_perturbation",
        "invariant_checks": {
            "source_ref_present": bool(refs),
            "scope": str(scope or "macro_transform")[:80],
            "authority_preserved": True,
            "agency_preserved": True,
            "orbit_membership_cannot_satisfy_source_invariant": True,
        },
        "runtime_recheck_reason": (
            "source_reanchoring_required"
            if relation in {"outside", "one_line_perturbation"}
            else ""
        ),
        "authority_level": "direction_only",
        "action_grammar": "direction_with_ref",
        "claim_permission": "none",
        "fact_claim_allowed": False,
        "may_satisfy_invariant": False,
        "source_reopen_required_before_claim": True,
        "boundary": {
            "group_action_is_navigation_diagnostic": True,
            "orbit_membership_is_not_source_evidence": True,
            "one_line_change_is_perturbation_not_orbit": True,
            "may_glue_routes": False,
        },
    }


def source_reanchoring_audit(
    anchor: hexagram.HexagramRef,
    current: hexagram.HexagramRef,
    transition_history: Sequence[hexagram.HexagramRef],
    *,
    source_reopened: bool = False,
) -> dict[str, Any]:
    anchor_state = hexagram.resolve_hexagram(anchor)
    current_state = hexagram.resolve_hexagram(current)
    states = [hexagram.resolve_hexagram(item) for item in transition_history]
    if not states or states[0].lines != anchor_state.lines:
        states = [anchor_state, *states]
    transition_pairs = list(zip(states, states[1:], strict=False))
    cumulative = sum(hexagram.hamming_distance(left, right) for left, right in transition_pairs)
    anchor_distance = hexagram.hamming_distance(anchor_state, current_state)
    unique_states = {state.lines for state in states}
    reanchoring_required = (
        not source_reopened
        and (anchor_distance >= 3 or cumulative >= 6 or len(unique_states) >= 4)
    )
    return {
        "kind": "yi_source_reanchoring_audit",
        "anchor": _state_payload(anchor_state),
        "current": _state_payload(current_state),
        "anchor_hamming_distance": anchor_distance,
        "transition_count_since_anchor": max(0, len(states) - 1),
        "cumulative_transition_distance": cumulative,
        "unique_state_count_since_anchor": len(unique_states),
        "source_reopened_since_anchor": bool(source_reopened),
        "source_reanchoring_required": reanchoring_required,
        "runtime_recheck_reason": "source_reanchoring_required" if reanchoring_required else "",
        "authority_level": "direction_only",
        "claim_permission": "none",
        "boundary": {
            "drift_metric_is_navigation_only": True,
            "current_distance_does_not_cancel_transition_churn": True,
            "reset_requires_source_reopen": True,
        },
    }


def orbit_oscillation_audit(
    transition_history: Sequence[hexagram.HexagramRef],
    *,
    window: int = 5,
) -> dict[str, Any]:
    states = [hexagram.resolve_hexagram(item) for item in transition_history][-max(2, window):]
    relations = [
        _group_relation(left, right)
        for left, right in zip(states, states[1:], strict=False)
    ]
    reversible_steps = [item for item in relations if item in {"opposite", "reverse"}]
    unique_states = {state.lines for state in states}
    warning = (
        len(states) >= 4
        and len(reversible_steps) >= len(states) - 1
        and len(unique_states) <= 2
    )
    return {
        "kind": "yi_orbit_oscillation_audit",
        "window_size": len(states),
        "relations": relations,
        "unique_state_count": len(unique_states),
        "orbit_oscillation_warning": warning,
        "runtime_recheck_reason": "orbit_oscillation_warning" if warning else "",
        "authority_level": "direction_only",
        "claim_permission": "none",
        "boundary": {
            "oscillation_is_attention_warning": True,
            "warning_does_not_mutate_policy": True,
            "source_reopen_required_before_claim": True,
        },
    }


def line_flip_neighbors(value: hexagram.HexagramRef) -> list[hexagram.Hexagram]:
    item = hexagram.resolve_hexagram(value)
    return [item.change_lines((position,)) for position in range(1, 7)]


def relation_label(
    source: hexagram.HexagramRef,
    target: hexagram.HexagramRef,
    *,
    operation_set: str = "cr_reversible",
) -> RelationLabel:
    left = hexagram.resolve_hexagram(source)
    right = hexagram.resolve_hexagram(target)
    if left.lines == right.lines:
        return "same_state"
    if right.lines in {member.lines for member in reversible_orbit(left, operation_set=operation_set)}:
        return "same_reversible_orbit"
    if hexagram.hamming_distance(left, right) == 1:
        return "adjacent_flip"
    return "different_route_family"


def nuclear_dynamics(value: hexagram.HexagramRef) -> dict[str, Any]:
    item = hexagram.resolve_hexagram(value)
    path: list[hexagram.Hexagram] = []
    seen: dict[str, int] = {}
    current = item
    while current.name not in seen:
        seen[current.name] = len(path)
        path.append(current)
        current = current.nuclear
    cycle_start = seen[current.name]
    cycle = path[cycle_start:]
    cycle_names = [entry.name for entry in cycle]
    cycle_id = "nuclear:" + "->".join(cycle_names)
    return {
        "source": {"name": item.name, "number": item.number},
        "path": [entry.name for entry in path],
        "cycle": cycle_names,
        "cycle_id": cycle_id,
        "basin_id": cycle_id,
        "cycle_length": len(cycle),
        "projection_kind": "non_invertible_nuclear_projection",
        "reversible_orbit_member": False,
    }


def nuclear_basin_inventory() -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    for item in hexagram.HEXAGRAMS:
        basin = nuclear_dynamics(item)
        groups.setdefault(str(basin["basin_id"]), []).append(item.name)
    basin_sizes = Counter(len(names) for names in groups.values())
    return {
        "kind": "macro_nuclear_dynamics_inventory",
        "basin_count": len(groups),
        "basin_size_distribution": dict(sorted(basin_sizes.items())),
        "basins": {
            basin_id: {
                "source_state_count": len(names),
                "sample_sources": sorted(names)[:8],
            }
            for basin_id, names in sorted(groups.items())
        },
        "boundary": {
            "nuclear_is_non_invertible_projection": True,
            "not_reversible_orbit_generator": True,
            "no_route_merge_from_basin_membership": True,
        },
    }


def macro_transform_orbit_diagnostic(
    source: hexagram.HexagramRef,
    target: hexagram.HexagramRef,
    *,
    operation_set: str = "cr_reversible",
) -> dict[str, Any]:
    left = hexagram.resolve_hexagram(source)
    right = hexagram.resolve_hexagram(target)
    relation = relation_label(left, right, operation_set=operation_set)
    return {
        "kind": "macro_transform_orbit_diagnostic",
        "operation_set": operation_set,
        "operation_names": list(_operation_set(operation_set)),
        "source": {"name": left.name, "number": left.number},
        "target": {"name": right.name, "number": right.number},
        "relation": relation,
        "source_orbit_id": orbit_id(left, operation_set=operation_set),
        "target_orbit_id": orbit_id(right, operation_set=operation_set),
        "same_reversible_orbit": relation in {"same_state", "same_reversible_orbit"},
        "changed_lines": list(hexagram.changed_lines(left, right)),
        "hamming_distance": hexagram.hamming_distance(left, right),
        "line_flip_adjacency": relation == "adjacent_flip",
        "candidate_authority": "candidate_only",
        "authority_level": "navigation_only",
        "action_grammar": "direction_with_ref",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
        "foreground_emitted": False,
        "default_ranking_effect": "none",
        "boundary": {
            "deterministic_structure_only": True,
            "source_reopen_required_for_claims": True,
            "orbit_membership_is_not_source_support": True,
            "nuclear_not_in_reversible_orbit": True,
            "no_default_foreground_symbolic_prose": True,
        },
    }


def relation_matrix(
    states: Sequence[hexagram.HexagramRef],
    *,
    operation_set: str = "cr_reversible",
) -> list[dict[str, Any]]:
    resolved = [hexagram.resolve_hexagram(item) for item in states]
    return [
        macro_transform_orbit_diagnostic(source, target, operation_set=operation_set)
        for source in resolved
        for target in resolved
    ]


__all__ = [
    "REVERSIBLE_OPERATION_SETS",
    "RelationLabel",
    "ReversibleOperation",
    "apply_operation",
    "line_flip_neighbors",
    "macro_transform_orbit_diagnostic",
    "nuclear_basin_inventory",
    "nuclear_dynamics",
    "orbit_id",
    "relation_label",
    "relation_matrix",
    "reversible_orbit",
    "reversible_orbit_inventory",
    "reversible_orbit_members",
    "source_reanchoring_audit",
    "orbit_oscillation_audit",
    "yi_group_action_invariant_diagnostic",
]
