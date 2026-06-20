"""Core clean-source exact-search helpers shared by CLI and registry search."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def iter_clean_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if not path.exists():
        return messages
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("text"):
                messages.append(item)
    return messages


def score_message(message: dict[str, Any], terms: list[str]) -> float:
    text = str(message.get("text") or "")
    low = text.casefold()
    score = 0.0
    matched = False
    for term in terms:
        needle = term.casefold()
        if not needle:
            continue
        count = low.count(needle)
        if count:
            matched = True
            score += 8.0 + count * min(len(term), 20)
    if not matched:
        return 0.0
    if message.get("is_final") or message.get("phase") == "final_answer":
        score += 18.0
    elif message.get("role") == "user":
        score += 3.0
    elif message.get("phase") == "commentary":
        score -= 2.0
    return score
