"""Shared vocabulary for recall route-feedback signals.

Feedback rows are navigation calibration, not source truth. This module owns
the small set of canonical route-feedback signals plus aliases, polarity, and
default deltas so producers and consumers do not quietly drift apart. It does
not own downstream lifecycle states such as ``suppressed_hard_negative`` or
trace-admission roles such as ``positive_demo``.
"""

from __future__ import annotations

from typing import Any

POSITIVE_FEEDBACK_SIGNALS = frozenset(
    {
        "source_reopen_success",
        "user_confirmed",
        "prevented_failure",
        "reopened_deepened",
    }
)
HARD_NEGATIVE_FEEDBACK_SIGNALS = frozenset(
    {
        "wrong_route_drag",
        "dismissed",
        "manual_search_after_route",
        "context_suppressed",
        "user_correction",
        "ignored",
        "blocked",
        "superseded",
    }
)
PARKED_FEEDBACK_SIGNALS = frozenset(
    {
        "parked",
        "privacy_blocked",
        "stale",
        "off_phase",
        "needs_refine",
        "duplicate",
    }
)
SURFACE_FEEDBACK_SIGNALS = frozenset({"candidate_delivered"})
DECAY_FEEDBACK_SIGNALS = frozenset({"expired"})
ACTIVE_FLOW_SIGNALS = (
    POSITIVE_FEEDBACK_SIGNALS
    | HARD_NEGATIVE_FEEDBACK_SIGNALS
    | PARKED_FEEDBACK_SIGNALS
    | SURFACE_FEEDBACK_SIGNALS
    | DECAY_FEEDBACK_SIGNALS
)
NON_FOREGROUND_SIGNALS = HARD_NEGATIVE_FEEDBACK_SIGNALS | PARKED_FEEDBACK_SIGNALS | DECAY_FEEDBACK_SIGNALS
NEGATIVE_FEEDBACK_SIGNALS = HARD_NEGATIVE_FEEDBACK_SIGNALS | PARKED_FEEDBACK_SIGNALS | DECAY_FEEDBACK_SIGNALS

OUTCOME_ALIASES = {
    "helped": "source_reopen_success",
    "useful": "source_reopen_success",
    "confirmed": "user_confirmed",
    "wrong": "wrong_route_drag",
    "wrong_route": "wrong_route_drag",
    "noisy": "wrong_route_drag",
    "corrected": "user_correction",
    "dismiss": "dismissed",
    "manual_search": "manual_search_after_route",
    "context_suppression": "context_suppressed",
    "park": "parked",
    "privacy": "privacy_blocked",
    "prevented": "prevented_failure",
}

DEFAULT_SIGNAL_DELTAS = {
    "source_reopen_success": 1.0,
    "user_confirmed": 0.75,
    "prevented_failure": 0.75,
    "reopened_deepened": 1.0,
    "candidate_delivered": 0.1,
    "ignored": -0.15,
    "wrong_route_drag": -1.0,
    "dismissed": -0.9,
    "manual_search_after_route": -1.0,
    "context_suppressed": -0.9,
    # User corrections mean the route actively misled the user or agent. Keep
    # this as severe as wrong-route drag so a future alias cannot become a
    # neutral no-op while still being marked hard-negative.
    "user_correction": -1.0,
    "blocked": -1.0,
    "superseded": -0.8,
    "parked": -0.35,
    "privacy_blocked": -0.35,
    "stale": -0.35,
    "off_phase": -0.25,
    "needs_refine": -0.25,
    "duplicate": -0.25,
    "expired": -0.4,
}

