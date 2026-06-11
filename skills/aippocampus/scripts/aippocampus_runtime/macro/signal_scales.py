"""Shared macro signal-scale vocabulary.

Macro signals often arrive from adjacent agent/runtime surfaces, so callers use
friendly words like ``project`` while the state ledger wants canonical labels.
Keep that normalization in one place: scale controls project-level fanout and
stage movement, but never upgrades macro packets into evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeAlias

SignalScale: TypeAlias = Literal[
    "project_event",
    "continuity_domain",
    "journey",
    "thread",
    "unknown",
]

CANONICAL_SIGNAL_SCALES: tuple[SignalScale, ...] = (
    "project_event",
    "continuity_domain",
    "journey",
    "thread",
    "unknown",
)
SIGNAL_SCALE_ALIASES: dict[str, SignalScale] = {
    "project": "project_event",
    "project-level": "project_event",
    "project_level": "project_event",
    "project-scoped": "project_event",
    "project_scoped": "project_event",
    "domain": "continuity_domain",
    "continuity": "continuity_domain",
    "continuity-domain": "continuity_domain",
    "conversation": "thread",
}
PROJECT_LEVEL_SIGNAL_SCALES = frozenset({"project_event"})
PROMOTABLE_SIGNAL_SCALES = frozenset({"continuity_domain", "journey", "thread"})
DIAGNOSTIC_ONLY_SIGNAL_SCALES = frozenset({"unknown"})


def public_signal_scale_schema() -> dict[str, object]:
    return {
        "canonical_values": list(CANONICAL_SIGNAL_SCALES),
        "aliases": dict(SIGNAL_SCALE_ALIASES),
        "project_level_without_promotion": sorted(PROJECT_LEVEL_SIGNAL_SCALES),
        "requires_project_promotion": sorted(PROMOTABLE_SIGNAL_SCALES),
        "diagnostic_only": sorted(DIAGNOSTIC_ONLY_SIGNAL_SCALES),
        "promotion_boundary": (
            "continuity_domain, journey, and thread can affect project-level macro "
            "state only after explicit promotion; unknown remains diagnostic-only."
        ),
    }


def normalize_signal_scale(value: str | None) -> SignalScale:
    raw = str(value or "").strip().replace(" ", "_").casefold()
    normalized = SIGNAL_SCALE_ALIASES.get(raw, raw)
    if normalized in CANONICAL_SIGNAL_SCALES:
        return normalized
    allowed = ", ".join(CANONICAL_SIGNAL_SCALES)
    aliases = ", ".join(sorted(SIGNAL_SCALE_ALIASES))
    raise ValueError(
        "unsupported macro signal scale "
        f"{value!r}; canonical values: {allowed}; accepted aliases: {aliases}"
    )


def normalize_signal_scales(values: object) -> tuple[SignalScale, ...]:
    if isinstance(values, str) or not isinstance(values, Iterable):
        raise ValueError("macro signal scales must be an iterable of strings")
    scales: list[SignalScale] = []
    seen: set[SignalScale] = set()
    for value in values:
        scale = normalize_signal_scale(str(value))
        if scale in seen:
            continue
        seen.add(scale)
        scales.append(scale)
    if not scales:
        raise ValueError("macro signal scales must name at least one scale")
    return tuple(scales)


def can_promote_to_project(signal_scale: str | None) -> bool:
    return normalize_signal_scale(signal_scale) in PROMOTABLE_SIGNAL_SCALES


def requires_project_promotion(signal_scale: str | None) -> bool:
    scale = normalize_signal_scale(signal_scale)
    return scale in PROMOTABLE_SIGNAL_SCALES or scale in DIAGNOSTIC_ONLY_SIGNAL_SCALES


def is_project_level_signal(
    signal_scale: str | None,
    *,
    promoted_to_project: bool = False,
) -> bool:
    scale = normalize_signal_scale(signal_scale)
    if scale in PROJECT_LEVEL_SIGNAL_SCALES:
        return True
    return bool(promoted_to_project and scale in PROMOTABLE_SIGNAL_SCALES)


def project_level_signal_in(
    scales: tuple[SignalScale, ...],
    *,
    promoted_to_project: bool = False,
) -> bool:
    return any(
        is_project_level_signal(scale, promoted_to_project=promoted_to_project)
        for scale in scales
    )


def first_non_project_scale(scales: tuple[SignalScale, ...]) -> SignalScale | None:
    for scale in scales:
        if scale not in PROJECT_LEVEL_SIGNAL_SCALES:
            return scale
    return None


def signal_scale_diagnostic(
    signal_scale: str | None,
    *,
    promoted_to_project: bool = False,
) -> str | None:
    scale = normalize_signal_scale(signal_scale)
    if scale in PROJECT_LEVEL_SIGNAL_SCALES:
        return None
    if scale in DIAGNOSTIC_ONLY_SIGNAL_SCALES:
        return "unknown_signal_scale_diagnostic_only"
    if promoted_to_project:
        return None
    return f"{scale}_signal_ignored_without_project_promotion"


__all__ = [
    "CANONICAL_SIGNAL_SCALES",
    "DIAGNOSTIC_ONLY_SIGNAL_SCALES",
    "PROJECT_LEVEL_SIGNAL_SCALES",
    "PROMOTABLE_SIGNAL_SCALES",
    "SIGNAL_SCALE_ALIASES",
    "SignalScale",
    "can_promote_to_project",
    "first_non_project_scale",
    "is_project_level_signal",
    "normalize_signal_scale",
    "normalize_signal_scales",
    "project_level_signal_in",
    "public_signal_scale_schema",
    "requires_project_promotion",
    "signal_scale_diagnostic",
]
