#!/usr/bin/env python3
"""Storage-GC apply helpers for intentional rebuildable-cache eviction."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import (
    index_pointer_path,
    remove_sqlite_artifact,
    sqlite_sidecar_paths,
)
from aippocampus_runtime.core import file_sha256, now_utc
from aippocampus_runtime.ops.generation_eviction import (
    apply_generation_cleanup_candidate,
    candidate_is_supported_generation_cleanup,
)
from aippocampus_runtime.ops.storage_governance_contract import (
    CLASS_REBUILDABLE,
    SCHEMA_VERSION,
    TIER_REBUILDABLE_CACHE,
    human_bytes,
    status,
)

EVICTION_MANIFEST_KIND = "aippocampus_storage_eviction_manifest"
EVICTIONS_DIR_NAME = "evictions"
LOCK_FILENAMES = (
    ".index-publish.lock",
    ".rebuild.lock",
    ".build.lock",
    ".export.lock",
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{os.urandom(4).hex()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "candidate"


def _path_projection(path: Path, *, root: Path, include_paths: bool) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "path_label": path.name,
    }
    try:
        projection["relative_path"] = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        projection["relative_path"] = path.name
    if include_paths:
        projection["path"] = str(path)
    return projection


def _target_path(candidate: dict[str, Any]) -> Path | None:
    path = candidate.get("path") or {}
    value = path.get("path")
    return Path(str(value)).resolve() if value else None


def _owner_index_path(candidate: dict[str, Any]) -> Path | None:
    source_report = candidate.get("source_report") or {}
    owner = source_report.get("owner_index") or {}
    value = owner.get("path")
    return Path(str(value)).resolve() if value else None


def _sidecar_targets(path: Path) -> list[Path]:
    return [candidate for candidate in sqlite_sidecar_paths(path) if candidate.exists()]


def _active_locks(target: Path, index_dir: Path) -> list[Path]:
    roots = [index_dir, target.parent]
    if target.is_dir():
        roots.append(target)
    locks: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for filename in LOCK_FILENAMES:
            lock = root / filename
            if lock in seen:
                continue
            seen.add(lock)
            if lock.exists():
                locks.append(lock)
    return locks


def _failed_preconditions(
    candidate: dict[str, Any],
    *,
    target: Path,
    index_dir: Path,
    include_active: bool,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    source = deepcopy(candidate.get("preconditions") or {})
    failed: dict[str, dict[str, str]] = {}

    for name in ("raw_or_archive_source", "anchors_or_registry_refs"):
        item = source.get(name) or {}
        if item.get("status") != "passed":
            failed[name] = item or status(
                "blocked",
                evidence=f"{name} was not proven by the retention report.",
                requirement="Source and source refs must be proven before eviction.",
            )

    active = source.get("active_thread_exclusion") or {}
    if not include_active:
        failed["active_thread_exclusion"] = active or status(
            "blocked_by_default",
            evidence="--include-active was not passed.",
            requirement="Do not evict active-thread caches unless explicitly requested.",
        )
    else:
        source["active_thread_exclusion"] = status(
            "passed",
            evidence="--include-active was explicit for this apply run.",
            requirement="Do not evict active-thread caches unless explicitly requested.",
        )

    pointer_path = index_pointer_path(target)
    if pointer_path.exists():
        failed["last_known_good_pointer"] = status(
            "blocked",
            evidence=f"Version pointer exists at {pointer_path.name}; v1 does not mutate pointer state.",
            requirement="Apply mode must preserve last-known-good/index pointer semantics.",
        )
    else:
        source["last_known_good_pointer"] = status(
            "passed",
            evidence="No source_index.pointer.json was present for this stable cache path.",
            requirement="Apply mode must preserve last-known-good/index pointer semantics.",
        )

    source["writer_or_export_lease"] = status(
        "passed",
        evidence="No active build/export lease files were present for the target.",
        requirement="No active writer/build/export lease may own the target path.",
    )
    if _active_locks(target, index_dir):
        source["writer_or_export_lease"] = status(
            "blocked",
            evidence="A build/export lease file exists near the cache target.",
            requirement="No active writer/build/export lease may own the target path.",
        )
        failed["writer_or_export_lease"] = source["writer_or_export_lease"]

    return source, failed


def _block(candidate: dict[str, Any], reason_code: str, message: str, **extra: Any) -> dict[str, Any]:
    blocked = {
        "candidate_id": candidate.get("id"),
        "reason_code": reason_code,
        "message": message,
    }
    blocked.update(extra)
    return blocked


def _skip(candidate: dict[str, Any], reason_code: str, message: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("id"),
        "reason_code": reason_code,
        "message": message,
    }


def _candidate_is_supported(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("class") == CLASS_REBUILDABLE
        and candidate.get("tier") == TIER_REBUILDABLE_CACHE
        and str(candidate.get("kind") or "") == "rebuildable_generated_index"
        and str(candidate.get("id") or "") == "retention:rebuildable-main-sqlite"
    )


def _path_is_supported_main_sqlite(target: Path, owner_index: Path) -> bool:
    try:
        relative = target.resolve().relative_to(owner_index.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return relative == "source_index.sqlite"


def _path_level_required_block(candidate: dict[str, Any]) -> dict[str, Any]:
    return _block(
        candidate,
        "path_level_retention_required",
        "Retention candidate did not expose concrete target and owner index paths for apply.",
    )


def _unsafe_target_block(candidate: dict[str, Any]) -> dict[str, Any]:
    return _block(
        candidate,
        "unsafe_target_path",
        "Apply v1 only evicts the retention report's own index_dir/source_index.sqlite cache.",
    )


def _eviction_manifest_path(index_dir: Path, candidate: dict[str, Any]) -> Path:
    stamp = now_utc().replace(":", "").replace("-", "")
    return index_dir / EVICTIONS_DIR_NAME / f"storage-gc-{stamp}-{_safe_slug(str(candidate.get('id') or 'candidate'))}.json"


def _evict_sqlite_target(
    *,
    candidate: dict[str, Any],
    target: Path,
    index_dir: Path,
    include_paths: bool,
    source_preconditions: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], int]:
    if target.is_dir():
        targets = sorted(target.glob("seg-*/source_index.sqlite"))
    else:
        targets = [target]
    evictable = [item for item in targets if item.exists()]
    if not evictable:
        raise FileNotFoundError(str(target))

    recorded_paths: list[dict[str, Any]] = []
    reclaimed = 0
    for path in evictable:
        for artifact in [path, *_sidecar_targets(path)]:
            size = artifact.stat().st_size
            reclaimed += size
            item = {
                **_path_projection(artifact, root=index_dir, include_paths=include_paths),
                "bytes": size,
                "sha256": file_sha256(artifact),
            }
            if artifact != path:
                item["sidecar_of"] = path.name
            recorded_paths.append(item)
        remove_sqlite_artifact(path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVICTION_MANIFEST_KIND,
        "evicted_at": now_utc(),
        "eviction_status": "applied",
        "candidate_id": candidate.get("id"),
        "class": candidate.get("class"),
        "tier": candidate.get("tier"),
        "label": candidate.get("label"),
        "kind_label": candidate.get("kind"),
        "reason": "storage_gc_rebuildable_cache_eviction",
        "source_report": candidate.get("source_report"),
        "source_preconditions": source_preconditions,
        "evidence": candidate.get("evidence") or [],
        "evicted_paths": recorded_paths,
        "reclaimed_bytes": reclaimed,
        "reclaimed_human": human_bytes(reclaimed),
        "rebuild_command": candidate.get("rebuild_command"),
        "expected_rebuild_cost": candidate.get("expected_rebuild_cost"),
    }
    manifest_path = _eviction_manifest_path(index_dir, candidate)
    _json_atomic(manifest_path, manifest)
    applied = {
        "candidate_id": candidate.get("id"),
        "bytes": reclaimed,
        "human_bytes": human_bytes(reclaimed),
        "manifest_label": manifest_path.name,
        "evicted_path_count": len(recorded_paths),
    }
    if include_paths:
        applied["manifest"] = str(manifest_path)
    return applied, reclaimed


def apply_rebuildable_evictions(
    plan: dict[str, Any],
    *,
    include_active: bool,
    include_paths: bool,
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    reclaimed = 0
    has_supported_generation_cleanup = any(
        candidate_is_supported_generation_cleanup(candidate)
        for candidate in plan.get("candidates") or []
    )

    for candidate in plan.get("candidates") or []:
        source_report = candidate.get("source_report") or {}
        if candidate_is_supported_generation_cleanup(candidate):
            result = apply_generation_cleanup_candidate(
                candidate,
                include_active=include_active,
                include_paths=include_paths,
            )
            if result.get("applied"):
                applied.append(result["applied"])
                reclaimed += int(result.get("reclaimed_bytes") or 0)
            elif result.get("blocked"):
                blocked.append(result["blocked"])
            continue

        if source_report.get("kind") != "retention_report":
            if has_supported_generation_cleanup and source_report.get("kind") == "storage_capacity_report":
                skipped.append(
                    _skip(
                        candidate,
                        "plan_only_capacity_aggregate",
                        "Capacity aggregate candidates remain plan-only; generation cleanup candidates were handled separately.",
                    )
                )
                continue
            blocked.append(
                _block(
                    candidate,
                    "path_level_retention_required",
                    "Apply mode requires retention-report path-level evidence; capacity aggregates are dry-run only.",
                )
            )
            continue
        if not _candidate_is_supported(candidate):
            blocked.append(
                _block(
                    candidate,
                    "unsupported_rebuildable_candidate",
                    "Apply v1 supports rebuildable SQLite cache artifacts only.",
                )
            )
            continue
        target = _target_path(candidate)
        if target is None:
            blocked.append(_path_level_required_block(candidate))
            continue
        owner_index = _owner_index_path(candidate)
        if owner_index is None:
            blocked.append(_path_level_required_block(candidate))
            continue
        index_dir = owner_index
        if not _path_is_supported_main_sqlite(target, owner_index):
            blocked.append(_unsafe_target_block(candidate))
            continue
        source_preconditions, failed = _failed_preconditions(
            candidate,
            target=target,
            index_dir=index_dir,
            include_active=include_active,
        )
        if failed:
            reason_code = "active_lease" if "writer_or_export_lease" in failed else "precondition_failed"
            blocked.append(
                _block(
                    candidate,
                    reason_code,
                    "Storage GC apply preconditions failed.",
                    failed_preconditions=sorted(failed),
                    source_preconditions=source_preconditions,
                )
            )
            continue
        if not _is_relative_to(target, index_dir):
            blocked.append(
                _block(
                    candidate,
                    "unsafe_target_path",
                    "Target path is outside the resolved cache owner directory.",
                )
            )
            continue
        try:
            applied_item, bytes_reclaimed = _evict_sqlite_target(
                candidate=candidate,
                target=target,
                index_dir=index_dir,
                include_paths=include_paths,
                source_preconditions=source_preconditions,
            )
        except OSError as exc:
            blocked.append(
                _block(
                    candidate,
                    "eviction_failed",
                    f"Could not evict cache artifact: {type(exc).__name__}: {exc}",
                )
            )
            continue
        applied.append(applied_item)
        reclaimed += bytes_reclaimed

    return {
        "applied": applied,
        "blocked": blocked,
        "skipped": skipped,
        "reclaimed_bytes": reclaimed,
        "reclaimed_human": human_bytes(reclaimed),
    }


def latest_intentional_eviction(
    index_dir: Path,
    relative_path: str,
) -> dict[str, Any]:
    evictions_dir = index_dir / EVICTIONS_DIR_NAME
    if not evictions_dir.exists():
        return {"detected": False}
    matches: list[tuple[float, Path, dict[str, Any]]] = []
    for path in evictions_dir.glob("storage-gc-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("kind") != EVICTION_MANIFEST_KIND:
            continue
        if payload.get("eviction_status") != "applied":
            continue
        for item in payload.get("evicted_paths") or []:
            if item.get("relative_path") == relative_path:
                matches.append((path.stat().st_mtime, path, payload))
                break
    if not matches:
        return {"detected": False}
    _, path, payload = max(matches, key=lambda item: item[0])
    return {
        "detected": True,
        "rebuildable": payload.get("tier") == TIER_REBUILDABLE_CACHE,
        "manifest": str(path),
        "candidate_id": payload.get("candidate_id"),
        "rebuild_command": payload.get("rebuild_command"),
        "evicted_at": payload.get("evicted_at"),
    }
