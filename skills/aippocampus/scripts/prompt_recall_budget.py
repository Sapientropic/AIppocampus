#!/usr/bin/env python3
"""Foreground prompt-recall budget helpers."""

from __future__ import annotations

import time
from typing import Any

POST_SEMANTIC_RESERVE_MS = 1200.0
SEMANTIC_MIN_TIMEOUT_SECONDS = 0.5
PROBE_MIN_REMAINING_MS = 700.0
EVIDENCE_MIN_REMAINING_MS = 900.0


def remaining_ms(start: float, max_elapsed_ms: int | None) -> float | None:
    if not max_elapsed_ms or max_elapsed_ms <= 0:
        return None
    return max(0.0, float(max_elapsed_ms) - ((time.perf_counter() - start) * 1000.0))


def budget_allows(start: float, max_elapsed_ms: int | None, min_remaining_ms: float) -> bool:
    remaining = remaining_ms(start, max_elapsed_ms)
    return remaining is None or remaining >= min_remaining_ms


def semantic_timeout_for_budget(
    start: float,
    max_elapsed_ms: int | None,
    requested_timeout: float,
) -> float | None:
    if requested_timeout <= 0:
        return None
    remaining = remaining_ms(start, max_elapsed_ms)
    if remaining is None:
        return requested_timeout
    available = remaining - POST_SEMANTIC_RESERVE_MS
    if available < SEMANTIC_MIN_TIMEOUT_SECONDS * 1000.0:
        return None
    return min(requested_timeout, max(SEMANTIC_MIN_TIMEOUT_SECONDS, available / 1000.0))


def semantic_budget_result(
    reason: str,
    *,
    requested_timeout: float | None = None,
    effective_timeout: float | None = None,
    max_elapsed_ms: int | None = None,
) -> dict[str, Any]:
    budget_clipped = (
        requested_timeout is not None
        and (effective_timeout is None or float(effective_timeout) != float(requested_timeout))
    )
    return {
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "query_aliases": [],
        "memory_scope": [],
        "reasons": [reason],
        "errors": [reason],
        "budget": {
            "requested_timeout": requested_timeout,
            "effective_timeout": effective_timeout,
            "max_elapsed_ms": max_elapsed_ms,
            "budget_clipped": budget_clipped,
        },
    }
