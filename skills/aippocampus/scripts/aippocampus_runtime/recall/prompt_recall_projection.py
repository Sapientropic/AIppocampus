#!/usr/bin/env python3
"""Final foreground recall decision and source-evidence projection stage."""

from __future__ import annotations

from typing import Any, Mapping

from aippocampus_runtime.recall.foreground_confidence import (
    foreground_recall_confidence_decision,
)
from aippocampus_runtime.recall.prompt_cues import (
    current_checkout_live_fact_intent,
    is_decision_continuation,
    negative_evidence_intent,
    semantic_gate_can_request_evidence,
    semantic_gate_can_request_source_reopen,
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
from aippocampus_runtime.recall.prompt_route_blocks import memory_route_block_intent
from aippocampus_runtime.recall.query_profile import classify_query_profile


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
    if memory_route_block_intent(prompt):
        reasons.append("memory route withheld: user blocked old or superseded route")
        return []
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
    source_reopen_route_ready: bool = False,
    reasons: list[str],
) -> str | None:
    if (
        not semantic_gate_can_request_source_reopen(prompt, semantic_result)
        or evidence
        or source_reopen_route_ready
    ):
        return None
    reasons.append("semantic evidence did not bridge to source-backed evidence")
    return "semantic_evidence_without_source_bridge"


def semantic_delivery_reuse_source(
    *,
    raw_source: object,
    semantic_result: Mapping[str, Any],
    semantic_gate_mode: object,
    cold_shadowed: bool,
) -> str:
    source = _controlled_text(
        raw_source,
        {"none", "exact_semantic_cache", "cold_model_call", "semantic_cue_cache"},
        default="none",
    ) or "none"
    if source in {"exact_semantic_cache", "semantic_cue_cache"}:
        return source
    if cold_shadowed:
        return "cold_semantic_shadowed"

    diagnostic = str(semantic_result.get("diagnostic") or "").casefold()
    availability = str(semantic_result.get("availability_reason") or "").casefold()
    buckets = _dict_value(semantic_result.get("error_buckets"))
    mode = str(semantic_gate_mode or "").casefold()
    disabled_or_auth = diagnostic == "semantic_disabled_or_auth_unavailable"
    if disabled_or_auth and mode == "off":
        return "semantic_disabled_by_operator"
    if disabled_or_auth or buckets.get("auth_error"):
        return "semantic_unavailable_missing_auth"
    if (
        diagnostic
        in {
            "semantic_provider_read_timeout",
            "semantic_overall_deadline_exceeded",
            "semantic_timed_out_under_foreground_budget",
        }
        or availability == "semantic_worker_timeout"
        or buckets.get("read_timeout")
        or buckets.get("overall_deadline")
    ):
        return "semantic_provider_timeout"
    if source == "cold_model_call":
        return "cold_semantic_attempted"
    return source


