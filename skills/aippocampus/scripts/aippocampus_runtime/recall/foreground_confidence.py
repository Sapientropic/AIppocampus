"""Auditable foreground recall confidence gate.

This module keeps the prompt hook's final emit/refine decision in one place.
The hook still has many cue sources, but a cue alone should not turn a weak,
fallback-only, or source-thin match into route-looking foreground recall.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.recall.query_profile import classify_query_profile

SCHEMA_VERSION = 1

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

DECISION_EMIT_CONFIDENT = "emit_confident_route"
DECISION_EMIT_UNCERTAIN = "emit_uncertain_route"
DECISION_REFINE_LOW_SPECIFICITY = "refine_low_specificity"
DECISION_SKIP_NO_CANDIDATE = "skip_no_candidate"


def foreground_recall_confidence_decision(
    *,
    prompt: str,
    candidates: Sequence[Mapping[str, Any]],
    working_memory_matches: Sequence[Mapping[str, Any]],
    query_terms: Sequence[str],
    explicit: Sequence[str],
    associative: Sequence[str],
    cognitive_map_matches: Sequence[Mapping[str, Any]],
    semantic_memory_cue: bool,
    positive_evidence_intent: bool,
    has_memory_cue: bool,
    suppressed: bool,
    top_score: float,
    working_score: float,
    scent_threshold: float,
) -> dict[str, Any]:
    """Return the single foreground recall confidence decision.

    Source-like route handles may orient recall, but the foreground should stay
    honest about confidence. Explicit user intent can keep a source-backed route
    available; associative/source-thin cues need a score floor or a precise
    reopenable route before they emit.
    """

    candidate_rows = [row for row in candidates if isinstance(row, Mapping)]
    working_rows = [row for row in working_memory_matches if isinstance(row, Mapping)]
    profile = classify_query_profile(str(prompt or ""))
    score_floor_met = float(top_score or 0.0) >= float(scent_threshold or 0.0)
    working_score_floor_met = float(working_score or 0.0) >= float(scent_threshold or 0.0)
    explicit_user_intent = bool(explicit or positive_evidence_intent)
    associative_intent = bool(associative or cognitive_map_matches or semantic_memory_cue)
    source_route_count = sum(1 for row in candidate_rows if _has_reopenable_shape(row))
    fallback_only = bool(candidate_rows) and all(bool(row.get("fallback")) for row in candidate_rows)
    empty_or_zero = bool(candidate_rows) and max(_candidate_score(row) for row in candidate_rows) <= 0.0
    low_specificity = _low_specificity_query(profile, query_terms)
    reason_codes: list[str] = []

    if suppressed:
        reason_codes.append("suppressed_by_prompt_policy")
    if not has_memory_cue:
        reason_codes.append("no_memory_cue")
    if not (candidate_rows or working_rows):
        reason_codes.append("no_route_or_working_memory_candidate")
    if score_floor_met:
        reason_codes.append("score_floor_met")
    if working_score_floor_met:
        reason_codes.append("working_memory_score_floor_met")
    if source_route_count:
        reason_codes.append("reopenable_route_shape_present")
    if explicit_user_intent:
        reason_codes.append("explicit_or_evidence_intent")
    if associative_intent:
        reason_codes.append("associative_or_semantic_cue")
    if fallback_only:
        reason_codes.append("fallback_only_candidate_set")
    if empty_or_zero:
        reason_codes.append("empty_or_zero_score_candidates")
    if low_specificity:
        reason_codes.append("low_specificity_query")

    base_ready = bool(
        not suppressed
        and has_memory_cue
        and (candidate_rows or working_rows)
        and (
            score_floor_met
            or working_score_floor_met
            or explicit_user_intent
            or associative_intent
        )
    )
    if not base_ready:
        return _decision(
            emit=False,
            decision=DECISION_SKIP_NO_CANDIDATE,
            confidence=CONFIDENCE_LOW,
            reason_codes=reason_codes,
            action="skip",
        )

    strong_source_intent = bool(explicit_user_intent and source_route_count)
    score_or_working = bool(score_floor_met or working_score_floor_met)
    cue_only = bool(associative_intent and not (score_or_working or strong_source_intent))

    if fallback_only and not strong_source_intent and not score_or_working:
        reason_codes.append("fallback_only_below_confidence_floor")
        return _decision(
            emit=False,
            decision=DECISION_REFINE_LOW_SPECIFICITY,
            confidence=CONFIDENCE_LOW,
            reason_codes=reason_codes,
            action="refine",
        )
    if empty_or_zero and not (strong_source_intent or working_score_floor_met):
        reason_codes.append("zero_score_below_confidence_floor")
        return _decision(
            emit=False,
            decision=DECISION_REFINE_LOW_SPECIFICITY,
            confidence=CONFIDENCE_LOW,
            reason_codes=reason_codes,
            action="refine",
        )
    if (low_specificity or cue_only) and not (strong_source_intent or score_or_working):
        reason_codes.append("cue_only_below_confidence_floor")
        return _decision(
            emit=False,
            decision=DECISION_REFINE_LOW_SPECIFICITY,
            confidence=CONFIDENCE_LOW,
            reason_codes=reason_codes,
            action="refine",
        )

    if score_or_working or strong_source_intent:
        confidence = CONFIDENCE_HIGH if score_floor_met or strong_source_intent else CONFIDENCE_MEDIUM
        return _decision(
            emit=True,
            decision=DECISION_EMIT_CONFIDENT,
            confidence=confidence,
            reason_codes=reason_codes,
            action="emit",
        )

    reason_codes.append("uncertain_route_requires_short_boundary")
    return _decision(
        emit=True,
        decision=DECISION_EMIT_UNCERTAIN,
        confidence=CONFIDENCE_LOW,
        reason_codes=reason_codes,
        action="emit_uncertain",
    )


def _decision(
    *,
    emit: bool,
    decision: str,
    confidence: str,
    reason_codes: list[str],
    action: str,
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_foreground_recall_confidence_decision",
        "schema_version": SCHEMA_VERSION,
        "emit": bool(emit),
        "decision": decision,
        "route_confidence": confidence,
        "action": action,
        "claim_permission": "no_claim_before_reopen",
        "foreground_boundary": (
            "route_selection_only_reopen_before_claim"
            if emit
            else "ask_user_to_tighten_cue_or_reopen_source"
        ),
        "reason_codes": _unique(reason_codes),
    }


def _candidate_score(row: Mapping[str, Any]) -> float:
    for key in ("score", "probe_score", "rank_score", "hybrid_score"):
        value = row.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return max(0.0, float(value))
    return 0.0


def _has_reopenable_shape(row: Mapping[str, Any]) -> bool:
    if row.get("source_refs") or row.get("event_refs") or row.get("candidate_refs"):
        return True
    if row.get("source_handles") or row.get("source_handle_count"):
        return True
    if row.get("thread_key") and not row.get("source_free"):
        return True
    plan = row.get("reopen_plan")
    if isinstance(plan, Mapping) and str(plan.get("status") or "").casefold() == "ready":
        return True
    return False


def _low_specificity_query(profile: Mapping[str, Any], query_terms: Sequence[str]) -> bool:
    specific = int(profile.get("specific_prompt_term_count") or 0)
    generic = int(profile.get("generic_prompt_term_count") or 0)
    if specific == 0 and generic > 0:
        return True
    nonempty = [str(term).strip() for term in query_terms if str(term or "").strip()]
    return len(nonempty) == 1 and len(nonempty[0]) <= 3


def _unique(values: Sequence[str], *, limit: int = 12) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
        if len(result) >= limit:
            break
    return result
