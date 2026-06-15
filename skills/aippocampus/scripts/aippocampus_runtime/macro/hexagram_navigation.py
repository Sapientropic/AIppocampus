"""Navigation-only coordinates over deterministic hexagram structure."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from aippocampus_runtime.macro import hexagram as h


def _gray_code_lines(index: int) -> h.Lines6:
    gray = index ^ (index >> 1)
    return tuple((gray >> position) & 1 for position in range(6))  # type: ignore[return-value]


def _line_distance(left: h.Lines6, right: h.Lines6) -> int:
    return sum(1 for a, b in zip(left, right, strict=True) if a != b)


def _build_gray_walk_sequence() -> tuple[h.Hexagram, ...]:
    return tuple(h.hexagram_from_lines(_gray_code_lines(index)) for index in range(64))


SIX_BIT_GRAY_WALK_SEQUENCE = _build_gray_walk_sequence()
GRAY_WALK_SEQUENCE = SIX_BIT_GRAY_WALK_SEQUENCE
_GRAY_WALK_INDEX_BY_LINES = {
    item.lines: index for index, item in enumerate(SIX_BIT_GRAY_WALK_SEQUENCE)
}


def _validate_gray_walk() -> None:
    if len(SIX_BIT_GRAY_WALK_SEQUENCE) != 64:
        raise RuntimeError("six-bit Gray walk must contain 64 states")
    if len(_GRAY_WALK_INDEX_BY_LINES) != 64:
        raise RuntimeError("six-bit Gray walk must cover every hexagram exactly once")
    pairs = zip(SIX_BIT_GRAY_WALK_SEQUENCE, SIX_BIT_GRAY_WALK_SEQUENCE[1:], strict=False)
    for left, right in pairs:
        if _line_distance(left.lines, right.lines) != 1:
            raise RuntimeError("adjacent six-bit Gray walk states must differ by one line")
    if _line_distance(SIX_BIT_GRAY_WALK_SEQUENCE[-1].lines, SIX_BIT_GRAY_WALK_SEQUENCE[0].lines) != 1:
        raise RuntimeError("cyclic six-bit Gray walk wrap must differ by one line")


_validate_gray_walk()


def gray_walk_index(value: h.HexagramRef) -> int:
    item = h.resolve_hexagram(value)
    return _GRAY_WALK_INDEX_BY_LINES[item.lines]


def hexagram_by_gray_walk_index(index: int) -> h.Hexagram:
    if type(index) is not int or index < 0 or index >= len(SIX_BIT_GRAY_WALK_SEQUENCE):
        raise ValueError("Gray-walk index must be an integer from 0 to 63")
    return SIX_BIT_GRAY_WALK_SEQUENCE[index]


def gray_walk_prev(value: h.HexagramRef, *, wrap: bool = False) -> h.Hexagram | None:
    index = gray_walk_index(value)
    if index == 0:
        return SIX_BIT_GRAY_WALK_SEQUENCE[-1] if wrap else None
    return SIX_BIT_GRAY_WALK_SEQUENCE[index - 1]


def gray_walk_next(value: h.HexagramRef, *, wrap: bool = False) -> h.Hexagram | None:
    index = gray_walk_index(value)
    if index == len(SIX_BIT_GRAY_WALK_SEQUENCE) - 1:
        return SIX_BIT_GRAY_WALK_SEQUENCE[0] if wrap else None
    return SIX_BIT_GRAY_WALK_SEQUENCE[index + 1]


def king_wen_pair_relation(value: h.HexagramRef) -> dict[str, Any]:
    item = h.resolve_hexagram(value)
    pair_start = item.number if item.number % 2 == 1 else item.number - 1
    mate_number = pair_start + 1 if item.number == pair_start else pair_start
    mate = h.hexagram_by_number(mate_number)
    reverse_match = mate.lines == item.reverse.lines
    opposite_match = mate.lines == item.opposite.lines
    if reverse_match and opposite_match:
        relation = "reverse_and_opposite"
    elif reverse_match:
        relation = "reverse"
    elif opposite_match:
        relation = "opposite"
    else:
        relation = "other"
    return {
        "kind": "king_wen_adjacent_pair_relation",
        "pair_id": f"king_wen_pair:{pair_start}-{pair_start + 1}",
        "pair_start_number": pair_start,
        "source": {"name": item.name, "number": item.number},
        "pair_mate": {"name": mate.name, "number": mate.number},
        "relation": relation,
        "reverse_match": reverse_match,
        "opposite_match": opposite_match,
        "source_reverse_self_orbit": item.reverse.lines == item.lines,
        "mate_reverse_self_orbit": mate.reverse.lines == mate.lines,
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
        "interpretation_included": False,
    }


def king_wen_pair_relation_inventory() -> dict[str, Any]:
    rows = [king_wen_pair_relation(number) for number in range(1, 65, 2)]
    counts = Counter(str(row["relation"]) for row in rows)
    return {
        "kind": "king_wen_adjacent_pair_relation_inventory",
        "pair_count": len(rows),
        "relation_counts": dict(sorted(counts.items())),
        "pairs": rows,
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
        "interpretation_included": False,
    }


def _distance_summary(distances: list[int]) -> dict[str, Any]:
    if not distances:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": 0.0,
            "population_variance": 0.0,
            "distance_counts": {},
        }
    mean = sum(distances) / len(distances)
    variance = sum((value - mean) ** 2 for value in distances) / len(distances)
    return {
        "count": len(distances),
        "min": min(distances),
        "max": max(distances),
        "mean": round(mean, 6),
        "population_variance": round(variance, 6),
        "distance_counts": dict(sorted(Counter(distances).items())),
    }


def _lag1_distance_autocorrelation(distances: list[int]) -> dict[str, Any]:
    if len(distances) < 3:
        return {
            "formula": "pearson_correlation(distances[:-1], distances[1:])",
            "value": 0.0,
            "pair_count": 0,
        }
    left = distances[:-1]
    right = distances[1:]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    left_denominator = sum((a - left_mean) ** 2 for a in left)
    right_denominator = sum((b - right_mean) ** 2 for b in right)
    denominator = math.sqrt(left_denominator * right_denominator)
    value = numerator / denominator if denominator else 0.0
    return {
        "formula": "pearson_correlation(distances[:-1], distances[1:])",
        "value": round(value, 6),
        "pair_count": len(left),
    }


def _yang_count(item: h.Hexagram) -> int:
    return sum(item.lines)


def king_wen_sequence_profile() -> dict[str, Any]:
    """Return aggregate King Wen sequence statistics as navigation context.

    Chan 2026 is treated as a negative-result boundary here: sequence structure
    can be audited as movement shape, but it must not become a training
    schedule, ranking weight, source evidence, or foreground advice.
    """

    sequence = [h.hexagram_by_number(number) for number in range(1, 65)]
    distances = [
        h.hamming_distance(left, right)
        for left, right in zip(sequence, sequence[1:], strict=False)
    ]
    within_pair = [
        h.hamming_distance(sequence[index], sequence[index + 1])
        for index in range(0, len(sequence), 2)
    ]
    between_pair = [
        h.hamming_distance(sequence[index], sequence[index + 1])
        for index in range(1, len(sequence) - 1, 2)
    ]
    group_of_four_yang = [
        sum(_yang_count(item) for item in sequence[index : index + 4])
        for index in range(0, len(sequence), 4)
    ]
    pair_inventory = king_wen_pair_relation_inventory()
    return {
        "kind": "king_wen_sequence_profile",
        "state_count": len(sequence),
        "unique_state_count": len({item.lines for item in sequence}),
        "adjacent_transition_count": len(distances),
        "wrap_policy": "no_wrap",
        "adjacent_hamming": _distance_summary(distances),
        "lag_1_distance_autocorrelation": _lag1_distance_autocorrelation(distances),
        "group_of_four_yang_balance": {
            "group_count": len(group_of_four_yang),
            "window_size": 4,
            "counts": group_of_four_yang,
            "count_distribution": dict(sorted(Counter(group_of_four_yang).items())),
        },
        "pair_transition_hamming": {
            "within_pair": _distance_summary(within_pair),
            "between_pair": _distance_summary(between_pair),
            "within_pair_transition_count": len(within_pair),
            "between_pair_transition_count": len(between_pair),
            "within_pair_relation_counts": pair_inventory["relation_counts"],
        },
        "boundary": {
            "navigation_only": True,
            "not_training_schedule": True,
            "not_ranking_weight": True,
            "not_source_evidence": True,
            "source_reopen_required_before_claim": True,
            "chan_2026_negative_result_boundary": (
                "statistically_interesting_does_not_mean_operationally_useful_for_optimization"
            ),
        },
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
        "foreground_action_allowed": False,
        "interpretation_included": False,
        "raw_source_or_user_data_included": False,
        "line_texts_included": False,
        "model_calls": False,
    }


__all__ = [
    "GRAY_WALK_SEQUENCE",
    "SIX_BIT_GRAY_WALK_SEQUENCE",
    "gray_walk_index",
    "gray_walk_next",
    "gray_walk_prev",
    "hexagram_by_gray_walk_index",
    "king_wen_pair_relation",
    "king_wen_pair_relation_inventory",
    "king_wen_sequence_profile",
]
