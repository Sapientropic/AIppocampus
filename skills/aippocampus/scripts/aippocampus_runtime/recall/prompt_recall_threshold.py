#!/usr/bin/env python3
"""Context-aware scent-threshold policy for prompt-time recall.

This module only changes routing sensitivity for `scent`. It must not upgrade
old memory into evidence, and clean-source reopen remains the evidence
boundary. Same-user personal continuity is allowed to participate in routing;
hard privacy boundaries are reserved for secrets, unsafe exposure, and current
source/current-checkout facts.
"""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.recall.prompt_cues import (
    current_checkout_live_fact_intent,
    is_decision_continuation,
    prompt_is_secret_surface,
)
from aippocampus_runtime.recall.prompt_recall_policy import PROMPT_RECALL_GATE_POLICY

SAME_THREAD_CONTINUATION_DELTA = -1.0
SEMANTIC_REUSE_DELTA = -0.25
TOPIC_SIGNAL_EASING_DELTA = -0.75
TOPIC_SIGNAL_NEGATIVE_DELTA = 0.75
ACTIVE_LOCK_ROI_REINFORCE_DELTA = -0.25
ACTIVE_LOCK_ROI_SUPPRESS_DELTA = 0.5
MIN_SCENT_THRESHOLD = 3.5
MAX_SCENT_THRESHOLD_DELTA = 1.0

# Same-user continuity cues: these can shape routing and topic-signal reuse, but
# they must not become evidence for personal claims without clean-source reopen.
_BROAD_PERSONAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(压力|焦虑|难受|崩溃|害怕|孤独|家人|妈妈|爸爸|伴侣|礼物)",
        r"\b(stress|anxiety|anxious|overwhelmed|lonely|family|mom|dad|partner|gift)\b",
    ]
]


def broad_fresh_personal_prompt(prompt: str) -> bool:
    text = str(prompt or "").strip()
    return bool(text and any(pattern.search(text) for pattern in _BROAD_PERSONAL_PATTERNS))


def _adjustment(reason: str, delta: float) -> dict[str, Any]:
    return {"reason": reason, "delta": round(float(delta), 3)}


def scent_threshold_policy(
    *,
    prompt: str,
    thread_id: str | None = None,
    topic_epoch: str | None = None,
    semantic_gate_reuse: dict[str, Any] | None = None,
    topic_signal_state: dict[str, Any] | None = None,
    route_roi_summary: dict[str, Any] | None = None,
    explicit_recall_intent: bool = False,
    current_checkout_live_fact: bool | None = None,
    base_threshold: float = PROMPT_RECALL_GATE_POLICY.scent_threshold,
) -> dict[str, Any]:
    """Return a public-safe effective scent threshold and reason codes."""

    base = float(base_threshold)
    effective = base
    adjustments: list[dict[str, Any]] = []
    risk_boundary = "normal"
    live_fact = (
        current_checkout_live_fact_intent(prompt)
        if current_checkout_live_fact is None
        else bool(current_checkout_live_fact)
    )
    fresh_thread = not bool(str(thread_id or "").strip())
    if live_fact:
        risk_boundary = "current_repo_fact"
    elif prompt_is_secret_surface(prompt):
        risk_boundary = "privacy_sensitive"
    elif fresh_thread and broad_fresh_personal_prompt(prompt):
        risk_boundary = "personal_continuity"

    if risk_boundary in {"normal", "personal_continuity"}:
        if thread_id and topic_epoch and is_decision_continuation(prompt):
            effective += SAME_THREAD_CONTINUATION_DELTA
            adjustments.append(
                _adjustment("same_thread_decision_continuation", SAME_THREAD_CONTINUATION_DELTA)
            )
        reuse_source = str((semantic_gate_reuse or {}).get("source") or "")
        if reuse_source in {"exact_semantic_cache", "semantic_cue_cache"}:
            effective += SEMANTIC_REUSE_DELTA
            adjustments.append(_adjustment("semantic_reuse_hit", SEMANTIC_REUSE_DELTA))
        signal = topic_signal_state or {}
        weak_count = int(signal.get("weak_signal_count") or 0)
        positive_strength = float(signal.get("positive_strength") or 0.0)
        negative_strength = float(signal.get("negative_strength") or 0.0)
        if weak_count >= 3 and positive_strength >= 3.0:
            effective += TOPIC_SIGNAL_EASING_DELTA
            adjustments.append(
                _adjustment("topic_signal_accumulator_eased", TOPIC_SIGNAL_EASING_DELTA)
            )
        if not explicit_recall_intent and negative_strength >= 3.0:
            effective += TOPIC_SIGNAL_NEGATIVE_DELTA
            adjustments.append(
                _adjustment("topic_signal_negative_roi_suppressed", TOPIC_SIGNAL_NEGATIVE_DELTA)
            )
        roi = route_roi_summary or {}
        source_hits = int(roi.get("source_backed_hit_count") or 0)
        wrong_routes = int(roi.get("wrong_or_stale_route_count") or 0)
        if source_hits > wrong_routes and source_hits >= 2:
            effective += ACTIVE_LOCK_ROI_REINFORCE_DELTA
            adjustments.append(
                _adjustment("active_lock_roi_reinforced", ACTIVE_LOCK_ROI_REINFORCE_DELTA)
            )
        if not explicit_recall_intent and wrong_routes >= 3 and wrong_routes > source_hits:
            effective += ACTIVE_LOCK_ROI_SUPPRESS_DELTA
            adjustments.append(
                _adjustment("active_lock_roi_suppressed", ACTIVE_LOCK_ROI_SUPPRESS_DELTA)
            )

    effective = max(MIN_SCENT_THRESHOLD, min(base + MAX_SCENT_THRESHOLD_DELTA, effective))
    return {
        "base_threshold": round(base, 3),
        "effective_threshold": round(effective, 3),
        "adjustments": adjustments,
        "risk_boundary": risk_boundary,
        "topic_signal_accumulator": {
            "status": str((topic_signal_state or {}).get("status") or "not_used"),
            "weak_signal_count": int((topic_signal_state or {}).get("weak_signal_count") or 0),
            "positive_strength": round(
                float((topic_signal_state or {}).get("positive_strength") or 0.0), 3
            ),
            "negative_strength": round(
                float((topic_signal_state or {}).get("negative_strength") or 0.0), 3
            ),
            "topic_fingerprint": str((topic_signal_state or {}).get("topic_fingerprint") or ""),
        },
        "route_roi_summary": {
            "source_backed_hit_count": int((route_roi_summary or {}).get("source_backed_hit_count") or 0),
            "wrong_or_stale_route_count": int(
                (route_roi_summary or {}).get("wrong_or_stale_route_count") or 0
            ),
        },
    }
