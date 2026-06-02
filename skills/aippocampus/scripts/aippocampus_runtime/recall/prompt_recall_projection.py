#!/usr/bin/env python3
"""Final foreground recall decision and source-evidence projection stage."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.recall.prompt_cues import (
    current_checkout_live_fact_intent,
    is_decision_continuation,
    negative_evidence_intent,
    semantic_gate_can_request_evidence,
)
from aippocampus_runtime.recall.prompt_recall_ambiguity import (
    explicit_evidence_request_is_ambiguous,
    semantic_evidence_request_is_vague_cross_project,
)
from aippocampus_runtime.recall.prompt_recall_budget import (
    EVIDENCE_MIN_REMAINING_MS,
    budget_allows,
)
from aippocampus_runtime.recall.prompt_recall_core import EVIDENCE_LITE_MIN_PROBE_SCORE
from aippocampus_runtime.recall.prompt_recall_evidence import collect_evidence


def source_intent_evidence(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    query_terms: list[str],
    search_budget: int,
    explicit: list[str],
    important: list[str],
    semantic_result: dict[str, Any] | None,
    natural_evidence: list[str],
    source_evidence: list[str],
    ambiguous_evidence_request: bool,
    start: float,
    max_elapsed_ms: int | None,
    reasons: list[str],
) -> list[dict[str, Any]]:
    semantic_wants_evidence = bool(semantic_gate_can_request_evidence(prompt, semantic_result))
    natural_wants_evidence = bool(natural_evidence or source_evidence)
    if negative_evidence_intent(prompt):
        reasons.append("evidence withheld: user requested scent-only context")
        return []
    if current_checkout_live_fact_intent(prompt):
        reasons.append("current checkout required: read current repo first")
        return []
    has_evidence_intent = bool(explicit or semantic_wants_evidence or natural_wants_evidence)
    if not (candidates and search_budget > 0 and has_evidence_intent and not ambiguous_evidence_request):
        return []
    budget_ok = budget_allows(start, max_elapsed_ms, EVIDENCE_MIN_REMAINING_MS)
    semantic_availability_reason = str(
        (semantic_result or {}).get("availability_reason") or ""
    ).strip()
    semantic_budget_was_spent = bool(
        semantic_result
        and semantic_availability_reason != "foreground_budget_skipped"
        and (semantic_wants_evidence or explicit or natural_wants_evidence)
    )
    if not budget_ok and not semantic_budget_was_spent:
        return []
    if not budget_ok:
        # Foreground semantic can spend most of the hook budget before the local
        # clean-source probe runs. When the prompt already has a real evidence
        # intent, keep this short deterministic probe alive so semantic help can
        # fail open instead of silently downgrading source-backed recall to scent.
        reasons.append("local evidence probe preserved after semantic budget spend")
    evidence = collect_evidence(candidates, query_terms, search_budget)
    if evidence and natural_wants_evidence and not (explicit or important or semantic_wants_evidence):
        reasons.append("natural evidence intent upgrade")
    if evidence and semantic_wants_evidence and not (explicit or important or natural_wants_evidence):
        reasons.append("semantic-context evidence upgrade")
    return evidence


def ambiguous_evidence_request(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    explicit: list[str],
    source_evidence: list[str],
    natural_evidence: list[str],
    semantic_result: dict[str, Any] | None,
    scent_threshold: float,
    reasons: list[str],
) -> bool:
    ambiguous = bool(
        explicit
        and explicit_evidence_request_is_ambiguous(
            prompt, candidates, scent_threshold=scent_threshold
        )
    )
    if ambiguous:
        reasons.append("source evidence withheld: ambiguous cross-project entity")
    if semantic_evidence_request_is_vague_cross_project(
        prompt,
        candidates=candidates,
        explicit=explicit,
        source_evidence=source_evidence,
        natural_evidence=natural_evidence,
        semantic_result=semantic_result,
    ):
        ambiguous = True
        reasons.append("source evidence withheld: vague cross-project referent")
    return ambiguous


def semantic_bridge_diagnostic(
    *,
    prompt: str,
    semantic_result: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    reasons: list[str],
) -> str | None:
    if not semantic_gate_can_request_evidence(prompt, semantic_result) or evidence:
        return None
    reasons.append("semantic evidence did not bridge to source-backed evidence")
    return "semantic_evidence_without_source_bridge"


def choose_decision_evidence(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    query_terms: list[str],
    search_budget: int,
    explicit: list[str],
    associative: list[str],
    important: list[str],
    cognitive_map_matches: list[dict[str, Any]],
    semantic_memory_cue: bool,
    positive_evidence_intent: bool,
    has_memory_cue: bool,
    suppressed: bool,
    top_score: float,
    working_score: float,
    scent_threshold: float,
    semantic_result: dict[str, Any] | None,
    natural_evidence: list[str],
    source_evidence: list[str],
    ambiguous_evidence_request: bool,
    association_matches: list[dict[str, Any]],
    start: float,
    max_elapsed_ms: int | None,
    reasons: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    if not (
        not suppressed
        and has_memory_cue
        and (candidates or working_memory_matches)
        and (
            top_score >= scent_threshold
            or working_score >= scent_threshold
            or explicit
            or associative
            or cognitive_map_matches
            or semantic_memory_cue
            or positive_evidence_intent
        )
    ):
        return "skip", evidence
    evidence = source_intent_evidence(
        prompt=prompt,
        candidates=candidates,
        query_terms=query_terms,
        search_budget=search_budget,
        explicit=explicit,
        important=important,
        semantic_result=semantic_result,
        natural_evidence=natural_evidence,
        source_evidence=source_evidence,
        ambiguous_evidence_request=ambiguous_evidence_request,
        start=start,
        max_elapsed_ms=max_elapsed_ms,
        reasons=reasons,
    )
    if evidence:
        return "evidence", evidence
    evidence = _evidence_lite_continuation(
        prompt=prompt,
        candidates=candidates,
        query_terms=query_terms,
        search_budget=search_budget,
        association_matches=association_matches,
        working_memory_matches=working_memory_matches,
        start=start,
        max_elapsed_ms=max_elapsed_ms,
        reasons=reasons,
    )
    return ("evidence" if evidence else "scent"), evidence


def _evidence_lite_continuation(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    query_terms: list[str],
    search_budget: int,
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    start: float,
    max_elapsed_ms: int | None,
    reasons: list[str],
) -> list[dict[str, Any]]:
    if not (
        candidates
        and search_budget > 0
        and is_decision_continuation(prompt)
        and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
        and budget_allows(start, max_elapsed_ms, EVIDENCE_MIN_REMAINING_MS)
    ):
        return []
    if association_matches:
        evidence = collect_evidence(candidates, query_terms, 1)
        if evidence:
            reasons.append("evidence-lite decision continuation")
            return evidence
    if working_memory_matches:
        evidence = collect_evidence(candidates, query_terms, 1)
        if evidence:
            reasons.append("working-memory evidence-lite decision continuation")
            return evidence
    return []
