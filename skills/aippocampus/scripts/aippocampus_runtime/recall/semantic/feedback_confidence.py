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


def feedback_aware_recall_cue_confidence(row: Mapping[str, Any]) -> float:
    """Estimate learned recall-cue confidence from source-open and feedback history."""

    source_open_success_count = int(row.get("source_open_success_count") or 0)
    if source_open_success_count <= 0:
        return round(float(row.get("confidence") or 0.0), 4)
    false_positive_count = int(row.get("false_positive_count") or 0)
    explicit_useful_count = int(row.get("explicit_useful_feedback_count") or 0)
    base = float(row.get("source_open_confidence_basis") or SOURCE_REOPEN_CONFIDENCE)
    confidence = (
        base
        + max(0, source_open_success_count - 1) * RECALL_CUE_SUCCESS_CONFIDENCE_BONUS
        + explicit_useful_count * RECALL_CUE_EXPLICIT_USEFUL_CONFIDENCE_BONUS
        - false_positive_count * RECALL_CUE_FALSE_POSITIVE_CONFIDENCE_PENALTY
    )
    return round(max(0.0, min(0.99, confidence)), 4)
