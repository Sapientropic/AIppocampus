"""Exact semantic-gate result cache helpers.

This module owns the optimization cache for repeated semantic-gate prompts.
It deliberately reports only counts and value classes: cached aliases remain
routing hints, and clean-source reopening is still required before evidence can
be surfaced.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1
DEFAULT_MAX_CACHE_ENTRIES = 256
DEFAULT_CACHE_TTL_SECONDS = int(
    os.environ.get("AIPPOCAMPUS_SEMANTIC_CACHE_TTL", str(24 * 60 * 60))
)
CACHE_TELEMETRY_KEYS = (
    "lookups",
    "hits",
    "misses",
    "expired",
    "writes",
    "evictions",
)
_VALID_DECISIONS = {"skip", "background_only", "scent", "evidence"}
_DECISION_RANK = {"skip": 0, "background_only": 1, "scent": 2, "evidence": 3}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def _public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _public_confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def empty_cache_telemetry() -> dict[str, Any]:
    return {
        "lookups": 0,
        "hits": 0,
        "misses": 0,
        "expired": 0,
        "writes": 0,
        "evictions": 0,
        "eviction_reasons": {},
    }


def normalized_cache_telemetry(data: dict[str, Any]) -> dict[str, Any]:
    telemetry = data.get("telemetry")
    if not isinstance(telemetry, dict):
        telemetry = {}
    normalized = empty_cache_telemetry()
    for key in CACHE_TELEMETRY_KEYS:
        normalized[key] = _public_count(telemetry.get(key))
    reasons = telemetry.get("eviction_reasons")
    if isinstance(reasons, Mapping):
        normalized["eviction_reasons"] = {
            str(key): _public_count(value) for key, value in reasons.items()
        }
    return normalized


def _bump_cache_telemetry(
    data: dict[str, Any],
    key: str,
    amount: int = 1,
    *,
    eviction_reason: str | None = None,
) -> dict[str, Any]:
    telemetry = normalized_cache_telemetry(data)
    if key in CACHE_TELEMETRY_KEYS:
        telemetry[key] = _public_count(telemetry.get(key)) + max(0, int(amount))
    if eviction_reason:
        reasons = telemetry.setdefault("eviction_reasons", {})
        if isinstance(reasons, dict):
            reasons[eviction_reason] = _public_count(reasons.get(eviction_reason)) + max(
                0, int(amount)
            )
    data["telemetry"] = telemetry
    return telemetry


def _cache_entries(data: dict[str, Any]) -> dict[str, Any]:
    raw_entries = data.get("entries")
    return dict(raw_entries) if isinstance(raw_entries, dict) else {}


def _save_cache(path: Path, data: dict[str, Any]) -> None:
    _write_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "updated_at": now_utc(),
            "telemetry": normalized_cache_telemetry(data),
            "entries": _cache_entries(data),
        },
    )


def _cache_entry_is_expired(entry: Mapping[str, Any], *, ttl_seconds: int) -> bool:
    created = float(entry.get("created_unix") or 0.0)
    return bool(ttl_seconds > 0 and created and time.time() - created > ttl_seconds)


def _cache_value_metadata(result: Mapping[str, Any]) -> dict[str, Any]:
    decision = str(result.get("decision") or "skip")
    decision_score = _DECISION_RANK.get(decision, 0)
    diagnostics = result.get("cache_diagnostics")
    semantic_cue_key = bool(
        isinstance(diagnostics, Mapping) and diagnostics.get("semantic_cues_in_cache_key")
    )
    alias_count = (
        len(result.get("query_aliases") or [])
        if isinstance(result.get("query_aliases"), list)
        else 0
    )
    score = decision_score * 10.0 + _public_confidence(result.get("confidence")) * 10.0
    score += min(4, alias_count)
    value_class = decision if decision in _VALID_DECISIONS else "skip"
    if semantic_cue_key and decision_score >= _DECISION_RANK["scent"]:
        # This is eviction protection for source-backed cue reuse, not an
        # evidence claim. Cached aliases remain routing hints only.
        score += 8.0
        value_class = "source_backed_semantic_cue"
    return {
        "value_class": value_class,
        "value_score": round(score, 4),
        "protected": value_class == "source_backed_semantic_cue",
    }


def _cache_entry_for_result(
    result: dict[str, Any], *, previous: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    slim = dict(result)
    slim.pop("elapsed_ms", None)
    slim.pop("cached", None)
    now = time.time()
    return {
        "created_at": str((previous or {}).get("created_at") or now_utc()),
        "created_unix": float((previous or {}).get("created_unix") or now),
        "updated_at": now_utc(),
        "updated_unix": now,
        "hit_count": _public_count((previous or {}).get("hit_count")),
        "last_hit_at": (previous or {}).get("last_hit_at"),
        "last_hit_unix": float((previous or {}).get("last_hit_unix") or 0.0),
        **_cache_value_metadata(slim),
        "result": slim,
    }


def read_cache(
    path: Path,
    key: str,
    *,
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    data = _load_json(path)
    entries = _cache_entries(data)
    entry = entries.get(key)
    _bump_cache_telemetry(data, "lookups")
    if not isinstance(entry, dict):
        telemetry = _bump_cache_telemetry(data, "misses")
        if diagnostics is not None:
            diagnostics.update({"lookup": "miss", "telemetry": telemetry})
        if path.exists():
            _save_cache(path, {**data, "entries": entries})
        return None
    if _cache_entry_is_expired(entry, ttl_seconds=ttl_seconds):
        entries.pop(key, None)
        _bump_cache_telemetry(data, "misses")
        telemetry = _bump_cache_telemetry(data, "expired")
        if diagnostics is not None:
            diagnostics.update({"lookup": "expired", "telemetry": telemetry})
        _save_cache(path, {**data, "entries": entries})
        return None
    result = entry.get("result")
    if isinstance(result, dict):
        entry["hit_count"] = _public_count(entry.get("hit_count")) + 1
        entry["last_hit_at"] = now_utc()
        entry["last_hit_unix"] = time.time()
        entries[key] = entry
        telemetry = _bump_cache_telemetry(data, "hits")
        _save_cache(path, {**data, "entries": entries})
        if diagnostics is not None:
            diagnostics.update({"lookup": "hit", "telemetry": telemetry})
        result = dict(result)
        result["cached"] = True
        return result
    telemetry = _bump_cache_telemetry(data, "misses")
    if diagnostics is not None:
        diagnostics.update({"lookup": "miss", "telemetry": telemetry})
    _save_cache(path, {**data, "entries": entries})
    return None


def write_cache(
    path: Path,
    key: str,
    result: dict[str, Any],
    *,
    max_entries: int = DEFAULT_MAX_CACHE_ENTRIES,
) -> None:
    data = _load_json(path)
    entries = _cache_entries(data)
    entries[key] = _cache_entry_for_result(result, previous=entries.get(key))
    _bump_cache_telemetry(data, "writes")
    if len(entries) > max_entries:
        sorted_entries = sorted(
            entries.items(),
            key=lambda item: (
                bool((item[1] or {}).get("protected")),
                float((item[1] or {}).get("value_score") or 0.0),
                float(
                    (item[1] or {}).get("last_hit_unix")
                    or (item[1] or {}).get("updated_unix")
                    or (item[1] or {}).get("created_unix")
                    or 0.0
                ),
            ),
        )
        evict_count = len(entries) - max_entries
        for evicted_key, _entry in sorted_entries[:evict_count]:
            entries.pop(evicted_key, None)
        _bump_cache_telemetry(
            data,
            "evictions",
            evict_count,
            eviction_reason="low_value_churn",
        )
    _save_cache(path, {**data, "entries": entries})


def semantic_cache_report(
    path: Path, *, ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
) -> dict[str, Any]:
    data = _load_json(path)
    entries = _cache_entries(data)
    active = 0
    expired = 0
    protected = 0
    value_classes: dict[str, int] = {}
    for entry in entries.values():
        if not isinstance(entry, Mapping):
            continue
        if _cache_entry_is_expired(entry, ttl_seconds=ttl_seconds):
            expired += 1
        else:
            active += 1
        if entry.get("protected"):
            protected += 1
        value_class = str(entry.get("value_class") or "unknown")
        value_classes[value_class] = value_classes.get(value_class, 0) + 1
    return {
        "kind": "aippocampus_semantic_recall_cache_report",
        "schema_version": SCHEMA_VERSION,
        "entry_count": len(entries),
        "active_entry_count": active,
        "expired_entry_count": expired,
        "protected_entry_count": protected,
        "value_classes": value_classes,
        "telemetry": normalized_cache_telemetry(data),
        "output_boundary": "semantic_cache_report_counts_only",
    }
