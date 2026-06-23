"""Internal APW foreground-action gates.

These checks decide whether a recovered APW route may become the compact
foreground action. Proof payloads stay in recall/detail data; MCP compact
callers should consume only the boolean product decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def card_allows_primary_source_action(card: Mapping[str, Any] | None) -> bool:
    """Return whether an APW card can safely become the foreground action."""

    if not isinstance(card, Mapping):
        return False
    if str(card.get("candidate_source_kind") or "") != "current_clean_source":
        return True
    gate = card.get("source_anchor_gate")
    if not isinstance(gate, Mapping):
        return False
    return str(gate.get("status") or "") != "blocked" and gate.get("target_source_matched") is not False


__all__ = ["card_allows_primary_source_action"]
