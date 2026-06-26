"""Weak-recall recovery layer orchestration.

These layers are navigation aids, not source truth. Keep the main recall path
as an orchestrator: new weak-recall fallbacks should be added here or in a
single owner helper, then verified by recall -> deepen/open source follow-through.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import associative_path_fallback as apw_fallback
from aippocampus_runtime.recall import background_recovery


def weak_recall_recovery_layers(
    *,
    query: str,
    cwd: Path,
    clean_source_dir: Path,
    registry_dir: Path,
    project: str,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
    include_associative_fallback: bool,
    associative_path_sidecar_dir: str | Path | None,
    associative_path_bridge_path: str | Path | None,
    associative_path_navigation_path: str | Path | None,
    associative_path_active_lock_path: str | Path | None,
    associative_path_feedback_path: str | Path | None,
    feedback_path: str | Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any] | None]:
    """Return background recovery plus APW policy for a weak ordinary recall."""

    background_recovery_card = background_recovery.background_recovery_for_weak_recall(
        query=query,
        registry_dir=registry_dir,
        project=project,
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    )
    associative_path_policy, associative_path_fallback = (
        apw_fallback.maybe_append_associative_path_fallback_with_policy(
            include_associative_fallback=include_associative_fallback,
            query=query,
            ordinary_status="ok" if memory_packets else "no_routes",
            memory_packets=memory_packets,
            deepen_requests=deepen_requests,
            triage_metrics=triage_metrics,
            cwd=cwd,
            sidecar_dir=associative_path_sidecar_dir,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            semantic_bridge_path=associative_path_bridge_path,
            navigation_path=associative_path_navigation_path,
            active_lock_path=associative_path_active_lock_path,
            feedback_path=associative_path_feedback_path or feedback_path,
        )
    )
    return background_recovery_card, associative_path_policy, associative_path_fallback
