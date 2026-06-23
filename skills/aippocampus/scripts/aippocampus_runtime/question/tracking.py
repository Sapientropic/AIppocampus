#!/usr/bin/env python3
"""Deterministic Phase 2 question tracking over source-backed candidates.

`question_extraction` writes provisional question candidates into the shared
`subconscious_jobs.jsonl` staging stream.  This module reads those rows,
groups related questions, and writes append-only `question_link` findings back
to the same stream.  The tracking layer treats generated findings as navigation
structure only: every link must keep the original clean-source refs attached,
and source-backed borderline links materialize by default as low-confidence
navigation with `borderline_auto` audit metadata.  Explicit confirmation
artifacts remain an opt-in calibration mode for stricter review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
)
from aippocampus_runtime.question.confirmation import (
    ConfirmationFn,
    append_confirmation_requests,
    borderline_confirmation_request,
    confirmation_diagnostics,
    load_confirmation_decisions,
    normalize_confirmation,
)
from aippocampus_runtime.question.feedback_policy import (
    QuestionPairFeedback,
    load_question_pair_feedback,
    matching_pair_feedback,
)
from aippocampus_runtime.question.prefilter_report import question_tracking_prefilter_fields
from aippocampus_runtime.question.source_refs import (
    SourceRefIndex,
    build_source_ref_index,
    compact_source_refs,
    source_ref_key,
)
from aippocampus_runtime.question.tracking_types import (
    FrontierMarker,
    PairDecision,
    QuestionCandidate,
    axis_overlap,
    axis_tokens,
    candidate_salience,
    compact_string_list,
    first_seen_from,
    match_score,
    normalize_tokens,
    parse_timestamp,
    same_text,
    stable_digest,
)
from aippocampus_runtime.recall.ambient_policy import default_ambient_policy_path
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows
from aippocampus_runtime.subconscious.jobs_config import default_jobs_output_path

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-question-tracking-v1"
FINDING_ROW_KIND = "aippocampus_subconscious_job_finding"
QUESTION_CANDIDATE_KIND = "question_candidate"
FRONTIER_MARKER_KIND = "frontier_marker"
QUESTION_LINK_KIND = "question_link"
DEFAULT_STRONG_THRESHOLD = 0.80
DEFAULT_BORDERLINE_THRESHOLD = 0.66


def load_tracking_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_jsonl_dict_rows(path).rows

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
    concepts = compact_string_list(row.get("concepts"), limit=12)
    what_features = compact_string_list(row.get("what_features"), limit=10)
    where_context = compact_string_list(row.get("where_context"), limit=8)
    intent_orientation = compact_text(str(row.get("intent_orientation") or ""), 80)
    phase_context = compact_text(str(row.get("phase_context") or ""), 80)
    collaboration_context = compact_string_list(row.get("collaboration_context"), limit=8)
    question_short = compact_text(str(row.get("question_short") or row.get("title") or ""), 90)
    salience = candidate_salience(
        row,
        question_text=question_text,
        source_refs=refs,
        concepts=concepts,
        what_features=what_features,
        where_context=where_context,
        intent_orientation=intent_orientation,
        phase_context=phase_context,
        collaboration_context=collaboration_context,
    )
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
        question_short=question_short,
        title=compact_text(str(row.get("title") or question_text), 140),
        summary=compact_text(str(row.get("summary") or ""), 480),
        source_refs=refs,
        concepts=concepts,
        what_features=what_features,
        where_context=where_context,
        intent_orientation=intent_orientation,
        phase_context=phase_context,
        collaboration_context=collaboration_context,
        salience=salience,
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


def adaptive_pair_thresholds(
    left: QuestionCandidate,
    right: QuestionCandidate,
    *,
    strong_threshold: float,
    borderline_threshold: float,
    feedback: tuple[QuestionPairFeedback, ...] = (),
) -> dict[str, Any]:
    separation = 0.0
    completion = 0.0
    reasons: list[str] = []

    what = axis_overlap(left.what_features or left.concepts, right.what_features or right.concepts)
    where = axis_overlap(left.where_context, right.where_context)
    collab = axis_overlap(left.collaboration_context, right.collaboration_context)
    if what >= 0.45:
        completion += 0.18
        reasons.append("what_feature_overlap")
    elif (left.what_features or left.concepts) and (right.what_features or right.concepts):
        separation += 0.10
        reasons.append("what_feature_conflict")
    if where >= 0.50:
        completion += 0.12
        reasons.append("where_context_overlap")
    elif left.where_context and right.where_context:
        separation += 0.10
        reasons.append("where_context_conflict")
    if left.intent_orientation and right.intent_orientation:
        if same_text(left.intent_orientation, right.intent_orientation):
            completion += 0.16
            reasons.append("same_intent_orientation")
        else:
            separation += 0.22
            reasons.append("intent_orientation_conflict")
    if left.phase_context and right.phase_context:
        if same_text(left.phase_context, right.phase_context):
            completion += 0.08
            reasons.append("same_phase_context")
        else:
            separation += 0.06
            reasons.append("phase_context_shift")
    if collab >= 0.50:
        completion += 0.04
        reasons.append("collaboration_context_overlap")
    if left.salience.score >= 0.65 and right.salience.score >= 0.65:
        completion += 0.06
        reasons.append("both_high_salience")
    if not left.salience.trackable or not right.salience.trackable:
        separation += 0.26
        reasons.append("low_salience_candidate")
    pair_feedback = matching_pair_feedback(feedback, [left.finding_id, right.finding_id])
    if pair_feedback:
        separation += 0.55
        reasons.append("dismissal_feedback_separation")

    delta = (separation - completion) * 0.12
    strong = max(0.0, min(1.0, strong_threshold + delta))
    borderline = max(0.0, min(strong - 0.05, borderline_threshold + delta * 0.75))
    return {
        "strong_threshold": round(strong, 4),
        "borderline_threshold": round(borderline, 4),
        "separation_pressure": round(separation, 4),
        "completion_pressure": round(completion, 4),
        "feedback_signal_count": len(pair_feedback),
        "reasons": unique_preserve(reasons, limit=10),
    }


def pair_is_trackable(left: QuestionCandidate, right: QuestionCandidate) -> bool:
    if left.salience.trackable and right.salience.trackable:
        return True
    # A single low-salience candidate can still participate when the other
    # candidate is well-anchored and the wording is an exact repeat. Two generic
    # low-information candidates should not create a noisy question link.
    return (left.salience.trackable or right.salience.trackable) and same_text(
        left.question_text, right.question_text
    )


def decide_pair(
    left: QuestionCandidate,
    right: QuestionCandidate,
    *,
    strong_threshold: float,
    borderline_threshold: float,
    confirmation_fn: ConfirmationFn | None,
    auto_accept_borderline: bool = True,
    feedback: tuple[QuestionPairFeedback, ...] = (),
) -> PairDecision | None:
    if not pair_is_trackable(left, right):
        return None
    score = match_score(left, right)
    current_pair_id = pair_id(left, right)
    threshold_policy = adaptive_pair_thresholds(
        left,
        right,
        strong_threshold=strong_threshold,
        borderline_threshold=borderline_threshold,
        feedback=feedback,
    )
    effective_strong = float(threshold_policy["strong_threshold"])
    effective_borderline = float(threshold_policy["borderline_threshold"])
    if "dismissal_feedback_separation" in threshold_policy["reasons"]:
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="feedback_separated",
            link_type="related",
            confidence=0.0,
            reason="dismissal feedback increased separation pressure",
            threshold_policy=threshold_policy,
            acceptance_source="feedback_separated",
        )
    if score >= effective_strong:
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="accepted",
            link_type="recurring",
            confidence=round(min(0.98, 0.62 + score * 0.34), 4),
            reason="deterministic multi-field score met strong threshold",
            threshold_policy=threshold_policy,
            acceptance_source="strong_score",
        )
    if score < effective_borderline:
        return None
    payload = borderline_confirmation_request(
        left,
        right,
        score,
        threshold_policy,
        pair_id=current_pair_id,
        schema_version=SCHEMA_VERSION,
    )
    confirmation = normalize_confirmation(
        confirmation_fn(payload) if confirmation_fn else None,
        payload=payload,
    )
    if not confirmation and not auto_accept_borderline:
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="needs_confirmation",
            link_type="related",
            confidence=0.0,
            reason="borderline score skipped without explicit confirmation artifact",
            threshold_policy=threshold_policy,
            acceptance_source="borderline_confirmation_required",
            confirmation_request=payload,
        )
    if not confirmation:
        # Borderline pairs have already passed source-ref, salience, feedback,
        # and adaptive-threshold gates. Auto-accepting them keeps the question
        # layer usable; the evidence block preserves how weak the link was so
        # later feedback, confirmation artifacts, or threshold calibration can
        # identify the auto materialization instead of laundering it into a
        # strong match.
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="accepted",
            link_type="recurring",
            confidence=round(min(0.82, 0.56 + score * 0.34), 4),
            reason="borderline score auto-accepted by source-backed deterministic policy",
            threshold_policy=threshold_policy,
            acceptance_source="borderline_auto",
            confirmation_request=payload,
        )
    if confirmation.get("decision") == "reject":
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="confirmation_rejected",
            link_type="related",
            confidence=0.0,
            reason="borderline score rejected by explicit confirmation artifact",
            threshold_policy=threshold_policy,
            acceptance_source="borderline_confirmation_rejected",
            confirmation=confirmation,
            confirmation_request=payload,
        )
    if confirmation.get("decision") != "accept":
        if auto_accept_borderline:
            # Default unattended question tracking should not let stale or
            # malformed calibration artifacts recreate the old human-review
            # gate. Keep the ignored artifact in diagnostics, but let the
            # source-backed borderline pair materialize as low-confidence
            # navigation so later feedback can correct it.
            return PairDecision(
                pair_id=current_pair_id,
                left_id=left.question_id,
                right_id=right.question_id,
                score=score,
                decision="accepted",
                link_type="recurring",
                confidence=round(min(0.82, 0.56 + score * 0.34), 4),
                reason="borderline score auto-accepted after ignoring invalid confirmation artifact",
                threshold_policy=threshold_policy,
                acceptance_source="borderline_auto",
                confirmation_request=payload,
                ignored_confirmation=confirmation,
            )
        return PairDecision(
            pair_id=current_pair_id,
            left_id=left.question_id,
            right_id=right.question_id,
            score=score,
            decision="confirmation_invalid",
            link_type="related",
            confidence=0.0,
            reason="borderline confirmation artifact was invalid",
            threshold_policy=threshold_policy,
            acceptance_source="borderline_confirmation_invalid",
            confirmation=confirmation,
            confirmation_request=payload,
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
        threshold_policy=threshold_policy,
        acceptance_source="borderline_confirmation",
        confirmation=confirmation,
        confirmation_request=payload,
    )

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
            "salience": {
                "score": candidate.salience.score,
                "tags": list(candidate.salience.tags),
                "reasons": list(candidate.salience.reasons),
                "trackable": candidate.salience.trackable,
            },
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
            "strong_pair_count": sum(
                1 for pair in accepted_pairs if pair.acceptance_source == "strong_score"
            ),
            "borderline_auto_accepted_pair_count": sum(
                1 for pair in accepted_pairs if pair.acceptance_source == "borderline_auto"
            ),
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
                    "acceptance_source": pair.acceptance_source,
                    "threshold_policy": pair.threshold_policy,
                    "confirmation": pair.confirmation,
                    "ignored_confirmation": pair.ignored_confirmation,
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


def salience_tag_counts(candidates: Iterable[QuestionCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for tag in candidate.salience.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items()))


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
    rows = load_tracking_rows(path)
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
    auto_accept_borderline: bool = True,
    feedback: tuple[QuestionPairFeedback, ...] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pair_decisions: list[PairDecision] = []
    skipped_borderline = 0
    skipped_low_salience = 0
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            if not pair_is_trackable(left, right):
                skipped_low_salience += 1
                continue
            decision = decide_pair(
                left,
                right,
                strong_threshold=strong_threshold,
                borderline_threshold=borderline_threshold,
                confirmation_fn=confirmation_fn,
                auto_accept_borderline=auto_accept_borderline,
                feedback=feedback,
            )
            if not decision:
                continue
            if decision.decision == "feedback_separated":
                pair_decisions.append(decision)
                continue
            if decision.decision != "accepted":
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
        "borderline_auto_accepted_pair_count": sum(
            1 for pair in accepted_pairs if pair.acceptance_source == "borderline_auto"
        ),
        "borderline_auto_ignored_confirmation_count": sum(
            1 for pair in accepted_pairs if pair.ignored_confirmation
        ),
        "borderline_skipped_pair_count": skipped_borderline,
        **confirmation_diagnostics(pair_decisions),
        "pending_confirmation_request_count": sum(
            1
            for pair in pair_decisions
            if pair.decision == "needs_confirmation" and pair.confirmation_request
        ),
        "pending_confirmation_requests": [
            pair.confirmation_request
            for pair in pair_decisions
            if pair.decision == "needs_confirmation" and pair.confirmation_request
        ][:24],
        "feedback_separated_pair_count": sum(
            1 for pair in pair_decisions if pair.decision == "feedback_separated"
        ),
        "feedback_separation_audit": [
            {
                "pair_id": pair.pair_id,
                "score": pair.score,
                "reason": pair.reason,
                "threshold_policy": pair.threshold_policy,
            }
            for pair in pair_decisions
            if pair.decision == "feedback_separated"
        ][:24],
        "low_salience_pair_skipped_count": skipped_low_salience,
        "link_count": len(links),
        "salience_tag_counts": salience_tag_counts(candidates),
        "low_salience_candidate_count": sum(1 for candidate in candidates if not candidate.salience.trackable),
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
    pending_confirmations_output_path: Path | None = None,
    ambient_policy_path: Path | None = None,
    auto_accept_borderline: bool = True,
    no_write: bool = False,
) -> dict[str, Any]:
    output = output_path or jobs_path
    source_index = build_source_ref_index(registry_path)
    candidates, frontiers, input_diagnostics, rows = load_tracking_inputs(
        jobs_path, source_index=source_index
    )
    feedback_path = ambient_policy_path or (
        default_ambient_policy_path(registry_path=registry_path) if registry_path else None
    )
    feedback = load_question_pair_feedback(feedback_path)
    links, link_diagnostics = build_question_links(
        candidates,
        frontiers,
        strong_threshold=strong_threshold,
        borderline_threshold=borderline_threshold,
        confirmation_fn=confirmation_fn,
        auto_accept_borderline=auto_accept_borderline,
        feedback=feedback,
    )
    existing_ids = existing_question_link_ids(rows if output == jobs_path else load_tracking_rows(output))
    fresh_links = [
        link for link in links if str(link.get("question_cluster_id") or "") not in existing_ids
    ]
    duplicate_count = len(links) - len(fresh_links)
    batch_id = f"question-tracking-{hashlib.sha1(now_utc().encode('utf-8')).hexdigest()[:12]}"
    wrote_count = 0
    if not no_write and fresh_links:
        wrote_count = append_question_links(output, fresh_links, batch_id=batch_id)
    pending_confirmation_wrote_count = 0
    if pending_confirmations_output_path is not None:
        pending_confirmation_wrote_count = append_confirmation_requests(
            pending_confirmations_output_path,
            link_diagnostics["pending_confirmation_requests"],
        )
    result: dict[str, Any] = {
        "ok": True,
        "job": "question_tracking",
        "jobs_input": str(jobs_path),
        "registry": str(registry_path) if registry_path else None,
        "output": str(output),
        "candidate_count": input_diagnostics["candidate_count"],
        "frontier_count": input_diagnostics["frontier_count"],
        "stale_candidate_count": input_diagnostics["stale_candidate_count"],
        "stale_frontier_count": input_diagnostics["stale_frontier_count"],
        **question_tracking_prefilter_fields(input_diagnostics, link_diagnostics),
        "source_ref_resolution": "registry_clean_source" if source_index else "shape_only",
        "source_ref_index_thread_count": input_diagnostics["source_ref_index_thread_count"],
        "source_ref_index_message_count": input_diagnostics["source_ref_index_message_count"],
        "ambient_policy_path": str(feedback_path) if feedback_path else None,
        "question_pair_feedback_count": len(feedback),
        "pending_confirmation_wrote_count": pending_confirmation_wrote_count,
        "link_count": len(links),
        "fresh_link_count": len(fresh_links),
        "duplicate_link_count": duplicate_count,
        "wrote_count": wrote_count,
        "wrote": bool(wrote_count),
        "no_write": no_write,
        "strong_threshold": strong_threshold,
        "borderline_threshold": borderline_threshold,
        "auto_accept_borderline": auto_accept_borderline,
        "links": links,
        "batch_id": batch_id,
    }
    diagnostic_keys = (
        "pair_count accepted_pair_count borderline_auto_accepted_pair_count "
        "borderline_auto_ignored_confirmation_count "
        "borderline_skipped_pair_count "
        "borderline_confirmation_accepted_pair_count borderline_confirmation_rejected_pair_count "
        "borderline_confirmation_stale_pair_count borderline_confirmation_malformed_pair_count "
        "borderline_confirmation_source_mismatch_pair_count borderline_confirmation_audit "
        "pending_confirmation_request_count pending_confirmation_requests "
        "feedback_separated_pair_count feedback_separation_audit "
        "low_salience_pair_skipped_count low_salience_candidate_count salience_tag_counts"
    ).split()
    for key in diagnostic_keys:
        result[key] = link_diagnostics[key]
    return result


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
    parser.add_argument(
        "--require-borderline-confirmation",
        action="store_true",
        help=(
            "Restore the old calibration mode: borderline pairs write compact "
            "confirmation requests instead of auto-materializing question links."
        ),
    )
    parser.add_argument(
        "--pending-confirmations-output",
        help=(
            "Write JSONL confirmation-request payloads for borderline pairs that "
            "need external/live review."
        ),
    )
    parser.add_argument("--ambient-policy", help="Optional ambient_recall_policy.jsonl feedback overlay.")
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
            pending_confirmations_output_path=(
                Path(args.pending_confirmations_output).resolve()
                if args.pending_confirmations_output
                else None
            ),
            ambient_policy_path=Path(args.ambient_policy).resolve() if args.ambient_policy else None,
            auto_accept_borderline=not args.require_borderline_confirmation,
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
