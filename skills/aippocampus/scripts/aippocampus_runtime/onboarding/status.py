#!/usr/bin/env python3
"""Read-only status diagnostics for agent-native Codex onboarding.

This module inspects registry rows, manifests, and SQLite freshness. It must not
repair artifacts, register rollouts, run frontier jobs, or write onboarding
outputs; `aippocampus_runtime.onboarding.codex` owns that orchestration.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aippocampus_runtime.registry.api import load_registry, registry_paths
from aippocampus_runtime.source.io_kernel import load_json_dict


def path_exists(value: Any) -> bool:
    if not value:
        return False
    try:
        return Path(str(value)).exists()
    except OSError:
        return False


def load_json_file(path: Path) -> dict[str, Any]:
    return load_json_dict(path).data


def maybe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_source_line_range(message: dict[str, Any]) -> tuple[int, int] | None:
    start = maybe_int(message.get("raw_start_line") or message.get("source_line"))
    end = maybe_int(message.get("raw_end_line") or message.get("source_line") or start)
    if start is None or end is None:
        return None
    return min(start, end), max(start, end)


def clean_source_missing_sqlite_lines(
    clean_source_messages: Path, sqlite_path: Path, *, sample_limit: int = 5
) -> dict[str, Any]:
    try:
        con = sqlite3.connect(sqlite_path)
        try:
            rows = con.execute("SELECT line FROM messages").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"checked": 0, "missing_count": 0, "samples": [], "error": str(exc)}
    sqlite_lines = {int(row[0]) for row in rows if row and row[0] is not None}
    checked = 0
    missing_count = 0
    samples: list[dict[str, Any]] = []
    try:
        with clean_source_messages.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                line_range = clean_source_line_range(message)
                if not line_range:
                    continue
                checked += 1
                start, end = line_range
                if any(
                    raw_line in sqlite_lines for raw_line in range(start, min(end, start + 100) + 1)
                ):
                    continue
                missing_count += 1
                if len(samples) < sample_limit:
                    samples.append(
                        {
                            "message_id": message.get("message_id") or message.get("id"),
                            "line_start": start,
                            "line_end": end,
                        }
                    )
    except OSError as exc:
        return {
            "checked": checked,
            "missing_count": missing_count,
            "samples": samples,
            "error": str(exc),
        }
    return {"checked": checked, "missing_count": missing_count, "samples": samples}


def same_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return str(left).casefold() == str(right).casefold()


def sqlite_consistency_issues(entry: dict[str, Any]) -> list[dict[str, Any]]:
    paths = entry.get("paths") or {}
    clean_messages = Path(str(paths.get("clean_source_messages_jsonl") or ""))
    sqlite_path = Path(str(paths.get("sqlite") or ""))
    if not clean_messages.exists() or not sqlite_path.exists():
        return []
    issues: list[dict[str, Any]] = []
    clean_manifest = load_json_file(clean_messages.parent / "manifest.json")
    index_manifest = load_json_file(sqlite_path.parent / "manifest.json")
    if clean_manifest and index_manifest:
        clean_rollout = str(clean_manifest.get("source_rollout") or "")
        index_rollout = str(index_manifest.get("source_rollout") or "")
        if clean_rollout and index_rollout and not same_path(clean_rollout, Path(index_rollout)):
            issues.append({"code": "source_rollout_mismatch"})
        clean_size = maybe_int(clean_manifest.get("source_rollout_size"))
        index_size = maybe_int(index_manifest.get("source_rollout_size"))
        if clean_size is not None and index_size is not None and clean_size > index_size:
            issues.append(
                {
                    "code": "source_rollout_size_behind",
                    "clean_source_size": clean_size,
                    "sqlite_source_size": index_size,
                }
            )
        clean_mtime = maybe_float(clean_manifest.get("source_rollout_mtime"))
        index_mtime = maybe_float(index_manifest.get("source_rollout_mtime"))
        if clean_mtime is not None and index_mtime is not None and clean_mtime > index_mtime:
            issues.append({"code": "source_rollout_mtime_behind"})
        clean_count = maybe_int(clean_manifest.get("message_count"))
        index_count = maybe_int(index_manifest.get("message_count"))
        if clean_count is not None and index_count is not None and clean_count > index_count:
            issues.append(
                {
                    "code": "message_count_behind",
                    "clean_source_messages": clean_count,
                    "sqlite_messages": index_count,
                }
            )
    # Opening every SQLite file and scanning every clean-source line makes
    # full-machine onboarding unnecessarily slow. Use manifest freshness as
    # the cheap gate, then do the line-level probe only when the manifests
    # already suggest the index may lag behind clean source.
    if issues or not clean_manifest or not index_manifest:
        line_probe = clean_source_missing_sqlite_lines(clean_messages, sqlite_path)
        if line_probe.get("error"):
            issues.append({"code": "sqlite_line_probe_failed", "message": line_probe["error"]})
        elif int(line_probe.get("missing_count") or 0) > 0:
            issues.append(
                {
                    "code": "missing_clean_source_lines",
                    "checked": line_probe.get("checked"),
                    "missing_count": line_probe.get("missing_count"),
                    "samples": line_probe.get("samples") or [],
                }
            )
    return issues


def registry_stats(*, registry_dir: Path | None = None) -> dict[str, Any]:
    json_path, _ = registry_paths(registry_dir)
    registry = load_registry(json_path)
    threads = [entry for entry in registry.get("threads") or [] if isinstance(entry, dict)]
    clean_count = 0
    sqlite_count = 0
    graph_count = 0
    rollout_count = 0
    missing: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for entry in threads:
        paths = entry.get("paths") or {}
        missing_fields: list[str] = []
        if path_exists(paths.get("rollout")):
            rollout_count += 1
        if path_exists(paths.get("clean_source_messages_jsonl")):
            clean_count += 1
        else:
            missing_fields.append("clean_source")
        if path_exists(paths.get("sqlite")):
            sqlite_count += 1
        else:
            missing_fields.append("sqlite_index")
        if path_exists(paths.get("graph_json")):
            graph_count += 1
        else:
            missing_fields.append("graph_json")
        if missing_fields:
            missing.append(
                {
                    "thread_key": entry.get("thread_key"),
                    "title": entry.get("title"),
                    "source_provider": entry.get("source_provider")
                    or (entry.get("session_meta") or {}).get("source"),
                    "rollout": paths.get("rollout"),
                    "workspace": paths.get("workspace"),
                    "missing": missing_fields,
                }
            )
        else:
            issues = sqlite_consistency_issues(entry)
            if issues:
                stale.append(
                    {
                        "thread_key": entry.get("thread_key"),
                        "title": entry.get("title"),
                        "source_provider": entry.get("source_provider")
                        or (entry.get("session_meta") or {}).get("source"),
                        "rollout": paths.get("rollout"),
                        "workspace": paths.get("workspace"),
                        "stale": ["sqlite_index"],
                        "issues": issues,
                    }
                )
    repair_artifacts = [*missing, *stale]
    return {
        "registry": str(json_path),
        "thread_count": len(threads),
        "rollout_count": rollout_count,
        "clean_source_count": clean_count,
        "sqlite_index_count": sqlite_count,
        "graph_json_count": graph_count,
        "missing_clean": len([item for item in missing if "clean_source" in item["missing"]]),
        "missing_sqlite": len([item for item in missing if "sqlite_index" in item["missing"]]),
        "missing_graph_json": len([item for item in missing if "graph_json" in item["missing"]]),
        "missing_artifacts": missing,
        "stale_sqlite": len(stale),
        "stale_artifacts": stale,
        "repair_artifacts": repair_artifacts,
    }


def public_registry_stats(stats: dict[str, Any]) -> dict[str, Any]:
    private_detail_keys = {"missing_artifacts", "stale_artifacts", "repair_artifacts"}
    return {key: value for key, value in stats.items() if key not in private_detail_keys}


def infer_project_label_for_cwd(cwd: Path, registry_path: Path) -> str | None:
    registry = load_registry(registry_path)
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        paths = entry.get("paths") or {}
        if same_path(paths.get("workspace"), cwd):
            return str(entry.get("project_label") or entry.get("workspace_name") or cwd.name)
    return cwd.name if cwd.name else None


def resolve_frontier_project_scope(
    *,
    cwd: Path,
    registry_path: Path,
    project: str | None,
    frontier_project: str | None,
) -> tuple[str | None, str]:
    if frontier_project:
        value = frontier_project.strip()
        if value in {"*", "all", "global"}:
            return None, "explicit_global"
        return value, "explicit_frontier_project"
    if project:
        return project, "project_arg"
    inferred = infer_project_label_for_cwd(cwd, registry_path)
    if inferred:
        return inferred, "cwd_registry_or_name"
    return None, "global_fallback"
