#!/usr/bin/env python3
"""Question-pair feedback helpers for tracking separation pressure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

FEEDBACK_EVENT_KIND = "aippocampus_ambient_policy_event"
DISMISS = "dismiss"
REOPEN = "reopen"
QUESTION_PAIR_TARGET_KINDS = {"question_link"}


@dataclass(frozen=True)
class QuestionPairFeedback:
    source_finding_ids: tuple[str, ...]
    action: str
    target_key: str
    target_kind: str
    created_at: str


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_ids(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        unique_preserve(
            [str(value) for value in row.get("source_finding_ids") or [] if str(value)],
            limit=32,
        )
    )


def load_question_pair_feedback(path: Path | None) -> tuple[QuestionPairFeedback, ...]:
    if path is None or not path.exists():
        return ()
    latest_by_source_ids: dict[frozenset[str], QuestionPairFeedback] = {}
    for row in load_jsonl_dict_rows(path).rows:
        if row.get("kind") != FEEDBACK_EVENT_KIND:
            continue
        action = str(row.get("action") or "")
        if action not in {DISMISS, REOPEN}:
            continue
        target_kind = str(row.get("target_kind") or "")
        if target_kind not in QUESTION_PAIR_TARGET_KINDS:
            continue
        source_ids = _source_ids(row)
        if len(source_ids) < 2:
            continue
        feedback = QuestionPairFeedback(
            source_finding_ids=source_ids,
            action=action,
            target_key=str(row.get("target_key") or ""),
            target_kind=target_kind,
            created_at=str(row.get("created_at") or ""),
        )
        key = frozenset(source_ids)
        existing = latest_by_source_ids.get(key)
        if existing is None or _parse_time(feedback.created_at) >= _parse_time(existing.created_at):
            latest_by_source_ids[key] = feedback
    return tuple(item for item in latest_by_source_ids.values() if item.action == DISMISS)


def pair_feedback_matches(feedback: QuestionPairFeedback, source_ids: Iterable[str]) -> bool:
    wanted = {str(value) for value in source_ids if str(value)}
    return len(wanted) >= 2 and wanted.issubset(set(feedback.source_finding_ids))


def matching_pair_feedback(
    feedback: Iterable[QuestionPairFeedback], source_ids: Iterable[str]
) -> tuple[QuestionPairFeedback, ...]:
    return tuple(item for item in feedback if pair_feedback_matches(item, source_ids))
