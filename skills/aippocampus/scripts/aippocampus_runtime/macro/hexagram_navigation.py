"""Navigation-only coordinates over deterministic hexagram structure."""

from __future__ import annotations

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


__all__ = [
    "GRAY_WALK_SEQUENCE",
    "SIX_BIT_GRAY_WALK_SEQUENCE",
    "gray_walk_index",
    "gray_walk_next",
    "gray_walk_prev",
    "hexagram_by_gray_walk_index",
    "king_wen_pair_relation",
    "king_wen_pair_relation_inventory",
]
