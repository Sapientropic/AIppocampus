#!/usr/bin/env python3
"""Reversible route suppression lifecycle projection.

Feedback suppression is route-local navigation calibration. It decides whether
a candidate should stay out of compact foreground, but it never deletes source
refs or turns feedback into factual evidence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.feedback.vocabulary import (
    ACTIVE_FLOW_SIGNALS,
    DEFAULT_SIGNAL_DELTAS,
    HARD_NEGATIVE_FEEDBACK_SIGNALS,
    NON_FOREGROUND_SIGNALS,
    PARKED_FEEDBACK_SIGNALS,
    POSITIVE_FEEDBACK_SIGNALS,
    normalize_feedback_signal,
)

POSITIVE_SUPPRESSION_SIGNALS = POSITIVE_FEEDBACK_SIGNALS
HARD_NEGATIVE_SUPPRESSION_SIGNALS = HARD_NEGATIVE_FEEDBACK_SIGNALS
PARKED_SUPPRESSION_SIGNALS = PARKED_FEEDBACK_SIGNALS


def _safe_token(value: Any, *, fallback_prefix: str) -> str:
    text = str(value or "").strip()
    if not text:
        return stable_json_join_id(fallback_prefix, "", ensure_ascii=False, default_str=False)
    safe = redact_sensitive_values(redact_private_paths(text))
    if safe != text or "\\" in safe or "/" in safe:
        return stable_json_join_id(fallback_prefix, safe, ensure_ascii=False, default_str=False)
    return safe[:160]


def _safe_signal(value: Any) -> str:
    signal = normalize_feedback_signal(value, default="")
    return signal if signal in ACTIVE_FLOW_SIGNALS else ""


def _invalid_signal_sample(event: Mapping[str, Any], route_id: str) -> dict[str, str]:
    return {
        "route_id": route_id,
        "signal": _safe_token(event.get("signal") or event.get("outcome"), fallback_prefix="signal"),
        "reason": "unknown_feedback_signal_quarantined",
    }


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def route_reason_codes(signals: Counter[str], score: float) -> list[str]:
    reasons: list[str] = []
    if signals.get("blocked"):
        reasons.append("blocked_route_not_foreground_eligible")
    if signals.get("wrong_route_drag"):
        reasons.append("wrong_route_drag_demoted")
    if signals.get("dismissed"):
        reasons.append("dismissed_route_suppressed")
    if signals.get("manual_search_after_route"):
        reasons.append("manual_search_after_route_demoted")
    if signals.get("context_suppressed"):
        reasons.append("context_suppression_applied")
    if signals.get("superseded"):
        reasons.append("superseded_route_demoted")
    if any(signals.get(signal) for signal in PARKED_SUPPRESSION_SIGNALS):
        reasons.append("parked_route_waiting_recheck")
    if signals.get("expired"):
        reasons.append("expired_route_decay_applied")
    if signals.get("source_reopen_success"):
        reasons.append("source_reopen_success_promoted")
    if signals.get("user_confirmed"):
        reasons.append("user_confirmed_promoted")
    if score <= 0 and not reasons:
        reasons.append("non_positive_activation_score")
    return reasons


def current_feedback_state(last_signal: str) -> str:
    if last_signal in POSITIVE_SUPPRESSION_SIGNALS:
        return "overridden_by_positive_source_open"
    if last_signal in HARD_NEGATIVE_SUPPRESSION_SIGNALS:
        return "suppressed_hard_negative"
    if last_signal in PARKED_SUPPRESSION_SIGNALS:
        return "parked_recheck"
    if last_signal == "expired":
        return "expired_recheck"
    return "neutral"


def foreground_eligible(signals: Counter[str], last_signal: str, score: float) -> bool:
    return score > 0 and (
        last_signal in POSITIVE_SUPPRESSION_SIGNALS
        or not any(signals.get(signal) for signal in NON_FOREGROUND_SIGNALS)
    )


def feedback_trace_family(outcome: str) -> str:
    if outcome in {"source_reopen_success", "user_confirmed", "prevented_failure"}:
        return "successful_recall_deepen_source_open"
    if outcome in HARD_NEGATIVE_SUPPRESSION_SIGNALS | PARKED_SUPPRESSION_SIGNALS | {"expired"}:
        return "repo_breadcrumb"
    return "joined_route_note"


def _lifecycle_status(counts: Counter[str], last_signal: str) -> str:
    negative = any(counts.get(signal) for signal in HARD_NEGATIVE_SUPPRESSION_SIGNALS)
    parked = any(counts.get(signal) for signal in PARKED_SUPPRESSION_SIGNALS)
    expired = bool(counts.get("expired"))
    if last_signal in POSITIVE_SUPPRESSION_SIGNALS:
        return "overridden_by_positive_source_open"
    if last_signal in HARD_NEGATIVE_SUPPRESSION_SIGNALS or negative:
        return "suppressed_hard_negative"
    if last_signal in PARKED_SUPPRESSION_SIGNALS or parked:
        return "parked_recheck"
    if last_signal == "expired" or expired:
        return "expired_recheck"
    return "neutral"


def suppression_lifecycle_report(
    events: Iterable[Mapping[str, Any]],
    *,
    detail: str = "compact",
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    invalid_signal_counts: Counter[str] = Counter()
    invalid_signal_samples: list[dict[str, str]] = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping) or event.get("kind") not in {
            "aippocampus_active_flow_event",
            "aippocampus_recall_feedback_event",
        }:
            continue
        if event.get("kind") == "aippocampus_active_flow_event":
            route_id = _safe_token(event.get("route_id"), fallback_prefix="route")
            signal = _safe_signal(event.get("signal"))
        else:
            route_id = _safe_token(event.get("candidate_id"), fallback_prefix="candidate")
            signal = _safe_signal(event.get("outcome"))
        if not signal:
            sample = _invalid_signal_sample(event, route_id)
            invalid_signal_counts[sample["signal"]] += 1
            if len(invalid_signal_samples) < 8:
                invalid_signal_samples.append(sample)
            continue
        row = grouped.setdefault(
            route_id,
            {
                "route_id": route_id,
                "signal_counts": Counter(),
                "activation_score": 0.0,
                "last_index": -1,
                "last_signal": "",
            },
        )
        row["signal_counts"][signal] += 1
        row["activation_score"] += _safe_float(
            event.get("weight_delta"),
            DEFAULT_SIGNAL_DELTAS[signal],
        )
        row["last_index"] = index
        row["last_signal"] = signal

    routes: list[dict[str, Any]] = []
    for row in grouped.values():
        counts: Counter[str] = row["signal_counts"]
        last_signal = str(row["last_signal"])
        score = round(float(row["activation_score"]), 6)
        status = _lifecycle_status(counts, last_signal)
        is_foreground_eligible = foreground_eligible(counts, last_signal, score)
        routes.append(
            {
                "route_id": row["route_id"],
                "status": status,
                "foreground_eligible": is_foreground_eligible,
                "activation_score": score,
                "reason_codes": route_reason_codes(counts, score),
                "signal_counts": dict(sorted(counts.items())),
                "claim_boundary": "feedback_suppression_is_navigation_calibration_not_source_truth",
            }
        )
    routes.sort(key=lambda item: (str(item["status"]), str(item["route_id"])))
    status_counts = Counter(str(row["status"]) for row in routes)
    foreground_ineligible_count = sum(1 for row in routes if not row.get("foreground_eligible"))
    if detail in {"detail", "full", "operator"}:
        return {
            "kind": "aippocampus_feedback_suppression_lifecycle",
            "schema_version": 1,
            "detail": detail,
            "route_count": len(routes),
            "routes": routes,
            "status_counts": dict(sorted(status_counts.items())),
            "hard_negative_count": status_counts.get("suppressed_hard_negative", 0),
            "overridden_by_positive_count": status_counts.get("overridden_by_positive_source_open", 0),
            "foreground_ineligible_count": foreground_ineligible_count,
            "invalid_signal_count": sum(invalid_signal_counts.values()),
            "invalid_signal_samples": invalid_signal_samples,
            "policy_boundary": {
                "suppression_is_route_local": True,
                "suppression_is_reversible": True,
                "feedback_is_not_source_truth": True,
            },
        }
    return {
        "kind": "aippocampus_feedback_suppression_lifecycle",
        "schema_version": 1,
        "detail": "compact",
        "status": (
            "has_suppression"
            if status_counts.get("suppressed_hard_negative") or foreground_ineligible_count
            else "clear"
        ),
        "hard_negative_count": status_counts.get("suppressed_hard_negative", 0),
        "overridden_by_positive_count": status_counts.get("overridden_by_positive_source_open", 0),
        "foreground_ineligible_count": foreground_ineligible_count,
        "invalid_signal_count": sum(invalid_signal_counts.values()),
        "claim_boundary": "feedback_suppression_is_navigation_calibration_not_source_truth",
    }
