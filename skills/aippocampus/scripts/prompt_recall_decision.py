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

from build_concept_graph import expand_concepts
from memory_candidate_router import strip_for_hook
from prompt_cues import (
    CONCEPT_EXPANSION_MAX_TERMS,
    concept_expansion_terms,
    expand_query_terms,
    is_decision_continuation,
    semantic_gate_can_request_evidence,
    semantic_gate_is_memory_cue,
    semantic_gate_terms,
    should_run_semantic_gate,
    working_memory_terms,
)
from prompt_recall_context import build_recall_decision_context
from prompt_recall_core import (
    DEFAULT_SEARCH_BUDGET,
    EVIDENCE_LITE_MIN_PROBE_SCORE,
    PROMPT_HOOK_SEMANTIC_TIMEOUT,
    SCENT_THRESHOLD,
    cognitive_map_terms,
    collect_evidence,
    default_project_timeline_path,
    fallback_search_candidates,
    load_project_timeline,
    merge_association_candidates,
    merge_cognitive_map_candidates,
    merge_timeline_candidates,
    rerank_candidates_with_probe,
    score_candidates,
    should_suppress,
    strip_private_fields,
    strip_semantic_gate,
)
from registry import unique_preserve
from semantic_recall_gate import run_semantic_gate

POST_SEMANTIC_RESERVE_MS = 1200.0
SEMANTIC_MIN_TIMEOUT_SECONDS = 0.5
PROBE_MIN_REMAINING_MS = 700.0
EVIDENCE_MIN_REMAINING_MS = 900.0


def _remaining_ms(start: float, max_elapsed_ms: int | None) -> float | None:
    if not max_elapsed_ms or max_elapsed_ms <= 0:
        return None
    return max(0.0, float(max_elapsed_ms) - ((time.perf_counter() - start) * 1000.0))


def _budget_allows(start: float, max_elapsed_ms: int | None, min_remaining_ms: float) -> bool:
    remaining = _remaining_ms(start, max_elapsed_ms)
    return remaining is None or remaining >= min_remaining_ms


def _semantic_timeout_for_budget(
    start: float,
    max_elapsed_ms: int | None,
    requested_timeout: float,
) -> float | None:
    if requested_timeout <= 0:
        return None
    remaining = _remaining_ms(start, max_elapsed_ms)
    if remaining is None:
        return requested_timeout
    available = remaining - POST_SEMANTIC_RESERVE_MS
    if available < SEMANTIC_MIN_TIMEOUT_SECONDS * 1000.0:
        return None
    return min(requested_timeout, max(SEMANTIC_MIN_TIMEOUT_SECONDS, available / 1000.0))


def _semantic_budget_result(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "query_aliases": [],
        "memory_scope": [],
        "reasons": [reason],
        "errors": [reason],
    }


def _association_seed_terms(association_matches: list[dict[str, Any]]) -> list[str]:
    association_terms: list[str] = []
    for match in association_matches:
        association_terms.append(str(match.get("term") or ""))
        association_terms.extend(str(value) for value in match.get("matched_terms") or [])
        if match.get("status") == "verified":
            association_terms.extend(str(value) for value in match.get("related_terms") or [])
    return association_terms


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


def _explicit_evidence_request_is_ambiguous(
    prompt: str,
    candidates: list[dict[str, Any]],
) -> bool:
    if len(candidates) < 2:
        return False
    strong = [
        candidate
        for candidate in candidates[:3]
        if float(candidate.get("score") or 0.0) >= SCENT_THRESHOLD
    ]
    if len(strong) < 2:
        return False
    labels = unique_preserve(
        [str(candidate.get("project_label") or "") for candidate in strong if candidate.get("project_label")],
        limit=4,
    )
    if len(labels) < 2:
        return False
    prompt_low = prompt.casefold()
    if any(label and label.casefold() in prompt_low for label in labels):
        return False
    shared_terms: dict[str, set[str]] = {}
    for candidate in strong:
        label = str(candidate.get("project_label") or "")
        for term in candidate.get("matched_terms") or []:
            normalized = str(term or "").strip().casefold()
            if len(normalized) < 3:
                continue
            shared_terms.setdefault(normalized, set()).add(label)
    if not any(len(term_labels) >= 2 for term_labels in shared_terms.values()):
        return False
    scores = [float(candidate.get("score") or 0.0) for candidate in strong[:2]]
    # If two project scopes are effectively tied on the same short entity and
    # the prompt did not name a project, source evidence would be guesswork.
    # Keep the ambient hint as scent and let the foreground model ask/follow up
    # instead of surfacing the wrong source-backed snippet.
    return abs(scores[0] - scores[1]) <= max(6.0, min(scores) * 0.15)


