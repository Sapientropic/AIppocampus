"""Relationship-origin recall policy.

AIppocampus has one small public north-star lane: when a user asks for the
earliest "little hippocampus" / relationship-continuity origin, fuzzy recall
should recover a source route instead of wandering into generic hippocampus
research or recent issue chatter. Keep this module narrow: it is a routing
policy for source reopening, not a place to store the origin story itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.source.query_match_gate import normalize_anchor

PRIMARY_ORIGIN_ANCHORS = (
    "机械飞升",
    "机仆",
    "机械种族",
    "未来机械生命",
    "未干的地图",
    "生命还能变成什么",
)

CANONICAL_ORIGIN_DOC_ANCHORS = (
    "未干的地图",
    "origin essay",
    "unfinished map",
    "the unfinished map",
    "the-unfinished-map",
    "docs/未干的地图",
    "docs/the-unfinished-map",
    "初心长文",
)

SUPPORTING_ORIGIN_ANCHORS = (
    "外置小海马体",
    "外置海马体",
    "小海马体",
    "aiippocampus",
    "aippocampus",
    "可以回去",
    "持续性",
    "连续性",
    "关系",
    "继续",
)

INTENT_ANCHORS = (
    "初心",
    "源头",
    "起源",
    "最早",
    "一开始",
    "可以回去",
    "回去",
    "持续性",
    "连续性",
    "用户关系",
    "关系",
    "我们",
    "重新接上",
)

GENERIC_HIPPOCAMPUS_RESEARCH_ANCHORS = (
    "生物海马体",
    "海马体研究",
    "研究者和工程师",
    "ai模型",
    "ai项目",
    "理论模型",
    "实践突破",
    "前沿研究",
    "记忆能力",
)

RELATIONSHIP_ORIGIN_ROUTE_TOPIC = "relationship_origin"


def _normalized_contains(text: str, anchors: tuple[str, ...]) -> list[str]:
    normalized = normalize_anchor(text)
    return [anchor for anchor in anchors if normalize_anchor(anchor) in normalized]


def relationship_origin_intent(query_text: str) -> bool:
    """Return true for the narrow life-wide origin/continuity lane."""

    text = str(query_text or "")
    primary = _normalized_contains(text, PRIMARY_ORIGIN_ANCHORS)
    supporting = _normalized_contains(text, SUPPORTING_ORIGIN_ANCHORS)
    intent = _normalized_contains(text, INTENT_ANCHORS)
    if primary:
        return True
    if supporting and intent:
        return True
    return False


def canonical_origin_doc_intent(query_text: str) -> bool:
    """Return true when the cue asks for the origin essay/document itself.

    Relationship-origin source-chain routes intentionally cover several nearby
    sources: the mechanical-ascension conversation, the external hippocampus
    design turn, and later reconstruction notes. A cue like "未干的地图" or
    "origin essay" is narrower than that whole lane. Keep this distinction
    explicit so a broad origin source cannot satisfy a request for the
    canonical essay/handoff merely because both belong to the same story.
    """

    return bool(_normalized_contains(str(query_text or ""), CANONICAL_ORIGIN_DOC_ANCHORS))


def relationship_origin_expansion_terms(query_text: str) -> list[str]:
    if not relationship_origin_intent(query_text):
        return []
    # These terms are navigation-only expansion anchors. They point retrieval
    # toward the canonical source lane but still require source reopen before
    # any claim about the old conversation.
    return [
        "小海马体",
        "外置海马体",
        "AIppocampus",
        "未干的地图",
        "机械飞升",
        "机仆",
        "机械种族",
        "未来机械生命",
        "生命还能变成什么",
        "可以回去",
        "关系连续性",
    ]


def relationship_origin_search_patterns(query_text: str) -> list[str]:
    if not relationship_origin_intent(query_text):
        return [query_text]
    return [
        query_text,
        "机械飞升 海马体 机仆 机械种族",
        "未干的地图 外置小海马体 生命还能变成什么",
        "AIppocampus 关系连续性 可以回去 小海马体",
    ]


def relationship_origin_match_diagnostics(
    query_text: str,
    haystack: str,
    *,
    scope_labels: list[str] | None = None,
    thread_title: str = "",
) -> dict[str, Any]:
    origin_intent = relationship_origin_intent(query_text)
    primary = _normalized_contains(haystack, PRIMARY_ORIGIN_ANCHORS)
    supporting = _normalized_contains(haystack, SUPPORTING_ORIGIN_ANCHORS)
    generic = _normalized_contains(haystack, GENERIC_HIPPOCAMPUS_RESEARCH_ANCHORS)
    scopes = {str(label).strip() for label in scope_labels or [] if str(label).strip()}
    title_low = str(thread_title or "").casefold()
    primary_count = len(primary)
    supporting_count = len(supporting)
    anchor_count = primary_count + supporting_count
    accepted_origin_route = bool(
        origin_intent
        and primary_count >= 1
        and anchor_count >= 2
    )
    generic_research_decoy = bool(origin_intent and generic and primary_count == 0)
    boost = 0.0
    if accepted_origin_route:
        boost += 5000.0 + primary_count * 1200.0 + supporting_count * 450.0
        if "relationship_continuity" in scopes:
            boost += 800.0
        if "aippocampus" in title_low:
            boost += 300.0
    elif origin_intent and primary_count == 1:
        boost += 900.0
    if generic_research_decoy:
        boost -= 6000.0 + len(generic) * 300.0
    elif origin_intent and generic and primary_count == 0:
        boost -= 1800.0
    reason_codes: list[str] = []
    if accepted_origin_route:
        reason_codes.append("relationship_origin_anchor_match")
    if "relationship_continuity" in scopes:
        reason_codes.append("relationship_continuity_scope")
    if generic_research_decoy:
        reason_codes.append("generic_hippocampus_research_demoted")
    return {
        "origin_intent": origin_intent,
        "accepted_origin_route": accepted_origin_route,
        "generic_research_decoy": generic_research_decoy,
        "primary_anchor_count": primary_count,
        "supporting_anchor_count": supporting_count,
        "matched_primary_anchors": primary[:5],
        "matched_supporting_anchors": supporting[:5],
        "rank_boost": boost,
        "reason_codes": reason_codes,
    }


def relationship_origin_rank_adjustment(
    *,
    query_text: str,
    match: Mapping[str, Any],
    haystack: str,
) -> float:
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    diagnostics = relationship_origin_match_diagnostics(
        query_text,
        haystack,
        scope_labels=[
            *[str(label) for label in match.get("scope_labels") or []],
            *[str(label) for label in match.get("semantic_scope_labels") or []],
        ],
        thread_title=str(thread_map.get("title") or ""),
    )
    return float(diagnostics.get("rank_boost") or 0.0)


def relationship_origin_allows_low_coverage(
    *,
    query_text: str,
    haystack: str,
    scope_labels: list[str] | None = None,
    thread_title: str = "",
) -> dict[str, Any]:
    diagnostics = relationship_origin_match_diagnostics(
        query_text,
        haystack,
        scope_labels=scope_labels,
        thread_title=thread_title,
    )
    return {
        **diagnostics,
        "accepted": bool(diagnostics.get("accepted_origin_route")),
        "suppression_override_reason": (
            "relationship_origin_source_anchors_matched"
            if diagnostics.get("accepted_origin_route")
            else ""
        ),
    }


__all__ = [
    "RELATIONSHIP_ORIGIN_ROUTE_TOPIC",
    "canonical_origin_doc_intent",
    "relationship_origin_allows_low_coverage",
    "relationship_origin_expansion_terms",
    "relationship_origin_intent",
    "relationship_origin_match_diagnostics",
    "relationship_origin_rank_adjustment",
    "relationship_origin_search_patterns",
]
