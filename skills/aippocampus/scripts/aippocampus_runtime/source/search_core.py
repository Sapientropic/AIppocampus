"""Core clean-source exact-search helpers shared by CLI and registry search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.source.jsonl_reader import load_jsonl_dict_rows


def load_clean_messages_with_loss(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = load_jsonl_dict_rows(path)
    return [item for item in result.rows if item.get("text")], result.loss


def iter_clean_messages(path: Path) -> list[dict[str, Any]]:
    messages, _ = load_clean_messages_with_loss(path)
    return messages


def clean_messages_jsonl_loss(path: Path) -> dict[str, Any]:
    _, loss = load_clean_messages_with_loss(path)
    return loss


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
