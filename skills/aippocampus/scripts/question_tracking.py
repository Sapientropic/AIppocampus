#!/usr/bin/env python3
"""Deterministic Phase 2 question tracking over source-backed candidates.

`question_extraction` writes provisional question candidates into the shared
`subconscious_jobs.jsonl` staging stream.  This module reads those rows,
groups related questions, and writes append-only `question_link` findings back
to the same stream.  The tracking layer treats generated findings as navigation
structure only: every link must keep the original clean-source refs attached,
and borderline links are skipped unless an explicit confirmation artifact
accepts them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from aippocampuslib import cli_error_payload, cli_exit_code_for_error_code, compact_text, now_utc
from question_source_refs import (
    SourceRefIndex,
    build_source_ref_index,
    compact_source_refs,
    source_ref_key,
)
from registry import registry_paths, unique_preserve
from subconscious_jobs_config import default_jobs_output_path

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-question-tracking-v1"
FINDING_ROW_KIND = "aippocampus_subconscious_job_finding"
QUESTION_CANDIDATE_KIND = "question_candidate"
FRONTIER_MARKER_KIND = "frontier_marker"
QUESTION_LINK_KIND = "question_link"
DEFAULT_STRONG_THRESHOLD = 0.80
DEFAULT_BORDERLINE_THRESHOLD = 0.66
HASH_VECTOR_DIMS = 96

ConfirmationFn = Callable[[dict[str, Any]], Mapping[str, Any] | None]

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
    confirmation: dict[str, Any] | None = None


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item


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
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def axis_tokens(candidate: QuestionCandidate) -> tuple[str, ...]:
    return normalize_tokens(
        candidate.question_text,
        candidate.question_short,
        " ".join(candidate.what_features),
        " ".join(candidate.concepts),
    )


def axis_overlap(left: Iterable[str], right: Iterable[str]) -> float:
    return token_jaccard(normalize_tokens(" ".join(left)), normalize_tokens(" ".join(right)))


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


def question_source_id(row: Mapping[str, Any], refs: Iterable[Mapping[str, Any]]) -> str:
    existing = str(row.get("fingerprint") or "").strip()
    if existing:
        return existing
    ref_blob = "|".join(":".join(source_ref_key(ref)) for ref in refs)
    return stable_digest(
        str(row.get("question_text") or row.get("title") or ""),
        ref_blob,
        prefix="sf",
        length=20,
    )


def candidate_from_row(
    row: Mapping[str, Any], *, source_index: SourceRefIndex | None = None
) -> QuestionCandidate | None:
    if row.get("kind") != FINDING_ROW_KIND:
        return None
    if str(row.get("finding_kind") or row.get("kind") or "") != QUESTION_CANDIDATE_KIND:
        return None
    refs = compact_source_refs(row.get("source_refs"), source_index=source_index)
    if not refs:
        return None
    question_text = compact_text(str(row.get("question_text") or row.get("title") or ""), 180)
    if not question_text:
        return None
    finding_id = question_source_id(row, refs)
    question_id = stable_digest(
        finding_id,
        question_text,
        "|".join(":".join(source_ref_key(ref)) for ref in refs),
        prefix="q",
        length=16,
    )
    return QuestionCandidate(
        question_id=question_id,
        finding_id=finding_id,
        question_text=question_text,
        question_short=compact_text(str(row.get("question_short") or row.get("title") or ""), 90),
        title=compact_text(str(row.get("title") or question_text), 140),
        summary=compact_text(str(row.get("summary") or ""), 480),
        source_refs=refs,
        concepts=compact_string_list(row.get("concepts"), limit=12),
        what_features=compact_string_list(row.get("what_features"), limit=10),
        where_context=compact_string_list(row.get("where_context"), limit=8),
        intent_orientation=compact_text(str(row.get("intent_orientation") or ""), 80),
        phase_context=compact_text(str(row.get("phase_context") or ""), 80),
        collaboration_context=compact_string_list(row.get("collaboration_context"), limit=8),
        created_at=str(row.get("created_at") or ""),
        first_seen=first_seen_from(row, refs),
    )


def frontier_from_row(
    row: Mapping[str, Any], *, source_index: SourceRefIndex | None = None
) -> FrontierMarker | None:
    if row.get("kind") != FINDING_ROW_KIND:
        return None
    if str(row.get("finding_kind") or row.get("kind") or "") != FRONTIER_MARKER_KIND:
        return None
    refs = compact_source_refs(row.get("source_refs"), source_index=source_index)
    if not refs:
        return None
    boundary = compact_text(str(row.get("boundary_reason") or row.get("summary") or ""), 260)
    if not boundary:
        return None
    finding_id = str(row.get("fingerprint") or "") or stable_digest(
        str(row.get("linked_question_short") or ""),
        boundary,
        prefix="sf",
        length=20,
    )
    return FrontierMarker(
        finding_id=finding_id,
        frontier_type=compact_text(str(row.get("frontier_type") or "unresolved"), 80),
        linked_question_short=compact_text(str(row.get("linked_question_short") or ""), 90),
        boundary_reason=boundary,
        source_refs=refs,
    )


def pair_id(left: QuestionCandidate, right: QuestionCandidate) -> str:
    first, second = sorted([left.finding_id, right.finding_id])
    return stable_digest(first, second, prefix="qp", length=18)


def load_confirmation_decisions(path: Path | None) -> ConfirmationFn | None:
    if path is None:
        return None
    rows = list(iter_jsonl(path))
    by_pair: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("pair_id") or "").strip()
        if not key:
            ids = [str(value) for value in row.get("source_finding_ids") or [] if str(value)]
            if len(ids) == 2:
                key = stable_digest(*sorted(ids), prefix="qp", length=18)
        if key:
            by_pair[key] = row

    def confirm(payload: dict[str, Any]) -> Mapping[str, Any] | None:
        return by_pair.get(str(payload.get("pair_id") or ""))

    return confirm


def normalize_confirmation(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    decision = str(raw.get("decision") or raw.get("action") or "").strip().casefold()
    if decision not in {"accept", "same", "link", "confirmed"}:
        return None
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return None
    if confidence < 0.45:
        return None
    link_type = str(raw.get("link_type") or "related").strip()
    if link_type not in {"recurring", "evolving", "parent_of", "child_of", "related"}:
        link_type = "related"
    return {
        "decision": "accept",
        "link_type": link_type,
        "confidence": round(confidence, 4),
        "model": compact_text(str(raw.get("model") or raw.get("source") or "external"), 120),
        "rationale": compact_text(str(raw.get("rationale") or raw.get("reason") or ""), 260),
    }


def decide_pair(
    left: QuestionCandidate,
    right: QuestionCandidate,
    *,
    strong_threshold: float,
    borderline_threshold: float,
    confirmation_fn: ConfirmationFn | None,
) -> PairDecision | None:
    score = match_score(left, right)
    current_pair_id = pair_id(left, right)
    if score >= strong_threshold:
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="accepted",
            link_type="recurring",
            confidence=round(min(0.98, 0.62 + score * 0.34), 4),
            reason="deterministic multi-field score met strong threshold",
        )
    if score < borderline_threshold:
        return None
    payload = {
        "pair_id": current_pair_id,
        "score": score,
        "source_finding_ids": [left.finding_id, right.finding_id],
        "left": question_for_confirmation(left),
        "right": question_for_confirmation(right),
    }
    confirmation = normalize_confirmation(confirmation_fn(payload) if confirmation_fn else None)
    if not confirmation:
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="needs_confirmation",
            link_type="related",
            confidence=0.0,
            reason="borderline score skipped without explicit confirmation artifact",
        )
    return PairDecision(
        pair_id=current_pair_id,
        left_id=left.question_id,
        right_id=right.question_id,
        score=score,
        decision="accepted",
        link_type=str(confirmation["link_type"]),
        confidence=float(confirmation["confidence"]),
        reason="borderline score accepted by explicit confirmation artifact",
        confirmation=confirmation,
    )


def question_for_confirmation(candidate: QuestionCandidate) -> dict[str, Any]:
    return {
        "question_id": candidate.question_id,
        "source_finding_id": candidate.finding_id,
        "question_text": candidate.question_text,
        "question_short": candidate.question_short,
        "intent_orientation": candidate.intent_orientation,
        "what_features": list(candidate.what_features),
        "where_context": list(candidate.where_context),
        "phase_context": candidate.phase_context,
        "source_refs": list(candidate.source_refs),
    }


def connected_components(candidates: list[QuestionCandidate], pairs: list[PairDecision]) -> list[list[str]]:
    parent = {candidate.question_id: candidate.question_id for candidate in candidates}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for pair in pairs:
        if pair.decision == "accepted":
            union(pair.left_id, pair.right_id)
    groups: dict[str, list[str]] = {}
    for candidate in candidates:
        groups.setdefault(find(candidate.question_id), []).append(candidate.question_id)
    return [sorted(ids) for ids in groups.values() if len(ids) >= 2]


def merge_refs(candidates: Iterable[QuestionCandidate], frontiers: Iterable[FrontierMarker]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in list(candidates) + list(frontiers):
        for ref in item.source_refs:
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
    return refs[:12]


def ordered_questions(candidates: Iterable[QuestionCandidate]) -> list[QuestionCandidate]:
    return sorted(
        candidates,
        key=lambda item: (
            parse_timestamp(item.first_seen) or datetime.max.replace(tzinfo=timezone.utc),
            len(axis_tokens(item)),
            item.question_id,
        ),
    )


def dependency_edges(candidates: list[QuestionCandidate]) -> list[dict[str, Any]]:
    ordered = ordered_questions(candidates)
    if len(ordered) < 2:
        return []
    root = ordered[0]
    edges = []
    for child in ordered[1:]:
        edges.append(
            {
                "from_question_id": child.question_id,
                "to_question_id": root.question_id,
                "relation": "ordered_after",
                "evidence_type": "heuristic_temporal_specificity_order",
                "reason": "ordering hint from first_seen then question specificity; not a factual dependency claim",
                "source_refs": merge_refs([root, child], [])[:6],
            }
        )
    return edges


def frontiers_for_cluster(
    candidates: Iterable[QuestionCandidate], frontiers: Iterable[FrontierMarker]
) -> list[FrontierMarker]:
    labels = {
        token
        for candidate in candidates
        for token in normalize_tokens(candidate.question_short, candidate.question_text)
    }
    out = []
    for frontier in frontiers:
        frontier_tokens = set(normalize_tokens(frontier.linked_question_short, frontier.boundary_reason))
        if labels and frontier_tokens and labels & frontier_tokens:
            out.append(frontier)
    return out[:6]


def question_link_fingerprint(cluster_id: str, question_ids: Iterable[str]) -> str:
    return stable_digest(cluster_id, "|".join(sorted(question_ids)), prefix="sf", length=20)


def cluster_link_type(pairs: Iterable[PairDecision]) -> str:
    explicit = [pair.link_type for pair in pairs if pair.confirmation]
    if explicit:
        if any(value in {"parent_of", "child_of", "evolving"} for value in explicit):
            return "evolving"
        if "recurring" in explicit:
            return "recurring"
        return "related"
    return "recurring"


def build_question_link(
    cluster_candidates: list[QuestionCandidate],
    pairs: list[PairDecision],
    frontiers: list[FrontierMarker],
) -> dict[str, Any]:
    ordered = ordered_questions(cluster_candidates)
    question_ids = [candidate.question_id for candidate in ordered]
    cluster_id = stable_digest(*question_ids, prefix="ql", length=18)
    accepted_pairs = [
        pair
        for pair in pairs
        if pair.decision == "accepted" and pair.left_id in question_ids and pair.right_id in question_ids
    ]
    source_refs = merge_refs(ordered, frontiers)
    first_seen = ordered[0].first_seen
    last_seen = ordered[-1].first_seen
    label = ordered[0].question_short or ordered[0].title or ordered[0].question_text
    link_type = cluster_link_type(accepted_pairs)
    confidence = round(
        min(0.98, sum(pair.confidence for pair in accepted_pairs) / max(1, len(accepted_pairs))),
        4,
    )
    linked_questions = [
        {
            "question_id": candidate.question_id,
            "source_finding_id": candidate.finding_id,
            "question_text": candidate.question_text,
            "question_short": candidate.question_short,
            "intent_orientation": candidate.intent_orientation,
            "what_features": list(candidate.what_features),
            "where_context": list(candidate.where_context),
            "phase_context": candidate.phase_context,
            "first_seen": candidate.first_seen,
            "source_refs": list(candidate.source_refs),
        }
        for candidate in ordered
    ]
    confirmed_pairs = [pair for pair in accepted_pairs if pair.confirmation]
    return {
        "job": "question_tracking",
        "kind": QUESTION_LINK_KIND,
        "finding_kind": QUESTION_LINK_KIND,
        "title": compact_text(f"Question continuity: {label}", 140),
        "summary": compact_text(
            f"Tracked {len(ordered)} source-backed question candidates as {link_type}.", 480
        ),
        "confidence": confidence,
        "source_refs": source_refs,
        "concepts": unique_preserve(
            [value for candidate in ordered for value in candidate.what_features + candidate.concepts],
            limit=14,
        ),
        "recommendation": "",
        "question_cluster_id": cluster_id,
        "linked_question_short": compact_text(label, 90),
        "question_count": len(ordered),
        "source_thread_count": len({ref.get("thread_key") for ref in source_refs if ref.get("thread_key")}),
        "link_type": link_type,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "evolution_note": compact_text(
            " -> ".join(candidate.question_short or candidate.question_text for candidate in ordered),
            300,
        ),
        "question_source_finding_ids": [candidate.finding_id for candidate in ordered],
        "linked_questions": linked_questions,
        "dependency_edges": dependency_edges(ordered),
        "frontier_refs": [
            {
                "source_finding_id": frontier.finding_id,
                "frontier_type": frontier.frontier_type,
                "linked_question_short": frontier.linked_question_short,
                "boundary_reason": frontier.boundary_reason,
                "source_refs": list(frontier.source_refs),
            }
            for frontier in frontiers
        ],
        "match_evidence": {
            "method": "deterministic_multifield_hash_vector_v1",
            "strong_pair_count": sum(1 for pair in accepted_pairs if not pair.confirmation),
            "borderline_confirmed_pair_count": len(confirmed_pairs),
            "accepted_pairs": [
                {
                    "pair_id": pair.pair_id,
                    "left_question_id": pair.left_id,
                    "right_question_id": pair.right_id,
                    "score": pair.score,
                    "link_type": pair.link_type,
                    "confidence": pair.confidence,
                    "reason": pair.reason,
                    "confirmation": pair.confirmation,
                }
                for pair in accepted_pairs
            ],
        },
        "fingerprint": question_link_fingerprint(cluster_id, question_ids),
        "quality": {
            "bucket": "usable" if confidence < 0.82 else "strong",
            "promotion_readiness": confidence,
            "signals": {
                "source_ref_count": len(source_refs),
                "source_thread_count": len({ref.get("thread_key") for ref in source_refs if ref.get("thread_key")}),
                "question_count": len(ordered),
            },
        },
    }


def existing_question_link_ids(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    ids = set()
    for row in rows:
        if row.get("kind") != FINDING_ROW_KIND:
            continue
        if str(row.get("finding_kind") or "") != QUESTION_LINK_KIND:
            continue
        cluster_id = str(row.get("question_cluster_id") or "").strip()
        if cluster_id:
            ids.add(cluster_id)
    return ids


def load_tracking_inputs(
    path: Path, *, source_index: SourceRefIndex | None = None
) -> tuple[list[QuestionCandidate], list[FrontierMarker], dict[str, int], list[dict[str, Any]]]:
    rows = list(iter_jsonl(path))
    candidates: list[QuestionCandidate] = []
    frontiers: list[FrontierMarker] = []
    stale_candidates = 0
    stale_frontiers = 0
    for row in rows:
        finding_kind = str(row.get("finding_kind") or "")
        if row.get("kind") == FINDING_ROW_KIND and finding_kind == QUESTION_CANDIDATE_KIND:
            candidate = candidate_from_row(row, source_index=source_index)
            if candidate:
                candidates.append(candidate)
            else:
                stale_candidates += 1
        if row.get("kind") == FINDING_ROW_KIND and finding_kind == FRONTIER_MARKER_KIND:
            frontier = frontier_from_row(row, source_index=source_index)
            if frontier:
                frontiers.append(frontier)
            else:
                stale_frontiers += 1
    diagnostics = {
        "input_row_count": len(rows),
        "candidate_count": len(candidates),
        "frontier_count": len(frontiers),
        "stale_candidate_count": stale_candidates,
        "stale_frontier_count": stale_frontiers,
        "source_ref_index_thread_count": source_index.thread_count if source_index else 0,
        "source_ref_index_message_count": source_index.message_count if source_index else 0,
    }
    return candidates, frontiers, diagnostics, rows


def build_question_links(
    candidates: list[QuestionCandidate],
    frontiers: list[FrontierMarker],
    *,
    strong_threshold: float = DEFAULT_STRONG_THRESHOLD,
    borderline_threshold: float = DEFAULT_BORDERLINE_THRESHOLD,
    confirmation_fn: ConfirmationFn | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pair_decisions: list[PairDecision] = []
    skipped_borderline = 0
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            decision = decide_pair(
                left,
                right,
                strong_threshold=strong_threshold,
                borderline_threshold=borderline_threshold,
                confirmation_fn=confirmation_fn,
            )
            if not decision:
                continue
            if decision.decision == "needs_confirmation":
                skipped_borderline += 1
                pair_decisions.append(decision)
                continue
            pair_decisions.append(decision)
    accepted_pairs = [pair for pair in pair_decisions if pair.decision == "accepted"]
    by_id = {candidate.question_id: candidate for candidate in candidates}
    links: list[dict[str, Any]] = []
    for component_ids in connected_components(candidates, accepted_pairs):
        cluster_candidates = [by_id[question_id] for question_id in component_ids]
        cluster_frontiers = frontiers_for_cluster(cluster_candidates, frontiers)
        links.append(build_question_link(cluster_candidates, accepted_pairs, cluster_frontiers))
    links.sort(key=lambda item: (str(item.get("first_seen") or ""), str(item.get("question_cluster_id") or "")))
    diagnostics = {
        "pair_count": len(pair_decisions),
        "accepted_pair_count": len(accepted_pairs),
        "borderline_skipped_pair_count": skipped_borderline,
        "link_count": len(links),
    }
    return links, diagnostics


def append_question_links(
    path: Path,
    links: Iterable[dict[str, Any]],
    *,
    batch_id: str,
    source: str = "deterministic_question_tracking",
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for link in links:
            payload = dict(link)
            payload.pop("kind", None)
            payload.pop("finding_kind", None)
            event = {
                "schema_version": SCHEMA_VERSION,
                "kind": FINDING_ROW_KIND,
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": "deterministic",
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": {"provider": "deterministic"},
                "usage": {},
                "finding_kind": QUESTION_LINK_KIND,
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
    return count


def run_question_tracking(
    *,
    jobs_path: Path,
    registry_path: Path | None = None,
    output_path: Path | None = None,
    strong_threshold: float = DEFAULT_STRONG_THRESHOLD,
    borderline_threshold: float = DEFAULT_BORDERLINE_THRESHOLD,
    confirmation_fn: ConfirmationFn | None = None,
    no_write: bool = False,
) -> dict[str, Any]:
    output = output_path or jobs_path
    source_index = build_source_ref_index(registry_path)
    candidates, frontiers, input_diagnostics, rows = load_tracking_inputs(
        jobs_path, source_index=source_index
    )
    links, link_diagnostics = build_question_links(
        candidates,
        frontiers,
        strong_threshold=strong_threshold,
        borderline_threshold=borderline_threshold,
        confirmation_fn=confirmation_fn,
    )
    existing_ids = existing_question_link_ids(rows if output == jobs_path else iter_jsonl(output))
    fresh_links = [
        link for link in links if str(link.get("question_cluster_id") or "") not in existing_ids
    ]
    duplicate_count = len(links) - len(fresh_links)
    batch_id = f"question-tracking-{hashlib.sha1(now_utc().encode('utf-8')).hexdigest()[:12]}"
    wrote_count = 0
    if not no_write and fresh_links:
        wrote_count = append_question_links(output, fresh_links, batch_id=batch_id)
    return {
        "ok": True,
        "job": "question_tracking",
        "jobs_input": str(jobs_path),
        "registry": str(registry_path) if registry_path else None,
        "output": str(output),
        "candidate_count": input_diagnostics["candidate_count"],
        "frontier_count": input_diagnostics["frontier_count"],
        "stale_candidate_count": input_diagnostics["stale_candidate_count"],
        "stale_frontier_count": input_diagnostics["stale_frontier_count"],
        "source_ref_resolution": "registry_clean_source" if source_index else "shape_only",
        "source_ref_index_thread_count": input_diagnostics["source_ref_index_thread_count"],
        "source_ref_index_message_count": input_diagnostics["source_ref_index_message_count"],
        "pair_count": link_diagnostics["pair_count"],
        "accepted_pair_count": link_diagnostics["accepted_pair_count"],
        "borderline_skipped_pair_count": link_diagnostics["borderline_skipped_pair_count"],
        "link_count": len(links),
        "fresh_link_count": len(fresh_links),
        "duplicate_link_count": duplicate_count,
        "wrote_count": wrote_count,
        "wrote": bool(wrote_count),
        "no_write": no_write,
        "strong_threshold": strong_threshold,
        "borderline_threshold": borderline_threshold,
        "links": links,
        "batch_id": batch_id,
    }


def default_registry_path(registry: str | None, registry_dir: str | None) -> Path | None:
    if registry:
        return Path(registry).resolve()
    if registry_dir:
        registry_path, _ = registry_paths(Path(registry_dir).resolve())
        return registry_path
    registry_path, _ = registry_paths(None)
    return registry_path


def default_jobs_path(registry: str | None, registry_dir: str | None) -> Path:
    registry_path = default_registry_path(registry, registry_dir)
    if registry_path:
        return default_jobs_output_path(registry_path=registry_path)
    registry_path, _ = registry_paths(None)
    return default_jobs_output_path(registry_path=registry_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--output")
    parser.add_argument("--strong-threshold", type=float, default=DEFAULT_STRONG_THRESHOLD)
    parser.add_argument("--borderline-threshold", type=float, default=DEFAULT_BORDERLINE_THRESHOLD)
    parser.add_argument("--borderline-confirmations")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else default_jobs_path(args.registry, args.registry_dir)
    )
    registry_path = default_registry_path(args.registry, args.registry_dir)
    output_path = Path(args.output).resolve() if args.output else jobs_path
    try:
        confirmation_fn = load_confirmation_decisions(
            Path(args.borderline_confirmations).resolve()
            if args.borderline_confirmations
            else None
        )
        result = run_question_tracking(
            jobs_path=jobs_path,
            registry_path=registry_path,
            output_path=output_path,
            strong_threshold=args.strong_threshold,
            borderline_threshold=args.borderline_threshold,
            confirmation_fn=confirmation_fn,
            no_write=args.no_write,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"question candidates: {result['candidate_count']}")
        print(f"question links: {result['fresh_link_count']} fresh / {result['link_count']} total")
        print(f"stale candidates skipped: {result['stale_candidate_count']}")
        print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
