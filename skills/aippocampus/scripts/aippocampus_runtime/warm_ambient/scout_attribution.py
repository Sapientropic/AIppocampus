#!/usr/bin/env python3
"""Public-safe scout attribution helpers for warm ambient recall cards."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.registry.api import unique_preserve


def _origin_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def with_scout_origin(card: dict[str, Any], *, row: dict[str, Any]) -> dict[str, Any]:
    lane = str(row.get("scout") or "").strip()
    family = str(row.get("scout_family") or "").strip()
    variant = str(row.get("scout_variant") or "").strip()
    if not lane:
        return card
    card["source_scout"] = lane
    card["source_scouts"] = unique_preserve([*_origin_values(card.get("source_scouts")), lane], limit=8)
    if family:
        card["source_scout_family"] = family
        card["source_scout_families"] = unique_preserve(
            [*_origin_values(card.get("source_scout_families")), family], limit=8
        )
    if variant:
        card["source_scout_variant"] = variant
        card["source_scout_variants"] = unique_preserve(
            [*_origin_values(card.get("source_scout_variants")), variant], limit=8
        )
    return card


def merge_scout_origins(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for field in ("source_scouts", "source_scout_families", "source_scout_variants"):
        existing[field] = unique_preserve(
            [*_origin_values(existing.get(field)), *_origin_values(incoming.get(field))],
            limit=8,
        )
    for field in ("source_scout", "source_scout_family", "source_scout_variant"):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]
