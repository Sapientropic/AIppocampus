"""Small text helpers shared across runtime packages."""

from __future__ import annotations

import re

CJK_RECALL_RANGES = "\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002ffff"
CJK_IDEOGRAPH_RE = re.compile(f"[{CJK_RECALL_RANGES}]")
CJK_SEQUENCE_RE = re.compile(f"[{CJK_RECALL_RANGES}]+")


def compact_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 5:
        return text[:max_chars]
    separator = " ... "
    available = max_chars - len(separator)
    head = max(1, available // 2)
    tail = max(1, available - head)
    return text[:head].rstrip() + separator + text[-tail:].lstrip()


def has_cjk_ideograph(text: str) -> bool:
    return bool(CJK_IDEOGRAPH_RE.search(str(text or "")))


def cjk_ideograph_count(text: str) -> int:
    return len(CJK_IDEOGRAPH_RE.findall(str(text or "")))


def iter_cjk_sequences(text: str, *, min_len: int = 2, max_len: int = 32) -> list[str]:
    sequences: list[str] = []
    for match in CJK_SEQUENCE_RE.finditer(str(text or "")):
        value = match.group(0)
        if len(value) < min_len:
            continue
        if len(value) <= max_len:
            sequences.append(value)
            continue
        for start in range(0, len(value), max_len):
            chunk = value[start : start + max_len]
            if len(chunk) >= min_len:
                sequences.append(chunk)
    return sequences


def cjk_ngrams(sequence: str, sizes: tuple[int, ...] = (2, 3, 4)) -> list[str]:
    grams: list[str] = []
    for size in sizes:
        if len(sequence) < size:
            continue
        grams.extend(
            sequence[index : index + size] for index in range(0, len(sequence) - size + 1)
        )
    return grams
