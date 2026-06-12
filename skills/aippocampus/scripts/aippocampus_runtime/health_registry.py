#!/usr/bin/env python3
"""Privacy-safe registry-wide health aggregation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.registry.store import registry_paths
from aippocampus_runtime.warm_ambient.hook_seen_threads import (
    hook_seen_ledger_path_for_registry,
    hook_seen_registry_diagnostic,
)


def load_json_fail_open(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_stat_size(path: Path | None, default: int = 0) -> int:
    if path is None:
        return default
    try:
        return path.stat().st_size if path.exists() else default
    except OSError:
        return default


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds_since(value: Any, *, now: datetime | None = None) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - parsed).total_seconds()))


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(max(0, numerator)) / float(denominator), 4)


def privacy_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def registry_health_report(
    *,
    registry_dir: str | Path | None = None,
    top: int = 10,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Return a privacy-safe registry-wide health rollup.

    The aggregate view is intentionally manifest-only: it reads registry rows
    and generated health/index manifests, not raw rollout or clean-source text.
    Default output uses stable hashed refs instead of local paths or titles so
    fleet health does not become a private-history disclosure surface.
    """
    registry_root_dir = (
        Path(registry_dir).resolve() if registry_dir else registry_paths(None)[0].parent
    )
    registry_path, _registry_md = registry_paths(registry_root_dir)
    registry = load_json_fail_open(registry_path)
    threads = [item for item in registry.get("threads") or [] if isinstance(item, dict)]
    hook_seen_reconciliation = hook_seen_registry_diagnostic(
        hook_seen_ledger_path_for_registry(registry_path),
        registered_thread_keys=[str(item.get("thread_key") or "") for item in threads],
        include_private_keys=include_paths,
    )
    action_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    status_counts = {"ok": 0, "needs_maintenance": 0, "unknown": 0}
    high_risk_threads: list[dict[str, Any]] = []
    total_rollout_bytes = 0
    total_index_bytes = 0
    total_clean_source_bytes = 0

    for entry in threads:
        thread_key = str(entry.get("thread_key") or entry.get("id") or "")
        paths = entry.get("paths") or {}
        thread_store = paths.get("registry_thread_store")
        thread_dir = Path(thread_store) if thread_store else None
        if thread_dir and not thread_dir.is_absolute():
            thread_dir = registry_root_dir / thread_dir
        if thread_key and (thread_dir is None or not thread_dir.exists()):
            candidate = registry_root_dir / "threads" / (thread_key.replace(":", "-") or "")
            thread_dir = candidate if candidate.exists() else None

        index_manifest = (
            load_json_fail_open(thread_dir / "index" / "manifest.json") if thread_dir else {}
        )
        clean_manifest = (
            load_json_fail_open(thread_dir / "clean-source" / "manifest.json")
            if thread_dir
            else {}
        )
        segments_manifest = (
            load_json_fail_open(thread_dir / "segments" / "manifest.json") if thread_dir else {}
        )
        raw_health = entry.get("health")
        health: dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        actions = [
            action_item
            for action_item in health.get("recommended_actions") or []
            if isinstance(action_item, dict)
        ]
        if health.get("ok") is True:
            status_counts["ok"] += 1
        elif health.get("ok") is False:
            status_counts["needs_maintenance"] += 1
        else:
            status_counts["unknown"] += 1
        for action_item in actions:
            action_id = str(action_item.get("id") or "unknown")
            severity = str(action_item.get("severity") or "unknown")
            action_counts[action_id] = action_counts.get(action_id, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        rollout_size = safe_int(entry.get("rollout_size"))
        total_rollout_bytes += rollout_size
        if thread_dir:
            total_index_bytes += safe_stat_size(
                resolve_sqlite_index_path(thread_dir / "index" / "source_index.sqlite")
            )
            total_clean_source_bytes += sum(
                safe_stat_size(thread_dir / "clean-source" / filename)
                for filename in ("manifest.json", "messages.jsonl", "turns.jsonl", "events.jsonl")
            )
        message_count = safe_int(entry.get("message_count"))
        indexed_message_count = safe_int(index_manifest.get("message_count"))
        message_delta = max(0, message_count - indexed_message_count)
        stale_age = age_seconds_since(index_manifest.get("created_at"))

        risk = (
            len(actions) * 1000
            + message_delta * 10
            + safe_int(entry.get("rollout_size")) // max(1, 1024 * 1024)
            + ((stale_age or 0) // 3600)
        )
        if risk > 0:
            row: dict[str, Any] = {
                "thread_ref": privacy_ref(thread_key or str(thread_dir or "")),
                "health_ok": health.get("ok") if "ok" in health else None,
                "message_count": message_count,
                "rollout_size": rollout_size,
                "index_message_delta": message_delta,
                "index_stale_age_seconds": stale_age,
                "recommended_action_ids": [str(item.get("id") or "unknown") for item in actions],
                "has_clean_source": bool(clean_manifest),
                "has_index": bool(index_manifest),
                "has_segments": bool(segments_manifest),
                "risk_score": risk,
            }
            if include_paths:
                row["thread_key"] = thread_key
                row["thread_dir"] = str(thread_dir) if thread_dir else None
            high_risk_threads.append(row)

    high_risk_threads.sort(key=lambda item: int(item.get("risk_score") or 0), reverse=True)
    return {
        "ok": (
            status_counts["needs_maintenance"] == 0
            and status_counts["unknown"] == 0
            and hook_seen_reconciliation["status"] == "ok"
        ),
        "registry": str(registry_path) if include_paths else None,
        "thread_count": len(threads),
        "status_counts": status_counts,
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "source_intake": {
            "hook_seen_registry_reconciliation": hook_seen_reconciliation,
        },
        "storage": {
            "rollout_bytes": total_rollout_bytes,
            "clean_source_bytes": total_clean_source_bytes,
            "generated_index_bytes": total_index_bytes,
            "index_amplification_ratio": ratio(total_index_bytes, total_clean_source_bytes),
        },
        "top_threads": high_risk_threads[: max(0, top)],
        "privacy": {
            "default_identifiers": "sha256 thread refs only",
            "message_bodies_read": False,
            "paths_included": include_paths,
        },
    }
