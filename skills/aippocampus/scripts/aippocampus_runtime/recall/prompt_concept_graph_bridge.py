"""Concept-graph fallback bridge for prompt recall.

The prompt hook can use graph expansion only after direct source candidates
miss. Keeping this bridge separate from the foreground decision owner makes the
"prove useful or abstain" rule easier to test without growing the hot path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation.association_terms import (
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.navigation.concept_graph import expand_concepts
from aippocampus_runtime.recall.prompt_cues import (
    CONCEPT_EXPANSION_MAX_TERMS,
    concept_expansion_terms,
)
from aippocampus_runtime.recall.query_policy import GENERIC_ANCHOR_TERMS, query_term_is_noise
from aippocampus_runtime.recall.semantic_recall_gate import is_generic_trigger_prompt_term
from aippocampus_runtime.registry.api import unique_preserve

GENERIC_CONCEPT_BRIDGE_TERMS = {
    "api",
    "audit",
    "benchmark",
    "benchmarks",
    "cache",
    "cli",
    "hook",
    "hooks",
    "index",
    "integration",
    "json",
    "jsonl",
    "llm",
    "mcp",
    "pipeline",
    "runtime",
    "smoke",
    "test",
    "tests",
    "tool",
    "tools",
    "validation",
    "worker",
    "workers",
    "工作流",
    "测试",
    "索引",
    "缓存",
}


def concept_graph_skip_diagnostic(
    *,
    candidates: list[dict[str, Any]],
    use_concept_graph: bool,
    prompt: str,
    concept_file: Path,
) -> dict[str, Any]:
    if candidates:
        reason = "direct_candidates_present"
    elif not use_concept_graph:
        reason = "concept_graph_disabled"
    elif not prompt:
        reason = "empty_prompt"
    elif not concept_file.exists():
        reason = "concept_graph_missing"
    else:
        reason = "budget_guard"
    return {"state": "not_attempted", "reason": reason}


def _useful_expansion_terms(concept_expansions: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for item in concept_expansions:
        term = normalize_term(str(item.get("term") or ""))
        if not term:
            continue
        low = term.casefold()
        # Concept expansion is a foreground navigation fallback, not evidence.
        # Keep exact broad infrastructure words out unless they are part of a
        # more specific phrase such as "Go runtime"; otherwise graph drift turns
        # project vocabulary into a false recall lift.
        if (
            low in GENERIC_CONCEPT_BRIDGE_TERMS
            or low in GENERIC_ANCHOR_TERMS
            or is_generic_trigger_prompt_term(term)
            or query_term_is_noise(term)
            or term_is_noise(term)
            or source_text_is_noise(term)
        ):
            continue
        terms.append(term)
    return unique_preserve(terms, limit=CONCEPT_EXPANSION_MAX_TERMS)


def _candidate_has_reopenable_source(candidate: dict[str, Any]) -> bool:
    entry = candidate.get("_entry") if isinstance(candidate.get("_entry"), dict) else {}
    paths = entry.get("paths") if isinstance(entry, dict) else None
    if isinstance(paths, dict) and any(
        paths.get(key)
        for key in (
            "clean_source_messages_jsonl",
            "sqlite",
            "anchors",
            "rollout",
            "workspace",
        )
    ):
        return True
    return bool(candidate.get("source_refs") or candidate.get("source_ref"))


def _candidate_supported_by_expansion(
    candidate: dict[str, Any], useful_terms: list[str]
) -> bool:
    if not _candidate_has_reopenable_source(candidate):
        return False
    useful = {term.casefold() for term in useful_terms}
    matched = {
        normalize_term(str(term)).casefold()
        for term in candidate.get("matched_terms") or []
        if normalize_term(str(term))
    }
    if matched & useful:
        return True
    blob_parts = [
        str(candidate.get("title") or ""),
        str(candidate.get("summary") or ""),
        " ".join(str(value) for value in candidate.get("keywords") or []),
        " ".join(str(value) for value in candidate.get("anchors") or []),
    ]
    entry = candidate.get("_entry") if isinstance(candidate.get("_entry"), dict) else {}
    if isinstance(entry, dict):
        blob_parts.extend(
            [
                str(entry.get("title") or ""),
                str(entry.get("summary") or ""),
                " ".join(str(value) for value in entry.get("keywords") or []),
                " ".join(str(value) for value in entry.get("anchor_titles") or []),
            ]
        )
    blob = "\n".join(blob_parts).casefold()
    return any(term.casefold() in blob for term in useful_terms)


def apply_concept_graph_bridge(
    *,
    concept_file: Path,
    seed_terms: list[str],
    score_candidates: Callable[[list[str]], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], dict[str, Any]]:
    concept_expansions = expand_concepts(
        concept_file, seed_terms, depth=2, max_terms=CONCEPT_EXPANSION_MAX_TERMS
    )
    if not concept_expansions:
        return (
            [],
            seed_terms,
            concept_expansions,
            {"state": "no_useful_expansion", "reason": "graph_returned_no_expansions"},
        )
    raw_expanded_terms = concept_expansion_terms(concept_expansions)
    expanded_terms = _useful_expansion_terms(concept_expansions)
    if not expanded_terms:
        return (
            [],
            seed_terms,
            [],
            {
                "state": "rejected_noisy_expansion",
                "reason": "no_foreground_safe_expansion_terms",
                "raw_expansion_count": len(concept_expansions),
                "rejected_broad_expansion_count": len(raw_expanded_terms),
            },
        )
    expanded_query_terms = unique_preserve(seed_terms + expanded_terms, limit=40)
    raw_expanded_candidates = score_candidates(expanded_query_terms)
    expanded_candidates = [
        candidate
        for candidate in raw_expanded_candidates
        if _candidate_supported_by_expansion(candidate, expanded_terms)
    ]
    if not expanded_candidates:
        return (
            [],
            seed_terms,
            [],
            {
                "state": "no_useful_expansion",
                "reason": "expansion_failed_source_followthrough_gate"
                if raw_expanded_candidates
                else "expansion_produced_no_registry_candidates",
                "raw_expansion_count": len(concept_expansions),
                "accepted_expansion_count": len(expanded_terms),
                "raw_candidate_count": len(raw_expanded_candidates),
            },
        )
    return (
        expanded_candidates,
        expanded_query_terms,
        [
            item
            for item in concept_expansions
            if normalize_term(str(item.get("term") or "")).casefold()
            in {term.casefold() for term in expanded_terms}
        ],
        {
            "state": "used",
            "reason": "expansion_produced_registry_candidates",
            "expansion_count": len(concept_expansions),
            "accepted_expansion_count": len(expanded_terms),
            "candidate_count": len(expanded_candidates),
            "rejected_candidate_count": len(raw_expanded_candidates) - len(expanded_candidates),
        },
    )


__all__ = ["apply_concept_graph_bridge", "concept_graph_skip_diagnostic"]
