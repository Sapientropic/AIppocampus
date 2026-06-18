"""Filtering for host-control envelopes before clean-source projection."""

from __future__ import annotations

import re

_HOST_INTERNAL_BLOCK_PATTERNS = (
    re.compile(r"(?is)<codex_internal_context\b[^>]*>.*?</codex_internal_context>"),
    re.compile(r"(?is)<subagent_notification\b[^>]*>.*?</subagent_notification>"),
)
_HOST_INTERNAL_MARKERS = (
    "codex_internal_context",
    "<subagent_notification",
    "subagent_notification",
)


def contains_host_internal_material(text: str) -> bool:
    original = str(text or "")
    lowered_original = original.lstrip().casefold()
    if any(lowered_original.startswith(marker) for marker in _HOST_INTERNAL_MARKERS):
        return True
    if any(marker in original.casefold() for marker in _HOST_INTERNAL_MARKERS):
        return True
    return any(pattern.search(original) for pattern in _HOST_INTERNAL_BLOCK_PATTERNS)


def filter_host_internal_clean_text(text: str) -> tuple[str, bool]:
    """Remove host-control envelopes before text enters ordinary clean source.

    Clean source is the default source-court surface for later agents. Host
    continuation wrappers and subagent notifications are useful audit material,
    but treating them as normal user/final conversation text lets foreground
    recall cite host machinery as if it were human continuity. Keep visible
    text around stripped wrapper blocks; drop wrapper-only messages.
    """

    original = str(text or "")
    cleaned = original
    removed = False
    for pattern in _HOST_INTERNAL_BLOCK_PATTERNS:
        cleaned, count = pattern.subn("", cleaned)
        removed = removed or bool(count)
    stripped = cleaned.strip()
    lowered_original = original.lstrip().casefold()
    if any(lowered_original.startswith(marker) for marker in _HOST_INTERNAL_MARKERS):
        return "", True
    if not stripped and any(marker in original.casefold() for marker in _HOST_INTERNAL_MARKERS):
        return "", True
    return stripped if removed else original, removed
