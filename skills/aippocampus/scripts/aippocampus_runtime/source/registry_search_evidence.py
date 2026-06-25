"""Private evidence counters for registry source-search ranking."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.source.artifact_role import match_is_demoted_artifact
from aippocampus_runtime.source.query_match_gate import normalize_anchor


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def query_anchor_rank(match: Mapping[str, Any]) -> tuple[int, int, float]:
    profile_value = match.get("query_match_profile")
    profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
    return (
        1 if profile.get("exact_phrase_match") else 0,
        _as_int(profile.get("matched_distinctive_anchor_count")),
        _as_float(profile.get("distinctive_anchor_coverage")),
    )


def match_is_useful_registry_target(match: Mapping[str, Any]) -> bool:
    if match_is_demoted_artifact(match):
        return False
    profile_value = match.get("query_match_profile")
    profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
    if profile.get("exact_identifier_query") and not profile.get("identifier_match"):
        return False
    anchor_count = _as_int(profile.get("distinctive_anchor_count"))
    if anchor_count == 0:
        return True
    if profile.get("exact_phrase_match"):
        return True
    if profile.get("relationship_origin_override"):
        return True
    return _as_int(profile.get("matched_distinctive_anchor_count")) > 0


def match_evidence_diagnostics(
    matches: list[dict[str, Any]],
    *,
    query_text: str,
    suppressed_count: int,
) -> dict[str, int]:
    normalized_query = normalize_anchor(query_text)
    diagnostics = {
        "ranking_context_match_count": 0,
        "exact_phrase_match_count": 0,
        "exact_phrase_visible_in_public_snippet_count": 0,
        "exact_phrase_preserved_by_internal_context_count": 0,
        "suppressed_low_coverage_match_count": suppressed_count,
    }
    for match in matches:
        ranking_haystack = str(match.get("_ranking_haystack") or "")
        public_snippet = str(match.get("snippet") or "")
        if ranking_haystack:
            diagnostics["ranking_context_match_count"] += 1
        profile_value = match.get("query_match_profile")
        profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
        if not profile.get("exact_phrase_match"):
            continue
        diagnostics["exact_phrase_match_count"] += 1
        public_has_exact = bool(
            normalized_query
            and len(normalized_query) >= 16
            and normalized_query in normalize_anchor(public_snippet)
        )
        if public_has_exact:
            diagnostics["exact_phrase_visible_in_public_snippet_count"] += 1
        elif ranking_haystack:
            diagnostics["exact_phrase_preserved_by_internal_context_count"] += 1
    return diagnostics


__all__ = [
    "match_evidence_diagnostics",
    "match_is_useful_registry_target",
    "query_anchor_rank",
]
