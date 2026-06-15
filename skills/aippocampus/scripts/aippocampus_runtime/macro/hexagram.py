from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Literal, TypeAlias

from aippocampus_runtime.macro.hexagram_tables import KING_WEN_SEQUENCE, TRIGRAM_LINE_TABLE

Line: TypeAlias = Literal[0, 1]
Lines3: TypeAlias = tuple[int, int, int]
Lines6: TypeAlias = tuple[int, int, int, int, int, int]
PerturbationBand: TypeAlias = Literal["none", "local", "medium", "large", "inversion"]

YIN: Line = 0
YANG: Line = 1
PUBLIC_RUNTIME_BOUNDARY = {
    "deterministic_structure_only": True,
    "line_texts_included": False,
    "interpretation_included": False,
    "model_calls": False,
}


@dataclass(frozen=True, slots=True)
class Trigram:
    name: str
    lines: Lines3


@dataclass(frozen=True, slots=True)
class Hexagram:
    number: int
    name: str
    upper_trigram: str
    lower_trigram: str
    lines: Lines6

    @property
    def bitstring_bottom_to_top(self) -> str:
        return "".join(str(line) for line in self.lines)

    @property
    def lower_lines(self) -> Lines3:
        return self.lines[:3]

    @property
    def upper_lines(self) -> Lines3:
        return self.lines[3:]

    @property
    def nuclear(self) -> Hexagram:
        lower = self.lines[1:4]
        upper = self.lines[2:5]
        return hexagram_from_lines((*lower, *upper))

    @property
    def opposite(self) -> Hexagram:
        return hexagram_from_lines(tuple(1 - line for line in self.lines))

    @property
    def reverse(self) -> Hexagram:
        return hexagram_from_lines(tuple(reversed(self.lines)))

    @property
    def wen_prev(self) -> Hexagram | None:
        return hexagram_by_number(self.number - 1) if self.number > 1 else None

    @property
    def wen_next(self) -> Hexagram | None:
        return hexagram_by_number(self.number + 1) if self.number < 64 else None

    def change_lines(self, positions: tuple[int, ...]) -> Hexagram:
        return change_lines(self, positions)

    def to_public_dict(self) -> dict[str, object]:
        """Serialize structure only; interpretation/advice belongs to a later layer."""
        return {
            "name": self.name,
            "number": self.number,
            "lines_bottom_to_top": list(self.lines),
            "bitstring_bottom_to_top": self.bitstring_bottom_to_top,
            "upper_trigram": self.upper_trigram,
            "lower_trigram": self.lower_trigram,
            "nuclear": self.nuclear.name,
            "opposite": self.opposite.name,
            "reverse": self.reverse.name,
            "wen_prev": self.wen_prev.name if self.wen_prev else None,
            "wen_next": self.wen_next.name if self.wen_next else None,
            "runtime_boundary": dict(PUBLIC_RUNTIME_BOUNDARY),
        }


HexagramRef: TypeAlias = Hexagram | str | int | tuple[int, ...]

TRIGRAMS: dict[str, Trigram] = {
    name: Trigram(name, lines) for name, lines in TRIGRAM_LINE_TABLE.items()
}


def _normalize_lines(lines: tuple[int, ...], *, length: int) -> tuple[int, ...]:
    if len(lines) != length:
        raise ValueError(f"expected {length} lines, got {len(lines)}")
    if any(type(line) is not int or line not in (YIN, YANG) for line in lines):
        raise ValueError("lines must be integers 0 for yin or 1 for yang")
    return lines


def _build_hexagrams() -> tuple[Hexagram, ...]:
    hexagrams: list[Hexagram] = []
    for number, name, upper, lower in KING_WEN_SEQUENCE:
        upper_lines = TRIGRAMS[upper].lines
        lower_lines = TRIGRAMS[lower].lines
        hexagrams.append(
            Hexagram(
                number=number,
                name=name,
                upper_trigram=upper,
                lower_trigram=lower,
                lines=(*lower_lines, *upper_lines),
            )
        )
    return tuple(hexagrams)


HEXAGRAMS = _build_hexagrams()
HEXAGRAMS_BY_NUMBER = {hexagram.number: hexagram for hexagram in HEXAGRAMS}
HEXAGRAMS_BY_NAME = {hexagram.name: hexagram for hexagram in HEXAGRAMS}
HEXAGRAMS_BY_LINES = {hexagram.lines: hexagram for hexagram in HEXAGRAMS}
TRIGRAMS_BY_LINES = {trigram.lines: trigram for trigram in TRIGRAMS.values()}


def _validate_tables() -> None:
    if len(HEXAGRAMS) != 64:
        raise RuntimeError("King Wen sequence must contain 64 hexagrams")
    if len(HEXAGRAMS_BY_NUMBER) != 64:
        raise RuntimeError("King Wen numbers must be unique")
    if len(HEXAGRAMS_BY_NAME) != 64:
        raise RuntimeError("hexagram names must be unique and exact")
    if len(HEXAGRAMS_BY_LINES) != 64:
        raise RuntimeError("hexagram line patterns must be unique")


