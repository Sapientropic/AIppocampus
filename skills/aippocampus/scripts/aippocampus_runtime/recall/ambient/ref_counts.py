"""Reference-count helpers for ambient recall cards."""

from __future__ import annotations

from typing import Any


def reopenable_ref_count(card: dict[str, Any]) -> int:
    refs = len([ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)])
    if refs:
        return refs
    for key in ("source_ref_count", "candidate_ref_count"):
        try:
            count = int(card.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            return count
    return 0
