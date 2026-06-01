"""Aggregate prompt-hook skip telemetry without logging prompt text."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime import core as runtime_core

PROMPT_SKIP_TELEMETRY_ENV = "AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY"


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
    semantic_gate = result.get("semantic_gate") if isinstance(result.get("semantic_gate"), dict) else {}
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
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    cache_status = ambient.get("cache_status") if isinstance(ambient.get("cache_status"), dict) else {}
    if cache_status.get("status") == "miss":
        return "cache_miss"
    return "other_skip"


def _default_skip_telemetry_path() -> Path:
    return runtime_core.aippocampus_registry_dir() / "aippocampus_prompt_hook_skip_telemetry.json"


def _load_skip_telemetry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _try_claim_telemetry_lock(path: Path) -> int | None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    except OSError:
        return None


def _release_telemetry_lock(path: Path, fd: int | None) -> None:
    if fd is None:
        return
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        lock_path.unlink()
    except OSError:
        pass


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
    lock_fd = _try_claim_telemetry_lock(path)
    if lock_fd is None:
        # UserPromptSubmit is foreground work; drop this sample instead of
        # waiting behind another hook and stretching the prompt latency budget.
        return
    try:
        _write_skip_telemetry_locked(
            result,
            path=path,
            hook_budget_ms=hook_budget_ms,
            semantic_timeout=semantic_timeout,
            runtime_load_ms=runtime_load_ms,
            hook_total_ms=hook_total_ms,
        )
    except OSError:
        return
    finally:
        _release_telemetry_lock(path, lock_fd)


def _write_skip_telemetry_locked(
    result: dict[str, Any],
    *,
    path: Path,
    hook_budget_ms: int | None,
    semantic_timeout: float | None,
    runtime_load_ms: float | None,
    hook_total_ms: float | None,
) -> None:
    telemetry = _load_skip_telemetry(path)
    telemetry.setdefault("schema_version", 1)
    telemetry["updated_at"] = runtime_core.now_utc()
    telemetry["total_events"] = int(telemetry.get("total_events") or 0) + 1
    telemetry["skip_events"] = int(telemetry.get("skip_events") or 0) + 1
    telemetry["privacy_boundary"] = "aggregate_skip_diagnostics_no_raw_prompt_or_source_text"

    skip_reason = _skip_reason_bucket(result)
    _counter_add(telemetry.setdefault("skip_reason_counts", {}), skip_reason)

    semantic_gate = result.get("semantic_gate") if isinstance(result.get("semantic_gate"), dict) else {}
    if semantic_gate:
        _counter_add(telemetry.setdefault("semantic_availability_reason_counts", {}), semantic_gate.get("availability_reason"))
        _counter_add(telemetry.setdefault("semantic_diagnostic_counts", {}), semantic_gate.get("diagnostic"))
        for bucket, count in (semantic_gate.get("error_buckets") or {}).items():
            try:
                amount = max(0, int(count))
            except (TypeError, ValueError):
                amount = 1
            _counter_add(telemetry.setdefault("semantic_error_bucket_counts", {}), bucket, amount=amount)

    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    cache_status = ambient.get("cache_status") if isinstance(ambient.get("cache_status"), dict) else {}
    if cache_status:
        _counter_add(telemetry.setdefault("cache_status_counts", {}), cache_status.get("status"))
    warm_background = ambient.get("warm_background") if isinstance(ambient.get("warm_background"), dict) else {}
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
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(json.dumps(safe_telemetry, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
