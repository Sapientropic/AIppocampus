"""Anchor coverage helpers for APW source-open candidates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aippocampus_runtime.recall.query_policy import (
    normalize_term,
    split_query_terms,
    unique_preserve,
)
from aippocampus_runtime.text import (
    iter_cjk_sequences,
    normalize_cjk_term,
    strip_cjk_deictic_prefix,
)

GENERIC_FLOW_ANCHORS = {
    "agent",
    "apw",
    "benchmark",
    "ci",
    "cli",
    "deepen",
    "dogfood",
    "issue",
    "issues",
    "key",
    "llm",
    "mcp",
    "pr",
    "recall",
    "source",
    "test",
    "tests",
}


def cjk_context_anchor_terms(query: str, *, limit: int = 8) -> list[str]:
    """Keep generic ASCII flow words from standing in for mixed CJK cues."""

    anchors: list[str] = []
    for sequence in iter_cjk_sequences(query, min_len=2, max_len=24):
        value = normalize_cjk_term(sequence)
        if 2 <= len(value) <= 12:
            anchors.append(value)
        stripped = strip_cjk_deictic_prefix(value)
        if stripped != value and 2 <= len(stripped) <= 12:
            anchors.append(stripped)
    return unique_preserve(anchors, limit=limit)


def query_anchor_terms(query: str, *, limit: int = 12) -> list[str]:
    normalized_query = normalize_term(query).casefold()
    split_terms = split_query_terms([query])
    anchors = [
        term
        for term in split_terms
        if term.casefold() != normalized_query or len(split_terms) == 1
    ]
    anchors.extend(cjk_context_anchor_terms(query, limit=limit))
    return unique_preserve(anchors or split_terms, limit=limit)


def matched_terms_from_text(text: str, terms: Sequence[str], *, limit: int = 8) -> list[str]:
    haystack = str(text or "").casefold()
    matched: list[str] = []
    for term in terms:
        clean = normalize_term(str(term or ""))
        if clean and clean.casefold() in haystack:
            matched.append(clean)
    return unique_preserve(matched, limit=limit)


def low_actual_anchor_coverage_reason(
    *,
    matched_terms: Sequence[str],
    anchor_terms: Sequence[str],
) -> str:
    """Require APW candidates to carry the advertised cue anchors."""

    anchors = {str(term).strip().casefold() for term in anchor_terms if str(term).strip()}
    matched = {str(term).strip().casefold() for term in matched_terms if str(term).strip()}
    cjk_context_anchors = {term for term in anchors if not term.isascii() and len(term) >= 2}
    if cjk_context_anchors and not (matched & cjk_context_anchors):
        return "missing_cjk_context_anchor"
    if len(anchors) <= 2:
        return "" if matched & anchors else "low_actual_source_anchor_coverage"
    meaningful_anchors = {
        term
        for term in anchors
        if term not in GENERIC_FLOW_ANCHORS and (not term.isascii() or len(term) >= 6)
    }
    if meaningful_anchors and not (matched & meaningful_anchors):
        return "low_actual_source_anchor_coverage"
    required = min(3, max(2, (len(anchors) + 1) // 2))
    coverage = len(matched & anchors) / max(1, len(anchors))
    if len(matched & anchors) >= required or coverage >= 0.5:
        return ""
    return "low_actual_source_anchor_coverage"


def source_anchor_gate(
    *,
    matched_terms: Sequence[str],
    anchor_terms: Sequence[str],
) -> dict[str, Any]:
    anchors = {str(term).strip().casefold() for term in anchor_terms if str(term).strip()}
    matched = {str(term).strip().casefold() for term in matched_terms if str(term).strip()}
    cjk_context_anchors = {term for term in anchors if not term.isascii() and len(term) >= 2}
    required = min(3, max(1, (len(anchors) + 1) // 2))
    hits = len(matched & anchors)
    missing_cjk_context = bool(cjk_context_anchors and not (matched & cjk_context_anchors))
    passed = hits >= required and not missing_cjk_context
    return {
        "status": "pass" if passed else "blocked",
        "reason": (
            "missing_cjk_context_anchor"
            if missing_cjk_context
            else "apw_source_anchor_coverage"
        ),
        "anchor_count": len(anchors),
        "opened_anchor_hits": hits,
        "required_anchor_hits": required,
        "target_source_matched": passed,
    }


__all__ = [
    "cjk_context_anchor_terms",
    "low_actual_anchor_coverage_reason",
    "matched_terms_from_text",
    "query_anchor_terms",
    "source_anchor_gate",
]
