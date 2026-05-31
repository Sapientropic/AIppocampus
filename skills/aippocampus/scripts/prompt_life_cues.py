#!/usr/bin/env python3
"""Compatibility shim for aippocampus_runtime.recall.life_cues."""

from __future__ import annotations

from aippocampus_runtime.recall.life_cues import (
    LIFE_WIDE_SCOPE_LABEL_CUES,
    PROFILE_RECALL_ALIASES,
    PROFILE_RECALL_PATTERNS,
    profile_recall_terms,
    unique_preserve,
)

__all__ = [
    "LIFE_WIDE_SCOPE_LABEL_CUES",
    "PROFILE_RECALL_ALIASES",
    "PROFILE_RECALL_PATTERNS",
    "profile_recall_terms",
    "unique_preserve",
]
