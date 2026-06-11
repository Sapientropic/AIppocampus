from __future__ import annotations

from typing import Mapping

from aippocampus_runtime.macro.hexagram import HexagramRef, resolve_hexagram

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
SCHEMA_VERSION = 1

# Explicit fixture mapping, bottom to top. Lines 1-2 are earth because they ask
# whether source/test/implementation substrate exists; lines 3-4 are human
# because they describe current action/workflow coordination; lines 5-6 are
# heaven because they describe project direction and public-claim posture.
_AXIS_MAPPING: tuple[dict[str, object], ...] = (
    {
        "line": 1,
        "layer": "earth",
        "axis_id": "earth_substrate_evidence",
        "why_this_line": "bottom source/test/implementation substrate",
    },
    {
        "line": 2,
        "layer": "earth",
        "axis_id": "earth_claim_support",
        "why_this_line": "earth-side support for broader direction or claim",
    },
    {
        "line": 3,
        "layer": "human",
        "axis_id": "human_current_action",
        "why_this_line": "current agent action route and task decision",
    },
    {
        "line": 4,
        "layer": "human",
        "axis_id": "human_workflow_coordination",
        "why_this_line": "handoff, issue, PR, and workflow coordination",
    },
    {
        "line": 5,
        "layer": "heaven",
        "axis_id": "heaven_project_direction",
        "why_this_line": "roadmap, north-star, and project-direction route",
    },
    {
        "line": 6,
        "layer": "heaven",
        "axis_id": "heaven_public_claim",
        "why_this_line": "public positioning and claim-posture route",
    },
)

_YING_PAIRS: tuple[dict[str, object], ...] = (
    {
        "pair_id": "earth_human",
        "lower_line": 1,
        "upper_line": 4,
        "question": "do substrate facts support the current action route",
    },
    {
        "pair_id": "earth_heaven",
        "lower_line": 2,
        "upper_line": 5,
        "question": "does bottom evidence support the project direction",
    },
    {
        "pair_id": "human_heaven",
        "lower_line": 3,
        "upper_line": 6,
        "question": "does current workflow support public or long-horizon claims",
    },
)


def axis_mapping() -> list[dict[str, object]]:
    return [dict(axis) for axis in _AXIS_MAPPING]


def _line_state(value: int) -> str:
    return "active" if value == 1 else "receptive"


def _axis_for_line(line: int) -> Mapping[str, object]:
    return _AXIS_MAPPING[line - 1]


def _axis_id(line: int) -> str:
    return str(_axis_for_line(line)["axis_id"])


def _axis_layer(line: int) -> str:
    return str(_axis_for_line(line)["layer"])


def _line_value(lines: tuple[int, ...], line: int) -> int:
    return lines[line - 1]


def _adjacent_relation(lines: tuple[int, ...], lower_line: int) -> dict[str, object]:
    upper_line = lower_line + 1
    lower = _line_value(lines, lower_line)
    upper = _line_value(lines, upper_line)
    same = lower == upper
    if upper == 1 and lower == 0:
        pressure = "upper_presses_lower"
        cheng = "support_missing"
        reason = "adjacent_pressure_without_lower_support"
    elif lower == 1 and upper == 0:
        pressure = "lower_carries_upper"
        cheng = "support_present"
        reason = "adjacent_lower_supports_upper"
    else:
        pressure = "no_pressure"
        cheng = "matched_state" if same else "mixed_state"
        reason = "adjacent_matched" if same else "adjacent_mixed"
    return {
        "lower_line": lower_line,
        "upper_line": upper_line,
        "lower_axis": _axis_id(lower_line),
        "upper_axis": _axis_id(upper_line),
        "lower_layer": _axis_layer(lower_line),
        "upper_layer": _axis_layer(upper_line),
        "bi": "比" if same else "不比",
        "cheng": "承" if cheng == "support_present" else cheng,
        "sheng_pressure": "乘" if pressure == "upper_presses_lower" else "none",
        "lower_state": _line_state(lower),
        "upper_state": _line_state(upper),
        "diagnostic": reason,
    }


def _ying_relation(lines: tuple[int, ...], pair: Mapping[str, object]) -> dict[str, object]:
    raw_lower_line = pair["lower_line"]
    raw_upper_line = pair["upper_line"]
    lower_line = raw_lower_line if type(raw_lower_line) is int else 1
    upper_line = raw_upper_line if type(raw_upper_line) is int else 4
    lower = _line_value(lines, lower_line)
    upper = _line_value(lines, upper_line)
    if lower == upper:
        status = "aligned"
        reason = "ying_axes_same_state"
    elif lower == 0 and upper == 1:
        status = "missing_lower_support"
        reason = f"broken_coupling_{pair['pair_id']}"
    else:
        status = "unused_lower_support"
        reason = f"support_present_but_upper_route_inactive_{pair['pair_id']}"
    return {
        "pair_id": str(pair["pair_id"]),
        "term": "应",
        "lower_line": lower_line,
        "upper_line": upper_line,
        "lower_axis": _axis_id(lower_line),
        "upper_axis": _axis_id(upper_line),
        "lower_layer": _axis_layer(lower_line),
        "upper_layer": _axis_layer(upper_line),
        "lower_state": _line_state(lower),
        "upper_state": _line_state(upper),
        "status": status,
        "diagnostic": reason,
        "question": str(pair["question"]),
    }


def build_line_topology_diagnostics(value: HexagramRef) -> dict[str, object]:
    hexagram = resolve_hexagram(value)
    adjacent = [_adjacent_relation(hexagram.lines, line) for line in range(1, 6)]
    ying = [_ying_relation(hexagram.lines, pair) for pair in _YING_PAIRS]
    broken = [relation for relation in ying if relation["status"] == "missing_lower_support"]
    reason_codes = [str(relation["diagnostic"]) for relation in broken]
    if not reason_codes:
        reason_codes.append("topology_no_broken_cross_layer_coupling")
    return {
        "kind": "macro_line_topology_diagnostics",
        "schema_version": SCHEMA_VERSION,
        "hexagram": {
            "name": hexagram.name,
            "number": hexagram.number,
            "bits_bottom_to_top": hexagram.bitstring_bottom_to_top,
        },
        "axis_mapping": axis_mapping(),
        "adjacent_relations": adjacent,
        "ying_relations": ying,
        "broken_couplings": broken,
        "reason_codes": reason_codes,
        "evaluation_questions": [
            "does_topology_reduce_wrong_layer_recall",
            "does_topology_clarify_route_fanout",
            "does_topology_identify_specific_cross_layer_coupling",
        ],
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "ranking_weight_changes": False,
        "source_boundary": {
            "topology_is_navigation_diagnostic": True,
            "attention_dependency_analogy_not_fact": True,
            "perturbation_chooses_where_to_look": True,
            "reopened_source_decides_what_happened": True,
            "no_p6a_or_hexarc_dependency": True,
        },
    }


__all__ = [
    "ACTION_GRAMMAR",
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "SCHEMA_VERSION",
    "axis_mapping",
    "build_line_topology_diagnostics",
]
