#!/usr/bin/env python3
"""Shared confidence thresholds for semantic recall decisions."""

from __future__ import annotations

MEMORY_CUE_CONFIDENCE = 0.35
BACKGROUND_WARM_CACHE_CONFIDENCE = 0.55
ACTIVE_CUE_CONFIDENCE = 0.55
EVIDENCE_DOWNGRADE_CONFIDENCE = 0.6
SOURCE_REOPEN_CONFIDENCE = 0.82


def meets_memory_cue_confidence(value: float) -> bool:
    return value >= MEMORY_CUE_CONFIDENCE


def meets_background_warm_cache_confidence(value: float) -> bool:
    return value >= BACKGROUND_WARM_CACHE_CONFIDENCE


def meets_active_cue_confidence(value: float) -> bool:
    return value >= ACTIVE_CUE_CONFIDENCE


def meets_source_reopen_confidence(value: float) -> bool:
    return value >= SOURCE_REOPEN_CONFIDENCE
