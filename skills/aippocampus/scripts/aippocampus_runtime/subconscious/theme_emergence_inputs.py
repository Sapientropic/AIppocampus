"""Input normalization for deterministic theme emergence.

Theme emergence is only a quiet navigation layer. Keeping row parsing and
concept specificity checks in this module makes the main runner stay focused on
clustering/materialization, and keeps the source-backed boundary visible next
to the code that admits inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.question.source_refs import source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

QUESTION_LINK_KIND = "question_link"
FRONTIER_MARKER_KIND = "frontier_marker"

BROAD_THEME_TERMS = {
    "agent",
    "agents",
    "aippocampus",
    "codex",
    "context",
    "memory",
    "project",
    "question",
    "questions",
    "source",
    "thread",
    "user",
    "workflow",
    "记忆",
    "问题",
    "项目",
    "用户",
}


@dataclass(frozen=True)
class QuestionLink:
    link_id: str
    finding_id: str
    title: str
    linked_question_short: str
    link_type: str
    confidence: float
    question_count: int
    source_refs: tuple[dict[str, Any], ...]
    concepts: tuple[str, ...]
    first_seen: str
    last_seen: str
    linked_questions: tuple[dict[str, Any], ...]
    theme_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrontierMarker:
    finding_id: str
    frontier_type: str
    linked_question_short: str
    boundary_reason: str
    source_refs: tuple[dict[str, Any], ...]
    concepts: tuple[str, ...]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_string_list(values: Any, *, limit: int = 12, max_chars: int = 90) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or "").strip(), max_chars)
        if text:
            out.append(text)
    return tuple(unique_preserve(out, limit=limit))


def compact_source_refs(values: Any, *, limit: int = 16) -> tuple[dict[str, Any], ...]:
    if not isinstance(values, list):
        return ()
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for ref in values:
        if not isinstance(ref, dict):
            continue
        clean = {
            key: ref.get(key)
            for key in (
                "ref",
                "turn_ref",
                "thread_key",
                "title",
                "project_label",
                "turn_id",
                "turn_index",
                "user_line",
                "assistant_line",
                "source_line",
                "line",
                "message_id",
                "timestamp",
            )
            if ref.get(key) not in {None, ""}
        }
        key = source_ref_key(clean)
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return tuple(out)


def normalize_concept(value: str) -> str:
    text = compact_text(str(value or "").strip(), 80)
    text = re.sub(r"\s+", " ", text)
    return text


def concept_key(value: str) -> str:
    return normalize_concept(value).casefold()


def concept_is_specific(value: str) -> bool:
    key = concept_key(value)
    if len(key) < 3 or key in BROAD_THEME_TERMS:
        return False
    if key.isascii() and " " not in key and "-" not in key and "_" not in key and len(key) < 7:
        return False
    return True


def concept_terms(*values: str) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for token in re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE):
            if len(token) >= 3 and token not in BROAD_THEME_TERMS:
                terms.add(token)
    return terms


def parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def row_finding_kind(row: Mapping[str, Any]) -> str:
    return str(row.get("finding_kind") or row.get("kind") or "").strip()


def row_finding_id(row: Mapping[str, Any]) -> str:
    return str(row.get("fingerprint") or row.get("question_cluster_id") or "").strip()


def question_link_from_row(row: Mapping[str, Any]) -> QuestionLink | None:
    if row_finding_kind(row) != QUESTION_LINK_KIND:
        return None
    link_type = str(row.get("link_type") or "").strip()
    if link_type != "recurring":
        return None
    refs = compact_source_refs(row.get("source_refs"))
    if not refs:
        return None
    concepts = compact_string_list(row.get("concepts"), limit=18)
    if not any(concept_is_specific(concept) for concept in concepts):
        return None
    link_id = str(row.get("question_cluster_id") or row.get("fingerprint") or "").strip()
    if not link_id:
        return None
    linked_questions = tuple(
        item for item in row.get("linked_questions") or [] if isinstance(item, dict)
    )
    return QuestionLink(
        link_id=link_id,
        finding_id=row_finding_id(row) or link_id,
        title=compact_text(str(row.get("title") or ""), 140),
        linked_question_short=compact_text(str(row.get("linked_question_short") or ""), 90),
        link_type=link_type,
        confidence=max(0.0, min(1.0, safe_float(row.get("confidence")))),
        question_count=max(1, safe_int(row.get("question_count"), 1)),
        source_refs=refs,
        concepts=concepts,
        first_seen=str(row.get("first_seen") or row.get("created_at") or ""),
        last_seen=str(row.get("last_seen") or row.get("created_at") or ""),
        linked_questions=linked_questions,
    )


def frontier_from_row(row: Mapping[str, Any]) -> FrontierMarker | None:
    if row_finding_kind(row) != FRONTIER_MARKER_KIND:
        return None
    refs = compact_source_refs(row.get("source_refs"))
    if not refs:
        return None
    finding_id = row_finding_id(row)
    if not finding_id:
        return None
    return FrontierMarker(
        finding_id=finding_id,
        frontier_type=compact_text(str(row.get("frontier_type") or "unresolved"), 60),
        linked_question_short=compact_text(str(row.get("linked_question_short") or ""), 90),
        boundary_reason=compact_text(str(row.get("boundary_reason") or row.get("summary") or ""), 260),
        source_refs=refs,
        concepts=compact_string_list(row.get("concepts"), limit=12),
    )
