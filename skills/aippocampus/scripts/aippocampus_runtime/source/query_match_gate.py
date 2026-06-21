"""Phrase-like query coverage gate for source search surfaces."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_QUERY_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{2,}")
_NORMALIZE_ANCHOR_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_LOW_SIGNAL_TERMS = {
    "about",
    "agent",
    "backed",
    "conversation",
    "is",
    "memory",
    "not",
    "recall",
    "safe",
    "search",
    "source",
    "source-backed",
    "sourcebacked",
    "that",
    "the",
    "thread",
}


def normalize_anchor(value: str) -> str:
    return _NORMALIZE_ANCHOR_RE.sub("", str(value or "").casefold())


def query_anchor_terms(query_text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for match in _QUERY_TOKEN_RE.finditer(query_text):
        token = normalize_anchor(match.group(0))
        if not token or token in seen or token in _LOW_SIGNAL_TERMS:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def query_match_gate(query_text: str) -> dict[str, Any]:
    anchors = query_anchor_terms(query_text)
    phrase_like = len(anchors) >= 4 or len(str(query_text or "").strip()) >= 48
    return {
        "phrase_like_query": phrase_like,
        "distinctive_anchors": anchors[:16],
        "distinctive_anchor_count": len(anchors),
        "minimum_anchor_coverage": 0.5 if len(anchors) >= 4 else 1.0,
        "minimum_matched_anchors": 2 if len(anchors) >= 4 else max(1, len(anchors)),
    }


def match_query_profile(
    *,
    query_text: str,
    gate: Mapping[str, Any],
    haystack: str,
) -> dict[str, Any]:
    normalized_haystack = normalize_anchor(haystack)
    normalized_query = normalize_anchor(query_text)
    anchors = [str(anchor) for anchor in gate.get("distinctive_anchors") or []]
    matched = [anchor for anchor in anchors if anchor in normalized_haystack]
    anchor_count = len(anchors)
    coverage = round(len(matched) / anchor_count, 3) if anchor_count else 0.0
    exact_phrase_match = bool(
        normalized_query and len(normalized_query) >= 16 and normalized_query in normalized_haystack
    )
    accepted = True
    suppression_reason = ""
    if gate.get("phrase_like_query") and not exact_phrase_match:
        min_matched = int(gate.get("minimum_matched_anchors") or 0)
        min_coverage = float(gate.get("minimum_anchor_coverage") or 0)
        if len(matched) < min_matched or coverage < min_coverage:
            accepted = False
            suppression_reason = "distinctive_anchor_coverage_too_low_for_phrase_like_query"
    return {
        "phrase_like_query": bool(gate.get("phrase_like_query")),
        "exact_phrase_match": exact_phrase_match,
        "distinctive_anchor_count": anchor_count,
        "matched_distinctive_anchor_count": len(matched),
        "distinctive_anchor_coverage": coverage,
        "matched_distinctive_anchors": matched[:8],
        "accepted": accepted,
        "suppression_reason": suppression_reason,
    }
