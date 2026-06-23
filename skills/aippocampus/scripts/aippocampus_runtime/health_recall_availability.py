"""Cheap recall-readiness helpers for health foreground cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.first_recall_readiness import health_readiness_fields
from aippocampus_runtime.source.io_kernel import load_json_dict


def registry_recall_availability(registry_path: Path) -> dict[str, Any]:
    """Return a cheap, redacted signal for whether ordinary recall can start.

    Health is a maintenance diagnostic, not the recall router. It must not run
    expensive broad recall just to decide a foreground card. A non-empty
    registry is enough to say read-only continuity recall is available as a
    first action, while workspace-local clean-source/index gaps remain visible
    as maintenance needed before exact latest/current-thread claims.
    """

    payload = load_json_dict(registry_path).data
    raw_threads = payload.get("threads")
    threads = [item for item in raw_threads if isinstance(item, Mapping)] if isinstance(raw_threads, list) else []
    with_clean_source = 0
    for entry in threads:
        paths = entry.get("paths")
        if isinstance(paths, Mapping) and (
            paths.get("clean_source_messages_jsonl")
            or paths.get("clean_source_dir")
            or paths.get("messages_jsonl")
        ):
            with_clean_source += 1
    return {
        "available": bool(threads),
        "source": "registry_threads" if threads else "none",
        "thread_count": len(threads),
        "thread_with_source_ref_count": with_clean_source,
        "registry_present": registry_path.exists(),
        "claim_boundary": "registry availability is a read-only recall signal, not source evidence",
    }


def operator_detail_placeholder(*, pressure: bool = False, include_command: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "available": False,
        "reason": "operator_detail_only",
    }
    if pressure:
        payload["pressure"] = False
    if include_command:
        payload["detail_command"] = "aippocampus health --detail full --json"
    return payload


def first_recall_maintenance_state(
    *,
    actions: Sequence[Mapping[str, Any]],
    registry_recall: Mapping[str, Any],
    clean_source_message_count: int,
    critical_action_count: int,
) -> dict[str, Any]:
    workspace_source_maintenance_required = any(
        item.get("id") in {"build_index", "build_clean_source", "build_segments"}
        for item in actions
    )
    continuity_recall_available = bool(registry_recall.get("available")) or bool(
        clean_source_message_count
    )
    maintenance_required_before_recall = bool(
        critical_action_count > 0 and not continuity_recall_available
    )
    return {
        "workspace_source_maintenance_required": workspace_source_maintenance_required,
        "continuity_recall_available": continuity_recall_available,
        "continuity_recall_unavailable": not continuity_recall_available,
        "maintenance_required_before_recall": maintenance_required_before_recall,
        "ordinary_first_recall_usable": not maintenance_required_before_recall,
        "registry_recall_available": bool(registry_recall.get("available")),
        "recall_availability_source": registry_recall.get("source"),
    }


def build_product_readiness(
    *,
    actions: Sequence[Mapping[str, Any]],
    registry_recall: Mapping[str, Any],
    clean_source_message_count: int,
    critical_action_count: int,
    high_severity_action_count: int,
    live_delta_tolerated: bool,
    freshness_degraded: bool,
    storage_pressure_cleanup_recommended: bool,
    checkpoint_due: bool,
) -> dict[str, Any]:
    first_recall_state = first_recall_maintenance_state(
        actions=actions,
        registry_recall=registry_recall,
        clean_source_message_count=clean_source_message_count,
        critical_action_count=critical_action_count,
    )
    maintenance_required = bool(first_recall_state["maintenance_required_before_recall"])
    maintenance_recommended = bool(actions)
    status = (
        "needs_maintenance"
        if maintenance_required
        else "ready_with_live_delta"
        if live_delta_tolerated
        else "ready_with_freshness_degraded"
        if freshness_degraded
        else "ready_with_storage_pressure"
        if storage_pressure_cleanup_recommended
        else "ready_with_optional_maintenance"
        if maintenance_recommended
        else "ready"
    )
    return {
        "status": status,
        "ready": bool(first_recall_state["ordinary_first_recall_usable"]),
        "ordinary_first_recall_usable": first_recall_state["ordinary_first_recall_usable"],
        **health_readiness_fields(
            maintenance_required_before_recall=maintenance_required,
            live_delta_tolerated=live_delta_tolerated,
            freshness_degraded=freshness_degraded,
        ),
        "freshness_degraded": freshness_degraded,
        "maintenance_recommended": maintenance_recommended,
        "maintenance_required_before_recall": maintenance_required,
        "workspace_source_maintenance_required": first_recall_state[
            "workspace_source_maintenance_required"
        ],
        "continuity_recall_available": first_recall_state["continuity_recall_available"],
        "continuity_recall_unavailable": first_recall_state["continuity_recall_unavailable"],
        "registry_recall_available": first_recall_state["registry_recall_available"],
        "recall_availability_source": first_recall_state["recall_availability_source"],
        "storage_pressure_cleanup_recommended": storage_pressure_cleanup_recommended,
        "blocking_action_count": critical_action_count if maintenance_required else 0,
        "high_severity_action_count": high_severity_action_count,
        "advisory_action_count": max(0, len(actions) - critical_action_count),
        "checkpoint_status": "due_when_idle" if checkpoint_due else "current",
        "next_best_action": (
            "apply_required_maintenance"
            if maintenance_required
            else "run_maintenance_when_latest_context_matters"
            if freshness_degraded and not live_delta_tolerated
            else "review_storage_gc_dry_run_when_idle"
            if storage_pressure_cleanup_recommended
            else "run_checkpoint_when_idle"
            if checkpoint_due
            else "continue"
        ),
    }
