"""Candidate planning filters and freshness diagnostics for recall."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.recall.scoring_policy import FRESHNESS_SCORING_POLICY


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.casefold() in {"1", "true", "yes", "stale", "conflict", "conflicted"}
    return bool(value)


def _lexical_score(candidate: Mapping[str, Any]) -> float:
    value = candidate.get("lexical_score", candidate.get("score", 0.0))
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _freshness_state(candidate: Mapping[str, Any]) -> str:
    if _truthy(candidate.get("conflict")) or _truthy(candidate.get("conflicted")):
        return "conflict"
    if _truthy(candidate.get("stale")):
        return "stale"
    freshness = str(candidate.get("freshness") or candidate.get("currentness") or "").casefold()
    if freshness in {"stale", "superseded", "old", "expired"}:
        return "stale"
    if freshness in {"conflict", "conflicted", "disputed"}:
        return "conflict"
    if freshness in {"current", "fresh", "active"}:
        return "current"
    return "unknown"


def freshness_score(candidate: Mapping[str, Any], freshness_mode: str) -> tuple[float, list[str]]:
    state = _freshness_state(candidate)
    policy = FRESHNESS_SCORING_POLICY
    reasons: list[str] = []
    if freshness_mode == "current_first":
        if state == "current":
            return policy.current_first_current_bonus, ["current_first_current_bonus"]
        if state == "stale":
            return policy.current_first_stale_penalty, ["stale_currentness"]
        if state == "conflict":
            return policy.current_first_conflict_penalty, ["conflict_currentness"]
    if freshness_mode == "history_friendly":
        if state == "stale":
            reasons.append("history_or_dispute_allows_stale")
        if state == "conflict":
            reasons.append("history_or_dispute_allows_conflict")
        return 0.0, reasons
    if state == "current":
        return policy.neutral_current_bonus, []
    if state == "stale":
        return policy.neutral_stale_penalty, []
    return 0.0, []


def _wrong_scope(candidate: Mapping[str, Any], scope: Mapping[str, Any]) -> str | None:
    for key in ("project_id", "thread_key", "session_id", "source_family"):
        wanted = scope.get(key)
        if wanted in (None, ""):
            continue
        actual = candidate.get(key)
        if actual not in (None, "") and str(actual) != str(wanted):
            return key
    return None


def _privacy_blocked(candidate: Mapping[str, Any]) -> bool:
    boundary = str(candidate.get("privacy_boundary") or candidate.get("privacy_profile") or "").casefold()
    return bool(candidate.get("blocked") or boundary in {"blocked", "private_blocked", "ignore_or_blocked"})


def plan_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    strategy: Mapping[str, Any],
    scope: Mapping[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Apply hard scope/privacy filters and soft freshness ranking.

    Stale and disputed candidates are deliberately soft/post boundaries by
    default. Hiding them at prefilter time breaks explicit history, audit, and
    dispute queries; freshness only changes ordering and authority diagnostics.
    """

    scope = scope or {}
    freshness_mode = str(strategy.get("freshness_mode") or "neutral")
    raw_hard_filters = strategy.get("hard_filters")
    hard_filters: Mapping[str, Any] = (
        raw_hard_filters if isinstance(raw_hard_filters, Mapping) else {}
    )
    prefilter_counts = {"wrong_scope": 0, "privacy_blocked": 0}
    soft_filter_counts = {"stale_currentness": 0, "conflict_currentness": 0}
    ranked: list[dict[str, Any]] = []

    for raw in candidates:
        candidate = dict(raw)
        wrong_scope = _wrong_scope(candidate, scope)
        if wrong_scope and hard_filters.get("scope", True):
            prefilter_counts["wrong_scope"] += 1
            continue
        if _privacy_blocked(candidate) and hard_filters.get("privacy", True):
            prefilter_counts["privacy_blocked"] += 1
            continue

        lexical = _lexical_score(candidate)
        fresh_score, reason_codes = freshness_score(candidate, freshness_mode)
        for reason in reason_codes:
            if reason in soft_filter_counts:
                soft_filter_counts[reason] += 1

        adjusted = lexical + fresh_score
        authority = str(candidate.get("authority") or strategy.get("authority_floor") or "direction_with_ref")
        if freshness_mode == "history_friendly" and _freshness_state(candidate) in {"stale", "conflict"}:
            authority = "direction_with_ref"
        candidate["authority"] = authority
        candidate["adjusted_score"] = round(adjusted, 3)
        candidate["diagnostics"] = {
            "lexical_score": round(lexical, 3),
            "freshness_score": round(fresh_score, 3),
            "freshness_mode": freshness_mode,
            "freshness_state": _freshness_state(candidate),
            "reason_codes": reason_codes,
            "now": now or "",
        }
        ranked.append(candidate)

    ranked.sort(
        key=lambda item: (
            -float(item.get("adjusted_score") or 0.0),
            str(item.get("candidate_id") or item.get("route_id") or ""),
        )
    )
    return {
        "ranked_candidates": ranked,
        "diagnostics": {
            "policy": "recall_candidate_planning_v1",
            "strategy": strategy.get("strategy") or "",
            "prefilter_counts": prefilter_counts,
            "soft_filter_counts": soft_filter_counts,
            "post_reopen_boundaries": ["source_reopen_required_for_claims"],
            "privacy_boundary": "counts_only_no_source_text",
        },
    }
