"""Reviewed-background recovery selection for ordinary recall."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import background_findings, recall_recovery_policy

BACKGROUND_ROUTE_TOKEN_RE = re.compile(r"\b(?:wm|sf)_[A-Za-z0-9]{8,}\b")


def contains_background_route_token(query: str) -> bool:
    return bool(BACKGROUND_ROUTE_TOKEN_RE.search(str(query or "")))


def background_recovery_for_weak_recall(
    *,
    query: str,
    registry_dir: Path,
    project: str,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return a reviewed background card only when weak recall needs recovery."""

    if not str(query or "").strip():
        return None
    if contains_background_route_token(query):
        # Background recovery is a first-hop scent. Once a foreground action has
        # injected a reviewed finding/source-finding id into the cue, repeat
        # recovery would append the same ids again and hide the direct
        # recall->deepen route in another background action.
        return None
    if not recall_recovery_policy.ordinary_recall_needs_recovery(
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    ):
        return None
    card = background_findings.background_findings_card(
        query,
        registry_dir=registry_dir,
        project=project,
        limit=2,
        detail="compact",
        prefer_reopenable=True,
    )
    if card.get("status") != "ok" or not isinstance(card.get("foreground_action"), Mapping):
        return None
    best = card.get("best_finding")
    best_map = best if isinstance(best, Mapping) else {}
    source_link_count = int(best_map.get("source_finding_count") or 0) + int(
        best_map.get("source_ref_count") or 0
    )
    if source_link_count <= 0:
        return None
    return card
