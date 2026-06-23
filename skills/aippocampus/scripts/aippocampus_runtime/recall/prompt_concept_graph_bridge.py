"""Concept-graph fallback bridge for prompt recall.

The prompt hook can use graph expansion only after direct source candidates
miss. Keeping this bridge separate from the foreground decision owner makes the
"prove useful or abstain" rule easier to test without growing the hot path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation.concept_graph import expand_concepts
from aippocampus_runtime.recall.prompt_cues import (
    CONCEPT_EXPANSION_MAX_TERMS,
    concept_expansion_terms,
)
from aippocampus_runtime.registry.api import unique_preserve


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
    expanded_terms = concept_expansion_terms(concept_expansions)
    if not expanded_terms:
        return (
            [],
            seed_terms,
            [],
            {
                "state": "rejected_noisy_expansion",
                "reason": "no_foreground_safe_expansion_terms",
                "raw_expansion_count": len(concept_expansions),
            },
        )
    expanded_query_terms = unique_preserve(seed_terms + expanded_terms, limit=40)
    expanded_candidates = score_candidates(expanded_query_terms)
    if not expanded_candidates:
        return (
            [],
            seed_terms,
            [],
            {
                "state": "no_useful_expansion",
                "reason": "expansion_produced_no_registry_candidates",
                "raw_expansion_count": len(concept_expansions),
            },
        )
    return (
        expanded_candidates,
        expanded_query_terms,
        concept_expansions,
        {
            "state": "used",
            "reason": "expansion_produced_registry_candidates",
            "expansion_count": len(concept_expansions),
            "candidate_count": len(expanded_candidates),
        },
    )


__all__ = ["apply_concept_graph_bridge", "concept_graph_skip_diagnostic"]
