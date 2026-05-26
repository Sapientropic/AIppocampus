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

from aippocampus_prompt_hook import (
    ASSOCIATIVE_CUES,
    CONCEPT_EXPANSION_MAX_TERMS,
    CONCEPT_TRIGGERS,
    DEFAULT_SEARCH_BUDGET,
    EVIDENCE_LITE_MIN_PROBE_SCORE,
    IMPORTANCE_CUES,
    PROMPT_HOOK_SEMANTIC_TIMEOUT,
    SCENT_THRESHOLD,
    association_term_is_generic,
    cognitive_map_terms,
    collect_evidence,
    concept_expansion_terms,
    current_project_label,
    default_associations_path,
    default_cognitive_map_path,
    default_concept_graph_path,
    default_project_timeline_path,
    default_semantic_triggers_path,
    default_working_memory_path,
    expand_concepts,
    expand_query_terms,
    explicit_recall_terms,
    fallback_search_candidates,
    is_decision_continuation,
    load_associations,
    load_cognitive_map,
    load_project_timeline,
    load_registry,
    load_working_memory,
    match_associations,
    match_cognitive_map,
    match_working_memory,
    matched_terms,
    merge_association_candidates,
    merge_cognitive_map_candidates,
    merge_timeline_candidates,
    registry_json_path,
    rerank_candidates_with_probe,
    run_semantic_gate,
    score_candidates,
    semantic_gate_can_request_evidence,
    semantic_gate_is_memory_cue,
    semantic_gate_terms,
    should_run_semantic_gate,
    should_suppress,
    source_text_is_noise,
    strip_for_hook,
    strip_private_fields,
    strip_semantic_gate,
    unique_preserve,
    working_memory_terms,
)


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
    semantic_timeout: int = PROMPT_HOOK_SEMANTIC_TIMEOUT,
    use_semantic_gate: bool = True,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None = None,
    use_cognitive_map: bool = True,
    use_concept_graph: bool = True,
    search_budget: int = DEFAULT_SEARCH_BUDGET,
) -> dict[str, Any]:
    start = time.perf_counter()
    cwd_path = Path(cwd).resolve()
    prompt = str(prompt or "").strip()
    path = registry_json_path(
        Path(registry_path).resolve() if registry_path else None,
        Path(registry_dir).resolve() if registry_dir else None,
    )
    association_file = (
        Path(associations_path).resolve()
        if associations_path
        else default_associations_path(registry_path=path)
    )
    concept_file = (
        Path(concept_graph_path).resolve()
        if concept_graph_path
        else default_concept_graph_path(registry_path=path)
    )
    cognitive_map_file = (
        Path(cognitive_map_path).resolve()
        if cognitive_map_path
        else default_cognitive_map_path(registry_path=path)
    )
    working_memory_file = (
        Path(working_memory_path).resolve()
        if working_memory_path
        else default_working_memory_path(registry_path=path)
    )
    semantic_triggers_file = (
        Path(semantic_triggers_path).resolve()
        if semantic_triggers_path
        else default_semantic_triggers_path(registry_path=path)
    )
    if source_text_is_noise(prompt):
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "cwd": str(cwd_path),
            "registry": str(path),
            "associations": str(association_file),
            "cognitive_map_path": str(cognitive_map_file),
            "concept_graph": str(concept_file),
            "working_memory_path": str(working_memory_file),
            "semantic_triggers_path": str(semantic_triggers_file),
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
    registry = load_registry(path)
    project_label = current_project_label(registry, cwd_path)
    cognitive_map = load_cognitive_map(cognitive_map_file) if use_cognitive_map and cognitive_map_file.exists() else {}
    cognitive_map_matches = (
        match_cognitive_map(prompt, cognitive_map, project_label=project_label)
        if prompt and cognitive_map
        else []
    )
    working_memory_rows = load_working_memory(working_memory_file) if working_memory_file.exists() else []
    working_memory_matches = (
        match_working_memory(
            prompt,
            working_memory_rows,
            project_label=project_label,
        )
        if prompt and working_memory_rows
        else []
    )
    associations = load_associations(association_file)
    association_matches = [
        match
        for match in (match_associations(prompt, associations) if prompt else [])
        if not association_term_is_generic(match)
    ]
    pre_explicit = explicit_recall_terms(prompt)
    pre_associative = matched_terms(prompt, set(CONCEPT_TRIGGERS) | ASSOCIATIVE_CUES)
    pre_important = matched_terms(prompt, IMPORTANCE_CUES)
    semantic_result: dict[str, Any] | None = None
    if use_semantic_gate and prompt and should_run_semantic_gate(
        prompt,
        explicit=pre_explicit,
        associative=pre_associative,
        important=pre_important,
        association_matches=association_matches,
        working_memory_matches=working_memory_matches,
        cognitive_map_matches=cognitive_map_matches,
    ):
        gate = semantic_gate_fn or run_semantic_gate
        try:
            semantic_result = gate(
                prompt,
                cwd=cwd_path,
                registry=registry,
                registry_path=path,
                associations=associations,
                working_memory=working_memory_rows,
                semantic_triggers_path=semantic_triggers_file,
                cache_path=Path(semantic_cache_path).resolve() if semantic_cache_path else None,
                mode=semantic_gate_mode,
                timeout=semantic_timeout,
            )
        except Exception as exc:
            semantic_result = {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "reasons": [f"semantic gate error: {exc}"],
                "errors": [str(exc)],
            }
    association_terms: list[str] = []
    for match in association_matches:
        association_terms.append(str(match.get("term") or ""))
        association_terms.extend(str(value) for value in match.get("matched_terms") or [])
        if match.get("status") == "verified":
            association_terms.extend(str(value) for value in match.get("related_terms") or [])

    seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + cognitive_map_terms(cognitive_map_matches)
        + association_terms
        + working_memory_terms(working_memory_matches)
        + semantic_gate_terms(semantic_result),
        limit=36,
    )
    concept_expansions: list[dict[str, Any]] = []
    query_terms = seed_terms
    explicit = pre_explicit
    associative = pre_associative
    important = pre_important

    candidates = score_candidates(prompt, registry, query_terms) if prompt else []
    candidates = merge_cognitive_map_candidates(candidates, registry, cognitive_map_matches, query_terms)
    candidates = merge_association_candidates(candidates, registry, association_matches, query_terms)
    timeline = load_project_timeline(default_project_timeline_path(path))
    candidates = merge_timeline_candidates(candidates, registry, timeline, prompt, cwd_path, query_terms)
    if not candidates and use_concept_graph and prompt and concept_file.exists():
        # Concept BFS is a recall bridge for prompts whose surface words miss
        # registry associations. Once direct association/timeline candidates
        # already exist, expanding concepts can easily introduce semantic drift
        # and corrupt clean-source probe ranking, so keep it as a fallback.
        concept_expansions = expand_concepts(concept_file, seed_terms, depth=2, max_terms=CONCEPT_EXPANSION_MAX_TERMS)
        if concept_expansions:
            query_terms = unique_preserve(seed_terms + concept_expansion_terms(concept_expansions), limit=40)
            candidates = score_candidates(prompt, registry, query_terms) if prompt else []
            candidates = merge_cognitive_map_candidates(candidates, registry, cognitive_map_matches, query_terms)
            candidates = merge_association_candidates(candidates, registry, association_matches, query_terms)
            candidates = merge_timeline_candidates(candidates, registry, timeline, prompt, cwd_path, query_terms)
    if not candidates and (explicit or associative):
        # Metadata can miss memorable wording that only exists inside the
        # SQLite message index. When the user explicitly asks to recover prior
        # speech, try a tiny recent-thread fallback before staying silent.
        candidates = fallback_search_candidates(registry, query_terms)
    semantic_memory_cue = semantic_gate_is_memory_cue(semantic_result)
    has_memory_cue = bool(
        explicit
        or associative
        or important
        or association_matches
        or cognitive_map_matches
        or concept_expansions
        or working_memory_matches
        or semantic_memory_cue
    )
    if candidates and has_memory_cue:
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
    working_score = max([float(item.get("score") or 0.0) for item in working_memory_matches] or [0.0])
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
        reasons.append("registry overlap: " + ", ".join(str(item["title"]) for item in candidates[:2]))
    if any(item.get("probe_score") for item in candidates[:3]):
        reasons.append("clean-source probe rerank")
    if any(item.get("timeline_source") for item in candidates[:3]):
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

    evidence: list[dict[str, Any]] = []
    decision = "skip"
    if not suppressed and has_memory_cue and (candidates or working_memory_matches) and (
        top_score >= SCENT_THRESHOLD or working_score >= SCENT_THRESHOLD or explicit or associative
        or cognitive_map_matches
        or semantic_memory_cue
    ):
        decision = "scent"
        semantic_wants_evidence = bool(
            semantic_gate_can_request_evidence(prompt, semantic_result)
        )
        if candidates and search_budget > 0 and (explicit or important or semantic_wants_evidence):
            evidence = collect_evidence(candidates, query_terms, search_budget)
            if evidence:
                decision = "evidence"
        elif (
            candidates
            and search_budget > 0
            and association_matches
            and is_decision_continuation(prompt)
            and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
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
        ):
            evidence = collect_evidence(candidates, query_terms, 1)
            if evidence:
                decision = "evidence"
                reasons.append("working-memory evidence-lite decision continuation")

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "decision": decision,
        "score": round(max(top_score, working_score), 3),
        "confidence": "high" if decision == "evidence" else "medium" if decision == "scent" else "low",
        "cwd": str(cwd_path),
        "registry": str(path),
        "associations": str(association_file),
        "cognitive_map_path": str(cognitive_map_file),
        "concept_graph": str(concept_file),
        "working_memory_path": str(working_memory_file),
        "semantic_triggers_path": str(semantic_triggers_file),
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
