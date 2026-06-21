#!/usr/bin/env python3
"""Stable types and scoring helpers for source-backed question tracking."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.registry.api import unique_preserve

HASH_VECTOR_DIMS = 96

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "keep",
    "me",
    "of",
    "on",
    "or",
    "should",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "why",
    "with",
}


@dataclass(frozen=True)
class SalienceProfile:
    score: float
    tags: tuple[str, ...]
    reasons: tuple[str, ...]
    trackable: bool


@dataclass(frozen=True)
class QuestionCandidate:
    question_id: str
    finding_id: str
    question_text: str
    question_short: str
    title: str
    summary: str
    source_refs: tuple[dict[str, Any], ...]
    concepts: tuple[str, ...]
    what_features: tuple[str, ...]
    where_context: tuple[str, ...]
    intent_orientation: str
    phase_context: str
    collaboration_context: tuple[str, ...]
    salience: SalienceProfile
    created_at: str
    first_seen: str


@dataclass(frozen=True)
class FrontierMarker:
    finding_id: str
    frontier_type: str
    linked_question_short: str
    boundary_reason: str
    source_refs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PairDecision:
    pair_id: str
    left_id: str
    right_id: str
    score: float
    decision: str
    link_type: str
    confidence: float
    reason: str
    threshold_policy: dict[str, Any]
    acceptance_source: str
    confirmation: dict[str, Any] | None = None
    confirmation_request: dict[str, Any] | None = None
    ignored_confirmation: dict[str, Any] | None = None


def stable_digest(*parts: str, prefix: str, length: int = 18) -> str:
    raw = "\n".join(parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:length]}"


def compact_string_list(values: Any, *, limit: int = 10, max_chars: int = 90) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), max_chars)
        if text:
            out.append(text)
    return tuple(unique_preserve(out, limit=limit))


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def first_seen_from(row: Mapping[str, Any], refs: Iterable[Mapping[str, Any]]) -> str:
    candidates = [
        parsed
        for parsed in [parse_timestamp(str(ref.get("timestamp") or "")) for ref in refs]
        if parsed
    ]
    row_time = parse_timestamp(str(row.get("created_at") or ""))
    if row_time:
        candidates.append(row_time)
    if not candidates:
        return str(row.get("created_at") or "")
    return min(candidates).isoformat().replace("+00:00", "Z")


def normalize_tokens(*values: str) -> tuple[str, ...]:
    text = " ".join(str(value or "") for value in values).casefold()
    raw_tokens = re.findall(r"[\w]+", text, flags=re.UNICODE)
    tokens = [token for token in raw_tokens if len(token) >= 2 and token not in STOPWORDS]
    return tuple(tokens)


def token_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def hashed_text_vector(tokens: Iterable[str], *, dims: int = HASH_VECTOR_DIMS) -> tuple[float, ...]:
    values = [0.0] * dims
    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dims
        sign = -1.0 if digest[2] % 2 else 1.0
        values[index] += sign
    return tuple(values)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def axis_tokens(candidate: QuestionCandidate) -> tuple[str, ...]:
    return normalize_tokens(
        candidate.question_text,
        candidate.question_short,
        " ".join(candidate.what_features),
        " ".join(candidate.concepts),
    )


def axis_overlap(left: Iterable[str], right: Iterable[str]) -> float:
    return token_jaccard(normalize_tokens(" ".join(left)), normalize_tokens(" ".join(right)))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def candidate_salience(
    row: Mapping[str, Any],
    *,
    question_text: str,
    source_refs: tuple[dict[str, Any], ...],
    concepts: tuple[str, ...],
    what_features: tuple[str, ...],
    where_context: tuple[str, ...],
    intent_orientation: str,
    phase_context: str,
    collaboration_context: tuple[str, ...],
) -> SalienceProfile:
    question_tokens = normalize_tokens(question_text)
    axis_count = sum(
        1
        for present in [
            bool(what_features or concepts),
            bool(where_context),
            bool(intent_orientation),
            bool(phase_context),
            bool(collaboration_context),
        ]
        if present
    )
    raw_quality = row.get("quality")
    quality: Mapping[str, Any] = raw_quality if isinstance(raw_quality, Mapping) else {}
    confidence = safe_float(row.get("confidence"), 0.0)
    evidence_strength = safe_float(quality.get("evidence_strength"), 0.0)
    novelty = safe_float(quality.get("novelty"), 0.0)
    actionability = safe_float(quality.get("actionability"), 0.0)
    score = 0.0
    tags: list[str] = []
    reasons: list[str] = []

    if source_refs:
        score += 0.24
        tags.append("source_backed")
        reasons.append("has clean-source refs")
    if confidence >= 0.78:
        score += 0.14
        tags.append("high_confidence")
        reasons.append("candidate confidence is high")
    if axis_count >= 3:
        score += 0.20
        tags.append("axis_rich")
        reasons.append("three or more question-map axes are present")
    elif axis_count >= 1:
        score += 0.09
        tags.append("axis_present")
        reasons.append("at least one question-map axis is present")
    if len(question_tokens) >= 6:
        score += 0.12
        tags.append("specific_wording")
        reasons.append("question wording has enough content tokens")
    elif len(question_tokens) <= 2:
        score -= 0.20
        tags.append("low_information")
        reasons.append("question wording is too generic")
    if evidence_strength:
        score += min(0.10, evidence_strength * 0.10)
        tags.append("evidence_weighted")
    if novelty:
        score += min(0.08, novelty * 0.08)
        tags.append("novelty_weighted")
    if actionability:
        score += min(0.08, actionability * 0.08)
        tags.append("actionable")
    text = " ".join(
        [question_text, str(row.get("summary") or ""), " ".join(concepts + what_features)]
    ).casefold()
    if any(term in text for term in ("unresolved", "frontier", "blocked", "deferred", "边界", "未解决")):
        score += 0.10
        tags.append("frontier_adjacent")
        reasons.append("wording indicates unresolved or boundary work")
    if any(term in text for term in ("continuity", "context", "compaction", "memory", "记忆", "连续")):
        score += 0.08
        tags.append("continuity_relevant")
        reasons.append("wording touches memory or continuity")

    clamped = round(max(0.0, min(1.0, score)), 4)
    trackable = bool(source_refs) and clamped >= 0.35 and "low_information" not in tags
    return SalienceProfile(
        score=clamped,
        tags=tuple(unique_preserve(tags, limit=10)),
        reasons=tuple(unique_preserve(reasons, limit=8)),
        trackable=trackable,
    )


def same_text(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold() and bool(left.strip())


def match_score(left: QuestionCandidate, right: QuestionCandidate) -> float:
    left_tokens = axis_tokens(left)
    right_tokens = axis_tokens(right)
    lexical = max(
        token_jaccard(left_tokens, right_tokens),
        cosine(hashed_text_vector(left_tokens), hashed_text_vector(right_tokens)),
    )
    what = axis_overlap(left.what_features or left.concepts, right.what_features or right.concepts)
    where = axis_overlap(left.where_context, right.where_context)
    phase = 1.0 if same_text(left.phase_context, right.phase_context) else 0.0
    collab = axis_overlap(left.collaboration_context, right.collaboration_context)
    orientation_bonus = 0.0
    if left.intent_orientation and right.intent_orientation:
        orientation_bonus = 0.08 if same_text(left.intent_orientation, right.intent_orientation) else -0.10
    score = lexical * 0.68 + what * 0.16 + where * 0.07 + phase * 0.04 + collab * 0.03
    score += orientation_bonus
    return round(max(0.0, min(1.0, score)), 6)

