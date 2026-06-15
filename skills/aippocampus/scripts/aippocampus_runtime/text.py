"""Small text helpers shared across runtime packages."""

from __future__ import annotations

import re


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
