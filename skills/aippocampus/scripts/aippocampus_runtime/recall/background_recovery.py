"""Reviewed-background recovery selection for ordinary recall."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import background_findings, recall_recovery_policy


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