_validate_tables()


def trigram_from_lines(lines: tuple[int, ...]) -> Trigram:
    normalized = _normalize_lines(lines, length=3)
    try:
        return TRIGRAMS_BY_LINES[normalized]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown trigram lines: {normalized!r}") from exc


def hexagram_by_number(number: int) -> Hexagram:
    if type(number) is not int:
        raise ValueError("hexagram number must be an integer")
    try:
        return HEXAGRAMS_BY_NUMBER[number]
    except KeyError as exc:
        raise ValueError(f"unknown King Wen hexagram number: {number!r}") from exc


def hexagram_by_name(name: str) -> Hexagram:
    if not isinstance(name, str):
        raise ValueError("hexagram name must be a string")
    stripped = name.strip()
    if stripped != name:
        raise ValueError("hexagram names must be exact, without surrounding whitespace")
    try:
        return HEXAGRAMS_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown hexagram name: {name!r}") from exc


def hexagram_from_lines(lines: tuple[int, ...]) -> Hexagram:
    normalized = _normalize_lines(lines, length=6)
    try:
        return HEXAGRAMS_BY_LINES[normalized]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown hexagram lines: {normalized!r}") from exc


def resolve_hexagram(value: HexagramRef) -> Hexagram:
    if isinstance(value, Hexagram):
        return value
    if isinstance(value, str):
        return hexagram_by_name(value)
    if type(value) is int:
        return hexagram_by_number(value)
    if isinstance(value, tuple):
        return hexagram_from_lines(value)
    raise ValueError(f"unsupported hexagram reference: {value!r}")


def _normalize_line_positions(positions: tuple[int, ...]) -> tuple[int, ...]:
    if not positions:
        return ()
    if any(type(position) is not int for position in positions):
        raise ValueError("changing line positions must be integers")
    if any(position < 1 or position > 6 for position in positions):
        raise ValueError("changing line positions are 1-based, bottom-to-top, from 1 to 6")
    if len(set(positions)) != len(positions):
        raise ValueError("changing line positions must not repeat")
    return tuple(sorted(positions))


def change_lines(value: HexagramRef, positions: tuple[int, ...]) -> Hexagram:
    hexagram = resolve_hexagram(value)
    normalized_positions = _normalize_line_positions(positions)
    changed = list(hexagram.lines)
    for position in normalized_positions:
        index = position - 1
        changed[index] = 1 - changed[index]
    return hexagram_from_lines(tuple(changed))


def changed_lines(a: HexagramRef, b: HexagramRef) -> tuple[int, ...]:
    first = resolve_hexagram(a)
    second = resolve_hexagram(b)
    return tuple(
        index + 1
        for index, (left, right) in enumerate(zip(first.lines, second.lines, strict=True))
        if left != right
    )


def hamming_distance(a: HexagramRef, b: HexagramRef) -> int:
    return len(changed_lines(a, b))


def perturbation_band(distance: int) -> PerturbationBand:
    if type(distance) is not int or distance < 0 or distance > 6:
        raise ValueError("hexagram perturbation distance must be an integer from 0 to 6")
    if distance == 0:
        return "none"
    if distance <= 2:
        return "local"
    if distance == 3:
        return "medium"
    if distance <= 5:
        return "large"
    return "inversion"


def public_hexagram_projection(value: HexagramRef) -> dict[str, object]:
    return resolve_hexagram(value).to_public_dict()


_NAVIGATION_EXPORTS = (
    "GRAY_WALK_SEQUENCE",
    "SIX_BIT_GRAY_WALK_SEQUENCE",
    "gray_walk_index",
    "gray_walk_next",
    "gray_walk_prev",
    "hexagram_by_gray_walk_index",
    "king_wen_pair_relation",
    "king_wen_pair_relation_inventory",
)


def __getattr__(name: str) -> object:
    if name in _NAVIGATION_EXPORTS:
        # Keep the historic ``hexagram.<navigation_helper>`` surface without
        # reintroducing the static hexagram <-> hexagram_navigation import cycle.
        navigation = import_module("aippocampus_runtime.macro.hexagram_navigation")
        return getattr(navigation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "HEXAGRAMS",
    "HEXAGRAMS_BY_LINES",
    "HEXAGRAMS_BY_NAME",
    "HEXAGRAMS_BY_NUMBER",
    "KING_WEN_SEQUENCE",
    "PUBLIC_RUNTIME_BOUNDARY",
    "TRIGRAMS",
    "Hexagram",
    "Line",
    "Lines3",
    "Lines6",
    "PerturbationBand",
    "Trigram",
    "YANG",
    "YIN",
    "change_lines",
    "changed_lines",
    "hamming_distance",
    "hexagram_by_name",
    "hexagram_by_number",
    "hexagram_from_lines",
    "perturbation_band",
    "public_hexagram_projection",
    "resolve_hexagram",
    "trigram_from_lines",
    *_NAVIGATION_EXPORTS,
]
