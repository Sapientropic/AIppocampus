#!/usr/bin/env python3
"""Cheap query profile diagnostics for foreground recall composition."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.recall.prompt_cues import (
    EXACT_WORDING_TOPIC_TERMS,
    RECENCY_CUES,
    SOURCE_EVIDENCE_REQUEST_TERMS,
    matched_terms,
    prompt_is_code_surface,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.recall.semantic_recall_gate import is_generic_trigger_prompt_term

AFFECTION_RE = re.compile(
    r"(烦|困扰|卡住|喜欢|在意|难过|焦虑|轻松|relief|frustrat|annoy|stuck|care about)",
    re.IGNORECASE,
)
FRONTIER_RE = re.compile(r"(下一步|没走完|unfinished|frontier|next step|继续那条路)", re.IGNORECASE)


def classify_query_profile(prompt: str) -> dict[str, Any]:
    """Classify prompt shape without calling a model or reading source text."""

    text = str(prompt or "")
    terms = split_query_terms([text])
    generic_count = sum(1 for term in terms if is_generic_trigger_prompt_term(term))
    specific_terms = [term for term in terms if _specific_profile_term(term)]
    reasons: list[str] = []
    if matched_terms(text, SOURCE_EVIDENCE_REQUEST_TERMS | EXACT_WORDING_TOPIC_TERMS):
        reasons.append("exact_wording_request")
        return _profile(
            "exact_phrase",
            "source_text",
            reasons,
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    if prompt_is_code_surface(text):
        reasons.append("code_surface_terms")
        return _profile(
            "coding_current_repo",
            "source_current_repo",
            reasons,
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    if matched_terms(text, RECENCY_CUES):
        reasons.append("temporal_revisit_terms")
    if AFFECTION_RE.search(text):
        reasons.append("affective_continuity_terms")
        return _profile(
            "affective_life_context",
            "ambient_life_context",
            reasons,
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    if FRONTIER_RE.search(text):
        reasons.append("frontier_terms")
        return _profile(
            "journey_frontier",
            "journey_navigation",
            reasons,
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    if _generic_recall_meta_prompt(text, generic_count=generic_count, specific_terms=specific_terms):
        reasons.append("generic_recall_meta_terms")
        return _profile(
            "generic_recall_meta",
            "recall_composer",
            reasons,
            composer="suppress_generic_scent",
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    if "temporal_revisit_terms" in reasons:
        return _profile(
            "temporal_revisit",
            "temporal_source_spread",
            reasons,
            generic_count=generic_count,
            specific_terms=specific_terms,
        )
    return _profile(
        "normal_recall",
        "source_text",
        reasons or ["default_source_text"],
        generic_count=generic_count,
        specific_terms=specific_terms,
    )


def _profile(
    profile: str,
    lane: str,
    reason_codes: list[str],
    *,
    composer: str = "default",
    generic_count: int,
    specific_terms: list[str],
) -> dict[str, Any]:
    return {
        "profile": profile,
        "lane": lane,
        "composer": composer,
        "reason_codes": reason_codes,
        "generic_prompt_term_count": generic_count,
        "specific_prompt_term_count": len(specific_terms),
    }


def _specific_profile_term(term: str) -> bool:
    text = str(term or "").strip()
    if not text:
        return False
    if is_generic_trigger_prompt_term(text):
        return False
    if re.fullmatch(r"#\d+", text):
        return True
    if re.search(r"[\u4e00-\u9fff]", text):
        return len(text) >= 3
    return len(text) >= 6


def _generic_recall_meta_prompt(
    prompt: str,
    *,
    generic_count: int,
    specific_terms: list[str],
) -> bool:
    # Keep this profile narrow: generic recall/meta terms can foreground
    # unrelated alias scent, but concrete source requests must stay on normal
    # source lanes instead of being globally muted.
    text = prompt.casefold()
    has_source_ref = any(term in text for term in ("source", "ref", "refs", "source ref"))
    has_issue_or_candidate = any(
        term in text for term in ("issue", "issues", "候选", "问题")
    )
    return bool(generic_count >= 3 and has_source_ref and has_issue_or_candidate and len(specific_terms) <= 4)
