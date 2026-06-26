"""Aggregate prompt-hook skip telemetry without logging prompt text."""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime import core as runtime_core
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.local_file_lock import (
    OwnerCheckedFileLease,
    OwnerCheckedLeaseBusyError,
    OwnerCheckedLeaseChangedError,
)

PROMPT_SKIP_TELEMETRY_ENV = "AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY"
HOST_TIMEOUT_RISK_BUCKET = "gte_4300"
CURRENT_LATENCY_WINDOW_SECONDS = 60 * 60
TELEMETRY_LOCK_STALE_AFTER_SECONDS = 30


def _flag_enabled(value: str | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().casefold() not in {"0", "false", "off", "no"}


def _counter_add(container: dict[str, Any], key: str | None, *, amount: int = 1) -> None:
    label = str(key or "unknown")
    container[label] = int(container.get(label) or 0) + amount


def _latency_bucket(value: Any) -> str:
    try:
        elapsed_ms = max(0.0, float(value))
    except (TypeError, ValueError):
        return "unknown"
    if elapsed_ms < 50:
        return "lt_50"
    if elapsed_ms < 250:
        return "lt_250"
    if elapsed_ms < 1000:
        return "lt_1000"
    if elapsed_ms < 2500:
        return "lt_2500"
    if elapsed_ms < 4300:
        return "lt_4300"
    return "gte_4300"


def _skip_reason_bucket(result: dict[str, Any]) -> str:
    raw_semantic_gate = result.get("semantic_gate")
    semantic_gate = raw_semantic_gate if isinstance(raw_semantic_gate, dict) else {}
    availability_reason = str(semantic_gate.get("availability_reason") or "").strip()
    if availability_reason:
        return availability_reason
    diagnostic = str(semantic_gate.get("diagnostic") or "").strip()
    if diagnostic:
        return diagnostic
    reason_text = " ".join(str(item) for item in result.get("reasons") or []).casefold()
    if "suppressed ordinary code-surface" in reason_text:
        return "suppressed_code_surface"
    if "privacy" in reason_text or "credential" in reason_text or "private-key" in reason_text:
        return "privacy_boundary"
    if "no ambient recall cue" in reason_text:
        return "no_ambient_recall_cue"
    raw_ambient = result.get("ambient_recall")
    ambient = raw_ambient if isinstance(raw_ambient, dict) else {}
    raw_cache_status = ambient.get("cache_status")
    cache_status = raw_cache_status if isinstance(raw_cache_status, dict) else {}
    if cache_status.get("status") == "miss":
        return "cache_miss"
    return "other_skip"


def _default_skip_telemetry_path() -> Path:
    return runtime_core.aippocampus_registry_dir() / "aippocampus_prompt_hook_skip_telemetry.json"


def default_skip_telemetry_path() -> Path:
    return _default_skip_telemetry_path()


def _load_skip_telemetry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _bucket_count(container: Any, *keys: str) -> int:
    current = container
    for key in keys:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    try:
        return max(0, int(current or 0))
    except (TypeError, ValueError):
        return 0


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latency_value_at_least(container: Mapping[str, Any], key: str, threshold: float) -> bool:
    try:
        value = float(container.get(key) or 0.0)
    except (TypeError, ValueError):
        return False
    return value >= threshold


def prompt_hook_latency_risk(
    *,
    telemetry_path: Path | None = None,
    host_timeout_ms: int = 5000,
    safe_internal_budget_ms: int = 3500,
    now: datetime | None = None,
    current_window_seconds: int = CURRENT_LATENCY_WINDOW_SECONDS,
) -> dict[str, Any]:
    """Project prompt-hook timeout risk without confusing stale history for now.

    The telemetry file is an aggregate skip ledger, not a live prompt-hook probe.
    Historical red-line counters stay visible for operator diagnosis, but the
    foreground status only becomes `near_host_timeout_risk` when a fresh latest
    sample is itself near the host timeout. This prevents old 4300ms-budget
    history from blocking every later session after the hook has already moved
    to the safer foreground budget.
    """

    path = telemetry_path or _default_skip_telemetry_path()
    telemetry = _load_skip_telemetry(path)
    if not telemetry:
        return {
            "kind": "aippocampus_prompt_hook_latency_risk",
            "status": "no_aggregate_telemetry",
            "current_status": "no_recent_telemetry",
            "freshness_status": "no_aggregate_telemetry",
            "historical_status": "no_history",
            "telemetry_found": False,
            "near_timeout_event_count": 0,
            "historical_near_timeout_event_count": 0,
            "repair_action": "",
            "privacy_boundary": "aggregate_only_no_prompt_source_or_local_path",
        }
    latency = telemetry.get("latency_ms") or {}
    buckets = latency.get("buckets") if isinstance(latency, dict) else {}
    hook_elapsed_near = _bucket_count(buckets, "hook_elapsed", HOST_TIMEOUT_RISK_BUCKET)
    hook_total_near = _bucket_count(buckets, "hook_total", HOST_TIMEOUT_RISK_BUCKET)
    runtime_load_near = _bucket_count(buckets, "runtime_load", HOST_TIMEOUT_RISK_BUCKET)
    startup_import_near = _bucket_count(buckets, "startup_import_io", HOST_TIMEOUT_RISK_BUCKET)
    near_timeout_event_count = max(
        hook_elapsed_near,
        hook_total_near,
        runtime_load_near,
        startup_import_near,
    )
    budget_counts = telemetry.get("hook_budget_ms_counts")
    high_budget_count = 0
    if isinstance(budget_counts, dict):
        for raw_budget, raw_count in budget_counts.items():
            try:
                budget = int(float(str(raw_budget)))
                count = int(raw_count or 0)
            except (TypeError, ValueError):
                continue
            if budget >= 4300:
                high_budget_count += max(0, count)
    historical_status = (
        "historical_near_timeout_seen"
        if near_timeout_event_count > 0 or high_budget_count > 0
        else "within_safe_margin"
    )
    historical_red_line_count = max(
        near_timeout_event_count,
        high_budget_count,
    )
    last = dict(latency.get("last") or {}) if isinstance(latency, dict) else {}
    last_event = telemetry.get("last_event")
    last_timestamp = str((last_event or {}).get("timestamp") or telemetry.get("updated_at") or "")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed_last = _parse_utc(last_timestamp)
    age_seconds = int((current - parsed_last).total_seconds()) if parsed_last else None
    fresh = bool(age_seconds is not None and 0 <= age_seconds <= int(current_window_seconds))
    near_timeout_threshold = max(0.0, float(host_timeout_ms) * 0.86)
    latest_near_timeout = any(
        _latency_value_at_least(last, key, near_timeout_threshold)
        for key in ("hook_elapsed", "hook_total", "runtime_load", "startup_import_io")
    )
    latest_budget_overrun = _latency_value_at_least(last, "hook_elapsed", safe_internal_budget_ms)
    current_red_line_count = 1 if fresh and (latest_near_timeout or latest_budget_overrun) else 0
    current_near_timeout_count = 1 if fresh and latest_near_timeout else 0
    if current_red_line_count:
        current_status = "near_host_timeout_risk"
    elif fresh:
        current_status = "within_safe_margin"
    elif historical_status == "historical_near_timeout_seen":
        current_status = "stale_history_only"
    else:
        current_status = "no_recent_telemetry"
    freshness_status = (
        "fresh_current_window"
        if fresh
        else "stale_history_only"
        if historical_status == "historical_near_timeout_seen"
        else "no_recent_telemetry"
    )
    return {
        "kind": "aippocampus_prompt_hook_latency_risk",
        "status": current_status,
        "current_status": current_status,
        "freshness_status": freshness_status,
        "historical_status": historical_status,
        "telemetry_found": True,
        "total_events": int(telemetry.get("total_events") or 0),
        "foreground_latency_red_line_violation_count": current_red_line_count,
        "near_timeout_event_count": current_near_timeout_count,
        "historical_foreground_latency_red_line_violation_count": historical_red_line_count,
        "historical_near_timeout_event_count": near_timeout_event_count,
        "high_internal_budget_event_count": high_budget_count,
        "host_timeout_ms": int(host_timeout_ms),
        "safe_internal_budget_ms": int(safe_internal_budget_ms),
        "current_window_seconds": int(current_window_seconds),
        "last_event_timestamp": last_timestamp,
        "last_event_age_seconds": age_seconds,
        "latency_bucket_counts": {
            "hook_elapsed_gte_4300": hook_elapsed_near,
            "hook_total_gte_4300": hook_total_near,
            "runtime_load_gte_4300": runtime_load_near,
            "startup_import_io_gte_4300": startup_import_near,
        },
        "last": last,
        "repair_action": (
            "aippocampus hooks prompt install --json"
            if current_status == "near_host_timeout_risk"
            else ""
        ),
        "diagnostic_action": "aippocampus hooks prompt status --last --json",
        "privacy_boundary": "aggregate_only_no_prompt_source_or_local_path",
        "cannot_claim": [
            "raw_prompt_or_source_text",
            "single_latest_run_proves_host_safety",
            "stale_history_proves_current_prompt_latency",
        ],
    }


def _telemetry_lease(path: Path) -> OwnerCheckedFileLease:
    lock_path = path.with_suffix(path.suffix + ".lock")
    return OwnerCheckedFileLease(
        lock_path,
        lock_kind="prompt_hook_skip_telemetry",
        stale_after_seconds=TELEMETRY_LOCK_STALE_AFTER_SECONDS,
        wait_timeout_seconds=0.0,
        payload_extra={"kind": "aippocampus_prompt_hook_skip_telemetry_lease"},
    )


def _nested_counter(root: dict[str, Any], *keys: str) -> dict[str, Any]:
    current = root
    for key in keys:
        child = current.setdefault(key, {})
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    return current


def write_skip_telemetry(
    result: dict[str, Any],
    *,
    hook_input: dict[str, Any] | None = None,
    telemetry_path: Path | None = None,
    enabled: bool | None = None,
    hook_budget_ms: int | None = None,
    semantic_timeout: float | None = None,
    runtime_load_ms: float | None = None,
    hook_total_ms: float | None = None,
    telemetry_write_ms: float | None = None,
) -> None:
    """Update local aggregate skip telemetry without logging prompt text."""
    del hook_input
    if enabled is None:
        enabled = _flag_enabled(os.environ.get(PROMPT_SKIP_TELEMETRY_ENV), default=True)
    if not enabled or result.get("decision") != "skip":
        return
    path = telemetry_path or _default_skip_telemetry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        with _telemetry_lease(path):
            _write_skip_telemetry_locked(
                result,
                path=path,
                hook_budget_ms=hook_budget_ms,
                semantic_timeout=semantic_timeout,
                runtime_load_ms=runtime_load_ms,
                hook_total_ms=hook_total_ms,
                telemetry_write_ms=telemetry_write_ms,
            )
    except (OwnerCheckedLeaseBusyError, OwnerCheckedLeaseChangedError, OSError):
        # UserPromptSubmit is foreground work; drop this sample instead of
        # waiting behind another hook and stretching the prompt latency budget.
        return


def _write_skip_telemetry_locked(
    result: dict[str, Any],
    *,
    path: Path,
    hook_budget_ms: int | None,
    semantic_timeout: float | None,
    runtime_load_ms: float | None,
    hook_total_ms: float | None,
    telemetry_write_ms: float | None,
) -> None:
    telemetry = _load_skip_telemetry(path)
    telemetry.setdefault("schema_version", 1)
    telemetry["updated_at"] = runtime_core.now_utc()
    telemetry["total_events"] = int(telemetry.get("total_events") or 0) + 1
    telemetry["skip_events"] = int(telemetry.get("skip_events") or 0) + 1
    telemetry["privacy_boundary"] = "aggregate_skip_diagnostics_no_raw_prompt_or_source_text"

    skip_reason = _skip_reason_bucket(result)
    _counter_add(telemetry.setdefault("skip_reason_counts", {}), skip_reason)

    raw_semantic_gate = result.get("semantic_gate")
    semantic_gate = raw_semantic_gate if isinstance(raw_semantic_gate, dict) else {}
    if semantic_gate:
        _counter_add(telemetry.setdefault("semantic_availability_reason_counts", {}), semantic_gate.get("availability_reason"))
        _counter_add(telemetry.setdefault("semantic_diagnostic_counts", {}), semantic_gate.get("diagnostic"))
        for bucket, count in (semantic_gate.get("error_buckets") or {}).items():
            try:
                amount = max(0, int(count))
            except (TypeError, ValueError):
                amount = 1
            _counter_add(telemetry.setdefault("semantic_error_bucket_counts", {}), bucket, amount=amount)

    raw_ambient = result.get("ambient_recall")
    ambient = raw_ambient if isinstance(raw_ambient, dict) else {}
    raw_cache_status = ambient.get("cache_status")
    cache_status = raw_cache_status if isinstance(raw_cache_status, dict) else {}
    if cache_status:
        _counter_add(telemetry.setdefault("cache_status_counts", {}), cache_status.get("status"))
    raw_warm_background = ambient.get("warm_background")
    warm_background = raw_warm_background if isinstance(raw_warm_background, dict) else {}
    if warm_background:
        _counter_add(telemetry.setdefault("warm_background_status_counts", {}), warm_background.get("status"))

    os_family = (platform.system() or os.name or "unknown").lower()
    python_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    _counter_add(telemetry.setdefault("platform_counts", {}), os_family)
    _counter_add(telemetry.setdefault("python_minor_counts", {}), python_minor)
    if hook_budget_ms is not None:
        _counter_add(telemetry.setdefault("hook_budget_ms_counts", {}), str(hook_budget_ms))
    if semantic_timeout is not None:
        _counter_add(telemetry.setdefault("semantic_timeout_counts", {}), str(semantic_timeout))

    latency = telemetry.setdefault("latency_ms", {})
    latency_buckets = _nested_counter(latency, "buckets")
    measurements = {
        "hook_elapsed": result.get("elapsed_ms"),
        "hook_total": hook_total_ms,
        "runtime_load": runtime_load_ms,
        "telemetry_write": telemetry_write_ms,
        "startup_import_io": max(0.0, float(hook_total_ms or 0.0) - float(result.get("elapsed_ms") or 0.0))
        if hook_total_ms is not None
        else 0.0,
    }
    for name, value in measurements.items():
        _counter_add(_nested_counter(latency_buckets, name), _latency_bucket(value))
    latency["last"] = {key: round(float(value), 2) for key, value in measurements.items() if value is not None}

    telemetry["last_event"] = {
        "timestamp": telemetry["updated_at"],
        "decision": "skip",
        "skip_reason": skip_reason,
        "os_family": os_family,
        "python": python_minor,
        "cache_status": cache_status.get("status"),
        "semantic_availability_reason": semantic_gate.get("availability_reason"),
        "semantic_diagnostic": semantic_gate.get("diagnostic"),
    }
    safe_telemetry = runtime_core.sanitize_external_model_payload(telemetry)
    atomic_write_json(path, safe_telemetry, indent=2)
