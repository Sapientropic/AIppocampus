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
]