APW_FOLLOWTHROUGH_POSITIVE_OUTCOMES = frozenset(
    {"source_reopened", "source_helped_task", "task_advanced"}
)
APW_FOLLOWTHROUGH_NEGATIVE_OUTCOMES = frozenset(
    {
        "action_ignored",
        "source_not_useful",
        "wrong_hop",
        "irrelevant_drag",
        "stale_route",
        "superseded_route",
        "private_or_wrong_scope",
        "manual_search_needed_first",
    }
)
APW_FOLLOWTHROUGH_OUTCOME_TO_SIGNAL = {
    "source_reopened": "source_reopen_success",
    "source_helped_task": "user_confirmed",
    "task_advanced": "user_confirmed",
    "action_ignored": "ignored",
    "source_not_useful": "wrong_route_drag",
    "wrong_hop": "wrong_route_drag",
    "irrelevant_drag": "wrong_route_drag",
    "stale_route": "superseded",
    "superseded_route": "superseded",
    "private_or_wrong_scope": "blocked",
    "manual_search_needed_first": "wrong_route_drag",
}

RECALL_OUTCOME_SIGNALS = frozenset(
    {
        "answer_improved_after_deepen",
        "source_reopen_success",
        "wrong_route_drag",
        "ignored",
        "requery_after_miss",
        "blocked_boundary",
        "user_correction",
        "deepened",
        "superseded",
        "accepted_route",
        "dismissed_anti_nag",
        "prevented_failure",
        "stale_route_revival",
        "manual_search_avoided",
        "no_visible_effect",
        "recall_added_noise",
        "user_confirmed_helpful",
        "user_reprompted_with_thread_id",
    }
)
ACTIVE_FLOW_RECALL_OUTCOME_POLICY = {
    "source_reopen_success": "source_reopen_success",
    "user_confirmed": "user_confirmed_helpful",
    "prevented_failure": "prevented_failure",
    "reopened_deepened": "deepened",
    "candidate_delivered": "no_visible_effect",
    "ignored": "ignored",
    "wrong_route_drag": "wrong_route_drag",
    "dismissed": "dismissed_anti_nag",
    "manual_search_after_route": "requery_after_miss",
    "context_suppressed": "recall_added_noise",
    "user_correction": "user_correction",
    "blocked": "blocked_boundary",
    "superseded": "superseded",
    "parked": "no_visible_effect",
    "privacy_blocked": "blocked_boundary",
    "stale": "superseded",
    "off_phase": "no_visible_effect",
    "needs_refine": "no_visible_effect",
    "duplicate": "superseded",
    "expired": "superseded",
}
RECALL_OUTCOME_ALIASES = {
    "confirm": "user_confirmed_helpful",
    "confirmed": "user_confirmed_helpful",
    "user_confirmed": "user_confirmed_helpful",
    "helpful": "user_confirmed_helpful",
}
HELPFUL_RECALL_OUTCOME_SIGNALS = frozenset(
    {
        "answer_improved_after_deepen",
        "accepted_route",
        "deepened",
        "manual_search_avoided",
        "prevented_failure",
        "source_reopen_success",
        "user_confirmed_helpful",
    }
)
NOISY_OR_HARMFUL_RECALL_OUTCOME_SIGNALS = frozenset(
    {
        "recall_added_noise",
        "requery_after_miss",
        "user_correction",
        "user_reprompted_with_thread_id",
        "wrong_route_drag",
    }
)
NO_VISIBLE_EFFECT_RECALL_OUTCOME_SIGNALS = frozenset(
    {"ignored", "no_visible_effect", "blocked_boundary", "superseded"}
)
RECALL_OUTCOME_CALIBRATION_DELTAS = {
    "accepted_route": 0.5,
    "answer_improved_after_deepen": 0.8,
    "blocked_boundary": -1.0,
    "deepened": 0.5,
    "dismissed_anti_nag": -0.9,
    "ignored": 0.0,
    "manual_search_avoided": 0.75,
    "no_visible_effect": 0.0,
    "prevented_failure": 0.75,
    "recall_added_noise": -0.75,
    "requery_after_miss": -0.6,
    "source_reopen_success": 1.0,
    "stale_route_revival": -0.4,
    "superseded": -0.8,
    "user_confirmed_helpful": 0.75,
    "user_correction": -1.0,
    "user_reprompted_with_thread_id": -0.5,
    "wrong_route_drag": -1.0,
}


