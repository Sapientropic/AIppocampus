"""Private-safe spend/yield diagnostics for model-backed runtime routes."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime import core as runtime_core
from aippocampus_runtime.recall.semantic_recall_gate import semantic_gate_mode
from aippocampus_runtime.warm_ambient.scheduler import warm_background_enabled

SCHEMA_VERSION = 1
DEFAULT_DAYS = 7
DEFAULT_WARN_EFFECTIVE_TOKENS = int(
    os.environ.get("AIPPOCAMPUS_SPEND_WARN_EFFECTIVE_TOKENS", "1000000")
)
DEFAULT_WARN_MIN_FOREGROUND_VALUE_RATE = float(
    os.environ.get("AIPPOCAMPUS_SPEND_WARN_MIN_FOREGROUND_VALUE_RATE", "0.10")
)
USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
)
VALUE_STATUSES = {"accepted", "activated", "materialized", "promoted", "ready", "written"}
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"


def _empty_model_telemetry() -> dict[str, Any]:
    return {
        "usage_available": False,
        "usage_missing_reason": "no_model_usage_artifacts_scanned",
        "usage_missing_reason_counts": {},
        "cache_metrics_kind": "none",
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "prompt_cache_hit_rate": None,
        "request_count": 0,
        "latency_ms": {
            "count": 0,
            "total": 0.0,
            "average": None,
            "max": 0.0,
        },
    }


def _empty_route() -> dict[str, Any]:
    return {
        "spend": {
            "request_count": 0,
            "known_usage": False,
            "effective_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
        },
        "model_telemetry": _empty_model_telemetry(),
        "yield": {
            "generated_candidates": 0,
            "suppressed_candidates": 0,
            "staging_rows": 0,
            "materialized_rows": 0,
            "foreground_cards": 0,
            "source_backed_evidence_cards": 0,
            "source_reopen_follow_through": 0,
            "skip_events": 0,
        },
        "status_counts": {},
        "by_day": {},
        "artifacts": [],
        "latest": {},
        "warnings": [],
    }


def _routes() -> dict[str, dict[str, Any]]:
    return {
        "warm_ambient": _empty_route(),
        "subconscious": _empty_route(),
        "semantic_gate": _empty_route(),
        "dream": _empty_route(),
        "prompt_hook": _empty_route(),
    }


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_time(value: Any) -> datetime | None:
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


def _now(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        parsed: datetime | None = value
    else:
        parsed = _parse_time(value)
        if parsed is None:
            parsed = _parse_time(runtime_core.now_utc())
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _row_time(row: Mapping[str, Any]) -> datetime | None:
    for key in ("created_at", "updated_at", "timestamp"):
        parsed = _parse_time(row.get(key))
        if parsed:
            return parsed
    return None


def _in_window(row: Mapping[str, Any], *, since: datetime) -> bool:
    parsed = _row_time(row)
    return parsed is None or parsed >= since


def _day_key(row: Mapping[str, Any]) -> str:
    parsed = _row_time(row)
    return parsed.date().isoformat() if parsed else "undated"


def _public_usage(value: Any) -> dict[str, int]:
    usage = value if isinstance(value, Mapping) else {}
    result: dict[str, int] = {}
    for key in USAGE_KEYS:
        if key in usage:
            result[key] = _safe_int(usage.get(key))
    return result


def _nested_mapping(row: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: Any = row
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return current if isinstance(current, Mapping) else {}


def _public_usage_from_row(row: Mapping[str, Any]) -> dict[str, int]:
    for candidate in (
        row.get("usage"),
        _nested_mapping(row, "model_telemetry", "usage"),
        _nested_mapping(row, "worker", "usage"),
        _nested_mapping(row, "worker_run", "usage"),
        _nested_mapping(row, "worker_result", "usage"),
        _nested_mapping(row, "result", "usage"),
        _nested_mapping(row, "summary", "usage"),
    ):
        usage = _public_usage(candidate)
        if usage:
            return usage
    return {}


def _cache_from_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    for candidate in (
        row.get("cache"),
        _nested_mapping(row, "model_telemetry", "cache"),
        _nested_mapping(row, "worker", "cache"),
        _nested_mapping(row, "worker_run", "cache"),
        _nested_mapping(row, "worker_result", "cache"),
        _nested_mapping(row, "result", "cache"),
        _nested_mapping(row, "summary", "cache"),
    ):
        if isinstance(candidate, Mapping):
            return candidate
    return {}


def _usage_missing_reason(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or row.get("worker_status") or "").casefold()
    reason = str(row.get("reason") or row.get("usage_missing_reason") or "").casefold()
    if status in {"dry_run", "not_run"} or reason == "dry_run":
        return "dry_run"
    if status in {"unavailable", "skipped", "suppressed"}:
        return "local_offline_provider" if "offline" in reason else "provider_did_not_return_usage"
    if row.get("usage") is None and _cache_from_row(row):
        return "provider_did_not_return_usage"
    return "artifact_legacy_no_usage"


def _latency_ms_from_row(row: Mapping[str, Any]) -> float:
    for key in ("latency_ms", "elapsed_ms", "duration_ms"):
        if key in row:
            return _safe_float(row.get(key))
    for container_key in ("model_telemetry", "worker", "worker_run", "worker_result", "result", "summary"):
        value = _nested_mapping(row, container_key).get("latency_ms")
        if value is not None:
            return _safe_float(value)
    return 0.0


def _effective_tokens(usage: Mapping[str, int]) -> int:
    total = _safe_int(usage.get("total_tokens"))
    if total:
        return total
    prompt = _safe_int(usage.get("prompt_tokens"))
    completion = _safe_int(usage.get("completion_tokens"))
    if prompt or completion:
        return prompt + completion
    return _safe_int(usage.get("prompt_cache_hit_tokens")) + _safe_int(
        usage.get("prompt_cache_miss_tokens")
    )


def _counter_increment(container: dict[str, Any], key: Any, amount: int = 1) -> None:
    label = str(key or "unknown")
    container[label] = _safe_int(container.get(label)) + max(0, int(amount))


def _record_model_telemetry(
    route: dict[str, Any],
    row: Mapping[str, Any],
    usage: Mapping[str, int],
    *,
    request_count: int,
) -> None:
    telemetry = route["model_telemetry"]
    count = max(0, int(request_count))
    telemetry["request_count"] += count
    if usage:
        telemetry["usage_available"] = True
        telemetry["usage_missing_reason"] = None
    else:
        reason = _usage_missing_reason(row)
        _counter_increment(telemetry["usage_missing_reason_counts"], reason, count or 1)
        if not telemetry["usage_available"]:
            telemetry["usage_missing_reason"] = reason
    cache = _cache_from_row(row)
    cache_kind = str(
        cache.get("kind")
        or cache.get("cache_metrics_kind")
        or row.get("cache_metrics_kind")
        or ""
    ).strip()
    hit = _safe_int(
        usage.get("prompt_cache_hit_tokens")
        or usage.get("cache_hit_tokens")
        or cache.get("hit_tokens")
        or cache.get("prompt_cache_hit_tokens")
    )
    miss = _safe_int(
        usage.get("prompt_cache_miss_tokens")
        or usage.get("cache_miss_tokens")
        or cache.get("miss_tokens")
        or cache.get("prompt_cache_miss_tokens")
    )
    if hit or miss:
        telemetry["prompt_cache_hit_tokens"] += hit
        telemetry["prompt_cache_miss_tokens"] += miss
        telemetry["cache_metrics_kind"] = cache_kind or "deepseek_prefix"
    elif cache_kind and telemetry["cache_metrics_kind"] == "none":
        telemetry["cache_metrics_kind"] = cache_kind
    latency = _latency_ms_from_row(row)
    if latency:
        latency_summary = telemetry["latency_ms"]
        latency_summary["count"] += 1
        latency_summary["total"] = round(
            float(latency_summary.get("total") or 0.0) + latency,
            2,
        )
        latency_summary["max"] = round(
            max(float(latency_summary.get("max") or 0.0), latency),
            2,
        )


def _by_day(route: dict[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    day = _day_key(row)
    return route["by_day"].setdefault(
        day,
        {
            "request_count": 0,
            "effective_tokens": 0,
            "generated_candidates": 0,
            "foreground_value_count": 0,
        },
    )


def _add_spend(
    route: dict[str, Any],
    usage_value: Any,
    *,
    row: Mapping[str, Any],
    request_count: int = 1,
) -> None:
    usage = _public_usage(usage_value) or _public_usage_from_row(row)
    spend = route["spend"]
    count = max(0, int(request_count))
    spend["request_count"] += count
    _record_model_telemetry(route, row, usage, request_count=count)
    if usage:
        spend["known_usage"] = True
    effective = _effective_tokens(usage)
    spend["effective_tokens"] += effective
    spend["prompt_tokens"] += _safe_int(usage.get("prompt_tokens"))
    spend["completion_tokens"] += _safe_int(usage.get("completion_tokens"))
    spend["total_tokens"] += _safe_int(usage.get("total_tokens"))
    spend["cache_hit_tokens"] += _safe_int(
        usage.get("prompt_cache_hit_tokens") or usage.get("cache_hit_tokens")
    )
    spend["cache_miss_tokens"] += _safe_int(
        usage.get("prompt_cache_miss_tokens") or usage.get("cache_miss_tokens")
    )
    day = _by_day(route, row)
    day["request_count"] += max(0, int(request_count))
    day["effective_tokens"] += effective


def _add_generated(route: dict[str, Any], row: Mapping[str, Any], count: int) -> None:
    amount = max(0, int(count))
    route["yield"]["generated_candidates"] += amount
    _by_day(route, row)["generated_candidates"] += amount


def _add_foreground_value(route: dict[str, Any], row: Mapping[str, Any], count: int) -> None:
    amount = max(0, int(count))
    _by_day(route, row)["foreground_value_count"] += amount


def _latest(route: dict[str, Any], key: str, row: Mapping[str, Any]) -> None:
    parsed = _row_time(row)
    if parsed is None:
        return
    text = parsed.isoformat().replace("+00:00", "Z")
    current = _parse_time(route["latest"].get(key))
    if current is None or parsed > current:
        route["latest"][key] = text


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
    except OSError:
        return


def _artifact(root: Path, name: str, *, exists: bool, scanned_rows: int = 0) -> dict[str, Any]:
    del root
    return {"name": name, "exists": bool(exists), "scanned_rows": max(0, int(scanned_rows))}


def _origin_text(row: Mapping[str, Any]) -> str:
    keys = (
        "kind",
        "source",
        "origin",
        "provenance",
        "provenance_class",
        "execution_mode",
        "adjudication_source",
        "truth_boundary",
        "source_candidate_batch_id",
        "source_candidate_type",
    )
    return " ".join(str(row.get(key) or "") for key in keys).casefold()


def _is_dream_row(row: Mapping[str, Any]) -> bool:
    candidate_type = str(row.get("candidate_type") or "").casefold()
    return candidate_type == DREAM_HYPOTHESIS_TYPE or "dream" in _origin_text(row)


def _is_subconscious_materialized_row(row: Mapping[str, Any], artifact_name: str) -> bool:
    # working_memory.jsonl is shared by subconscious routing and dream delivery,
    # so spend/yield diagnostics must attribute by stable row provenance rather
    # than by the file name alone.
    if artifact_name == "working_memory.jsonl" and _is_dream_row(row):
        return False
    origin = _origin_text(row)
    if artifact_name == "promotion_candidates.jsonl":
        return row.get("kind") == "aippocampus_promotion_candidate" or "subconscious" in origin
    if artifact_name == "semantic_triggers.jsonl":
        return row.get("source_candidate_type") is not None or "subconscious" in origin
    if artifact_name != "working_memory.jsonl":
        return "subconscious" in origin
    if row.get("kind") != "aippocampus_working_memory":
        return False
    if "subconscious" in origin:
        return True
    if str(row.get("source_candidate_batch_id") or "").startswith("subconscious-review-"):
        return True
    return bool(row.get("source_finding_ids"))


def _aggregate_warm(route: dict[str, Any], root: Path, *, since: datetime) -> None:
    job_dir = root / "ambient_warm_jobs"
    files = sorted(job_dir.glob("*.result.json")) if job_dir.exists() else []
    scanned = 0
    for path in files:
        row = _read_json(path)
        if row is None or not _in_window(row, since=since):
            continue
        scanned += 1
        _counter_increment(route["status_counts"], row.get("status"))
        request_count = _safe_int(
            row.get("observed_scout_result_count") or row.get("configured_scout_count") or 1
        )
        _add_spend(route, row.get("usage"), row=row, request_count=request_count)
        card_count = _safe_int(row.get("card_count"))
        _add_generated(route, row, card_count)
        if row.get("status") == "suppressed":
            route["yield"]["suppressed_candidates"] += card_count or 1
        cache_write_value = row.get("cache_write")
        cache_write: Mapping[str, Any] = (
            cache_write_value if isinstance(cache_write_value, Mapping) else {}
        )
        if cache_write.get("status") == "written":
            written_count = _safe_int(cache_write.get("card_count") or card_count)
            route["yield"]["materialized_rows"] += written_count
            _add_foreground_value(route, row, written_count)
        topic_action = row.get("topic_epoch_action")
        if topic_action:
            _counter_increment(route.setdefault("topic_epoch_action_counts", {}), topic_action)
        if row.get("available"):
            _latest(route, "last_available_run_at", row)
        _latest(route, "last_run_at", row)
    route["artifacts"].append(
        _artifact(root, "ambient_warm_jobs/*.result.json", exists=job_dir.exists(), scanned_rows=scanned)
    )


def _aggregate_subconscious(route: dict[str, Any], root: Path, *, since: datetime) -> None:
    scanned = 0
    for name in ("subconscious_jobs.jsonl", "subconscious_edges.jsonl"):
        path = root / name
        local_rows = 0
        for row in _iter_jsonl(path):
            if not _in_window(row, since=since):
                continue
            scanned += 1
            local_rows += 1
            _counter_increment(route["status_counts"], row.get("status"))
            _counter_increment(route.setdefault("job_counts", {}), row.get("job") or row.get("finding_kind"))
            _add_spend(route, row.get("usage"), row=row)
            route["yield"]["staging_rows"] += 1
            _add_generated(route, row, 1)
            _latest(route, "last_staging_write_at", row)
        route["artifacts"].append(_artifact(root, name, exists=path.exists(), scanned_rows=local_rows))

    for name in ("promotion_candidates.jsonl", "working_memory.jsonl", "semantic_triggers.jsonl"):
        path = root / name
        local_rows = 0
        for row in _iter_jsonl(path):
            if not _in_window(row, since=since):
                continue
            status = str(row.get("status") or row.get("promotion_status") or "").casefold()
            if not _is_subconscious_materialized_row(row, name):
                continue
            local_rows += 1
            route["yield"]["materialized_rows"] += 1
            _add_foreground_value(route, row, 1)
            if status in VALUE_STATUSES:
                _latest(route, "last_materialized_at", row)
            if str(row.get("support_level") or "").casefold() == "evidence":
                route["yield"]["source_backed_evidence_cards"] += 1
        route["artifacts"].append(_artifact(root, name, exists=path.exists(), scanned_rows=local_rows))
    if scanned:
        _latest(route, "last_run_at", {"created_at": route["latest"].get("last_staging_write_at")})


def _aggregate_dream(route: dict[str, Any], root: Path, *, since: datetime) -> None:
    for name in ("dream_queue.jsonl", "dream_findings.jsonl", "working_memory.jsonl"):
        path = root / name
        local_rows = 0
        for row in _iter_jsonl(path):
            if not _in_window(row, since=since):
                continue
            if not _is_dream_row(row):
                continue
            local_rows += 1
            _counter_increment(route["status_counts"], row.get("status"))
            _add_spend(route, row.get("usage"), row=row)
            if name == "working_memory.jsonl":
                route["yield"]["materialized_rows"] += 1
                _add_foreground_value(route, row, 1)
            else:
                route["yield"]["staging_rows"] += 1
                _add_generated(route, row, 1)
            _latest(route, "last_run_at", row)
        route["artifacts"].append(_artifact(root, name, exists=path.exists(), scanned_rows=local_rows))


def _aggregate_semantic(route: dict[str, Any], root: Path, *, since: datetime) -> None:
    telemetry_path = root / "aippocampus_prompt_hook_skip_telemetry.json"
    telemetry = _read_json(telemetry_path)
    scanned = 0
    if telemetry and _in_window(telemetry, since=since):
        scanned = 1
        route["yield"]["skip_events"] += _safe_int(telemetry.get("skip_events"))
        route["skip_reason_counts"] = {
            str(key): _safe_int(value)
            for key, value in (telemetry.get("skip_reason_counts") or {}).items()
        }
        route["semantic_diagnostic_counts"] = {
            str(key): _safe_int(value)
            for key, value in (telemetry.get("semantic_diagnostic_counts") or {}).items()
        }
        route["warm_background_status_counts"] = {
            str(key): _safe_int(value)
            for key, value in (telemetry.get("warm_background_status_counts") or {}).items()
        }
        _latest(route, "last_skip_telemetry_at", {"created_at": telemetry.get("updated_at")})
    route["spend"]["known_usage"] = False
    route["artifacts"].append(
        _artifact(root, "aippocampus_prompt_hook_skip_telemetry.json", exists=telemetry_path.exists(), scanned_rows=scanned)
    )


def _aggregate_prompt_hook(route: dict[str, Any], root: Path, *, since: datetime) -> None:
    status_path = root / "aippocampus_prompt_hook_last_status.json"
    status = _read_json(status_path)
    scanned = 0
    if status:
        latest = status.get("last_prompt_hook")
        latest = latest if isinstance(latest, Mapping) else {}
        if _in_window(latest, since=since):
            scanned = 1
            foreground = _safe_int(latest.get("card_count"))
            source_backed = _safe_int(latest.get("source_backed_count"))
            candidates = _safe_int(latest.get("candidate_count"))
            route["yield"]["foreground_cards"] += foreground
            route["yield"]["source_backed_evidence_cards"] += source_backed
            route["yield"]["generated_candidates"] += candidates
            _add_foreground_value(route, latest, foreground + source_backed)
            surface = latest.get("memory_surface")
            if surface:
                _counter_increment(route["status_counts"], surface)
            warm_background = latest.get("warm_background")
            if isinstance(warm_background, Mapping):
                route["latest"]["warm_background_status"] = str(
                    warm_background.get("status") or "unknown"
                )
            _latest(route, "last_prompt_hook_at", latest)
    route["artifacts"].append(
        _artifact(root, "aippocampus_prompt_hook_last_status.json", exists=status_path.exists(), scanned_rows=scanned)
    )


def _foreground_value_count(route: Mapping[str, Any]) -> int:
    yield_value = route.get("yield")
    y: Mapping[str, Any] = yield_value if isinstance(yield_value, Mapping) else {}
    return (
        _safe_int(y.get("foreground_cards"))
        + _safe_int(y.get("source_backed_evidence_cards"))
        + _safe_int(y.get("source_reopen_follow_through"))
        + _safe_int(y.get("materialized_rows"))
    )


def _signal_count(route: Mapping[str, Any]) -> int:
    yield_value = route.get("yield")
    y: Mapping[str, Any] = yield_value if isinstance(yield_value, Mapping) else {}
    return max(
        1,
        _safe_int(y.get("generated_candidates"))
        + _safe_int(y.get("staging_rows"))
        + _safe_int(y.get("skip_events")),
    )


def _attach_route_metrics_and_warnings(
    routes: dict[str, dict[str, Any]],
    *,
    warn_effective_tokens: int,
    warn_min_foreground_value_rate: float,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for name, route in routes.items():
        value_count = _foreground_value_count(route)
        signal_count = _signal_count(route)
        value_rate = round(value_count / signal_count, 4)
        route["yield"]["foreground_value_count"] = value_count
        route["yield"]["foreground_value_rate"] = value_rate
        effective_tokens = _safe_int((route.get("spend") or {}).get("effective_tokens"))
        if effective_tokens >= warn_effective_tokens and value_rate < warn_min_foreground_value_rate:
            warning = {
                "code": f"low_yield_high_spend:{name}",
                "route": name,
                "effective_tokens": effective_tokens,
                "foreground_value_rate": value_rate,
                "thresholds": {
                    "effective_tokens": warn_effective_tokens,
                    "min_foreground_value_rate": warn_min_foreground_value_rate,
                },
                "message": (
                    "Recent model-backed work spent above the warning threshold "
                    "without enough foreground/materialized value. Inspect this route before launching more background work."
                ),
            }
            route["warnings"].append(warning)
            warnings.append(warning)
    return warnings


def _finalize_model_telemetry(routes: Mapping[str, dict[str, Any]]) -> None:
    for route in routes.values():
        telemetry = route.get("model_telemetry")
        if not isinstance(telemetry, dict):
            continue
        hit = _safe_int(telemetry.get("prompt_cache_hit_tokens"))
        miss = _safe_int(telemetry.get("prompt_cache_miss_tokens"))
        total = hit + miss
        telemetry["prompt_cache_hit_rate"] = round(hit / total, 4) if total else None
        latency = telemetry.get("latency_ms")
        if isinstance(latency, dict):
            count = _safe_int(latency.get("count"))
            total_latency = _safe_float(latency.get("total"))
            latency["average"] = round(total_latency / count, 2) if count else None
            latency["total"] = round(total_latency, 2)
            latency["max"] = round(_safe_float(latency.get("max")), 2)
        reasons = telemetry.get("usage_missing_reason_counts")
        if telemetry.get("usage_available"):
            telemetry["usage_missing_reason"] = None
        elif isinstance(reasons, Mapping) and len(reasons) > 1:
            telemetry["usage_missing_reason"] = "mixed"


def _subconscious_hook_enabled() -> bool:
    raw = os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    if raw is None:
        raw = os.environ.get("AIIPPOCAMPUS_SUBCONSCIOUS_HOOK", "1")
    return str(raw).strip().casefold() not in {"0", "false", "off", "no"}


def _dream_delivery_mode() -> str:
    raw = str(os.environ.get("AIPPOCAMPUS_DREAM_DELIVERY_MODE") or "off").strip().casefold()
    return raw if raw in {"off", "shadow", "delivered"} else "custom"


def _budget_guardrails(
    warnings: list[dict[str, Any]],
    *,
    warn_effective_tokens: int,
    warn_min_foreground_value_rate: float,
) -> dict[str, Any]:
    return {
        "warning_effective_tokens": warn_effective_tokens,
        "warning_min_foreground_value_rate": warn_min_foreground_value_rate,
        "routes_to_pause_or_inspect": sorted({str(item["route"]) for item in warnings}),
        "runtime_policy": {
            "prompt_hook_fail_open": True,
            "doctor_only_no_model_calls": True,
            "provider_billing_dashboard_scraped": False,
        },
        "operator_switches": {
            "warm_ambient": {
                "env": "AIPPOCAMPUS_WARM_RECALL_BACKGROUND",
                "enabled": warm_background_enabled(),
            },
            "semantic_gate": {
                "env": "AIPPOCAMPUS_SEMANTIC_GATE",
                "mode": semantic_gate_mode(),
            },
            "subconscious": {
                "env": "AIPPOCAMPUS_SUBCONSCIOUS_HOOK",
                "enabled": _subconscious_hook_enabled(),
            },
            "dream_delivery": {
                "env": "AIPPOCAMPUS_DREAM_DELIVERY_MODE",
                "mode": _dream_delivery_mode(),
            },
        },
    }


def _totals(routes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    spend_counter: Counter[str] = Counter()
    yield_counter: Counter[str] = Counter()
    for route in routes.values():
        for key, value in (route.get("spend") or {}).items():
            if isinstance(value, bool):
                continue
            spend_counter[key] += _safe_int(value)
        for key, value in (route.get("yield") or {}).items():
            if isinstance(value, float):
                continue
            yield_counter[key] += _safe_int(value)
    return {"spend": dict(spend_counter), "yield": dict(yield_counter)}


def build_spend_doctor_report(
    *,
    registry_dir: Path | str | None = None,
    days: int = DEFAULT_DAYS,
    now: str | datetime | None = None,
    warn_effective_tokens: int = DEFAULT_WARN_EFFECTIVE_TOKENS,
    warn_min_foreground_value_rate: float = DEFAULT_WARN_MIN_FOREGROUND_VALUE_RATE,
) -> dict[str, Any]:
    root = Path(registry_dir).resolve() if registry_dir else runtime_core.aippocampus_registry_dir()
    window_days = max(1, int(days or DEFAULT_DAYS))
    now_dt = _now(now)
    since = now_dt - timedelta(days=window_days)
    routes = _routes()
    _aggregate_warm(routes["warm_ambient"], root, since=since)
    _aggregate_subconscious(routes["subconscious"], root, since=since)
    _aggregate_semantic(routes["semantic_gate"], root, since=since)
    _aggregate_dream(routes["dream"], root, since=since)
    _aggregate_prompt_hook(routes["prompt_hook"], root, since=since)
    _finalize_model_telemetry(routes)
    warnings = _attach_route_metrics_and_warnings(
        routes,
        warn_effective_tokens=max(1, int(warn_effective_tokens)),
        warn_min_foreground_value_rate=max(0.0, _safe_float(warn_min_foreground_value_rate)),
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_spend_doctor",
        "ok": True,
        "status": "warning" if warnings else "ok",
        "generated_at": now_dt.isoformat().replace("+00:00", "Z"),
        "window": {
            "days": window_days,
            "since": since.isoformat().replace("+00:00", "Z"),
            "until": now_dt.isoformat().replace("+00:00", "Z"),
        },
        "privacy_boundary": {
            "raw_prompts_included": False,
            "raw_source_text_included": False,
            "api_keys_included": False,
            "local_paths_included": False,
            "provider_billing_credentials_included": False,
            "artifact_paths_included": False,
        },
        "routes": routes,
        "totals": _totals(routes),
        "warnings": warnings,
        "warning_codes": [str(item["code"]) for item in warnings],
        "budget_guardrails": _budget_guardrails(
            warnings,
            warn_effective_tokens=max(1, int(warn_effective_tokens)),
            warn_min_foreground_value_rate=max(0.0, _safe_float(warn_min_foreground_value_rate)),
        ),
        "reporting_boundary": {
            "registry_location_printed": False,
            "price_table_configured": False,
            "estimated_cost_supported": False,
            "cost_basis": "tokens_only_no_provider_billing_scrape",
        },
    }
    return runtime_core.sanitize_external_model_payload(report)


def render_text(report: Mapping[str, Any]) -> str:
    lines = [
        "AIppocampus spend doctor",
        f"- Status: {report.get('status')}",
        f"- Window: {(report.get('window') or {}).get('days')} days",
    ]
    totals_value = report.get("totals")
    totals: Mapping[str, Any] = totals_value if isinstance(totals_value, Mapping) else {}
    spend_value = totals.get("spend")
    spend: Mapping[str, Any] = spend_value if isinstance(spend_value, Mapping) else {}
    lines.append(f"- Effective tokens: {_safe_int(spend.get('effective_tokens'))}")
    for warning in report.get("warnings") or []:
        if isinstance(warning, Mapping):
            lines.append(f"- Warning: {warning.get('code')}")
    guardrails = report.get("budget_guardrails")
    if isinstance(guardrails, Mapping) and guardrails.get("routes_to_pause_or_inspect"):
        routes = ", ".join(str(item) for item in guardrails["routes_to_pause_or_inspect"])
        lines.append(f"- Inspect before more background work: {routes}")
    lines.append("- Privacy: aggregate counts only; no prompts, source text, keys, or local paths")
    lines.append("")
    return "\n".join(lines)
