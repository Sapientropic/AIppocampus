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
    if not match_has_direct_source_open_route(match):
        return False
    profile_value = match.get("query_match_profile")
    profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
    if profile and not profile.get("accepted"):
        return False
    if profile.get("exact_identifier_query") and not profile.get("identifier_match"):
        return False
    anchor_count = _as_int(profile.get("distinctive_anchor_count"))
    if anchor_count == 0:
        return True
    if profile.get("exact_phrase_match"):
        return True
    if profile.get("relationship_origin_override"):
        return True
    matched_count = _as_int(profile.get("matched_distinctive_anchor_count"))
    min_matched = _as_int(profile.get("minimum_matched_anchors"), 1)
    coverage = _as_float(profile.get("distinctive_anchor_coverage"))
    min_coverage = _as_float(profile.get("minimum_anchor_coverage"))
    return matched_count >= min_matched and coverage >= min_coverage


def match_has_direct_source_open_route(match: Mapping[str, Any]) -> bool:
    """Return whether a search hit can safely drive the default source-open action.

    SQLite index hits are useful navigation evidence, but older index rows often
    carry only index/raw line numbers. Those numbers are not a stable clean-source
    reopen key, and letting them reach the foreground `open-source` action caused
    partial exact-search hits to fail at follow-through. Direct source-open needs
    a clean-source identity; line-only SQLite hits stay diagnostic until a clean
    source match or a refined search supplies one.
    """

    route_value = match.get("source_route")
    route: Mapping[str, Any] = route_value if isinstance(route_value, Mapping) else {}
    if route.get("kind") == "repo_checkout_doc_hit":
        return bool(match.get("source_window_command") or match.get("reopen_command"))
    if not str(route.get("thread_key") or "").strip():
        return False
    if str(match.get("source") or "") == "sqlite" and not route.get("message_id"):
        return False
    return bool(route.get("message_id") or route.get("line"))


def duplicate_ref_has_direct_source_open_route(
    match: Mapping[str, Any],
    ref: Mapping[str, Any],
    route_ref: Mapping[str, Any],
) -> bool:
    return match_has_direct_source_open_route(
        {
            "source": match.get("source"),
            "message_id": ref.get("message_id"),
            "source_route": route_ref,
        }
    )


def suppressed_match_state(
    *,
    phrase_like_query: bool,
    visible_match_count: int,
    suppressed_match_count: int,
) -> tuple[bool, bool]:
    """Classify suppressed-only searches before the renderer chooses actions."""

    no_phrase_like_matches = (
        phrase_like_query and visible_match_count == 0 and suppressed_match_count > 0
    )
    low_coverage_only_matches = (
        not no_phrase_like_matches
        and visible_match_count == 0
        and suppressed_match_count > 0
    )
    return no_phrase_like_matches, low_coverage_only_matches


def first_match_usefulness_status(
    first_match: Mapping[str, Any] | None,
    *,
    first_match_profile: Mapping[str, Any],
    first_match_useful: bool,
    low_coverage_only_matches: bool = False,
) -> str:
    if first_match is None:
        return "low_coverage_matches_only" if low_coverage_only_matches else "no_matches"
    if match_is_demoted_artifact(first_match):
        return "demoted_artifact"
    if (
        first_match_profile.get("exact_identifier_query")
        and not first_match_profile.get("identifier_match")
    ):
        return "identifier_not_found"
    if not match_has_direct_source_open_route(first_match):
        return "source_route_not_reopenable"
    if not first_match_useful:
        return "query_anchor_missing"
    return "topic_bearing_candidate"


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
    "duplicate_ref_has_direct_source_open_route",
    "first_match_usefulness_status",
    "match_has_direct_source_open_route",
    "match_evidence_diagnostics",
    "match_is_useful_registry_target",
    "query_anchor_rank",
    "suppressed_match_state",
]
