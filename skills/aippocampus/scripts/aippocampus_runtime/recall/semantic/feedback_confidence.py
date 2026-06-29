#!/usr/bin/env python3
"""Feedback-aware confidence for learned recall cues.

The value computed here is foreground navigation eligibility, not source
authority. Learned cues still require source reopen before claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.recall.semantic.confidence_policy import SOURCE_REOPEN_CONFIDENCE

RECALL_CUE_SUCCESS_CONFIDENCE_BONUS = 0.01
RECALL_CUE_EXPLICIT_USEFUL_CONFIDENCE_BONUS = 0.05
RECALL_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY = 0.16
SEMANTIC_CUE_HIT_CONFIDENCE_BONUS = 0.005
SEMANTIC_CUE_CONFIDENCE_CEILING = SOURCE_REOPEN_CONFIDENCE
SEMANTIC_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY = RECALL_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY


def feedback_aware_recall_cue_confidence(row: Mapping[str, Any]) -> float:
    """Estimate learned recall-cue confidence from positive and negative history.

    Generic semantic hits are navigation aliases, not stronger evidence than a
    source reopen. They keep an immutable confidence basis so each status refresh
    does not repeatedly penalize the already-decayed visible confidence.
    """

    source_open_success_count = int(row.get("source_open_success_count") or 0)
    hit_count = int(row.get("hit_count") or 0)
    false_positive_count = int(row.get("false_positive_count") or 0)
    explicit_useful_count = int(row.get("explicit_useful_feedback_count") or 0)
    if source_open_success_count > 0:
        base = float(row.get("source_open_confidence_basis") or SOURCE_REOPEN_CONFIDENCE)
        success_bonus = max(0, source_open_success_count - 1) * RECALL_CUE_SUCCESS_CONFIDENCE_BONUS
        false_positive_penalty = false_positive_count * RECALL_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY
    else:
        raw_base = float(row.get("semantic_hit_confidence_basis") or row.get("confidence") or 0.0)
        base = min(raw_base, SEMANTIC_CUE_CONFIDENCE_CEILING)
        success_bonus = max(0, hit_count - 1) * SEMANTIC_CUE_HIT_CONFIDENCE_BONUS
        false_positive_penalty = false_positive_count * SEMANTIC_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY
    confidence = base + success_bonus + explicit_useful_count * RECALL_CUE_EXPLICIT_USEFUL_CONFIDENCE_BONUS
    confidence -= false_positive_penalty
    return round(max(0.0, min(0.99, confidence)), 4)
