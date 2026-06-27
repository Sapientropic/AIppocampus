"""Fixed vocabulary route-topic labels for clean-source navigation."""

from __future__ import annotations

# aippocampus-instruction-surface: clean-source route-topic owner; topic labels
# are route-selection hints, not source evidence or permission to claim.
import re
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.source.relationship_origin import RELATIONSHIP_ORIGIN_ROUTE_TOPIC

_ROUTE_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "benchmark_claim_posture",
        (
            "benchmark",
            "quality gate",
            "quality_gate",
            "claim",
            "cannot_claim",
            "current claims",
            "evidence map",
            "readiness",
            "over-conservative",
            "overconservative",
        ),
    ),
    (
        "issue_backlog_interpretation",
        ("issue", "backlog", "project triage", "milestone", "roadmap", "planning"),
    ),
    (
        "developer_assessment",
        ("developer assessment", "evaluation", "review", "critique", "second-user"),
    ),
    (
        "competitor_comparison",
        ("competitor", "comparison", "baseline", "external", "amemgym", "longmemeval", "mem0", "zep"),
    ),
    (
        "route_usefulness_feedback",
        (
            "usefulness",
            "blind deepen",
            "manual search",
            "wrong route",
            "route label",
            "hint collision",
            "wasted motion",
        ),
    ),
    (
        "source_reopen_boundary",
        ("source reopen", "source-backed", "currentness", "conflict", "privacy", "mask"),
    ),
    (
        "agent_native_recall_facade",
        (
            "agent recall",
            "agent-native",
            "agent native",
            "memorypacket",
            "memory packet",
            "opt-in",
            "opt in",
            "deepen",
            "mcp",
            "facade",
        ),
    ),
    (
        "workflow_contract",
        ("aippo", "working contract", "clause", "skill", "ficus"),
    ),
    (
        "coding_route_recovery",
        ("rejected route", "test failed", "failed route", "patch", "pr", "pull request"),
    ),
    (
        RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
        (
            "小海马体",
            "外置海马体",
            "未干的地图",
            "机械飞升",
            "机仆",
            "机械种族",
            "未来机械生命",
            "生命还能变成什么",
        ),
    ),
)
_TOPIC_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _topic_cue_match_count(text: str, cues: tuple[str, ...]) -> int:
    folded_text = text.casefold()
    tokens = _TOPIC_TOKEN_RE.findall(text.casefold())
    token_set = set(tokens)
    normalized_text = " ".join(tokens)
    count = 0
    for cue in cues:
        folded_cue = cue.casefold()
        cue_tokens = _TOPIC_TOKEN_RE.findall(folded_cue)
        if not cue_tokens:
            if folded_cue and folded_cue in folded_text:
                count += 1
            continue
        if len(cue_tokens) == 1:
            if cue_tokens[0] in token_set:
                count += 1
            continue
        if " ".join(cue_tokens) in normalized_text:
            count += 1
    return count


def _topic_matches(text: str) -> list[tuple[int, str]]:
    matched: list[tuple[int, str]] = []
    for topic, cues in _ROUTE_TOPIC_RULES:
        # Topic labels are foreground route-selection hints, so broad substring
        # matches are worse than silence: "pr" inside "PRIVATE" or "review"
        # inside "preview" makes clean routes collide and sends agents to the
        # wrong source. Keep short cues token-bound and let source scope labels
        # carry the route when no safe topic cue is present.
        score = _topic_cue_match_count(text, cues)
        if score:
            matched.append((score, topic))
    matched.sort(key=lambda item: (-item[0], item[1]))
    return matched


def _clean_hit_text(hit: Mapping[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            hit.get("phase"),
            hit.get("role"),
            hit.get("snippet"),
            " ".join(str(label) for label in hit.get("scope_labels") or []),
            " ".join(str(label) for label in hit.get("semantic_scope_labels") or []),
        )
    ).casefold()


def route_topic_for_clean_hit(hit: Mapping[str, Any], *, intent: str) -> dict[str, Any]:
    local_matches = _topic_matches(_clean_hit_text(hit))
    matched = local_matches or _topic_matches(str(intent or "").casefold())
    if matched:
        matched_topics = [topic for _, topic in matched]
        return {
            "route_topic": matched_topics[0],
            "label_granularity": "topic_label",
            "route_label_specificity_score": 1.0 if len(matched_topics) == 1 else 0.85,
            "topic_reason_codes": [f"topic_{topic}" for topic in matched_topics[:3]],
        }
    return {
        "route_topic": "",
        "label_granularity": "scope_bucket_only",
        "route_label_specificity_score": 0.35,
        "topic_reason_codes": ["no_safe_topic_label"],
    }


def route_topic_low_coverage_acceptance(
    hit: Mapping[str, Any],
    *,
    intent: str,
    query_profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a navigation-only acceptance for known topic-bearing partial hits.

    The ordinary phrase gate should still suppress generic long-query fragments.
    A fixed route-topic match is narrower: both the user cue and the local clean
    source must independently match the same known topic. That lets recall pick
    the current clean-source route instead of falling through to unrelated
    semantic seeds, while the profile remains explicit that this is not exact
    phrase evidence.
    """

    if query_profile.get("accepted"):
        return {}
    local_matches = _topic_matches(_clean_hit_text(hit))
    query_matches = _topic_matches(str(intent or "").casefold())
    if not local_matches or not query_matches:
        return {}
    query_topics = {topic for _, topic in query_matches}
    shared = [topic for _, topic in local_matches if topic in query_topics]
    if not shared:
        return {}
    return {
        "accepted": True,
        "acceptance_reason": "shared_route_topic_label_navigation_only",
        "route_topic": shared[0],
        "route_topic_label_navigation_only": True,
        "matched_route_topics": shared[:3],
    }


__all__ = ["route_topic_for_clean_hit", "route_topic_low_coverage_acceptance"]