def normalize_feedback_signal(value: Any, *, default: str = "candidate_delivered") -> str:
    """Normalize route-feedback aliases to one canonical signal."""

    text = str(value or "").strip()
    if text in ACTIVE_FLOW_SIGNALS:
        return text
    folded = text.casefold()
    if folded in ACTIVE_FLOW_SIGNALS:
        return folded
    alias = OUTCOME_ALIASES.get(folded)
    return alias or default


def feedback_signal_polarity(signal: Any) -> str:
    canonical = normalize_feedback_signal(signal, default="")
    if canonical in POSITIVE_FEEDBACK_SIGNALS:
        return "positive"
    if canonical in HARD_NEGATIVE_FEEDBACK_SIGNALS:
        return "hard_negative"
    if canonical in PARKED_FEEDBACK_SIGNALS:
        return "parked"
    if canonical in DECAY_FEEDBACK_SIGNALS:
        return "decay"
    if canonical in SURFACE_FEEDBACK_SIGNALS:
        return "surface"
    return "unknown"


def feedback_signal_is_positive(signal: Any) -> bool:
    return feedback_signal_polarity(signal) == "positive"


def feedback_signal_is_negative(signal: Any) -> bool:
    return feedback_signal_polarity(signal) in {"hard_negative", "parked", "decay"}


def default_signal_delta(signal: Any) -> float:
    return DEFAULT_SIGNAL_DELTAS.get(normalize_feedback_signal(signal, default=""), 0.0)


def recall_outcome_calibration_delta(outcome: Any) -> float | None:
    """Return the explicit calibration delta for a normalized recall outcome."""

    canonical = normalize_recall_outcome_signal(outcome, default="")
    if canonical not in RECALL_OUTCOME_CALIBRATION_DELTAS:
        return None
    return RECALL_OUTCOME_CALIBRATION_DELTAS[canonical]


def normalize_recall_outcome_signal(value: Any, *, default: str = "ignored") -> str:
    """Normalize recall outcome feedback without widening it into source evidence."""

    text = str(value or "").strip()
    if text in RECALL_OUTCOME_SIGNALS:
        return text
    folded = text.casefold()
    if folded in RECALL_OUTCOME_SIGNALS:
        return folded
    if folded in RECALL_OUTCOME_ALIASES:
        return RECALL_OUTCOME_ALIASES[folded]
    canonical = normalize_feedback_signal(folded, default="")
    if canonical in ACTIVE_FLOW_RECALL_OUTCOME_POLICY:
        return ACTIVE_FLOW_RECALL_OUTCOME_POLICY[canonical]
    return default


__all__ = [
    "ACTIVE_FLOW_SIGNALS",
    "ACTIVE_FLOW_RECALL_OUTCOME_POLICY",
    "APW_FOLLOWTHROUGH_NEGATIVE_OUTCOMES",
    "APW_FOLLOWTHROUGH_OUTCOME_TO_SIGNAL",
    "APW_FOLLOWTHROUGH_POSITIVE_OUTCOMES",
    "DECAY_FEEDBACK_SIGNALS",
    "DEFAULT_SIGNAL_DELTAS",
    "HARD_NEGATIVE_FEEDBACK_SIGNALS",
    "HELPFUL_RECALL_OUTCOME_SIGNALS",
    "NEGATIVE_FEEDBACK_SIGNALS",
    "NOISY_OR_HARMFUL_RECALL_OUTCOME_SIGNALS",
    "NO_VISIBLE_EFFECT_RECALL_OUTCOME_SIGNALS",
    "NON_FOREGROUND_SIGNALS",
    "OUTCOME_ALIASES",
    "PARKED_FEEDBACK_SIGNALS",
    "POSITIVE_FEEDBACK_SIGNALS",
    "RECALL_OUTCOME_CALIBRATION_DELTAS",
    "RECALL_OUTCOME_SIGNALS",
    "RECALL_OUTCOME_ALIASES",
    "SURFACE_FEEDBACK_SIGNALS",
    "default_signal_delta",
    "feedback_signal_is_negative",
    "feedback_signal_is_positive",
    "feedback_signal_polarity",
    "normalize_feedback_signal",
    "normalize_recall_outcome_signal",
    "recall_outcome_calibration_delta",
]
