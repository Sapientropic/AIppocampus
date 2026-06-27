"""Storage-pressure health adapters with explicit operator boundaries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

from aippocampus_runtime.ops.storage_governance_contract import human_bytes

STORAGE_PRESSURE_RECLAIMABLE_BYTES = 512 * 1024 * 1024
STORAGE_PRESSURE_AMPLIFICATION_RATIO = 10.0
STORAGE_PRESSURE_CANDIDATE_COUNT = 100
STORAGE_GC_BOUNDED_DETAIL_COMMAND = "aippocampus storage gc --dry-run --json --top 1 --cwd ."
STORAGE_GC_FULL_DETAIL_COMMAND = "aippocampus storage gc --dry-run --json --full --cwd ."
EXPENSIVE_OPERATOR_DIAGNOSTIC_TIMEOUT_MS = 30000


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _base_storage_pressure_payload(
    *,
    status: str,
    pressure: bool,
    reasons: list[str],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "available": True,
        "status": status,
        "pressure": pressure,
        "reasons": reasons,
        "metrics": dict(metrics),
        "dry_run_command": STORAGE_GC_BOUNDED_DETAIL_COMMAND,
        "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
        "repair_command": (
            "aippocampus storage gc --apply --class rebuildable "
            "--include-active --summary-json --cwd ."
        ),
        "source_history_protected": True,
        "foreground_blocking": False,
        "privacy_boundary": {
            "paths_included": False,
            "raw_rollout_bodies_read": False,
            "clean_source_bodies_read": False,
            "rebuildable_cache_only": True,
        },
    }


def deferred_storage_pressure_report() -> dict[str, Any]:
    return {
        "available": False,
        "status": "deferred",
        "partial": True,
        "pressure": None,
        "reason": "expensive_storage_pressure_diagnostic_requires_opt_in",
        "next_operator_action": (
            "aippocampus health --detail full --json "
            f"--include-expensive-diagnostics --operator-timeout-ms {EXPENSIVE_OPERATOR_DIAGNOSTIC_TIMEOUT_MS}"
        ),
        "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
        "source_history_protected": True,
        "foreground_blocking": False,
        "privacy_boundary": {
            "paths_included": False,
            "raw_rollout_bodies_read": False,
            "clean_source_bodies_read": False,
            "rebuildable_cache_only": True,
        },
        "claim_boundary": (
            "Storage pressure was not assessed in the bounded full-detail pass; "
            "use next_operator_action for the explicit expensive diagnostic."
        ),
    }


def _timeout_report(*, max_elapsed_ms: int, elapsed_ms: float | None = None) -> dict[str, Any]:
    payload = deferred_storage_pressure_report()
    payload.update(
        {
            "status": "timeout",
            "reason": "storage_pressure_diagnostic_timeout",
            "elapsed_ms": elapsed_ms,
            "timeout_ms": max(0, int(max_elapsed_ms)),
            "claim_boundary": (
                "Storage pressure scan exceeded the operator time budget; "
                "use the summary command for an explicit no-write review."
            ),
        }
    )
    return payload


def _pressure_from_metrics(
    metrics: Mapping[str, Any],
    *,
    pressure_present: bool = False,
) -> tuple[str, list[str], dict[str, Any]]:
    reclaimable = safe_int(metrics.get("reclaimable_rebuildable_bytes"))
    amplification = float(metrics.get("generated_index_amplification_ratio") or 0.0)
    candidate_count = safe_int(metrics.get("eviction_candidate_count"))
    reasons: list[str] = []
    if reclaimable >= STORAGE_PRESSURE_RECLAIMABLE_BYTES:
        reasons.append("reclaimable_rebuildable_cache_bytes_high")
    if amplification >= STORAGE_PRESSURE_AMPLIFICATION_RATIO:
        reasons.append("generated_index_amplification_ratio_high")
    if candidate_count >= STORAGE_PRESSURE_CANDIDATE_COUNT:
        reasons.append("rebuildable_eviction_candidate_count_high")
    if pressure_present and not reasons:
        reasons.append("storage_governance_summary_pressure_present")
    return (
        "pressure" if reasons else "ok",
        reasons,
        {
            "reclaimable_rebuildable_bytes": reclaimable,
            "reclaimable_rebuildable_human": metrics.get("reclaimable_rebuildable_human"),
            "protected_source_bytes": safe_int(metrics.get("protected_source_bytes")),
            "protected_source_human": metrics.get("protected_source_human"),
            "generated_index_amplification_ratio": amplification,
            "eviction_candidate_count": candidate_count,
        },
    )


def _storage_pressure_from_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    status, reasons, metrics = _pressure_from_metrics(
        dict(summary.get("metrics") or {}),
        pressure_present=str(summary.get("pressure_interpretation") or "") == "pressure_present",
    )
    return _base_storage_pressure_payload(
        status=status,
        pressure=bool(reasons),
        reasons=reasons,
        metrics=metrics,
    )


def _subprocess_registry_cache_pressure_report(
    cwd: Path,
    registry_dir: Path,
    *,
    max_elapsed_ms: int,
) -> dict[str, Any]:
    if max_elapsed_ms <= 0:
        return _timeout_report(max_elapsed_ms=max_elapsed_ms, elapsed_ms=0.0)
    scripts_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(scripts_root)
        if not existing_pythonpath
        else os.pathsep.join([str(scripts_root), existing_pythonpath])
    )
    command = [
        sys.executable,
        "-m",
        "aippocampus_runtime.ops.storage_governance",
        "gc",
        "--dry-run",
        "--summary-json",
        "--class",
        "rebuildable",
        "--top",
        "1",
        "--fanout-budget",
        "16",
        "--cwd",
        str(cwd),
        "--registry-dir",
        str(registry_dir),
    ]
    started_at = perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=max_elapsed_ms / 1000.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        return _timeout_report(max_elapsed_ms=max_elapsed_ms, elapsed_ms=elapsed_ms)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
    if completed.returncode != 0:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "storage_governance_summary_failed",
            "exit_code": completed.returncode,
            "elapsed_ms": elapsed_ms,
            "error": (completed.stderr or completed.stdout or "")[:400],
            "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
            "source_history_protected": True,
            "foreground_blocking": False,
        }
    try:
        summary = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "storage_governance_summary_non_json",
            "error_type": type(exc).__name__,
            "elapsed_ms": elapsed_ms,
            "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
            "source_history_protected": True,
            "foreground_blocking": False,
        }
    report = _storage_pressure_from_summary(summary if isinstance(summary, Mapping) else {})
    report["elapsed_ms"] = elapsed_ms
    report["timeout_ms"] = max_elapsed_ms
    report["summary_source"] = "bounded_storage_governance_subprocess"
    return report


def registry_cache_pressure_report(
    cwd: Path,
    registry_dir: Path,
    *,
    max_elapsed_ms: int | None = None,
) -> dict[str, Any]:
    if max_elapsed_ms is not None:
        return _subprocess_registry_cache_pressure_report(
            cwd,
            registry_dir,
            max_elapsed_ms=max_elapsed_ms,
        )
    try:
        from aippocampus_runtime.ops import storage_governance  # noqa: PLC0415
        from aippocampus_runtime.ops.storage_governance_contract import (  # noqa: PLC0415
            CLASS_REBUILDABLE,
        )

        plan = storage_governance.build_plan(
            cwd,
            registry_dir=registry_dir,
            class_filter=CLASS_REBUILDABLE,
            include_paths=False,
            top=3,
            fanout_budget=16,
        )
    except Exception as exc:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "storage_governance_unavailable",
            "error_type": type(exc).__name__,
            "source_history_protected": True,
            "foreground_blocking": False,
        }
    status, reasons, metrics = _pressure_from_metrics(dict(plan.get("metrics") or {}))
    return _base_storage_pressure_payload(
        status=status,
        pressure=bool(reasons),
        reasons=reasons,
        metrics=metrics,
    )


def generation_cache_pressure_report(
    index_generations: Mapping[str, Any],
    segment_generations: Mapping[str, Any],
) -> dict[str, Any]:
    index_bytes = safe_int(index_generations.get("generation_gc_candidate_bytes"))
    segment_bytes = safe_int(segment_generations.get("generation_gc_candidate_bytes"))
    index_count = safe_int(index_generations.get("generation_gc_candidate_count"))
    segment_count = safe_int(segment_generations.get("generation_gc_candidate_count"))
    reclaimable = index_bytes + segment_bytes
    candidate_count = index_count + segment_count
    reasons: list[str] = []
    if reclaimable >= STORAGE_PRESSURE_RECLAIMABLE_BYTES:
        reasons.append("loaded_generation_gc_candidate_bytes_high")
    if candidate_count >= STORAGE_PRESSURE_CANDIDATE_COUNT:
        reasons.append("loaded_generation_gc_candidate_count_high")
    payload = _base_storage_pressure_payload(
        status="pressure" if reasons else "ok",
        pressure=bool(reasons),
        reasons=reasons,
        metrics={
            "reclaimable_rebuildable_bytes": reclaimable,
            "reclaimable_rebuildable_human": human_bytes(reclaimable),
            "index_generation_gc_candidate_bytes": index_bytes,
            "segment_generation_gc_candidate_bytes": segment_bytes,
            "eviction_candidate_count": candidate_count,
            "index_generation_gc_candidate_count": index_count,
            "segment_generation_gc_candidate_count": segment_count,
            "generated_index_amplification_ratio": 0.0,
        },
    )
    payload.update(
        {
            "scope": "current_thread_generation_diagnostics",
            "claim_boundary": (
                "Current-thread old generation candidates are rebuildable-cache "
                "pressure only; review storage GC before any apply."
            ),
        }
    )
    return payload