def _run_semantic_gate_for_prompt(
    *,
    prompt: str,
    cwd_path: Path,
    registry: dict[str, Any],
    registry_path: Path,
    associations: dict[str, Any],
    working_memory_rows: list[dict[str, Any]],
    semantic_triggers_file: Path,
    semantic_cache_path: Path | str | None,
    semantic_gate_mode: str | None,
    semantic_timeout: float,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None,
    use_semantic_gate: bool,
    start: float,
    max_elapsed_ms: int | None,
    explicit: list[str],
    associative: list[str],
    important: list[str],
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    cognitive_map_matches: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if (
        use_semantic_gate
        and prompt
        and should_run_semantic_gate(
            prompt,
            explicit=explicit,
            associative=associative,
            important=important,
            association_matches=association_matches,
            working_memory_matches=working_memory_matches,
            cognitive_map_matches=cognitive_map_matches,
        )
    ):
        gate = semantic_gate_fn or run_semantic_gate
        budgeted_timeout = _semantic_timeout_for_budget(
            start, max_elapsed_ms, float(semantic_timeout)
        )
        if budgeted_timeout is None:
            return _semantic_budget_result("semantic gate skipped by prompt hook foreground budget")
        try:
            return gate(
                prompt,
                cwd=cwd_path,
                registry=registry,
                registry_path=registry_path,
                associations=associations,
                working_memory=working_memory_rows,
                semantic_triggers_path=semantic_triggers_file,
                cache_path=Path(semantic_cache_path).resolve() if semantic_cache_path else None,
                mode=semantic_gate_mode,
                timeout=budgeted_timeout,
            )
        except Exception as exc:
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "reasons": [f"semantic gate error: {exc}"],
                "errors": [str(exc)],
            }
    if (
        use_semantic_gate
        and max_elapsed_ms
        and not _budget_allows(start, max_elapsed_ms, POST_SEMANTIC_RESERVE_MS)
    ):
        return _semantic_budget_result("semantic gate skipped by prompt hook foreground budget")
    return None


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
        "elapsed_ms": elapsed_ms,
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
    semantic_cache_path: Path | str | None = None,
    semantic_gate_mode: str | None = None,
    semantic_timeout: float = PROMPT_HOOK_SEMANTIC_TIMEOUT,
    use_semantic_gate: bool = True,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None = None,
    use_cognitive_map: bool = True,
    use_concept_graph: bool = True,
    search_budget: int = DEFAULT_SEARCH_BUDGET,
    max_elapsed_ms: int | None = None,
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
        use_cognitive_map=use_cognitive_map,
    )
    prompt = context.prompt
    cwd_path = context.cwd_path
    path = context.registry_path
    concept_file = context.concept_graph_path
    semantic_triggers_file = context.semantic_triggers_path
    if context.is_noise:
        return _noise_prompt_result(context, start)
    registry = context.registry
    cognitive_map_matches = context.cognitive_map_matches
    working_memory_rows = context.working_memory_rows
    working_memory_matches = context.working_memory_matches
    associations = context.associations
    association_matches = context.association_matches
    pre_explicit = context.pre_explicit
    pre_associative = context.pre_associative
    pre_important = context.pre_important
    semantic_result = _run_semantic_gate_for_prompt(
        prompt=prompt,
        cwd_path=cwd_path,
        registry=registry,
        registry_path=path,
        associations=associations,
        working_memory_rows=working_memory_rows,
        semantic_triggers_file=semantic_triggers_file,
        semantic_cache_path=semantic_cache_path,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
        semantic_gate_fn=semantic_gate_fn,
        use_semantic_gate=use_semantic_gate,
        start=start,
        max_elapsed_ms=max_elapsed_ms,
        explicit=pre_explicit,
        associative=pre_associative,
        important=pre_important,
        association_matches=association_matches,
        working_memory_matches=working_memory_matches,
        cognitive_map_matches=cognitive_map_matches,
    )
    seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + cognitive_map_terms(cognitive_map_matches)
        + _association_seed_terms(association_matches)
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
    if (
        not candidates
        and use_concept_graph
        and prompt
        and concept_file.exists()
        and _budget_allows(start, max_elapsed_ms, PROBE_MIN_REMAINING_MS)
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
    if not candidates and (explicit or associative):
        # Metadata can miss memorable wording that only exists inside the
        # SQLite message index. When the user explicitly asks to recover prior
        # speech, try a tiny recent-thread fallback before staying silent.
        candidates = fallback_search_candidates(registry, query_terms)
    semantic_memory_cue = semantic_gate_is_memory_cue(semantic_result)
    timeline_memory_cue = any(item.get("life_wide_timeline_source") for item in candidates)
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
    )
    if (
        candidates
        and has_memory_cue
        and _budget_allows(start, max_elapsed_ms, PROBE_MIN_REMAINING_MS)
    ):
        candidates = rerank_candidates_with_probe(candidates, query_terms)
    suppressed = should_suppress(
        prompt,
        explicit,
        associative,
        candidates,
        working_memory_matches,
        cognitive_map_cue=bool(cognitive_map_matches),
        semantic_memory_cue=semantic_memory_cue,
    )
    top_score = float(candidates[0]["score"]) if candidates else 0.0
    working_score = max(
        [float(item.get("score") or 0.0) for item in working_memory_matches] or [0.0]
    )
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
        suppressed=suppressed,
    )
    ambiguous_evidence_request = bool(
        explicit and _explicit_evidence_request_is_ambiguous(prompt, candidates)
    )
    if ambiguous_evidence_request:
        reasons.append("source evidence withheld: ambiguous cross-project entity")

    evidence: list[dict[str, Any]] = []
    decision = "skip"
    if (
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
        )
    ):
        decision = "scent"
        semantic_wants_evidence = bool(semantic_gate_can_request_evidence(prompt, semantic_result))
        if (
            candidates
            and search_budget > 0
            and (explicit or important or semantic_wants_evidence)
            and not ambiguous_evidence_request
            and _budget_allows(start, max_elapsed_ms, EVIDENCE_MIN_REMAINING_MS)
        ):
            evidence = collect_evidence(candidates, query_terms, search_budget)
            if evidence:
                decision = "evidence"
        elif (
            candidates
            and search_budget > 0
            and association_matches
            and is_decision_continuation(prompt)
            and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
            and _budget_allows(start, max_elapsed_ms, EVIDENCE_MIN_REMAINING_MS)
        ):
            evidence = collect_evidence(candidates, query_terms, 1)
            if evidence:
                decision = "evidence"
                reasons.append("evidence-lite decision continuation")
        elif (
            candidates
            and search_budget > 0
            and working_memory_matches
            and is_decision_continuation(prompt)
            and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
            and _budget_allows(start, max_elapsed_ms, EVIDENCE_MIN_REMAINING_MS)
        ):
            evidence = collect_evidence(candidates, query_terms, 1)
            if evidence:
                decision = "evidence"
                reasons.append("working-memory evidence-lite decision continuation")

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "decision": decision,
        "score": round(max(top_score, working_score), 3),
        "confidence": "high"
        if decision == "evidence"
        else "medium"
        if decision == "scent"
        else "low",
        **context.hook_path_fields(),
        "query_terms": query_terms[:16],
        "cognitive_map": cognitive_map_matches[:4],
        "concept_expansions": concept_expansions[:8],
        "reasons": reasons or ["no ambient recall cue"],
        "candidates": strip_private_fields(candidates[:3]),
        "evidence": evidence[:search_budget],
        "working_memory": strip_for_hook(working_memory_matches[:3]),
        "semantic_gate": strip_semantic_gate(semantic_result),
        "elapsed_ms": elapsed_ms,
    }
