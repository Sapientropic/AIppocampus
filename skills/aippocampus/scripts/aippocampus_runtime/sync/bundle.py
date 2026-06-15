#!/usr/bin/env python3
"""Local-folder sync bundle for AIppocampus generated memory artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.core import aippocampus_registry_dir, file_sha256, now_utc, safe_path_name
from aippocampus_runtime.sync.contract import (
    LOCAL_FOLDER_BACKEND,
    SYNC_BUNDLE_KIND,
    SYNC_MANIFEST_NAME,
    SYNC_SCHEMA_VERSION,
    build_sync_manifest,
)

CLEAN_SOURCE_CHUNK_BYTES = 1024 * 1024
CLEAN_SOURCE_CHUNK_STORE = "clean-source-chunks"
CLEAN_SOURCE_CHUNK_MANIFEST = Path(CLEAN_SOURCE_CHUNK_STORE) / "manifest.json"
CLEAN_SOURCE_CHUNKED_FILES = (
    "messages.jsonl",
    "turns.jsonl",
    "events.jsonl",
    "source-texture.jsonl",
    "semantic-scope-labels.jsonl",
)
CLEAN_SOURCE_PATH_KEYS = (
    ("messages.jsonl", "clean_source_messages_jsonl"),
    ("turns.jsonl", "clean_source_turns_jsonl"),
    ("events.jsonl", "clean_source_events_jsonl"),
    ("source-texture.jsonl", "clean_source_texture_jsonl"),
)
ROOT_SIDECARS = (
    "threads.json",
    "threads.md",
    "associations.json",
    "cognitive_map.json",
    "concept_index.sqlite",
    "semantic_triggers.jsonl",
    "working_memory.jsonl",
)
MANAGED_SYNC_DIRS = ("registry", "raw-rollouts")
THREAD_FILES = (
    ("clean-source", "manifest.json"),
    ("index", "manifest.json"),
    ("index", "graph.json"),
)


class SyncManifestError(ValueError):
    """Raised when an existing sync manifest is present but cannot be trusted."""


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_sync_manifest(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(f"missing sync manifest: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncManifestError(f"invalid sync manifest JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SyncManifestError(f"sync manifest must be a JSON object: {path}")
    return data


def validate_existing_sync_manifest(path: Path) -> dict[str, Any]:
    manifest = load_sync_manifest(path)
    if (
        manifest.get("kind") != SYNC_BUNDLE_KIND
        or manifest.get("schema_version") != SYNC_SCHEMA_VERSION
    ):
        raise SyncManifestError(f"unrecognized sync manifest: {path}")
    return manifest


def _relative_sync_path_parts(value: str | Path) -> tuple[str, ...]:
    text = str(value).replace("\\", "/")
    path = Path(text)
    parts = path.parts
    drive_like = bool(parts and len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha())
    if (
        "\x00" in text
        or path.is_absolute()
        or path.drive
        or drive_like
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"unsafe sync manifest path: {value}")
    return tuple(str(part) for part in parts)


def validate_relative_sync_path(value: str | Path) -> Path:
    return Path(*_relative_sync_path_parts(value))


def sync_path_under(root: Path, relative_path: str | Path) -> Path:
    parts = _relative_sync_path_parts(relative_path)
    # Sync manifest paths are logical POSIX-like locators. Join only validated
    # components so object keys and bundle manifests cannot smuggle separators,
    # drives, or parent traversal into filesystem sinks before containment check.
    path = root.joinpath(*parts)
    return ensure_within(root, path)


def ensure_within(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"path escapes sync boundary: {path}")
    return resolved_path


def paths_overlap(left: Path, right: Path) -> bool:
    resolved_left = left.resolve()
    resolved_right = right.resolve()
    return (
        resolved_left == resolved_right
        or resolved_left in resolved_right.parents
        or resolved_right in resolved_left.parents
    )


def sync_file_entry(sync_root: Path, relative_path: Path) -> dict:
    path = sync_path_under(sync_root, relative_path)
    return {
        "path": relative_path.as_posix(),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def iter_registry_sync_files(registry_dir: Path) -> Iterable[tuple[Path, Path]]:
    registry_dir = registry_dir.resolve()
    for name in ROOT_SIDECARS:
        source = registry_dir / name
        if source.is_file():
            yield source, Path("registry") / name

    threads_dir = registry_dir / "threads"
    if not threads_dir.exists():
        return
    for thread_dir in sorted(item for item in threads_dir.iterdir() if item.is_dir()):
        for parts in THREAD_FILES:
            source = thread_dir.joinpath(*parts)
            if source.is_file():
                yield source, Path("registry") / "threads" / thread_dir.name / Path(*parts)


def iter_clean_source_sync_files(registry_dir: Path) -> Iterable[tuple[Path, Path]]:
    registry_dir = registry_dir.resolve()
    threads_dir = registry_dir / "threads"
    if not threads_dir.exists():
        return
    for thread_dir in sorted(item for item in threads_dir.iterdir() if item.is_dir()):
        clean_root = thread_dir / "clean-source"
        for name in CLEAN_SOURCE_CHUNKED_FILES:
            source = clean_root / name
            if source.is_file():
                yield source, Path("registry") / "threads" / thread_dir.name / "clean-source" / name


def iter_raw_rollout_files(registry_dir: Path) -> Iterable[tuple[Path, Path]]:
    registry = load_json(registry_dir / "threads.json")
    for entry in registry.get("threads") or []:
        rollout = (entry.get("paths") or {}).get("rollout")
        if not rollout:
            continue
        source = Path(rollout)
        if not source.is_file():
            continue
        thread_key = safe_path_name(str(entry.get("thread_key") or source.stem), "thread")
        yield source, Path("raw-rollouts") / f"{thread_key}.jsonl"


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def thread_dir_name(thread_key: str, fallback: str = "thread") -> str:
    return safe_path_name(thread_key, fallback)


def clean_source_path_fields(
    clean_root: Path,
    locator_root: Path,
    *,
    portable: bool,
) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for filename, key in CLEAN_SOURCE_PATH_KEYS:
        locator = locator_root / filename
        fields[key] = (
            locator.as_posix() if portable else str(locator)
        ) if (clean_root / filename).is_file() else None
    return fields


def portable_registry_for_sync(registry_dir: Path, *, include_raw: bool) -> dict[str, Any]:
    registry = load_json(registry_dir / "threads.json")
    portable = dict(registry)
    threads = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        key = str(item.get("thread_key") or "")
        thread_root = Path("registry") / "threads" / thread_dir_name(key)
        local_thread_root = registry_dir / "threads" / thread_dir_name(key)
        paths = dict(item.get("paths") or {})

        # Sync bundles should not canonize source-device absolute paths. Keep
        # generated artifacts as bundle-relative locators; target-device pull
        # repairs them to local absolute paths. User workspace/rollout paths are
        # device locators, so they are cleared unless raw rollout was explicitly
        # included in the bundle.
        paths["workspace"] = None
        paths["registry_thread_store"] = (
            thread_root.as_posix() if local_thread_root.exists() else None
        )
        clean_root = local_thread_root / "clean-source"
        paths["clean_source_dir"] = (
            (thread_root / "clean-source").as_posix() if clean_root.exists() else None
        )
        paths.update(clean_source_path_fields(clean_root, thread_root / "clean-source", portable=True))
        index_root = local_thread_root / "index"
        paths["index_dir"] = (thread_root / "index").as_posix() if index_root.exists() else None
        paths["graph_json"] = (
            (thread_root / "index" / "graph.json").as_posix()
            if (index_root / "graph.json").is_file()
            else None
        )
        paths["messages_jsonl"] = (
            (thread_root / "index" / "messages.jsonl").as_posix()
            if (index_root / "messages.jsonl").is_file()
            else None
        )
        # Generated SQLite caches, including generation pointer targets, are not
        # a portable source surface. Target devices repair this locator only
        # after a local rebuild creates a cache in the target registry.
        paths["sqlite"] = None
        raw_name = Path("raw-rollouts") / f"{thread_dir_name(key)}.jsonl"
        raw_source = paths.get("rollout")
        paths["rollout"] = (
            raw_name.as_posix()
            if include_raw and raw_source and Path(raw_source).is_file()
            else None
        )
        item["paths"] = paths
        item["path_locator_policy"] = {
            "kind": "portable_sync_locators",
            "generated_artifacts": "bundle_relative",
            "workspace": "device_local_unresolved",
            "raw_rollout": "excluded_unless_include_raw",
        }
        threads.append(item)
    portable["threads"] = threads
    portable["sync_portable_paths"] = True
    return portable


def write_sync_file(
    source: Path, destination: Path, *, registry_root: Path, relative_path: Path, include_raw: bool
) -> None:
    if relative_path.as_posix() == "registry/threads.json":
        save_json(destination, portable_registry_for_sync(registry_root, include_raw=include_raw))
        return
    copy_file(source, destination)


def clean_source_chunk_path(chunk_hash: str) -> Path:
    return Path(CLEAN_SOURCE_CHUNK_STORE) / "sha256" / chunk_hash[:2] / f"{chunk_hash}.chunk"


def write_clean_source_chunks(source: Path, sync_root: Path, logical_path: Path) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    file_hash = hashlib.sha256()
    total = 0
    ordinal = 0
    with source.open("rb") as handle:
        while True:
            data = handle.read(CLEAN_SOURCE_CHUNK_BYTES)
            if not data:
                break
            chunk_hash = bytes_sha256(data)
            chunk_path = clean_source_chunk_path(chunk_hash)
            destination = sync_path_under(sync_root, chunk_path)
            if not destination.is_file() or file_sha256(destination) != chunk_hash:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            chunks.append(
                {
                    "ordinal": ordinal,
                    "offset": total,
                    "path": chunk_path.as_posix(),
                    "size": len(data),
                    "sha256": chunk_hash,
                }
            )
            file_hash.update(data)
            total += len(data)
            ordinal += 1
    return {
        "path": logical_path.as_posix(),
        "size": total,
        "sha256": file_hash.hexdigest(),
        "chunks": chunks,
    }


def write_clean_source_delta(sync_root: Path, registry_root: Path) -> tuple[dict[str, Any], list[dict]]:
    files = [
        write_clean_source_chunks(source, sync_root, relative_path)
        for source, relative_path in iter_clean_source_sync_files(registry_root)
    ]
    chunk_paths = sorted(
        {chunk["path"] for item in files for chunk in item.get("chunks", [])}
    )
    delta = {
        "kind": "content_addressed_clean_source_chunks",
        "schema_version": 1,
        "chunk_bytes": CLEAN_SOURCE_CHUNK_BYTES,
        "generated_cache_export": "explicit_only",
        "file_count": len(files),
        "chunk_count": len(chunk_paths),
        "files": files,
        "privacy_boundary": {
            "contains_private_clean_source_text": True,
            "chunk_ids_are_content_hashes": True,
            "generated_caches": "excluded_unless_explicit_export_mode",
        },
    }
    if not files:
        return delta, []
    save_json(sync_root / CLEAN_SOURCE_CHUNK_MANIFEST, delta)
    entries = [sync_file_entry(sync_root, CLEAN_SOURCE_CHUNK_MANIFEST)]
    entries.extend(sync_file_entry(sync_root, Path(path)) for path in chunk_paths)
    return delta, entries


def clear_managed_sync_dirs(sync_root: Path) -> None:
    for name in MANAGED_SYNC_DIRS:
        target = sync_root / name
        if target.exists():
            shutil.rmtree(target)


def ensure_push_sync_root_safe(registry_root: Path, sync_root: Path) -> None:
    for name in MANAGED_SYNC_DIRS:
        managed_target = sync_root / name
        if paths_overlap(managed_target, registry_root):
            raise ValueError(
                "refusing to use sync dir because managed path "
                f"{managed_target} overlaps registry root {registry_root}"
            )

    managed_dirs = [sync_root / name for name in MANAGED_SYNC_DIRS if (sync_root / name).exists()]
    if not managed_dirs:
        return

    manifest_path = sync_root / SYNC_MANIFEST_NAME
    if not manifest_path.exists():
        names = ", ".join(path.name for path in managed_dirs)
        raise ValueError(
            "refusing to clear existing managed sync dirs without a valid "
            f"{SYNC_MANIFEST_NAME}: {names}"
        )
    validate_existing_sync_manifest(manifest_path)


def push_sync_bundle(
    registry_dir: str | Path | None,
    sync_dir: str | Path,
    *,
    include_raw: bool = False,
    allow_plaintext_raw: bool = False,
) -> dict:
    if include_raw and not allow_plaintext_raw:
        raise ValueError("raw_requires_encryption: use encrypted sync for raw rollout transfer")
    registry_root = (
        Path(registry_dir).resolve() if registry_dir else aippocampus_registry_dir().resolve()
    )
    sync_root = Path(sync_dir).resolve()
    sync_root.mkdir(parents=True, exist_ok=True)
    ensure_push_sync_root_safe(registry_root, sync_root)
    clear_managed_sync_dirs(sync_root)

    copied: list[dict] = []
    for source, relative_path in iter_registry_sync_files(registry_root):
        write_sync_file(
            source,
            sync_path_under(sync_root, relative_path),
            registry_root=registry_root,
            relative_path=relative_path,
            include_raw=include_raw,
        )
        copied.append(sync_file_entry(sync_root, relative_path))
    clean_source_delta, clean_source_entries = write_clean_source_delta(sync_root, registry_root)
    copied.extend(clean_source_entries)
    if include_raw:
        for source, relative_path in iter_raw_rollout_files(registry_root):
            copy_file(source, sync_path_under(sync_root, relative_path))
            copied.append(sync_file_entry(sync_root, relative_path))

    copied.sort(key=lambda item: item["path"])
    manifest = build_sync_manifest(
        backend=LOCAL_FOLDER_BACKEND,
        clean_source_delta=clean_source_delta,
        files=copied,
        include_raw=include_raw,
    )
    manifest_path = sync_root / SYNC_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "sync_dir": str(sync_root),
        "manifest": str(manifest_path),
        "file_count": len(copied),
    }


def destination_for(target_registry: Path, relative_path: str) -> Path:
    path = validate_relative_sync_path(relative_path)
    if path.parts and path.parts[0] == "registry":
        return target_registry.joinpath(*path.parts[1:])
    return target_registry / path


def resolve_pulled_locator(target_registry: Path, value: str | None) -> str | None:
    if not value:
        return None
    raw_path = Path(str(value))
    if raw_path.is_absolute() or raw_path.drive:
        return str(raw_path) if raw_path.exists() else None
    path = validate_relative_sync_path(value)
    if path.parts and path.parts[0] == "registry":
        candidate = target_registry.joinpath(*path.parts[1:])
    else:
        candidate = target_registry / path
    return str(ensure_within(target_registry, candidate)) if candidate.exists() else None


def is_clean_source_chunk_store_path(relative_path: Path) -> bool:
    return bool(relative_path.parts) and relative_path.parts[0] == CLEAN_SOURCE_CHUNK_STORE


def clean_source_delta_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    delta = manifest.get("clean_source_delta") or {}
    files = delta.get("files") or []
    return [item for item in files if isinstance(item, dict)]


def materialize_clean_source_delta_file(
    sync_root: Path, file_manifest: dict[str, Any], destination: Path
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    total = 0
    file_hash = hashlib.sha256()
    with tmp.open("wb") as out:
        for chunk in file_manifest.get("chunks") or []:
            relative_path = validate_relative_sync_path(str(chunk.get("path") or ""))
            if not is_clean_source_chunk_store_path(relative_path):
                raise ValueError(f"unexpected clean-source chunk path: {relative_path}")
            source = sync_path_under(sync_root, relative_path)
            data = source.read_bytes()
            expected_hash = str(chunk.get("sha256") or "")
            if bytes_sha256(data) != expected_hash:
                raise ValueError(f"clean_source_chunk_hash_mismatch: {relative_path.as_posix()}")
            if len(data) != int(chunk.get("size") or 0):
                raise ValueError(f"clean_source_chunk_size_mismatch: {relative_path.as_posix()}")
            out.write(data)
            file_hash.update(data)
            total += len(data)
    if total != int(file_manifest.get("size") or 0):
        tmp.unlink(missing_ok=True)
        raise ValueError(f"clean_source_file_size_mismatch: {file_manifest.get('path')}")
    if file_hash.hexdigest() != str(file_manifest.get("sha256") or ""):
        tmp.unlink(missing_ok=True)
        raise ValueError(f"clean_source_file_hash_mismatch: {file_manifest.get('path')}")
    tmp.replace(destination)


def verify_clean_source_delta_file(sync_root: Path, file_manifest: dict[str, Any]) -> None:
    total = 0
    file_hash = hashlib.sha256()
    for chunk in file_manifest.get("chunks") or []:
        relative_path = validate_relative_sync_path(str(chunk.get("path") or ""))
        if not is_clean_source_chunk_store_path(relative_path):
            raise ValueError(f"unexpected clean-source chunk path: {relative_path}")
        source = sync_path_under(sync_root, relative_path)
        data = source.read_bytes()
        expected_hash = str(chunk.get("sha256") or "")
        if bytes_sha256(data) != expected_hash:
            raise ValueError(f"clean_source_chunk_hash_mismatch: {relative_path.as_posix()}")
        if len(data) != int(chunk.get("size") or 0):
            raise ValueError(f"clean_source_chunk_size_mismatch: {relative_path.as_posix()}")
        file_hash.update(data)
        total += len(data)
    if total != int(file_manifest.get("size") or 0):
        raise ValueError(f"clean_source_file_size_mismatch: {file_manifest.get('path')}")
    if file_hash.hexdigest() != str(file_manifest.get("sha256") or ""):
        raise ValueError(f"clean_source_file_hash_mismatch: {file_manifest.get('path')}")


def repair_registry_locators(target_registry: Path) -> dict[str, Any]:
    registry_path = target_registry / "threads.json"
    registry = load_json(registry_path)
    if not registry:
        return {
            "ok": False,
            "registry": str(registry_path),
            "repaired_entries": 0,
            "issues": [{"code": "missing_registry"}],
        }

    repaired_entries = 0
    unresolved: list[dict[str, str]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("thread_key") or "")
        thread_root = target_registry / "threads" / thread_dir_name(key)
        paths = dict(entry.get("paths") or {})
        before = json.dumps(paths, ensure_ascii=False, sort_keys=True)

        if thread_root.exists():
            paths["registry_thread_store"] = str(thread_root)
            clean_root = thread_root / "clean-source"
            paths["clean_source_dir"] = str(clean_root) if clean_root.exists() else None
            paths.update(clean_source_path_fields(clean_root, clean_root, portable=False))
            index_root = thread_root / "index"
            paths["index_dir"] = str(index_root) if index_root.exists() else None
            paths["graph_json"] = (
                str(index_root / "graph.json") if (index_root / "graph.json").is_file() else None
            )
            paths["messages_jsonl"] = (
                str(index_root / "messages.jsonl")
                if (index_root / "messages.jsonl").is_file()
                else None
            )
            sqlite_path = resolve_sqlite_index_path(index_root / "source_index.sqlite")
            paths["sqlite"] = str(sqlite_path) if sqlite_path.is_file() else None
        else:
            unresolved.append(
                {"thread_key": key, "path": str(thread_root), "code": "missing_thread_store"}
            )

        rollout = (
            resolve_pulled_locator(target_registry, paths.get("rollout"))
            if paths.get("rollout")
            else None
        )
        paths["rollout"] = rollout
        workspace = paths.get("workspace")
        paths["workspace"] = (
            str(Path(workspace)) if workspace and Path(workspace).exists() else None
        )
        entry["paths"] = paths
        entry["path_locator_policy"] = {
            "kind": "target_device_locators",
            "generated_artifacts": "target_registry_absolute",
            "workspace": "device_local_or_unresolved",
            "raw_rollout": "target_registry_raw_rollouts_or_unresolved",
        }
        after = json.dumps(paths, ensure_ascii=False, sort_keys=True)
        if after != before:
            repaired_entries += 1

    registry["sync_path_repaired_at"] = now_utc()
    save_json(registry_path, registry)
    return {
        "ok": not unresolved,
        "registry": str(registry_path),
        "repaired_entries": repaired_entries,
        "issues": unresolved,
    }


def pull_sync_bundle(sync_dir: str | Path, target_registry_dir: str | Path | None = None) -> dict:
    sync_root = Path(sync_dir).resolve()
    target_registry = (
        Path(target_registry_dir).resolve()
        if target_registry_dir
        else aippocampus_registry_dir().resolve()
    )
    manifest = load_sync_manifest(sync_root / SYNC_MANIFEST_NAME)
    delta_file_paths = {
        validate_relative_sync_path(str(item.get("path") or "")).as_posix()
        for item in clean_source_delta_files(manifest)
    }

    copied = 0
    skipped = 0
    conflicts = 0
    conflict_root = target_registry / ".sync-conflicts" / now_utc().replace(":", "")
    for item in manifest.get("files") or []:
        relative_path = validate_relative_sync_path(str(item.get("path") or ""))
        source = sync_path_under(sync_root, relative_path)
        if not source.is_file():
            continue
        if is_clean_source_chunk_store_path(relative_path):
            continue
        if relative_path.as_posix() in delta_file_paths:
            continue
        destination = ensure_within(
            target_registry, destination_for(target_registry, relative_path.as_posix())
        )
        if not destination.exists():
            copy_file(source, destination)
            copied += 1
            continue
        if file_sha256(destination) == item.get("sha256"):
            skipped += 1
            continue
        conflict_path = ensure_within(
            conflict_root, destination_for(conflict_root, relative_path.as_posix())
        )
        copy_file(source, conflict_path)
        conflicts += 1

    for item in clean_source_delta_files(manifest):
        relative_path = validate_relative_sync_path(str(item.get("path") or ""))
        destination = ensure_within(
            target_registry, destination_for(target_registry, relative_path.as_posix())
        )
        if not destination.exists():
            materialize_clean_source_delta_file(sync_root, item, destination)
            copied += 1
            continue
        if file_sha256(destination) == item.get("sha256"):
            skipped += 1
            continue
        conflict_path = ensure_within(
            conflict_root, destination_for(conflict_root, relative_path.as_posix())
        )
        materialize_clean_source_delta_file(sync_root, item, conflict_path)
        conflicts += 1

    path_repair = repair_registry_locators(target_registry)
    return {
        "ok": conflicts == 0 and bool(path_repair.get("ok")),
        "target_registry_dir": str(target_registry),
        "copied": copied,
        "skipped": skipped,
        "conflicts": conflicts,
        "conflict_dir": str(conflict_root) if conflicts else None,
        "path_repair": path_repair,
    }


def repair_sync_bundle(sync_dir: str | Path) -> dict:
    sync_root = Path(sync_dir).resolve()
    manifest_path = sync_root / SYNC_MANIFEST_NAME
    try:
        manifest = load_sync_manifest(manifest_path, missing_ok=True)
    except SyncManifestError as exc:
        return {
            "ok": False,
            "sync_dir": str(sync_root),
            "issues": [
                {
                    "code": "invalid_manifest",
                    "path": str(manifest_path),
                    "message": str(exc),
                }
            ],
        }
    if not manifest:
        return {
            "ok": False,
            "sync_dir": str(sync_root),
            "issues": [{"code": "missing_manifest", "path": str(manifest_path)}],
        }

    issues: list[dict] = []
    for item in manifest.get("files") or []:
        try:
            relative_path = validate_relative_sync_path(str(item.get("path") or ""))
        except ValueError as exc:
            issues.append(
                {"code": "unsafe_path", "path": str(item.get("path") or ""), "message": str(exc)}
            )
            continue
        path = sync_path_under(sync_root, relative_path)
        if not path.exists():
            issues.append({"code": "missing_file", "path": relative_path.as_posix()})
            continue
        actual = file_sha256(path)
        if actual != item.get("sha256"):
            issues.append(
                {
                    "code": "hash_mismatch",
                    "path": relative_path.as_posix(),
                    "expected": item.get("sha256"),
                    "actual": actual,
                }
            )
    for item in clean_source_delta_files(manifest):
        logical_path = str(item.get("path") or "")
        try:
            validate_relative_sync_path(logical_path)
            verify_clean_source_delta_file(sync_root, item)
        except (ValueError, OSError) as exc:
            issues.append(
                {
                    "code": "clean_source_delta_invalid",
                    "path": logical_path,
                    "message": str(exc),
                }
            )
    return {
        "ok": not issues,
        "sync_dir": str(sync_root),
        "checked": len(manifest.get("files") or []),
        "issues": issues,
    }


def status_sync_bundle(sync_dir: str | Path) -> dict:
    sync_root = Path(sync_dir).resolve()
    manifest_path = sync_root / SYNC_MANIFEST_NAME
    try:
        manifest = load_sync_manifest(manifest_path, missing_ok=True)
    except SyncManifestError as exc:
        return {
            "ok": False,
            "sync_dir": str(sync_root),
            "manifest_exists": True,
            "schema_version": None,
            "file_count": 0,
            "raw_rollout_included": False,
            "issues": [
                {
                    "code": "invalid_manifest",
                    "path": str(manifest_path),
                    "message": str(exc),
                }
            ],
        }
    repair = repair_sync_bundle(sync_root) if manifest else None
    return {
        "ok": bool(manifest) and bool(repair and repair.get("ok")),
        "sync_dir": str(sync_root),
        "manifest_exists": bool(manifest),
        "schema_version": manifest.get("schema_version") if manifest else None,
        "file_count": manifest.get("file_count") if manifest else 0,
        "raw_rollout_included": manifest.get("raw_rollout_included") if manifest else False,
        "issues": (repair or {}).get("issues", []),
    }


def available_requires_sync_dir_status() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "available_requires_sync_dir",
        "backend": "local_folder",
        "backends": ["local_folder", "http_object_store"],
        "commands": ["status", "push", "pull", "repair"],
        "next_command": "aippocampus sync status --sync-dir <folder> --json",
        "raw_rollout_sync": "explicit_only",
        "claim_boundary": "sync capability exists, but no local sync backend is selected",
    }


def _parser_command(argv: list[str] | None, base_prog: str) -> tuple[str, list[str] | None, str | None]:
    commands = {"status", "push", "pull", "repair"}
    if argv and argv[0] in commands and any(arg in {"-h", "--help"} for arg in argv[1:]):
        return f"{base_prog} {argv[0]}", list(argv[1:]), argv[0]
    return base_prog, argv, None


def main(argv: list[str] | None = None) -> int:
    prog, parse_argv, command_override = _parser_command(argv, "aippocampus sync")
    parser = argparse.ArgumentParser(prog=prog)
    if command_override is None:
        parser.add_argument("command", choices=["status", "push", "pull", "repair"])
    parser.add_argument("--sync-dir")
    parser.add_argument("--registry-dir", default=None)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--encrypt", action="store_true")
    parser.add_argument("--require-encrypted", action="store_true")
    parser.add_argument("--recipient", action="append", default=[])
    parser.add_argument("--recipient-file", action="append", default=[])
    parser.add_argument("--identity-file", action="append", default=[])
    parser.add_argument("--age-bin", default=None)
    parser.add_argument("--no-decrypt", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(parse_argv)
    if command_override is not None:
        args.command = command_override

    try:
        if args.command == "status":
            if not args.sync_dir:
                result = available_requires_sync_dir_status()
            elif args.require_encrypted:
                encrypted_sync_bundle = importlib.import_module(
                    "aippocampus_runtime.sync.encrypted.bundle"
                )

                result = encrypted_sync_bundle.status_encrypted_sync_bundle(
                    args.sync_dir,
                    identity_files=args.identity_file,
                    age_bin=args.age_bin,
                    decrypt=bool(args.identity_file),
                )
            else:
                result = status_sync_bundle(args.sync_dir)
        elif args.command == "push":
            if not args.sync_dir:
                raise ValueError("missing_sync_dir: push requires --sync-dir")
            if args.encrypt:
                encrypted_sync_bundle = importlib.import_module(
                    "aippocampus_runtime.sync.encrypted.bundle"
                )

                result = encrypted_sync_bundle.push_encrypted_sync_bundle(
                    args.registry_dir,
                    args.sync_dir,
                    recipients=args.recipient,
                    recipient_files=args.recipient_file,
                    include_raw=args.include_raw,
                    age_bin=args.age_bin,
                )
            else:
                result = push_sync_bundle(
                    args.registry_dir,
                    args.sync_dir,
                    include_raw=args.include_raw,
                )
        elif args.command == "pull":
            if not args.sync_dir:
                raise ValueError("missing_sync_dir: pull requires --sync-dir")
            if args.require_encrypted:
                encrypted_sync_bundle = importlib.import_module(
                    "aippocampus_runtime.sync.encrypted.bundle"
                )

                result = encrypted_sync_bundle.pull_encrypted_sync_bundle(
                    args.sync_dir,
                    args.registry_dir,
                    identity_files=args.identity_file,
                    age_bin=args.age_bin,
                )
            else:
                result = pull_sync_bundle(args.sync_dir, args.registry_dir)
        else:
            if not args.sync_dir:
                raise ValueError("missing_sync_dir: repair requires --sync-dir")
            if args.require_encrypted:
                encrypted_sync_bundle = importlib.import_module(
                    "aippocampus_runtime.sync.encrypted.bundle"
                )

                result = encrypted_sync_bundle.repair_encrypted_sync_bundle(
                    args.sync_dir,
                    identity_files=args.identity_file,
                    age_bin=args.age_bin,
                    no_decrypt=args.no_decrypt,
                )
            else:
                result = repair_sync_bundle(args.sync_dir)
    except ValueError as exc:
        result = {
            "ok": False,
            "sync_dir": str(Path(args.sync_dir).resolve()) if args.sync_dir else None,
            "issues": [{"code": str(exc).split(":", 1)[0], "message": str(exc)}],
        }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("status") == "available_requires_sync_dir":
            print("sync status: capability available; no sync folder selected")
            print(f"next: {result.get('next_command')}")
            print(f"boundary: {result.get('claim_boundary')}")
        else:
            print(f"sync {args.command}: {'ok' if result.get('ok') else 'needs attention'}")
        if result.get("manifest"):
            print(f"manifest: {result['manifest']}")
        if result.get("issues"):
            for issue in result["issues"]:
                print(f"- {issue.get('code')}: {issue.get('path')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
