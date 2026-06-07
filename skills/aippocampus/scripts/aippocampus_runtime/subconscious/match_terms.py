#!/usr/bin/env python3
"""Working-memory trigger matching helpers."""

from __future__ import annotations

from collections.abc import Collection

from aippocampus_runtime.navigation.associations import normalize_term
from aippocampus_runtime.recall.query_policy import split_query_terms


def prompt_parts_for(prompt: str, *, generic_terms: Collection[str]) -> list[str]:
    return [
        part.casefold()
        for part in split_query_terms([prompt])
        if len(part) >= 4 and part.casefold() not in generic_terms
    ]


def broad_match_term(
    term: str,
    project_label: str | None,
    *,
    generic_terms: Collection[str],
) -> bool:
    low = normalize_term(term).casefold()
    if not low or low in generic_terms:
        return True
    return bool(project_label and low == project_label.casefold())


def trigger_matches_prompt(
    term: str,
    *,
    prompt_low: str,
    prompt_parts: list[str],
    generic_terms: Collection[str],
    project_label: str | None,
) -> bool:
    if broad_match_term(term, project_label, generic_terms=generic_terms):
        return False
    low = term.casefold()
    term_parts = [
        part.casefold()
        for part in split_query_terms([term])
        if len(part) >= 4 and part.casefold() not in generic_terms
    ]
    if not low:
        return False
    if " " not in low and "-" not in low:
        return low in prompt_low or any(part and part in low for part in prompt_parts)

    # Multi-word triggers should stay concrete. Mixed-language prompts may
    # separate the phrase while still containing every meaningful component.
    component_parts = [part for part in term_parts if part != low]
    return low in prompt_low or (
        bool(component_parts) and all(part in prompt_low for part in component_parts)
    )
