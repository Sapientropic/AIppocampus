#!/usr/bin/env python3
"""Prompt recall decision logic for the AIppocampus foreground hook.

The UserPromptSubmit entrypoint imports this module only after its low-level
registry/search helpers are defined. Keeping the scoring orchestration here
prevents the hook glue from becoming the place every recall policy accumulates.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.navigation.concept_graph import expand_concepts
from aippocampus_runtime.recall.ambient_policy import policy_update_for_prompt
from aippocampus_runtime.recall.prompt_cues import (
    CONCEPT_EXPANSION_MAX_TERMS,
    concept_expansion_terms,
    current_checkout_live_fact_intent,
    expand_query_terms,
    is_decision_continuation,
    natural_evidence_intent,
    negative_evidence_intent,
    semantic_gate_can_request_evidence,
    semantic_gate_can_warm_cue_cache,
    semantic_gate_is_memory_cue,
    semantic_gate_terms,
    source_evidence_intent,
    working_memory_terms,
)
from aippocampus_runtime.recall.prompt_recall_ambient import (
    attach_ambient_recall,
    cached_cards_for_policy,
)
from aippocampus_runtime.recall.prompt_recall_ambiguity import (
    explicit_evidence_request_is_ambiguous,
    semantic_evidence_request_is_vague_cross_project,
)
from aippocampus_runtime.recall.prompt_recall_budget import (
    EVIDENCE_MIN_REMAINING_MS,
    PROBE_MIN_REMAINING_MS,
    budget_allows,
)
from aippocampus_runtime.recall.prompt_recall_context import build_recall_decision_context
from aippocampus_runtime.recall.prompt_recall_core import (
    DEFAULT_SEARCH_BUDGET,
    EVIDENCE_LITE_MIN_PROBE_SCORE,
    PROMPT_HOOK_SEMANTIC_TIMEOUT,
    SCENT_THRESHOLD,
    candidate_summary,
    cognitive_map_terms,
    default_project_timeline_path,
    fallback_search_candidates,
    load_project_timeline,
    merge_association_candidates,
    merge_cognitive_map_candidates,
    merge_timeline_candidates,
    rerank_candidates_with_probe,
    score_candidates,
    should_suppress,
    sort_candidates,
)
from aippocampus_runtime.recall.prompt_recall_evidence import (
    collect_evidence,
    strip_private_fields,
    strip_semantic_gate,
)
from aippocampus_runtime.recall.prompt_recall_semantic import run_semantic_gate_for_context
from aippocampus_runtime.recall.query_policy import semantic_trigger_terms
from aippocampus_runtime.recall.semantic_cue_cache import (
    default_semantic_cues_path,
    record_semantic_cue_hits,
)
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.subconscious.candidate_router import strip_for_hook


def _deep_archival_requested(prompt: str) -> bool:
    text = str(prompt or "").casefold()
    cues = (
        "原话", "原文", "逐字", "准确怎么说", "具体怎么说", "一字不差",
        "exact wording", "original wording", "verbatim", "quote", "dispute",
    )
    return any(cue in text for cue in cues)


def _association_seed_terms(association_matches: list[dict[str, Any]]) -> list[str]:
    association_terms: list[str] = []
    for match in association_matches:
        association_terms.append(str(match.get("term") or ""))
        association_terms.extend(str(value) for value in match.get("matched_terms") or [])
        if match.get("status") == "verified":
            association_terms.extend(str(value) for value in match.get("related_terms") or [])
    return association_terms


def _semantic_trigger_seed_terms(matches: list[dict[str, Any]]) -> list[str]:
    return semantic_trigger_terms(matches, limit=24)


def _decision_reasons(
    *,
    explicit: list[str],
    associative: list[str],
    association_matches: list[dict[str, Any]],
    cognitive_map_matches: list[dict[str, Any]],
    concept_expansions: list[dict[str, Any]],
    important: list[str],
    candidates: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    semantic_result: dict[str, Any] | None,
    natural_evidence: list[str],
    source_evidence: list[str],
    suppressed: bool,
) -> list[str]:
    reasons: list[str] = []
    if explicit:
        reasons.append("explicit recall cue: " + ", ".join(explicit[:4]))
    if associative:
        reasons.append("associative cue: " + ", ".join(associative[:4]))
    if association_matches:
        reasons.append(
            "dynamic association: "
            + ", ".join(str(item.get("term") or "") for item in association_matches[:4])
        )
    if cognitive_map_matches:
        reasons.append(
            "cognitive map route: "
            + ", ".join(
                str((item.get("landmark_labels") or item.get("matched_cues") or [""])[0])
                for item in cognitive_map_matches[:3]
            )
        )
    if concept_expansions:
        reasons.append(
            "concept graph expansion: "
            + ", ".join(str(item.get("term") or "") for item in concept_expansions[:4])
        )
    if important:
        reasons.append("importance cue: " + ", ".join(important[:3]))
    if natural_evidence:
        reasons.append("natural evidence intent: " + ", ".join(natural_evidence[:2]))
    if source_evidence:
        reasons.append("source evidence intent: " + ", ".join(source_evidence[:2]))
    if candidates:
        reasons.append(
            "registry overlap: " + ", ".join(str(item["title"]) for item in candidates[:2])
        )
    if any(item.get("probe_score") for item in candidates[:3]):
        reasons.append("clean-source probe rerank")
    if any(item.get("life_wide_timeline_source") for item in candidates[:3]):
        reasons.append("life-wide timeline cue")
    elif any(item.get("timeline_source") for item in candidates[:3]):
        reasons.append("project timeline recency cue")
    if working_memory_matches:
        reasons.append(
            "soft working memory: "
            + ", ".join(str(item.get("title") or "") for item in working_memory_matches[:2])
        )
    if semantic_result and semantic_result.get("available"):
        aliases = ", ".join(str(item) for item in (semantic_result.get("query_aliases") or [])[:4])
        semantic_reason = f"semantic gate: {semantic_result.get('decision')} confidence={semantic_result.get('confidence')}"
        if aliases:
            semantic_reason += f" aliases={aliases}"
        reasons.append(semantic_reason)
    if suppressed:
        reasons.append("suppressed ordinary code-surface prompt")
    return reasons


def _score_recall_candidates(
    *,
    prompt: str,
    registry: dict[str, Any],
    timeline: dict[str, Any],
    cwd_path: Path,
    query_terms: list[str],
    cognitive_map_matches: list[dict[str, Any]],
    association_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not prompt:
        return []
    candidates = score_candidates(prompt, registry, query_terms)
    candidates = merge_cognitive_map_candidates(
        candidates, registry, cognitive_map_matches, query_terms
    )
    candidates = merge_association_candidates(
        candidates, registry, association_matches, query_terms
    )
    return merge_timeline_candidates(candidates, registry, timeline, prompt, cwd_path, query_terms)


def _merge_semantic_trigger_source_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    semantic_trigger_matches: list[dict[str, Any]],
    query_terms: list[str],
) -> list[dict[str, Any]]:
    """Let reviewed/learned cue refs wake their source thread without a model call.

    Active semantic cues already require repeated hits and source refs before
    promotion. Reusing those refs here keeps multilingual foreground recall
    cache-first, instead of adding every translated phrase to hard-coded cue
    lists or waiting on a cold semantic worker inside the prompt-hook budget.
    """

    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    for trigger in semantic_trigger_matches:
        refs = [ref for ref in trigger.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            continue
        trigger_terms = semantic_trigger_terms([trigger], limit=8)
        for ref in refs[:4]:
            thread_key = str(ref.get("thread_key") or "")
            entry = by_thread.get(thread_key)
            if not entry:
                continue
            existing = by_key.get(thread_key)
            if existing:
                existing["score"] = round(
                    max(float(existing.get("score") or 0.0), SCENT_THRESHOLD), 3
                )
                existing["matched_terms"] = unique_preserve(
                    list(existing.get("matched_terms") or []) + trigger_terms,
                    limit=8,
                )
                continue
            item = candidate_summary(entry, SCENT_THRESHOLD, query_terms)
            item["matched_terms"] = unique_preserve(trigger_terms, limit=8)
            item["semantic_trigger_source"] = True
            candidates.append(item)
            by_key[thread_key] = item
    return sort_candidates(candidates)


def _noise_prompt_result(context: Any, start: float) -> dict[str, Any]:
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "decision": "skip",
        "score": 0.0,
        "confidence": "low",
        **context.hook_path_fields(),
        "query_terms": [],
        "cognitive_map": [],
        "concept_expansions": [],
        "reasons": ["suppressed system/goal noise"],
        "candidates": [],
        "evidence": [],
        "working_memory": [],
        "semantic_gate": None,
        "semantic_bridge_diagnostic": None,
        "elapsed_ms": elapsed_ms,
    }


def _policy_update_result(context: Any, start: float, update: dict[str, Any]) -> dict[str, Any]:
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "decision": "skip",
        "score": 0.0,
        "confidence": "low",
        **context.hook_path_fields(),
        "query_terms": [],
        "cognitive_map": [],
        "concept_expansions": [],
        "reasons": [f"ambient policy {update.get('action')} {update.get('status')}"],
        "candidates": [],
        "evidence": [],
        "working_memory": [],
        "semantic_gate": None,
        "semantic_bridge_diagnostic": None,
        "semantic_cue_cache": None,
        "ambient_policy_update": update,
        "elapsed_ms": elapsed_ms,
    }


def _maybe_policy_update_result(
    *,
    context: Any,
    prompt: str,
    registry_path: Path,
    ambient_cache_path: Path | str | None,
    thread_id: str | None,
    workspace: str,
    start: float,
) -> dict[str, Any] | None:
    update = policy_update_for_prompt(
        prompt=prompt,
        rows=context.working_memory_all_rows,
        cached_cards=cached_cards_for_policy(
            registry_path=registry_path,
            ambient_cache_path=ambient_cache_path,
            thread_id=thread_id,
            workspace=workspace,
        ),
        policy_path=context.ambient_policy_path,
        thread_id=thread_id,
        workspace=workspace,
    )
    return _policy_update_result(context, start, update) if update is not None else None


def _source_intent_evidence(
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


def _ambiguous_evidence_request(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    explicit: list[str],
    source_evidence: list[str],
    natural_evidence: list[str],
    semantic_result: dict[str, Any] | None,
    reasons: list[str],
) -> bool:
    ambiguous = bool(
        explicit
        and explicit_evidence_request_is_ambiguous(
            prompt, candidates, scent_threshold=SCENT_THRESHOLD
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


def _semantic_bridge_diagnostic(
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


def _choose_decision_evidence(
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
            top_score >= SCENT_THRESHOLD
            or working_score >= SCENT_THRESHOLD
            or explicit
            or associative
            or cognitive_map_matches
            or semantic_memory_cue
            or positive_evidence_intent
        )
    ):
        return "skip", evidence
    evidence = _source_intent_evidence(
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
        prompt=prompt, candidates=candidates, query_terms=query_terms, search_budget=search_budget,
        association_matches=association_matches, working_memory_matches=working_memory_matches,
        start=start, max_elapsed_ms=max_elapsed_ms, reasons=reasons,
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


def _semantic_cue_source_refs(
    *,
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for hit in evidence:
        refs.append(
            {
                "thread_key": hit.get("thread_key"),
                "title": hit.get("title"),
                "line": hit.get("line"),
                "source_line": hit.get("line"),
                "source": hit.get("source"),
                "turn_index": hit.get("turn_index"),
            }
        )
    if refs:
        return refs
    for candidate in candidates[:3]:
        refs.append(
            {
                "thread_key": candidate.get("thread_key"),
                "title": candidate.get("title"),
                "project_label": candidate.get("project_label"),
                "source": "registry_candidate",
            }
        )
    return refs


def _limit_dream_matches(matches: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return matches
    allowed = max(0, int(limit))
    kept_dreams = 0
    out: list[dict[str, Any]] = []
    for item in matches:
        if item.get("candidate_type") != "dream_hypothesis":
            out.append(item)
            continue
        if kept_dreams >= allowed:
            continue
        kept_dreams += 1
        out.append(item)
    return out


def _record_semantic_cue_hits(
    *,
    prompt: str,
    semantic_result: dict[str, Any] | None,
    semantic_cues_path: Path | str | None,
    registry_path: Path,
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    suppressed: bool,
) -> dict[str, Any] | None:
    if (
        suppressed
        or not semantic_result
        or not semantic_gate_can_warm_cue_cache(semantic_result)
        or not candidates
    ):
        return None
    path = (
        Path(semantic_cues_path).resolve()
        if semantic_cues_path
        else default_semantic_cues_path(registry_path=registry_path)
    )
    refs = _semantic_cue_source_refs(evidence=evidence, candidates=candidates)
    try:
        return record_semantic_cue_hits(
            path,
            prompt=prompt,
            semantic_result=semantic_result,
            source_refs=refs,
            route="semantic_gate",
        )
    except Exception as exc:
        # Cue cache writes are learning hints. The foreground hook must keep
        # recall behavior intact even when the local cache is read-only or stale.
        return {
            "path": str(path),
            "updated_count": 0,
            "active_count": 0,
            "warning": {
                "stage": "semantic_cue_cache_write",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        }


def assess_prompt(
    prompt: str,
    *,
    cwd: Path | str,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    associations_path: Path | str | None = None,
    cognitive_map_path: Path | str | None = None,
    concept_graph_path: Path | str | None = None,
    working_memory_path: Path | str | None = None,
    semantic_triggers_path: Path | str | None = None,
    semantic_cues_path: Path | str | None = None,
    ambient_policy_path: Path | str | None = None,
    semantic_cache_path: Path | str | None = None,
    semantic_gate_mode: str | None = None,
    semantic_timeout: float = PROMPT_HOOK_SEMANTIC_TIMEOUT,
    use_semantic_gate: bool = True,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None = None,
    use_cognitive_map: bool = True,
    use_concept_graph: bool = True,
    search_budget: int = DEFAULT_SEARCH_BUDGET,
    max_elapsed_ms: int | None = None,
    thread_id: str | None = None, ambient_cache_path: Path | str | None = None,
    topic_epoch: str | None = None, use_thread_cache: bool = True,
    warm_background: bool | None = None, warm_job_dir: Path | str | None = None,
    warm_max_workers: int | None = None, warm_timeout: float | None = None, warm_quorum: int | None = None,
    dream_hypothesis_limit: int | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    context = build_recall_decision_context(
        prompt,
        cwd=cwd,
        registry_path=registry_path,
        registry_dir=registry_dir,
        associations_path=associations_path,
        cognitive_map_path=cognitive_map_path,
        concept_graph_path=concept_graph_path,
        working_memory_path=working_memory_path,
        semantic_triggers_path=semantic_triggers_path,
        semantic_cues_path=semantic_cues_path,
        ambient_policy_path=ambient_policy_path,
        use_cognitive_map=use_cognitive_map,
    )
    prompt = context.prompt
    cwd_path = context.cwd_path
    path = context.registry_path
    concept_file = context.concept_graph_path
    ambient_policy_file = context.ambient_policy_path
    if context.is_noise:
        return _noise_prompt_result(context, start)
    policy_result = _maybe_policy_update_result(
        context=context,
        prompt=prompt,
        registry_path=path,
        ambient_cache_path=ambient_cache_path,
        thread_id=thread_id,
        workspace=str(cwd_path),
        start=start,
    )
    if policy_result is not None:
        return policy_result
    registry = context.registry
    cognitive_map_matches = context.cognitive_map_matches
    working_memory_matches = _limit_dream_matches(context.working_memory_matches, dream_hypothesis_limit)
    association_matches = context.association_matches
    pre_explicit = context.pre_explicit
    pre_associative = context.pre_associative
    pre_important = context.pre_important
    natural_evidence = natural_evidence_intent(prompt)
    source_evidence = source_evidence_intent(prompt)
    negative_evidence = negative_evidence_intent(prompt)
    current_checkout_live_fact = current_checkout_live_fact_intent(prompt)
    semantic_result, semantic_gate_reuse = run_semantic_gate_for_context(
        prompt=prompt, context=context, semantic_cache_path=semantic_cache_path,
        semantic_gate_mode=semantic_gate_mode, semantic_timeout=semantic_timeout,
        semantic_gate_fn=semantic_gate_fn, use_semantic_gate=use_semantic_gate,
        start=start, max_elapsed_ms=max_elapsed_ms,
    )
    seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + cognitive_map_terms(cognitive_map_matches)
        + _association_seed_terms(association_matches)
        + _semantic_trigger_seed_terms(context.semantic_trigger_matches)
        + working_memory_terms(working_memory_matches)
        + semantic_gate_terms(semantic_result),
        limit=36,
    )
    concept_expansions: list[dict[str, Any]] = []
    query_terms = seed_terms
    explicit = pre_explicit
    associative = pre_associative
    important = pre_important

    timeline = load_project_timeline(default_project_timeline_path(path))
    candidates = _score_recall_candidates(
        prompt=prompt,
        registry=registry,
        timeline=timeline,
        cwd_path=cwd_path,
        query_terms=query_terms,
        cognitive_map_matches=cognitive_map_matches,
        association_matches=association_matches,
    )
    candidates = _merge_semantic_trigger_source_candidates(candidates, registry, context.semantic_trigger_matches, query_terms)
    if (
        not candidates
        and use_concept_graph
        and prompt
        and concept_file.exists()
        and budget_allows(start, max_elapsed_ms, PROBE_MIN_REMAINING_MS)
    ):
        # Concept BFS is a recall bridge for prompts whose surface words miss
        # registry associations. Once direct association/timeline candidates
        # already exist, expanding concepts can easily introduce semantic drift
        # and corrupt clean-source probe ranking, so keep it as a fallback.
        concept_expansions = expand_concepts(
            concept_file, seed_terms, depth=2, max_terms=CONCEPT_EXPANSION_MAX_TERMS
        )
        if concept_expansions:
            query_terms = unique_preserve(
                seed_terms + concept_expansion_terms(concept_expansions), limit=40
            )
            candidates = _score_recall_candidates(
                prompt=prompt,
                registry=registry,
                timeline=timeline,
                cwd_path=cwd_path,
                query_terms=query_terms,
                cognitive_map_matches=cognitive_map_matches,
                association_matches=association_matches,
            )
            candidates = _merge_semantic_trigger_source_candidates(candidates, registry, context.semantic_trigger_matches, query_terms)
    if not candidates and (explicit or associative or natural_evidence or source_evidence):
        # Metadata can miss memorable wording that only exists inside the
        # SQLite message index. When the user explicitly asks to recover prior
        # speech, try a tiny recent-thread fallback before staying silent.
        candidates = fallback_search_candidates(registry, query_terms)
    semantic_memory_cue = semantic_gate_is_memory_cue(semantic_result)
    timeline_memory_cue = any(item.get("life_wide_timeline_source") for item in candidates)
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
        or positive_evidence_intent
    )
    if candidates and has_memory_cue and budget_allows(start, max_elapsed_ms, PROBE_MIN_REMAINING_MS):
        candidates = rerank_candidates_with_probe(candidates, query_terms)
    suppressed = should_suppress(
        prompt,
        explicit,
        associative,
        candidates,
        working_memory_matches,
        cognitive_map_cue=bool(cognitive_map_matches),
        semantic_memory_cue=semantic_memory_cue,
        source_evidence_cue=bool((source_evidence or natural_evidence) and not negative_evidence),
    )
    top_score = float(candidates[0]["score"]) if candidates else 0.0
    working_score = max([float(item.get("score") or 0.0) for item in working_memory_matches] or [0.0])
    reasons = _decision_reasons(
        explicit=explicit,
        associative=associative,
        association_matches=association_matches,
        cognitive_map_matches=cognitive_map_matches,
        concept_expansions=concept_expansions,
        important=important,
        candidates=candidates,
        working_memory_matches=working_memory_matches,
        semantic_result=semantic_result,
        natural_evidence=natural_evidence,
        source_evidence=source_evidence,
        suppressed=suppressed,
    )
    if current_checkout_live_fact:
        reasons.append("current checkout required: read current repo first")
    ambiguous_evidence_request = _ambiguous_evidence_request(
        prompt=prompt,
        candidates=candidates,
        explicit=explicit,
        source_evidence=source_evidence,
        natural_evidence=natural_evidence,
        semantic_result=semantic_result,
        reasons=reasons,
    )

    decision, evidence = _choose_decision_evidence(
        prompt=prompt, candidates=candidates, working_memory_matches=working_memory_matches,
        query_terms=query_terms, search_budget=search_budget, explicit=explicit,
        associative=associative, important=important, cognitive_map_matches=cognitive_map_matches,
        semantic_memory_cue=semantic_memory_cue, positive_evidence_intent=positive_evidence_intent,
        has_memory_cue=has_memory_cue, suppressed=suppressed, top_score=top_score,
        working_score=working_score, semantic_result=semantic_result, natural_evidence=natural_evidence,
        source_evidence=source_evidence, ambiguous_evidence_request=ambiguous_evidence_request,
        association_matches=association_matches, start=start, max_elapsed_ms=max_elapsed_ms,
        reasons=reasons,
    )

    semantic_bridge_diagnostic = _semantic_bridge_diagnostic(
        prompt=prompt,
        semantic_result=semantic_result,
        evidence=evidence,
        reasons=reasons,
    )

    semantic_cue_cache = _record_semantic_cue_hits(
        prompt=prompt, semantic_result=semantic_result, semantic_cues_path=semantic_cues_path,
        registry_path=path, evidence=evidence, candidates=candidates, suppressed=suppressed,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    result = {
        "decision": decision,
        "score": round(max(top_score, working_score), 3),
        "confidence": "high" if decision == "evidence" else "medium" if decision == "scent" else "low",
        **context.hook_path_fields(),
        "query_terms": query_terms[:16],
        "cognitive_map": cognitive_map_matches[:4],
        "concept_expansions": concept_expansions[:8],
        "reasons": reasons or ["no ambient recall cue"],
        "candidates": strip_private_fields(candidates[:3]),
        "evidence": evidence[:search_budget],
        "working_memory": strip_for_hook(working_memory_matches[:3]),
        "ambient_policy": context.ambient_policy_diagnostics,
        "semantic_gate": strip_semantic_gate(semantic_result),
        "semantic_gate_reuse": semantic_gate_reuse,
        "semantic_bridge_diagnostic": semantic_bridge_diagnostic,
        "semantic_cue_cache": semantic_cue_cache,
        "elapsed_ms": elapsed_ms, "deep_archival_requested": _deep_archival_requested(prompt),
    }
    return attach_ambient_recall(
        result, prompt=prompt, thread_id=thread_id, workspace=str(cwd_path), registry_path=path,
        ambient_cache_path=ambient_cache_path, ambient_policy_path=ambient_policy_file, topic_epoch=topic_epoch, use_thread_cache=use_thread_cache, warm_background=warm_background, warm_job_dir=warm_job_dir,
        warm_max_workers=warm_max_workers, warm_timeout=warm_timeout, warm_quorum=warm_quorum,
    )
