"""Manual review ingestion for Dream real-history evals."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.subconscious.candidate_router import iter_jsonl

MANUAL_SOURCE_REVIEW_KIND = "dream_manual_source_review"
MANUAL_REVIEW_STATUSES = {
    "supported",
    "refuted",
    "unknown",
    "stale",
    "superseded",
    "noisy",
    "over_personalized",
}
WRONG_HINT_OUTCOMES = {
    "wrong_hint",
    "irrelevant",
    "stale",
    "superseded",
    "over_personalized",
    "user_correction",
}
HIGH_ANNOYANCE_VALUES = {"high", "annoying", "noisy"}


def load_manual_source_review_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"manual source-review file not found: {path}")
    return [
        row
        for row in iter_jsonl(path)
        if row.get("kind") == MANUAL_SOURCE_REVIEW_KIND
    ]


def manual_source_review_metrics(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    reviewed = 0
    source_backed = 0
    wrong_hint_count = 0
    high_annoyance_count = 0
    stale_or_superseded_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("review_status") or row.get("status") or "unknown").casefold()
        if status not in MANUAL_REVIEW_STATUSES:
            status = "unknown"
        outcome = str(row.get("user_visible_outcome") or row.get("outcome") or "").casefold()
        annoyance = str(row.get("annoyance_risk") or row.get("noise_risk") or "").casefold()
        reviewed += 1
        status_counts[status] += 1
        if row.get("source_refs"):
            source_backed += 1
        if outcome in WRONG_HINT_OUTCOMES:
            wrong_hint_count += 1
        if annoyance in HIGH_ANNOYANCE_VALUES:
            high_annoyance_count += 1
        if status in {"stale", "superseded"}:
            stale_or_superseded_count += 1
    return {
        "reviewed_count": reviewed,
        "source_backed_review_count": source_backed,
        "status_counts": dict(sorted(status_counts.items())),
        "wrong_hint_count": wrong_hint_count,
        "high_annoyance_count": high_annoyance_count,
        "stale_or_superseded_count": stale_or_superseded_count,
    }
