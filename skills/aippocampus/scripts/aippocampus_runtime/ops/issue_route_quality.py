#!/usr/bin/env python3
"""Public-safe route-quality checks for recent GitHub issue/comment continuity."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_TOPIC = "graded trust semantics for ambient source-backed packets"
DEFAULT_TOPIC_TERMS = (
    "graded trust",
    "bounded evidence",
    "source-backed packet",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "")


def _contains_all(haystack: str, needles: Sequence[str]) -> bool:
    clean = haystack.casefold()
    return all(needle.casefold() in clean for needle in needles)


def _comment_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _as_list(payload.get("comments")) if isinstance(item, dict)]


def _parent_issue_present(text: str, parent_issue_number: int) -> bool:
    patterns = (
        rf"#{parent_issue_number}\b",
        rf"\bissue\s+{parent_issue_number}\b",
        rf"\bparent\s+{parent_issue_number}\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _first_comment_url(comments: Sequence[Mapping[str, Any]], parent_issue_number: int) -> str:
    for comment in comments:
        body = _text(comment.get("body"))
        if _parent_issue_present(body, parent_issue_number):
            return _text(comment.get("url"))
    for comment in comments:
        url = _text(comment.get("url"))
        if url:
            return url
    return ""


def evaluate_same_thread_issue_comment_route_quality(
    payload: Mapping[str, Any],
    *,
    expected_issue_number: int = 786,
    expected_parent_issue_number: int = 791,
    topic: str = DEFAULT_TOPIC,
    topic_terms: Sequence[str] = DEFAULT_TOPIC_TERMS,
    mode: str = "public_fixture",
) -> dict[str, Any]:
    """Return a redacted route-quality readout over public issue metadata.

    The smoke is about route precision, not evidence authority: issue/comment
    metadata may give the agent a source-reopenable current-thread route, but
    it still must not become a factual memory claim without source reopen.
    """

    comments = _comment_items(payload)
    issue_number = int(payload.get("number") or 0)
    issue_url = _text(payload.get("url"))
    comment_url = _first_comment_url(comments, expected_parent_issue_number)
    public_text = "\n".join(
        [
            _text(payload.get("title")),
            _text(payload.get("body")),
            *[_text(comment.get("body")) for comment in comments],
        ]
    )
    topic_present = _contains_all(public_text, topic_terms)
    parent_present = _parent_issue_present(public_text, expected_parent_issue_number)
    issue_number_present = issue_number == expected_issue_number
    comment_context_present = bool(comments and comment_url)
    source_refs_available = bool(issue_url and comment_url)
    precise_route = bool(
        issue_number_present
        and topic_present
        and parent_present
        and comment_context_present
        and source_refs_available
    )
    return {
        "measured": True,
        "mode": mode,
        "agent_behavior": (
            "uses_precise_current_thread_route" if precise_route else "broad_scent_only"
        ),
        "route": {
            "issue_number": issue_number,
            "parent_issue_number": expected_parent_issue_number if parent_present else None,
            "topic": topic,
            "action_grammar": "reopenable_route" if precise_route else "direction_only",
            "manual_query_invention_count": 0 if precise_route else 1,
            "source_refs_available": source_refs_available,
            "source_ref_kinds": ["issue_url", "comment_url"] if source_refs_available else [],
        },
        "precision": {
            "issue_number_and_topic_present": issue_number_present and topic_present,
            "parent_relation_present": parent_present,
            "comment_context_present": comment_context_present,
            "broad_topic_scent_only_fails": bool(topic_present and precise_route),
        },
        "source_boundary": {
            "support_level": "source_required",
            "promoted_to_evidence": False,
            "source_reopen_required": True,
            "public_github_metadata_only": True,
        },
        "privacy": {
            "raw_issue_body_serialized": False,
            "raw_comment_body_serialized": False,
            "local_paths_serialized": False,
            "tokens_serialized": False,
        },
        "boundary": {
            "route_quality_only": True,
            "not_live_semantic_quality": True,
            "does_not_close_parent_issue": True,
        },
    }


def same_thread_issue_comment_readout(
    route_quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    quality = _as_dict(route_quality)
    route = _as_dict(quality.get("route"))
    precision = _as_dict(quality.get("precision"))
    measured = bool(quality.get("measured"))
    precise_route = bool(
        measured
        and quality.get("agent_behavior") == "uses_precise_current_thread_route"
        and route.get("action_grammar") == "reopenable_route"
        and precision.get("issue_number_and_topic_present")
        and precision.get("parent_relation_present")
        and precision.get("comment_context_present")
        and int(route.get("manual_query_invention_count") or 0) == 0
    )
    return {
        "same_thread_issue_comment_route_quality_measured": measured,
        "same_thread_issue_comment_route_quality": (
            "public_fixture_precise_route" if precise_route else "not_measured"
        ),
        "same_thread_issue_comment_manual_query_count": (
            int(route.get("manual_query_invention_count") or 0) if measured else None
        ),
    }


def fixture_same_thread_issue_comment_route_quality() -> dict[str, Any]:
    payload = {
        "number": 786,
        "title": "Define graded trust semantics for ambient source-backed packets",
        "body": (
            "AIppocampus should distinguish graded trust, bounded evidence, "
            "and source-backed packet routing without flattening everything to scent."
        ),
        "url": "https://github.com/Sapientropic/AIppocampus/issues/786",
        "comments": [
            {
                "url": (
                    "https://github.com/Sapientropic/AIppocampus/issues/786"
                    "#issuecomment-public-route-quality"
                ),
                "body": (
                    "Parent umbrella for the broader presence-first audit: #791. "
                    "Keep this issue focused on graded trust/action grammar."
                ),
            }
        ],
    }
    return evaluate_same_thread_issue_comment_route_quality(payload)