def route_delivery_diagnostic(*, state: Mapping[str, Any]) -> dict[str, Any]:
    """Project no-raw-prompt delivery diagnostics for the foreground hook.

    This intentionally reports only booleans, counts, and controlled labels.
    Semantic aliases, candidate ids, source snippets, and prompt text stay out:
    the diagnostic explains why a route did not reach the final packet without
    turning model-only semantic output into source-backed evidence.
    """

    query_profile = classify_query_profile(str(state.get("prompt") or ""))
    semantic_result = _dict_value(state.get("semantic_result"))
    semantic_gate_reuse = _dict_value(state.get("semantic_gate_reuse"))
    hot_path_funnel = _dict_value(state.get("hot_path_funnel"))
    candidates = _list_value(state.get("candidates"))
    evidence = _list_value(state.get("evidence"))
    semantic_bridge = _controlled_text(
        state.get("semantic_bridge_diagnostic"),
        {"semantic_evidence_without_source_bridge"},
    )
    semantic_mode = str(state.get("semantic_gate_mode") or "").casefold()
    cold_shadowed = bool(
        state.get("use_semantic_gate")
        and not state.get("effective_use_semantic_gate")
        and hot_path_funnel.get("decision") == "scent"
    )
    reuse_source = semantic_delivery_reuse_source(
        raw_source=semantic_gate_reuse.get("source"),
        semantic_result=semantic_result,
        semantic_gate_mode=semantic_mode,
        cold_shadowed=cold_shadowed,
    )
    cache_hit = bool(
        semantic_gate_reuse.get("exact_cache_hit")
        or semantic_result.get("cached")
        or str((semantic_result.get("cache_diagnostics") or {}).get("lookup") or "")
        == "hit"
    )
    semantic_cache_bridge_gap = bool(
        semantic_bridge == "semantic_evidence_without_source_bridge" and cache_hit
    )
    semantic_source_reopen_route = bool(state.get("semantic_source_reopen_route"))
    semantic_source_candidate_count = len(candidates) if semantic_source_reopen_route else 0
    semantic_partial_failure = bool(
        semantic_result.get("partial_success")
        or (
            semantic_result.get("available")
            and semantic_result.get("error_buckets")
        )
    )
    foreground_profile = "explicit_recall" if semantic_mode == "on" else "ambient_hot_path"
    return {
        "foreground_profile": foreground_profile,
        "foreground_route_profile": query_profile.get("profile") or "normal_recall",
        "foreground_lane": query_profile.get("lane") or "source_text",
        "generic_prompt_term_count": int(query_profile.get("generic_prompt_term_count") or 0),
        "specific_prompt_term_count": int(query_profile.get("specific_prompt_term_count") or 0),
        "semantic_trigger_generic_term_suppressed_count": (
            int(query_profile.get("generic_prompt_term_count") or 0)
            if query_profile.get("composer") == "suppress_generic_scent"
            else 0
        ),
        "foreground_suppression_reasons": (
            ["generic_meta_terms_only"]
            if query_profile.get("composer") == "suppress_generic_scent"
            else []
        ),
        "decision": _controlled_text(
            state.get("decision"), {"skip", "scent", "evidence"}, default="skip"
        ),
        "semantic_bridge_diagnostic": semantic_bridge,
        "semantic_gate_cache_hit_but_no_source_bridge": semantic_cache_bridge_gap,
        "semantic_reuse_source": reuse_source,
        "semantic_waited": reuse_source
        in {"cold_semantic_attempted", "semantic_provider_timeout"},
        "semantic_partial_failure": semantic_partial_failure,
        "cold_semantic_shadowed": cold_shadowed,
        "background_scheduled": False,
        "hot_path_candidates_after_merge": sum(
            1 for item in candidates if isinstance(item, dict) and item.get("hot_path_source")
        ),
        "final_candidate_count": len(candidates),
        "evidence_count": len(evidence),
        "semantic_source_reopen_route": semantic_source_reopen_route,
        "semantic_source_reopen_candidate_count": semantic_source_candidate_count,
    }


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
    confidence_decision = foreground_recall_confidence_decision(
        prompt=prompt,
        candidates=candidates,
        working_memory_matches=working_memory_matches,
        query_terms=query_terms,
        explicit=explicit,
        associative=associative,
        cognitive_map_matches=cognitive_map_matches,
        semantic_memory_cue=semantic_memory_cue,
        positive_evidence_intent=positive_evidence_intent,
        has_memory_cue=has_memory_cue,
        suppressed=suppressed,
        top_score=top_score,
        working_score=working_score,
        scent_threshold=scent_threshold,
    )
    if not confidence_decision["emit"]:
        reasons.append(
            "foreground recall withheld: "
            + str(confidence_decision["decision"]).replace("_", " ")
        )
        for reason in confidence_decision.get("reason_codes") or []:
            if reason in {
                "cue_only_below_confidence_floor",
                "fallback_only_below_confidence_floor",
                "zero_score_below_confidence_floor",
            }:
                reasons.append(str(reason))
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


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _controlled_text(
    value: Any, allowed: set[str], *, default: str | None = None
) -> str | None:
    text = str(value or "")
    return text if text in allowed else default


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
    if memory_route_block_intent(prompt):
        reasons.append("memory route withheld: user blocked old or superseded route")
        return []
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
