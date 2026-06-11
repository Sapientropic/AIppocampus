from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

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
    "乾": Trigram("乾", (YANG, YANG, YANG)),
    "兑": Trigram("兑", (YANG, YANG, YIN)),
    "离": Trigram("离", (YANG, YIN, YANG)),
    "震": Trigram("震", (YANG, YIN, YIN)),
    "巽": Trigram("巽", (YIN, YANG, YANG)),
    "坎": Trigram("坎", (YIN, YANG, YIN)),
    "艮": Trigram("艮", (YIN, YIN, YANG)),
    "坤": Trigram("坤", (YIN, YIN, YIN)),
}

KING_WEN_SEQUENCE: tuple[tuple[int, str, str, str], ...] = (
    (1, "乾", "乾", "乾"),
    (2, "坤", "坤", "坤"),
    (3, "屯", "坎", "震"),
    (4, "蒙", "艮", "坎"),
    (5, "需", "坎", "乾"),
    (6, "讼", "乾", "坎"),
    (7, "师", "坤", "坎"),
    (8, "比", "坎", "坤"),
    (9, "小畜", "巽", "乾"),
    (10, "履", "乾", "兑"),
    (11, "泰", "坤", "乾"),
    (12, "否", "乾", "坤"),
    (13, "同人", "乾", "离"),
    (14, "大有", "离", "乾"),
    (15, "谦", "坤", "艮"),
    (16, "豫", "震", "坤"),
    (17, "随", "兑", "震"),
    (18, "蛊", "艮", "巽"),
    (19, "临", "坤", "兑"),
    (20, "观", "巽", "坤"),
    (21, "噬嗑", "离", "震"),
    (22, "贲", "艮", "离"),
    (23, "剥", "艮", "坤"),
    (24, "复", "坤", "震"),
    (25, "无妄", "乾", "震"),
    (26, "大畜", "艮", "乾"),
    (27, "颐", "艮", "震"),
    (28, "大过", "兑", "巽"),
    (29, "坎", "坎", "坎"),
    (30, "离", "离", "离"),
    (31, "咸", "兑", "艮"),
    (32, "恒", "震", "巽"),
    (33, "遁", "乾", "艮"),
    (34, "大壮", "震", "乾"),
    (35, "晋", "离", "坤"),
    (36, "明夷", "坤", "离"),
    (37, "家人", "巽", "离"),
    (38, "睽", "离", "兑"),
    (39, "蹇", "坎", "艮"),
    (40, "解", "震", "坎"),
    (41, "损", "艮", "兑"),
    (42, "益", "巽", "震"),
    (43, "夬", "兑", "乾"),
    (44, "姤", "乾", "巽"),
    (45, "萃", "兑", "坤"),
    (46, "升", "坤", "巽"),
    (47, "困", "兑", "坎"),
    (48, "井", "坎", "巽"),
    (49, "革", "兑", "离"),
    (50, "鼎", "离", "巽"),
    (51, "震", "震", "震"),
    (52, "艮", "艮", "艮"),
    (53, "渐", "巽", "艮"),
    (54, "归妹", "震", "兑"),
    (55, "丰", "震", "离"),
    (56, "旅", "离", "艮"),
    (57, "巽", "巽", "巽"),
    (58, "兑", "兑", "兑"),
    (59, "涣", "巽", "坎"),
    (60, "节", "坎", "兑"),
    (61, "中孚", "巽", "兑"),
    (62, "小过", "震", "艮"),
    (63, "既济", "坎", "离"),
    (64, "未济", "离", "坎"),
)


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
]
