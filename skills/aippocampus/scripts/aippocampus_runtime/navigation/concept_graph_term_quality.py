"""Shared term-quality gate for concept-graph ingress.

Concept-graph labels are navigation hints, not source evidence. This owner sits
between producers and graph materialization so association, timeline, and
subconscious producers cannot each grow their own CJK fragment policy. The
report intentionally stores buckets and counters only; raw labels stay out of
default JSON because graph quality reports may be run on private history.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from aippocampus_runtime.navigation.association_terms import normalize_term, term_is_noise
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.text import (
    CJK_DOMAIN_ANCHORS,
    cjk_ideograph_count,
    has_cjk_ideograph,
    is_distinctive_cjk_anchor,
    is_low_value_cjk_fragment,
    strip_cjk_deictic_prefix,
)

TERM_QUALITY_SCHEMA_VERSION = "concept_graph_term_quality_v1"
INGRESS_VALUES = ("association", "related_term", "timeline", "subconscious")
CJK_BAD_EDGE_CHARS = frozenset("的了和与或而但在把对给吗呢吧啊是")


@dataclass(frozen=True)
class TermQualityContext:
    ingress: str
    reviewed: bool = False
    static_anchor: bool = False
    source_backed: bool = False
    hit_count: int = 0
    thread_count: int = 0
    phrase_stat: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class TermQualityDecision:
    term: str
    accepted: bool
    reason: str
    ingress: str
    cjk: bool
    av_bucket: str
    support_bucket: str


def _safe_ingress(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in INGRESS_VALUES else "unknown"


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _accessor_values(stat: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
    if not stat:
        return None, None
    if "left_accessor_variety" not in stat or "right_accessor_variety" not in stat:
        return None, None
    return _as_int(stat.get("left_accessor_variety")), _as_int(stat.get("right_accessor_variety"))


def accessor_variety_bucket(
    stat: Mapping[str, Any] | None,
    *,
    cjk: bool,
) -> str:
    if not cjk:
        return "not_cjk"
    left_av, right_av = _accessor_values(stat)
    if left_av is None or right_av is None:
        return "unknown"
    max_av = max(left_av, right_av)
    if max_av <= 1:
        return "0-1"
    if max_av <= 3:
        return "2-3"
    return "4+"


def _has_low_accessor_variety(context: TermQualityContext) -> bool:
    left_av, right_av = _accessor_values(context.phrase_stat)
    if left_av is None or right_av is None:
        return False
    document_count = _as_int((context.phrase_stat or {}).get("document_count"))
    return max(left_av, right_av) <= 1 and document_count <= 1


def _has_good_accessor_variety(context: TermQualityContext) -> bool:
    left_av, right_av = _accessor_values(context.phrase_stat)
    if left_av is None or right_av is None:
        return False
    document_count = _as_int((context.phrase_stat or {}).get("document_count"))
    return max(left_av, right_av) >= 2 or document_count >= 2


def _support_bucket(context: TermQualityContext) -> str:
    if context.reviewed:
        return "reviewed"
    if context.static_anchor:
        return "static_anchor"
    if context.thread_count >= 2:
        return "multi_thread"
    if context.hit_count >= 2:
        return "multi_hit"
    if context.source_backed:
        return "source_backed"
    return "mined_or_unknown"


def _has_strong_support(context: TermQualityContext) -> bool:
    return (
        context.reviewed
        or context.static_anchor
        or context.thread_count >= 2
        or context.hit_count >= 2
        or _has_good_accessor_variety(context)
    )


def _bad_cjk_edge(term: str) -> bool:
    value = strip_cjk_deictic_prefix(term)
    return bool(value) and (value[0] in CJK_BAD_EDGE_CHARS or value[-1] in CJK_BAD_EDGE_CHARS)


def assess_concept_term(label: Any, context: TermQualityContext) -> TermQualityDecision:
    term = normalize_term(str(label or ""))
    ingress = _safe_ingress(context.ingress)
    cjk = has_cjk_ideograph(term)
    av_bucket = accessor_variety_bucket(context.phrase_stat, cjk=cjk)
    support_bucket = _support_bucket(context)
    if not term:
        return TermQualityDecision(term, False, "empty", ingress, cjk, av_bucket, support_bucket)

    if cjk:
        squashed = strip_cjk_deictic_prefix(term)
        if _bad_cjk_edge(squashed):
            return TermQualityDecision(
                term, False, "bad_cjk_boundary", ingress, cjk, av_bucket, support_bucket
            )
        if is_low_value_cjk_fragment(squashed):
            return TermQualityDecision(
                term,
                False,
                "low_value_cjk_fragment",
                ingress,
                cjk,
                av_bucket,
                support_bucket,
            )
        if term_is_noise(term):
            return TermQualityDecision(
                term, False, "term_noise", ingress, cjk, av_bucket, support_bucket
            )
        if squashed in CJK_DOMAIN_ANCHORS:
            return TermQualityDecision(
                term, True, "domain_anchor", ingress, cjk, av_bucket, support_bucket
            )
        if context.reviewed:
            return TermQualityDecision(
                term, True, "reviewed_anchor", ingress, cjk, av_bucket, support_bucket
            )
        if context.static_anchor:
            return TermQualityDecision(
                term, True, "static_anchor", ingress, cjk, av_bucket, support_bucket
            )
        if _has_low_accessor_variety(context) and not _has_strong_support(context):
            return TermQualityDecision(
                term,
                False,
                "low_accessor_variety",
                ingress,
                cjk,
                av_bucket,
                support_bucket,
            )
        if cjk_ideograph_count(squashed) >= 13 and not _has_strong_support(context):
            return TermQualityDecision(
                term, False, "long_cjk_clause", ingress, cjk, av_bucket, support_bucket
            )
        if not is_distinctive_cjk_anchor(squashed) and not _has_good_accessor_variety(context):
            return TermQualityDecision(
                term, False, "weak_cjk_anchor", ingress, cjk, av_bucket, support_bucket
            )
        return TermQualityDecision(
            term, True, "cjk_anchor", ingress, cjk, av_bucket, support_bucket
        )

    if term_is_noise(term):
        return TermQualityDecision(term, False, "term_noise", ingress, cjk, av_bucket, support_bucket)
    return TermQualityDecision(term, True, "non_cjk", ingress, cjk, av_bucket, support_bucket)


def _bump_nested(payload: dict[str, Any], family: str, key: str, value: str) -> None:
    target = payload.setdefault(family, {}).setdefault(key, {})
    target[value] = int(target.get(value) or 0) + 1


def _bump(payload: dict[str, Any], family: str, key: str) -> None:
    target = payload.setdefault(family, {})
    target[key] = int(target.get(key) or 0) + 1


class ConceptTermQualityTracker:
    def __init__(self) -> None:
        self._payload: dict[str, Any] = {
            "schema_version": TERM_QUALITY_SCHEMA_VERSION,
            "mode": "advisory_build_gate",
            "raw_labels_default": "omitted",
            "candidate_counts_by_ingress": {},
            "accepted_counts_by_ingress": {},
            "rejected_counts_by_ingress": {},
            "rejected_reason_counts": {},
            "cjk_av_buckets_by_ingress": {},
            "support_buckets_by_ingress": {},
        }

    def record(self, decision: TermQualityDecision) -> None:
        _bump(self._payload, "candidate_counts_by_ingress", decision.ingress)
        _bump_nested(
            self._payload,
            "cjk_av_buckets_by_ingress",
            decision.ingress,
            decision.av_bucket,
        )
        _bump_nested(
            self._payload,
            "support_buckets_by_ingress",
            decision.ingress,
            decision.support_bucket,
        )
        if decision.accepted:
            _bump(self._payload, "accepted_counts_by_ingress", decision.ingress)
            return
        _bump(self._payload, "rejected_counts_by_ingress", decision.ingress)
        _bump(self._payload, "rejected_reason_counts", decision.reason)

    def accepts(self, label: Any, context: TermQualityContext) -> bool:
        decision = assess_concept_term(label, context)
        self.record(decision)
        return decision.accepted

    def filter_terms(
        self,
        values: Iterable[Any],
        context: TermQualityContext,
        *,
        phrase_stats_by_term: Mapping[str, Mapping[str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        out: list[str] = []
        for value in unique_preserve([normalize_term(str(item or "")) for item in values], limit=limit):
            if not value:
                continue
            stat = (phrase_stats_by_term or {}).get(value.casefold())
            value_context = replace(context, phrase_stat=stat or context.phrase_stat)
            if self.accepts(value, value_context):
                out.append(value)
        return out

    def to_payload(self) -> dict[str, Any]:
        return json_safe_quality_payload(self._payload)


def json_safe_quality_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for key in (
        "candidate_counts_by_ingress",
        "accepted_counts_by_ingress",
        "rejected_counts_by_ingress",
        "rejected_reason_counts",
    ):
        out[key] = dict(sorted((out.get(key) or {}).items()))
    for key in ("cjk_av_buckets_by_ingress", "support_buckets_by_ingress"):
        nested = out.get(key) or {}
        out[key] = {
            str(ingress): dict(sorted((values or {}).items()))
            for ingress, values in sorted(nested.items())
            if isinstance(values, Mapping)
        }
    return out


__all__ = [
    "ConceptTermQualityTracker",
    "TermQualityContext",
    "accessor_variety_bucket",
    "assess_concept_term",
    "json_safe_quality_payload",
]
