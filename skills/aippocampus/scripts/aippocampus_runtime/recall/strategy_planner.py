"""Deterministic query-intent to recall strategy planning."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_SOURCE_REF_RE = re.compile(
    r"(\bsource[_ -]?ref\b|\bmsg[-_:]?\d+\b|\bmessage[-_:]?\d+\b|#L\d+\b|\bline\s+\d+\b)",
    re.I,
)
_EXACT_RE = re.compile(r"(\bexact\b|\bverbatim\b|\bquote\b|原文|逐字|准确措辞|exact wording)", re.I)
_EXPLORATORY_RE = re.compile(
    r"(\bbroadly\b|\banything\b|\beverything\b|what do we know|explor|survey|梳理|探索|有哪些|都有什么)",
    re.I,
)
_HISTORY_DISPUTE_RE = re.compile(
    r"(\bstale\b|\bdisputed?\b|\bconflict(?:ed)?\b|\bsuperseded\b|\bhistory\b|争议|冲突|过期|历史|旧版本|被替代)",
    re.I,
)
_CURRENT_RE = re.compile(r"(\bcurrent\b|\blatest\b|\bnow\b|当前|现在|最新)", re.I)


_STRATEGIES: dict[str, dict[str, Any]] = {
    "exact_lookup": {
        "top_k": 5,
        "fanout_budget": 4,
        "candidate_max": 48,
        "filter_strictness": "strict",
        "authority_floor": "bounded_evidence",
        "freshness_mode": "neutral",
        "hard_filters": {"scope": True, "privacy": True, "stale": False, "conflict": False},
    },
    "route_recall": {
        "top_k": 12,
        "fanout_budget": 8,
        "candidate_max": 120,
        "filter_strictness": "normal",
        "authority_floor": "direction_with_ref",
        "freshness_mode": "current_first",
        "hard_filters": {"scope": True, "privacy": True, "stale": False, "conflict": False},
    },
    "exploratory_recall": {
        "top_k": 24,
        "fanout_budget": 18,
        "candidate_max": 220,
        "filter_strictness": "soft",
        "authority_floor": "direction_with_ref",
        "freshness_mode": "neutral",
        "hard_filters": {"scope": True, "privacy": True, "stale": False, "conflict": False},
    },
    "source_reopen": {
        "top_k": 4,
        "fanout_budget": 3,
        "candidate_max": 32,
        "filter_strictness": "strict",
        "authority_floor": "reopenable_route",
        "freshness_mode": "neutral",
        "hard_filters": {"scope": True, "privacy": True, "stale": False, "conflict": False},
    },
    "history_or_dispute": {
        "top_k": 18,
        "fanout_budget": 12,
        "candidate_max": 160,
        "filter_strictness": "soft",
        "authority_floor": "direction_with_ref",
        "freshness_mode": "history_friendly",
        "hard_filters": {"scope": True, "privacy": True, "stale": False, "conflict": False},
    },
}


def _strategy_payload(strategy: str, reasons: Iterable[str]) -> dict[str, Any]:
    base = dict(_STRATEGIES[strategy])
    base["strategy"] = strategy
    base["diagnostics"] = {
        "policy": "deterministic_recall_strategy_v1",
        "reasons": list(dict.fromkeys(reasons)),
        "default_llm_classifier": False,
    }
    return base


def select_recall_strategy(
    query: str,
    *,
    explicit_strategy: str | None = None,
    source_refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Select retrieval breadth and authority settings from cheap cues."""

    text = str(query or "")
    reasons: list[str] = []
    if explicit_strategy in _STRATEGIES:
        return _strategy_payload(explicit_strategy, ["explicit_strategy"])
    if source_refs:
        reasons.append("source_ref_argument")
        return _strategy_payload("source_reopen", reasons)
    if _SOURCE_REF_RE.search(text):
        reasons.append("source_ref_cue")
        return _strategy_payload("source_reopen", reasons)
    if _HISTORY_DISPUTE_RE.search(text):
        reasons.append("history_or_dispute_cue")
        return _strategy_payload("history_or_dispute", reasons)
    if _EXACT_RE.search(text):
        reasons.append("exact_lookup_cue")
        return _strategy_payload("exact_lookup", reasons)
    if _EXPLORATORY_RE.search(text):
        reasons.append("exploratory_cue")
        return _strategy_payload("exploratory_recall", reasons)
    if _CURRENT_RE.search(text):
        reasons.append("currentness_cue")
    else:
        reasons.append("default_route_recall")
    return _strategy_payload("route_recall", reasons)
