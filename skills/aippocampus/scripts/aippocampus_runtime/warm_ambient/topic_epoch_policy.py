#!/usr/bin/env python3
"""Warm ambient topic-epoch write policy."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.warm_ambient.diagnostics import guard_coverage_incomplete

SOURCE_ADDRESSABLE_SUPPORT_LEVELS = {"evidence", "candidate"}
SOURCE_VALIDATION_DROP_STATUSES = {"missing_source_ref", "unsupported"}


def _source_addressable_card_count(cards: list[dict[str, Any]]) -> int:
    count = 0
    for card in cards:
        if not isinstance(card, dict):
            continue
        refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            continue
        raw_validation = card.get("source_validation")
        validation = raw_validation if isinstance(raw_validation, dict) else {}
        status = str(validation.get("status") or "").strip().casefold()
        if status in SOURCE_VALIDATION_DROP_STATUSES:
            continue
        support = str(card.get("support_level") or "").strip().casefold()
        if support in SOURCE_ADDRESSABLE_SUPPORT_LEVELS:
            count += 1
    return count


def apply_topic_epoch_write_policy(
    decision: dict[str, Any],
    *,
    cards: list[dict[str, Any]],
    useful_signal_quorum_met: bool,
    guard_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Convert topic-epoch votes into cache write policy after local evidence checks.

    A scout-level `suppress` vote means "do not blindly reuse the previous topic
    epoch"; it is not a privacy gate by itself. Once local validation has kept
    source-addressable cards and quorum is met, rotating the epoch preserves the
    stale-topic protection without discarding useful source handles.
    """

    action = str(decision.get("action") or "").strip().casefold()
    clean = dict(decision)
    source_addressable_count = _source_addressable_card_count(cards)
    clean["source_addressable_card_count"] = source_addressable_count
    if action != "suppress":
        clean.setdefault("write_policy", "allow")
        return clean
    if source_addressable_count and useful_signal_quorum_met and not guard_coverage_incomplete(guard_coverage):
        clean["requested_action"] = action
        clean["action"] = "rotate"
        clean["suppress_write"] = False
        clean["write_policy"] = "rotate_epoch"
        clean["reason"] = compact_text(
            "; ".join(
                part
                for part in (
                    str(decision.get("reason") or "").strip(),
                    "source-addressable cards prefer epoch rotation over write suppression",
                )
                if part
            ),
            220,
        )
    else:
        clean["write_policy"] = "withhold_cache"
    return clean
