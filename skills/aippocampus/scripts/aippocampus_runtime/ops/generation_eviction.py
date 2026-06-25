"""Apply-time eviction helpers for old generated artifact generations."""

from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.generation_pins import generation_cleanup_contract
from aippocampus_runtime.artifacts.publish import INDEX_POINTER_NAME, SEGMENTS_POINTER_NAME
from aippocampus_runtime.core import file_sha256, now_utc
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.ops.storage_governance_contract import (
    CLASS_REBUILDABLE,
    SCHEMA_VERSION,
    TIER_REBUILDABLE_CACHE,
    human_bytes,
    status,
)

EVICTION_MANIFEST_KIND = "aippocampus_storage_eviction_manifest"
EVICTIONS_DIR_NAME = "evictions"
GENERATION_CLEANUP_KINDS = {
    "rebuildable_old_index_generations",
    "rebuildable_old_segment_generations",
}
LOCK_FILENAMES = (
    ".index-publish.lock",
    ".rebuild.lock",
    ".build.lock",
    ".export.lock",
)


def candidate_is_supported_generation_cleanup(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("class") == CLASS_REBUILDABLE
        and candidate.get("tier") == TIER_REBUILDABLE_CACHE
        and str(candidate.get("kind") or "") in GENERATION_CLEANUP_KINDS
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "candidate"


def _path_projection(path: Path, *, root: Path, include_paths: bool) -> dict[str, Any]:
    projection: dict[str, Any] = {"path_label": path.name}
    try:
        projection["relative_path"] = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        projection["relative_path"] = path.name
    if include_paths:
        projection["path"] = str(path)
    return projection


def _block(candidate: dict[str, Any], reason_code: str, message: str, **extra: Any) -> dict[str, Any]:
    blocked = {
        "candidate_id": candidate.get("id"),
        "reason_code": reason_code,
        "message": message,
    }
    blocked.update(extra)
    return blocked


def _target_path(candidate: dict[str, Any]) -> Path | None:
    path = candidate.get("path") or {}
    value = path.get("path")
    return Path(str(value)).resolve() if value else None


def _active_locks(target: Path, index_dir: Path, *, pointer_parent: Path) -> list[Path]:
    roots = [index_dir, target.parent, pointer_parent]
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


def _generation_id_from_pointer_value(pointer_path: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = pointer_path.parent / candidate
    try:
        relative = candidate.relative_to(pointer_path.parent)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "generations" and parts[1].startswith("gen_"):
        return parts[1]
    return None


def _protected_pointer_generations(
    pointer_path: Path,
) -> tuple[set[str], dict[str, str] | None]:
    if not pointer_path.exists():
        return set(), status(
            "blocked",
            evidence=f"{pointer_path.name} is missing at apply time.",
            requirement="Generation cleanup must prove current and last-known-good pointer targets.",
        )
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), status(
            "blocked",
            evidence=f"{pointer_path.name} is unreadable at apply time: {type(exc).__name__}.",
            requirement="Generation cleanup must prove current and last-known-good pointer targets.",
        )
    if not isinstance(payload, dict):
        return set(), status(
            "blocked",
            evidence=f"{pointer_path.name} does not contain a JSON object.",
            requirement="Generation cleanup must prove current and last-known-good pointer targets.",
        )
    protected = {
        item
        for item in (
            payload.get("current_generation"),
            payload.get("last_known_good_generation"),
            _generation_id_from_pointer_value(pointer_path, payload.get("current")),
            _generation_id_from_pointer_value(pointer_path, payload.get("last_known_good")),
        )
        if isinstance(item, str) and item
    }
    if not protected:
        return set(), status(
            "blocked",
            evidence=f"{pointer_path.name} does not expose resolvable generation targets.",
            requirement="Generation cleanup must prove current and last-known-good pointer targets.",
        )
    return protected, None


def _generation_paths(candidate: dict[str, Any], target: Path) -> tuple[Path, Path, Path] | None:
    kind = str(candidate.get("kind") or "")
    if kind == "rebuildable_old_index_generations":
        if target.parent.name != "generations":
            return None
        pointer_parent = target.parent.parent
        return pointer_parent, pointer_parent / INDEX_POINTER_NAME, pointer_parent
    if kind == "rebuildable_old_segment_generations":
        if target.parent.name != "generations":
            return None
        pointer_parent = target.parent.parent
        if pointer_parent.name != "segments":
            return None
        return pointer_parent, pointer_parent / SEGMENTS_POINTER_NAME, pointer_parent.parent
    return None


def _failed_preconditions(
    candidate: dict[str, Any],
    *,
    target: Path,
    pointer_parent: Path,
    pointer_path: Path,
    index_dir: Path,
    include_active: bool,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    source = deepcopy(candidate.get("preconditions") or {})
    failed: dict[str, dict[str, str]] = {}

    for name in ("raw_or_clean_source", "clean_source_manifest"):
        item = source.get(name) or {}
        if item.get("status") != "passed":
            failed[name] = item or status(
                "blocked",
                evidence=f"{name} was not proven by the capacity report.",
                requirement="Generated generation cleanup must preserve rebuildable source.",
            )

    if not include_active:
        failed["active_thread_exclusion"] = source.get("active_thread_exclusion") or status(
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

    protected, pointer_failure = _protected_pointer_generations(pointer_path)
    if pointer_failure is not None:
        source["last_known_good_pointer"] = pointer_failure
        failed["last_known_good_pointer"] = pointer_failure
    elif target.name in protected:
        source["last_known_good_pointer"] = status(
            "blocked",
            evidence=f"{target.name} is still current or last-known-good in {pointer_path.name}.",
            requirement="Generation cleanup must preserve current and last-known-good pointer targets.",
        )
        failed["last_known_good_pointer"] = source["last_known_good_pointer"]
    else:
        source["last_known_good_pointer"] = status(
            "passed",
            evidence=f"{target.name} is not current or last-known-good in {pointer_path.name}.",
            requirement="Generation cleanup must preserve current and last-known-good pointer targets.",
        )

    cleanup = generation_cleanup_contract(pointer_parent, target, freshness_paths=[pointer_path])
    source["reader_pin_or_ttl_contract"] = status(
        cleanup["status"],
        evidence=", ".join(cleanup["evidence"]),
        requirement=cleanup["requirement"],
    )
    if cleanup["status"] != "passed":
        failed["reader_pin_or_ttl_contract"] = source["reader_pin_or_ttl_contract"]

    source["writer_or_export_lease"] = status(
        "passed",
        evidence="No active build/export lease files were present for the generation target.",
        requirement="No active writer/build/export lease may own the target path.",
    )
    if _active_locks(target, index_dir, pointer_parent=pointer_parent):
        source["writer_or_export_lease"] = status(
            "blocked",
            evidence="A build/export lease file exists near the generation target.",
            requirement="No active writer/build/export lease may own the target path.",
        )
        failed["writer_or_export_lease"] = source["writer_or_export_lease"]

    return source, failed


def _eviction_manifest_path(index_dir: Path, candidate: dict[str, Any]) -> Path:
    stamp = now_utc().replace(":", "").replace("-", "")
    return (
        index_dir
        / EVICTIONS_DIR_NAME
        / f"storage-gc-{stamp}-{_safe_slug(str(candidate.get('id') or 'candidate'))}.json"
    )


def _evict_generation_target(
    *,
    candidate: dict[str, Any],
    target: Path,
    index_dir: Path,
    include_paths: bool,
    source_preconditions: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], int]:
    if not target.is_dir():
        raise FileNotFoundError(str(target))

    recorded_paths: list[dict[str, Any]] = []
    reclaimed = 0
    for artifact in sorted(path for path in target.rglob("*") if path.is_file()):
        size = artifact.stat().st_size
        reclaimed += size
        recorded_paths.append(
            {
                **_path_projection(artifact, root=index_dir, include_paths=include_paths),
                "bytes": size,
                "sha256": file_sha256(artifact),
            }
        )
    shutil.rmtree(target)

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
        "reason": "storage_gc_old_generation_eviction",
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
    atomic_write_json(manifest_path, manifest, indent=2)
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


def apply_generation_cleanup_candidate(
    candidate: dict[str, Any],
    *,
    include_active: bool,
    include_paths: bool,
) -> dict[str, Any]:
    target = _target_path(candidate)
    if target is None:
        return {
            "blocked": _block(
                candidate,
                "path_level_retention_required",
                "Generation cleanup candidate did not expose a concrete target path.",
            ),
            "applied": None,
            "reclaimed_bytes": 0,
        }
    resolved = _generation_paths(candidate, target)
    if resolved is None:
        return {
            "blocked": _block(
                candidate,
                "unsafe_target_path",
                "Generation cleanup target is not an old index or segment generation directory.",
            ),
            "applied": None,
            "reclaimed_bytes": 0,
        }
    pointer_parent, pointer_path, index_dir = resolved
    if not _is_relative_to(target, index_dir):
        return {
            "blocked": _block(
                candidate,
                "unsafe_target_path",
                "Generation target is outside the resolved cache owner directory.",
            ),
            "applied": None,
            "reclaimed_bytes": 0,
        }

    source_preconditions, failed = _failed_preconditions(
        candidate,
        target=target,
        pointer_parent=pointer_parent,
        pointer_path=pointer_path,
        index_dir=index_dir,
        include_active=include_active,
    )
    if failed:
        return {
            "blocked": _block(
                candidate,
                "active_lease" if "writer_or_export_lease" in failed else "precondition_failed",
                "Storage GC generation cleanup preconditions failed.",
                failed_preconditions=sorted(failed),
                source_preconditions=source_preconditions,
            ),
            "applied": None,
            "reclaimed_bytes": 0,
        }
    try:
        applied, reclaimed = _evict_generation_target(
            candidate=candidate,
            target=target,
            index_dir=index_dir,
            include_paths=include_paths,
            source_preconditions=source_preconditions,
        )
    except OSError as exc:
        return {
            "blocked": _block(
                candidate,
                "eviction_failed",
                f"Could not evict generation artifact: {type(exc).__name__}: {exc}",
            ),
            "applied": None,
            "reclaimed_bytes": 0,
        }
    return {"applied": applied, "blocked": None, "reclaimed_bytes": reclaimed}
