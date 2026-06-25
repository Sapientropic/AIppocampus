"""Stale AIppocampus temp-artifact inventory and cleanup."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TMP_SUFFIX = ".tmp"
PLUGIN_INSTALL_TMP_SUFFIX = ".tmp-aippocampus-install"
TMP_PATTERN_ATOMIC_WRITE = "aippocampus_atomic_write_tmp"
TMP_PATTERN_LEGACY_THREADS_JSON = "legacy_threads_json_tmp_dash"
TMP_PATTERN_LEGACY_TMP_DASH = "legacy_tmp_dash"
TMP_PATTERN_SQLITE_BUILD = "sqlite_build_tmp_dir"
TMP_PATTERN_PLUGIN_INSTALL = "plugin_install_tmp_dir"


def _human_bytes(size: int) -> str:
    value = float(max(0, int(size)))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024 or unit == "PB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def tmp_artifact_pattern(path: Path) -> str | None:
    """Return the AIppocampus-owned temp pattern for a stale artifact candidate.

    Keep this list intentionally narrow. Registry/startup cleanup must never
    become a broad `*.tmp` broom because AIppocampus can live beside user-owned
    local artifacts. New writers that introduce a durable temp naming pattern
    should register it here instead of adding another ad hoc sweep.
    """

    name = path.name
    if path.is_dir() and name.endswith(PLUGIN_INSTALL_TMP_SUFFIX):
        return TMP_PATTERN_PLUGIN_INSTALL
    if path.is_dir() and ".sqlite-build-" in name:
        return TMP_PATTERN_SQLITE_BUILD
    if not path.is_file():
        return None
    if ".aippocampus-" in name and name.endswith(TMP_SUFFIX):
        return TMP_PATTERN_ATOMIC_WRITE
    if name.startswith(".threads.json.tmp-"):
        return TMP_PATTERN_LEGACY_THREADS_JSON
    if ".tmp-" in name:
        return TMP_PATTERN_LEGACY_TMP_DASH
    return None


def _path_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0
    return 0


def stale_tmp_artifacts(
    root: Path,
    *,
    max_age_seconds: float = 300.0,
    include_paths: bool = False,
) -> list[dict[str, Any]]:
    """Return stale AIppocampus-owned temp artifacts under `root`.

    The inventory is public-safe by default: it reports pattern, type, countable
    size, and a path label, not absolute local paths. It intentionally covers
    historical temp patterns seen in real registries in addition to the current
    `.aippocampus-*.tmp` writer contract.
    """

    now = time.time()
    artifacts: list[dict[str, Any]] = []
    if not root.exists():
        return artifacts
    for item in root.rglob("*"):
        pattern = tmp_artifact_pattern(item)
        if pattern is None:
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        age = now - stat.st_mtime
        if age < max_age_seconds:
            continue
        artifact: dict[str, Any] = {
            "pattern": pattern,
            "kind": "dir" if item.is_dir() else "file",
            "path_label": item.name,
            "bytes": _path_size(item),
            "age_seconds": int(age),
        }
        if include_paths:
            artifact["path"] = str(item)
        artifacts.append(artifact)
    artifacts.sort(key=lambda row: (str(row["pattern"]), str(row["path_label"])))
    return artifacts


def tmp_artifact_summary(artifacts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_pattern: dict[str, dict[str, Any]] = {}
    total_count = 0
    total_bytes = 0
    for item in artifacts:
        pattern = str(item.get("pattern") or "unknown")
        size = int(item.get("bytes") or 0)
        bucket = by_pattern.setdefault(
            pattern,
            {
                "count": 0,
                "bytes": 0,
                "human_bytes": "0 B",
            },
        )
        bucket["count"] = int(bucket["count"]) + 1
        bucket["bytes"] = int(bucket["bytes"]) + size
        bucket["human_bytes"] = _human_bytes(int(bucket["bytes"]))
        total_count += 1
        total_bytes += size
    return {
        "total_count": total_count,
        "total_bytes": total_bytes,
        "total_human_bytes": _human_bytes(total_bytes),
        "by_pattern": by_pattern,
    }


def cleanup_stale_tmp_artifacts(
    root: Path,
    *,
    max_age_seconds: float = 300.0,
    dry_run: bool = False,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Delete stale AIppocampus temp artifacts selected by `stale_tmp_artifacts`."""

    artifacts = stale_tmp_artifacts(
        root,
        max_age_seconds=max_age_seconds,
        include_paths=True,
    )
    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for artifact in artifacts:
        path = Path(str(artifact["path"]))
        public_artifact = dict(artifact)
        if not include_paths:
            public_artifact.pop("path", None)
        if dry_run:
            deleted.append(public_artifact)
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(public_artifact)
        except OSError as exc:
            failure = dict(public_artifact)
            failure["error_type"] = type(exc).__name__
            failed.append(failure)
    deleted_bytes = sum(int(item.get("bytes") or 0) for item in deleted)
    return {
        "kind": "aippocampus_stale_tmp_cleanup",
        "ok": not failed,
        "dry_run": dry_run,
        "deleted_count": len(deleted),
        "deleted_bytes": deleted_bytes,
        "deleted_human_bytes": _human_bytes(deleted_bytes),
        "failed_count": len(failed),
        "summary_before_cleanup": tmp_artifact_summary(artifacts),
        "deleted": deleted[:12],
        "failed": failed[:12],
    }


