#!/usr/bin/env python3
"""Context-aware scent-threshold policy for prompt-time recall.

This module only changes routing sensitivity for `scent`. It must not upgrade
old memory into evidence or turn broad sensitive prompts into personalized
recall; clean-source reopen remains the evidence boundary.
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
MIN_SCENT_THRESHOLD = 3.5

# Safety-only blockers: these phrases can prevent threshold lowering, but they
# must not become recall activation cues or evidence for any personal claim.
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
    elif prompt_is_secret_surface(prompt) or (fresh_thread and broad_fresh_personal_prompt(prompt)):
        risk_boundary = "privacy_sensitive"

    if risk_boundary == "normal":
        if thread_id and topic_epoch and is_decision_continuation(prompt):
            effective += SAME_THREAD_CONTINUATION_DELTA
            adjustments.append(
                _adjustment("same_thread_decision_continuation", SAME_THREAD_CONTINUATION_DELTA)
            )
        reuse_source = str((semantic_gate_reuse or {}).get("source") or "")
        if reuse_source in {"exact_semantic_cache", "semantic_cue_cache"}:
            effective += SEMANTIC_REUSE_DELTA
            adjustments.append(_adjustment("semantic_reuse_hit", SEMANTIC_REUSE_DELTA))

    effective = max(MIN_SCENT_THRESHOLD, min(base, effective))
    return {
        "base_threshold": round(base, 3),
        "effective_threshold": round(effective, 3),
        "adjustments": adjustments,
        "risk_boundary": risk_boundary,
    }
