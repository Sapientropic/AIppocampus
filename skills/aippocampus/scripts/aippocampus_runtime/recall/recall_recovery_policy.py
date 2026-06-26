"""Shared weak-recall recovery policy for foreground recall helpers.

APW, reviewed background findings, and future lightweight recovery lanes should
agree on when ordinary recall is weak enough to need help. Keeping the cheap
predicate here prevents the recurring agent bug where one lane is fixed while
another still treats a generic route as good enough.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def ordinary_recall_needs_recovery(
    *,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
) -> bool:
    """Return whether recall should surface a recovery lane before broad search."""

    specificity_floor = float(triage_metrics.get("route_label_specificity_floor") or 0.0)
    return (
        not memory_packets
        or not deepen_requests
        # A single route can look "distinctive" only because there is nothing
        # else to compare it against. Treat labels below 0.5 as weak so recovery
        # lanes can offer narrower navigation without changing ordinary ranking.
        or specificity_floor < 0.5
        or float(triage_metrics.get("packet_triage_distinctiveness") or 0.0) < 0.5
    )


__all__ = ["ordinary_recall_needs_recovery"]