def stale_tmp_recovery_card(root: Path, *, max_age_seconds: float = 300.0) -> dict[str, Any]:
    """Inspect AIppocampus temporary artifacts under one root.

    The card is safe for foreground startup/readiness paths: it reports counts
    and one recovery command, not private paths. Callers that own a specific
    operator view may expose exact paths behind an explicit detail mode.
    """

    artifacts = stale_tmp_artifacts(root, max_age_seconds=max_age_seconds)
    summary = tmp_artifact_summary(artifacts)
    stale_tmp = sum(1 for item in artifacts if item.get("kind") == "file")
    plugin_orphans = int(
        summary["by_pattern"].get(TMP_PATTERN_PLUGIN_INSTALL, {}).get("count") or 0
    )
    found = int(summary["total_count"])
    return {
        "kind": "aippocampus_interrupted_write_recovery",
        "ok": found == 0,
        "status": "ok" if found == 0 else "interrupted_write_artifacts_found",
        "checked_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "stale_tmp_file_count": stale_tmp,
        "orphaned_plugin_install_dir_count": plugin_orphans,
        "stale_tmp_total_bytes": summary["total_bytes"],
        "stale_tmp_total_human_bytes": summary["total_human_bytes"],
        "stale_tmp_by_pattern": summary["by_pattern"],
        "foreground_action": (
            {
                "id": "review_interrupted_writes",
                "command": "aippocampus maintenance status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "local_recovery_diagnostic_not_source_truth",
                "why": "Interrupted write artifacts were detected; review maintenance before relying on generated recall state.",
            }
            if found
            else {
                "id": "no_interrupted_write_artifacts",
                "kind": "no_op",
                "mutation_risk": "none",
                "claim_boundary": "local_recovery_diagnostic_not_source_truth",
                "why": "No stale AIppocampus tmp or orphaned plugin install artifacts were detected.",
            }
        ),
        "safe_next_actions": (
            [
                {
                    "id": "inspect_interrupted_writes",
                    "command": "aippocampus maintenance status --json",
                    "mutation_risk": "read_only",
                    "claim_boundary": "local_recovery_diagnostic_not_source_truth",
                    "why": "Inspect counts and recovery state without mutating local storage.",
                },
                {
                    "id": "cleanup_interrupted_writes",
                    "command": (
                        "aippocampus maintenance apply --cleanup-interrupted-writes "
                        "--summary-json"
                    ),
                    "mutation_risk": "explicit_local_delete_of_ai_owned_tmp_artifacts",
                    "claim_boundary": "local_recovery_action_not_source_truth",
                    "why": "Delete only stale AIppocampus-owned temp artifacts after reviewing the recovery card.",
                },
            ]
            if found
            else []
        ),
    }
