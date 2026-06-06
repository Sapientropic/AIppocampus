#!/usr/bin/env python3
"""Route-context preparation for foreground prompt recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.recall.ambient_cache import topic_epoch_from_terms
from aippocampus_runtime.recall.living_cue_cache import (
    default_living_cues_path,
    load_living_cue_entries,
)
from aippocampus_runtime.recall.prompt_cues import (
    CONCEPT_EXPANSION_MAX_TERMS,
    expand_query_terms,
    semantic_gate_is_memory_cue,
    semantic_gate_terms,
    working_memory_terms,
)
from aippocampus_runtime.recall.prompt_recall_ambient import prompt_topic_signal_context
from aippocampus_runtime.recall.prompt_recall_budget import (
    PROBE_MIN_REMAINING_MS,
    budget_allows,
)
from aippocampus_runtime.recall.prompt_recall_core import (
    fallback_search_candidates,
    rerank_candidates_with_probe,
)
from aippocampus_runtime.recall.prompt_recall_hot_path import (
    candidate_indexes_from_registry,
    run_hot_path_funnel,
)
from aippocampus_runtime.recall.prompt_recall_semantic import run_semantic_gate_for_context
from aippocampus_runtime.recall.prompt_recall_threshold import scent_threshold_policy
from aippocampus_runtime.recall.query_policy import semantic_trigger_terms
from aippocampus_runtime.registry.api import unique_preserve

RECALL_SIGNAL_CUE_REASONS = {
    "topic_signal_accumulator_eased",
    "active_lock_roi_reinforced",
}


def association_seed_terms(association_matches: list[dict[str, Any]]) -> list[str]:
    association_terms: list[str] = []
    for match in association_matches:
        association_terms.append(str(match.get("term") or ""))
        association_terms.extend(str(value) for value in match.get("matched_terms") or [])
        if match.get("status") == "verified":
            association_terms.extend(str(value) for value in match.get("related_terms") or [])
    return association_terms


def semantic_trigger_seed_terms(matches: list[dict[str, Any]]) -> list[str]:
    return semantic_trigger_terms(matches, limit=24)


def _should_skip_default_semantic_gate_for_hot_path(
    *,
    hot_path_funnel: dict[str, Any],
    semantic_gate_mode: str | None,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None,
    natural_evidence: list[str],
    source_evidence: list[str],
) -> bool:
    """Skip only the default cold semantic path when a local route already exists."""

    return (
        hot_path_funnel.get("decision") == "scent"
        and str(semantic_gate_mode or "").casefold() != "on"
        and semantic_gate_fn is None
        and not natural_evidence
        and not source_evidence
    )


def _living_cue_entries_for_hot_path(
    *,
    registry_path: Path,
    living_cues_path: Path | str | None,
) -> list[dict[str, Any]]:
    living_cues_file = (
        Path(living_cues_path).resolve()
        if living_cues_path
        else default_living_cues_path(registry_path.parent)
    )
    return load_living_cue_entries(living_cues_file) if living_cues_file.exists() else []


def _run_local_hot_path(
    *,
    prompt: str,
    registry: dict[str, Any],
    registry_path: Path,
    local_seed_terms: list[str],
    living_cues_path: Path | str | None,
) -> dict[str, Any]:
    return run_hot_path_funnel(
        prompt=prompt,
        query_terms=local_seed_terms,
        candidate_indexes=candidate_indexes_from_registry(registry),
        living_cue_entries=_living_cue_entries_for_hot_path(
            registry_path=registry_path,
            living_cues_path=living_cues_path,
        ),
    )


def _threshold_adjustment_reasons(threshold_policy: dict[str, Any]) -> list[str]:
    return [
        str(item.get("reason"))
        for item in threshold_policy.get("adjustments") or []
        if isinstance(item, dict) and item.get("reason")
    ]


def prepare_route_context(
    *,
    prompt: str,
    context: Any,
    registry: dict[str, Any],
    registry_path: Path,
    cwd_path: Path,
    cognitive_map_matches: list[dict[str, Any]],
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    cognitive_map_terms: list[str],
    living_cues_path: Path | str | None,
    use_semantic_gate: bool,
    semantic_gate_mode: str | None,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None,
    semantic_cache_path: Path | str | None,
    semantic_timeout: float,
    natural_evidence: list[str],
    source_evidence: list[str],
    current_checkout_live_fact: bool,
    pre_explicit: list[str],
    ambient_cache_path: Path | str | None,
    thread_id: str | None,
    topic_epoch: str | None,
    start: float,
    max_elapsed_ms: int | None,
) -> dict[str, Any]:
    local_seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + cognitive_map_terms
        + association_seed_terms(association_matches)
        + semantic_trigger_seed_terms(context.semantic_trigger_matches)
        + working_memory_terms(working_memory_matches),
        limit=36,
    )
    hot_path_funnel = _run_local_hot_path(
        prompt=prompt,
        registry=registry,
        registry_path=registry_path,
        local_seed_terms=local_seed_terms,
        living_cues_path=living_cues_path,
    )
    effective_use_semantic_gate = use_semantic_gate
    if _should_skip_default_semantic_gate_for_hot_path(
        hot_path_funnel=hot_path_funnel,
        semantic_gate_mode=semantic_gate_mode,
        semantic_gate_fn=semantic_gate_fn,
        natural_evidence=natural_evidence,
        source_evidence=source_evidence,
    ):
        effective_use_semantic_gate = False
    semantic_result, semantic_gate_reuse = run_semantic_gate_for_context(
        prompt=prompt,
        context=context,
        semantic_cache_path=semantic_cache_path,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
        semantic_gate_fn=semantic_gate_fn,
        use_semantic_gate=effective_use_semantic_gate,
        start=start,
        max_elapsed_ms=max_elapsed_ms,
    )
    topic_signal_context = prompt_topic_signal_context(
        ambient_cache_path=ambient_cache_path,
        registry_path=registry_path,
        thread_id=thread_id,
        workspace=str(cwd_path),
        topic_epoch=topic_epoch,
        terms=local_seed_terms,
    )
    threshold_policy = scent_threshold_policy(
        prompt=prompt,
        thread_id=thread_id,
        topic_epoch=str(topic_signal_context.get("topic_epoch") or topic_epoch_from_terms([])),
        semantic_gate_reuse=semantic_gate_reuse,
        topic_signal_state=topic_signal_context.get("topic_signal_state"),
        route_roi_summary=topic_signal_context.get("route_roi_summary"),
        explicit_recall_intent=bool(pre_explicit or natural_evidence or source_evidence),
        current_checkout_live_fact=current_checkout_live_fact,
    )
    adjustment_reasons = _threshold_adjustment_reasons(threshold_policy)
    # Repeated weak same-topic routes and proven active-lock ROI are a small
    # positive recall cue. Negative ROI only raises the threshold; it must not
    # keep a bad route alive as a cue.
    threshold_memory_cue = bool(RECALL_SIGNAL_CUE_REASONS & set(adjustment_reasons))
    seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + cognitive_map_terms
        + association_seed_terms(association_matches)
        + semantic_trigger_seed_terms(context.semantic_trigger_matches)
        + working_memory_terms(working_memory_matches)
        + semantic_gate_terms(semantic_result),
        limit=36,
    )
    return {
        "local_seed_terms": local_seed_terms,
        "hot_path_funnel": hot_path_funnel,
        "effective_use_semantic_gate": effective_use_semantic_gate,
        "semantic_result": semantic_result,
        "semantic_gate_reuse": semantic_gate_reuse,
        "topic_signal_context": topic_signal_context,
        "threshold_policy": threshold_policy,
        "threshold_adjustment_reasons": adjustment_reasons,
        "threshold_memory_cue": threshold_memory_cue,
        "seed_terms": seed_terms,
    }


def candidate_memory_context(
    *,
    registry: dict[str, Any],
    query_terms: list[str],
    candidates: list[dict[str, Any]],
    explicit: list[str],
    associative: list[str],
    important: list[str],
    association_matches: list[dict[str, Any]],
    cognitive_map_matches: list[dict[str, Any]],
    concept_expansions: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    semantic_result: dict[str, Any] | None,
    natural_evidence: list[str],
    source_evidence: list[str],
    negative_evidence: list[str],
    threshold_memory_cue: bool,
    start: float,
    max_elapsed_ms: int | None,
) -> dict[str, Any]:
    semantic_memory_cue = semantic_gate_is_memory_cue(semantic_result)
    if not candidates and (
        explicit or associative or natural_evidence or source_evidence or semantic_memory_cue
    ):
        candidates = fallback_search_candidates(registry, query_terms)
    timeline_memory_cue = any(item.get("life_wide_timeline_source") for item in candidates)
    hot_path_memory_cue = any(item.get("hot_path_source") for item in candidates)
    positive_evidence_intent = bool((natural_evidence or source_evidence) and not negative_evidence)
    has_memory_cue = bool(
        explicit
        or associative
        or important
        or association_matches
        or cognitive_map_matches
        or concept_expansions
        or working_memory_matches
        or semantic_memory_cue
        or timeline_memory_cue
        or hot_path_memory_cue
        or positive_evidence_intent
        or threshold_memory_cue
    )
    if candidates and has_memory_cue and budget_allows(start, max_elapsed_ms, PROBE_MIN_REMAINING_MS):
        candidates = rerank_candidates_with_probe(candidates, query_terms)
    return {
        "candidates": candidates,
        "semantic_memory_cue": semantic_memory_cue,
        "positive_evidence_intent": positive_evidence_intent,
        "has_memory_cue": has_memory_cue,
    }


__all__ = [
    "CONCEPT_EXPANSION_MAX_TERMS",
    "association_seed_terms",
    "candidate_memory_context",
    "prepare_route_context",
    "semantic_trigger_seed_terms",
]
