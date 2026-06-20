"""Shared publishing helpers for generated AIppocampus artifacts."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from aippocampus_runtime.artifacts.generation_pins import generation_cleanup_contract

DEFAULT_ARTIFACT_LEASE_STALE_SECONDS = 6 * 60 * 60
DEFAULT_ARTIFACT_LEASE_WAIT_SECONDS = 1.0
DEFAULT_SQLITE_BUSY_TIMEOUT_MS = 30_000
INDEX_POINTER_NAME = "source_index.pointer.json"
INDEX_SQLITE_NAME = "source_index.sqlite"
INDEX_GENERATIONS_DIR = "generations"
INDEX_VERSIONS_DIR = "versions"
SEGMENTS_POINTER_NAME = "segments.pointer.json"
SEGMENTS_MANIFEST_NAME = "manifest.json"
SEGMENTS_GENERATIONS_DIR = "generations"


class ArtifactLeaseBusyError(RuntimeError):
    """Raised when a same-directory artifact lease is held by another writer."""

    def __init__(
        self,
        lease_path: Path,
        *,
        wait_timeout_seconds: float,
    ) -> None:
        self.lease_path = lease_path
        self.wait_timeout_seconds = wait_timeout_seconds
        super().__init__(
            f"artifact writer lease already held: {lease_path}. "
            "Wait for the current writer or remove the stale lease after verification."
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sqlite_sidecar_paths(path: Path) -> list[Path]:
    return [path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def remove_sqlite_artifact(path: Path) -> None:
    for candidate in [path, *sqlite_sidecar_paths(path)]:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def unique_temp_sqlite_path(destination: Path) -> Path:
    stamp = f"{os.getpid()}-{int(time.time() * 1000)}"
    return destination.with_name(f".{destination.name}.tmp-{stamp}")


def index_pointer_path(sqlite_or_pointer_path: Path) -> Path:
    if sqlite_or_pointer_path.name == INDEX_POINTER_NAME:
        return sqlite_or_pointer_path
    if (
        sqlite_or_pointer_path.parent.parent.name == INDEX_GENERATIONS_DIR
        and sqlite_or_pointer_path.parent.name.startswith("gen_")
    ):
        return sqlite_or_pointer_path.parent.parent.parent / INDEX_POINTER_NAME
    if sqlite_or_pointer_path.parent.name == INDEX_VERSIONS_DIR:
        return sqlite_or_pointer_path.parent.parent / INDEX_POINTER_NAME
    return sqlite_or_pointer_path.with_name(INDEX_POINTER_NAME)


def segment_pointer_path(manifest_or_pointer_path: Path) -> Path:
    if manifest_or_pointer_path.name == SEGMENTS_POINTER_NAME:
        return manifest_or_pointer_path
    if (
        manifest_or_pointer_path.parent.parent.name == SEGMENTS_GENERATIONS_DIR
        and manifest_or_pointer_path.parent.name.startswith("gen_")
    ):
        return manifest_or_pointer_path.parent.parent.parent / SEGMENTS_POINTER_NAME
    return manifest_or_pointer_path.with_name(SEGMENTS_POINTER_NAME)


def _load_pointer(pointer_path: Path) -> dict:
    if not pointer_path.exists():
        return {}
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_pointer_with_diagnostics(pointer_path: Path) -> tuple[dict[str, Any], str | None]:
    if not pointer_path.exists():
        return {}, None
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, type(exc).__name__
    if not isinstance(data, dict):
        return {}, "pointer_not_object"
    return data, None


def _candidate_from_pointer(pointer_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = pointer_path.parent / candidate
    return candidate


def _pointer_value(pointer_path: Path, path: Path) -> str:
    try:
        return path.relative_to(pointer_path.parent).as_posix()
    except ValueError:
        return str(path)


def _first_existing_pointer_candidate(pointer_path: Path, pointer: dict) -> Path | None:
    for key in ("current", "last_known_good", "stable"):
        candidate = _candidate_from_pointer(pointer_path, pointer.get(key))
        if candidate and candidate.is_file():
            return candidate
    return None


def _generation_id_for_path(pointer_path: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        relative = path.relative_to(pointer_path.parent)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == INDEX_GENERATIONS_DIR and parts[1].startswith("gen_"):
        return parts[1]
    return None


def _segment_generation_id_for_path(pointer_path: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        relative = path.relative_to(pointer_path.parent)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == SEGMENTS_GENERATIONS_DIR and parts[1].startswith("gen_"):
        return parts[1]
    return None


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _safe_dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        total += _safe_file_size(item)
    return total


def writer_lease_diagnostics(
    output_dir: Path,
    lease_name: str,
    *,
    stale_after_seconds: int = DEFAULT_ARTIFACT_LEASE_STALE_SECONDS,
) -> dict[str, Any]:
    """Return redacted writer-lease state for foreground recovery cards.

    Publishing leases are operational state, not source evidence. Diagnostics
    deliberately expose only the lease file name, age, and active/stale status
    so a foreground agent can retry or ask for operator cleanup without seeing
    local paths.
    """

    lease_path = Path(output_dir) / lease_name
    if not lease_path.exists():
        return {
            "writer_lease_name": lease_name,
            "writer_lease_status": "absent",
            "active_writer_lease": False,
            "stale_writer_lease": False,
            "writer_lease_age_seconds": None,
            "writer_lease_stale_after_seconds": int(stale_after_seconds),
        }
    try:
        age_seconds = max(0, int(time.time() - lease_path.stat().st_mtime))
    except OSError:
        age_seconds = None
    stale = age_seconds is not None and age_seconds > int(stale_after_seconds)
    return {
        "writer_lease_name": lease_name,
        "writer_lease_status": "stale" if stale else "active",
        "active_writer_lease": not stale,
        "stale_writer_lease": stale,
        "writer_lease_age_seconds": age_seconds,
        "writer_lease_stale_after_seconds": int(stale_after_seconds),
    }


def _diagnostic_relative_path(path: Path, *, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    try:
        return path.resolve().relative_to(path.parent.parent.parent.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _generation_path_projection(
    path: Path,
    *,
    root: Path | None,
    include_paths: bool,
) -> dict[str, Any]:
    projected: dict[str, Any] = {"relative_path": _diagnostic_relative_path(path, root=root)}
    if include_paths:
        projected["path"] = str(path)
    return projected


def index_generation_diagnostics(
    sqlite_or_pointer_path: Path,
    *,
    root: Path | None = None,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Summarize source-index generations without treating them as source truth.

    Old generation directories are copy-on-write reader targets. This diagnostic
    reports which generations are safe candidates for future reader-pin/TTL
    cleanup, but intentionally performs no deletion and exposes no absolute
    paths unless the caller opts into local maintainer diagnostics.
    """

    pointer_path = index_pointer_path(Path(sqlite_or_pointer_path))
    index_dir = pointer_path.parent
    pointer_started = time.perf_counter()
    pointer, pointer_error = _load_pointer_with_diagnostics(pointer_path)
    pointer_load_ms = round((time.perf_counter() - pointer_started) * 1000, 3)
    generations_dir = index_dir / INDEX_GENERATIONS_DIR
    generation_dirs = sorted(item for item in generations_dir.glob("gen_*") if item.is_dir())
    current_path = _candidate_from_pointer(pointer_path, pointer.get("current"))
    last_known_good_path = _candidate_from_pointer(pointer_path, pointer.get("last_known_good"))
    stable_path = _candidate_from_pointer(pointer_path, pointer.get("stable")) or index_dir / INDEX_SQLITE_NAME

    current_generation = (
        str(pointer.get("current_generation"))
        if pointer.get("current_generation")
        else _generation_id_for_path(pointer_path, current_path)
    )
    last_known_good_generation = (
        str(pointer.get("last_known_good_generation"))
        if pointer.get("last_known_good_generation")
        else _generation_id_for_path(pointer_path, last_known_good_path)
    )
    protected_generations = {
        item
        for item in (current_generation, last_known_good_generation)
        if isinstance(item, str) and item
    }

    generation_rows: list[dict[str, Any]] = []
    gc_candidates: list[dict[str, Any]] = []
    for generation_dir in generation_dirs:
        generation_id = generation_dir.name
        sqlite_path = generation_dir / INDEX_SQLITE_NAME
        size = _safe_dir_size(generation_dir)
        cleanup = generation_cleanup_contract(
            index_dir,
            generation_dir,
            freshness_paths=[pointer_path],
        )
        row = {
            "generation": generation_id,
            "bytes": size,
            "role": "protected" if generation_id in protected_generations else "old",
            "sqlite_exists": sqlite_path.is_file(),
            "cleanup_status": (
                "protected_current_or_last_known_good"
                if generation_id in protected_generations
                else cleanup["cleanup_status"]
            ),
            "generation_age_seconds": cleanup["generation_age_seconds"],
            "reader_pin_ttl_seconds": cleanup["ttl_seconds"],
            "active_reader_pin_count": cleanup["active_reader_pin_count"],
            "expired_reader_pin_count": cleanup["expired_reader_pin_count"],
            "cleanup_evidence": list(cleanup["evidence"]),
            **_generation_path_projection(generation_dir, root=root, include_paths=include_paths),
        }
        generation_rows.append(row)
        if generation_id not in protected_generations:
            gc_candidates.append(row)

    current_exists = bool(current_path and current_path.is_file())
    last_known_good_exists = bool(last_known_good_path and last_known_good_path.is_file())
    stable_exists = bool(stable_path and stable_path.is_file())
    if not pointer_path.exists():
        status_name = "pointer_missing"
        fallback_used = "stable" if stable_exists else None
    elif pointer_error:
        status_name = "pointer_unreadable"
        fallback_used = "stable" if stable_exists else None
    elif current_exists:
        status_name = "ok"
        fallback_used = "current"
    elif last_known_good_exists:
        status_name = "current_missing_last_known_good_available"
        fallback_used = "last_known_good"
    elif stable_exists:
        status_name = "current_and_last_known_good_missing_stable_available"
        fallback_used = "stable"
    else:
        status_name = "dangling_pointer"
        fallback_used = None

    current_bytes = (
        _safe_dir_size(current_path.parent)
        if current_path is not None
        and current_path.parent.name == current_generation
        and current_path.parent.parent.name == INDEX_GENERATIONS_DIR
        else 0
    )
    last_known_good_bytes = (
        _safe_dir_size(last_known_good_path.parent)
        if last_known_good_path is not None
        and last_known_good_path.parent.name == last_known_good_generation
        and last_known_good_path.parent.parent.name == INDEX_GENERATIONS_DIR
        else 0
    )
    old_generation_bytes = sum(int(item["bytes"]) for item in gc_candidates)
    active_reader_pin_count = sum(int(item["active_reader_pin_count"]) for item in generation_rows)
    expired_reader_pin_count = sum(int(item["expired_reader_pin_count"]) for item in generation_rows)
    publish_latency = pointer.get("publish_latency_ms")
    try:
        publish_latency_ms = float(publish_latency) if publish_latency is not None else None
    except (TypeError, ValueError):
        publish_latency_ms = None

    return {
        "pointer_exists": pointer_path.exists(),
        "pointer_error": pointer_error,
        "status": status_name,
        "fallback_used": fallback_used,
        "current_generation": current_generation,
        "last_known_good_generation": last_known_good_generation,
        "current_generation_exists": current_exists,
        "last_known_good_generation_exists": last_known_good_exists,
        "stable_compatibility_exists": stable_exists,
        "compatibility_path": pointer.get("compatibility_path") or pointer.get("stable"),
        "generation_count": len(generation_rows),
        "current_generation_bytes": current_bytes,
        "last_known_good_generation_bytes": last_known_good_bytes,
        "old_generation_count": len(gc_candidates),
        "old_generation_bytes": old_generation_bytes,
        "generation_gc_candidate_count": len(gc_candidates),
        "generation_gc_candidate_bytes": old_generation_bytes,
        "generation_gc_candidates": gc_candidates,
        "active_reader_pin_count": active_reader_pin_count,
        "expired_reader_pin_count": expired_reader_pin_count,
        "pointer_load_ms": pointer_load_ms,
        "publish_latency_ms": publish_latency_ms,
        "cleanup_policy": "reader_pin_ttl_contract",
        **writer_lease_diagnostics(index_dir, ".index-publish.lock"),
    }


def segment_generation_diagnostics(
    manifest_or_pointer_path: Path,
    *,
    root: Path | None = None,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Summarize segment generations without deleting reader-pinnable shards.

    Segment manifests now publish through `segments.pointer.json`, but old
    generation directories can still be pinned by foreground queries. This
    diagnostic mirrors the main-index reporting shape so storage governance can
    plan future cleanup without touching generated shards before #581's
    reader-pin/TTL contract exists.
    """

    pointer_path = segment_pointer_path(Path(manifest_or_pointer_path))
    segments_dir = pointer_path.parent
    pointer_started = time.perf_counter()
    pointer, pointer_error = _load_pointer_with_diagnostics(pointer_path)
    pointer_load_ms = round((time.perf_counter() - pointer_started) * 1000, 3)
    generations_dir = segments_dir / SEGMENTS_GENERATIONS_DIR
    generation_dirs = sorted(item for item in generations_dir.glob("gen_*") if item.is_dir())
    current_path = _candidate_from_pointer(pointer_path, pointer.get("current"))
    last_known_good_path = _candidate_from_pointer(pointer_path, pointer.get("last_known_good"))
    stable_path = (
        _candidate_from_pointer(pointer_path, pointer.get("stable"))
        or segments_dir / SEGMENTS_MANIFEST_NAME
    )

    current_generation = (
        str(pointer.get("current_generation"))
        if pointer.get("current_generation")
        else _segment_generation_id_for_path(pointer_path, current_path)
    )
    last_known_good_generation = (
        str(pointer.get("last_known_good_generation"))
        if pointer.get("last_known_good_generation")
        else _segment_generation_id_for_path(pointer_path, last_known_good_path)
    )
    protected_generations = {
        item
        for item in (current_generation, last_known_good_generation)
        if isinstance(item, str) and item
    }

    generation_rows: list[dict[str, Any]] = []
    gc_candidates: list[dict[str, Any]] = []
    for generation_dir in generation_dirs:
        generation_id = generation_dir.name
        manifest_path = generation_dir / SEGMENTS_MANIFEST_NAME
        size = _safe_dir_size(generation_dir)
        cleanup = generation_cleanup_contract(
            segments_dir,
            generation_dir,
            freshness_paths=[pointer_path],
        )
        row = {
            "generation": generation_id,
            "bytes": size,
            "role": "protected" if generation_id in protected_generations else "old",
            "manifest_exists": manifest_path.is_file(),
            "cleanup_status": (
                "protected_current_or_last_known_good"
                if generation_id in protected_generations
                else cleanup["cleanup_status"]
            ),
            "generation_age_seconds": cleanup["generation_age_seconds"],
            "reader_pin_ttl_seconds": cleanup["ttl_seconds"],
            "active_reader_pin_count": cleanup["active_reader_pin_count"],
            "expired_reader_pin_count": cleanup["expired_reader_pin_count"],
            "cleanup_evidence": list(cleanup["evidence"]),
            **_generation_path_projection(generation_dir, root=root, include_paths=include_paths),
        }
        generation_rows.append(row)
        if generation_id not in protected_generations:
            gc_candidates.append(row)

    current_exists = bool(current_path and current_path.is_file())
    last_known_good_exists = bool(last_known_good_path and last_known_good_path.is_file())
    stable_exists = bool(stable_path and stable_path.is_file())
    if not pointer_path.exists():
        status_name = "pointer_missing"
        fallback_used = "stable" if stable_exists else None
    elif pointer_error:
        status_name = "pointer_unreadable"
        fallback_used = "stable" if stable_exists else None
    elif current_exists:
        status_name = "ok"
        fallback_used = "current"
    elif last_known_good_exists:
        status_name = "current_missing_last_known_good_available"
        fallback_used = "last_known_good"
    elif stable_exists:
        status_name = "current_and_last_known_good_missing_stable_available"
        fallback_used = "stable"
    else:
        status_name = "dangling_pointer"
        fallback_used = None

    current_bytes = (
        _safe_dir_size(current_path.parent)
        if current_path is not None
        and current_path.parent.name == current_generation
        and current_path.parent.parent.name == SEGMENTS_GENERATIONS_DIR
        else 0
    )
    last_known_good_bytes = (
        _safe_dir_size(last_known_good_path.parent)
        if last_known_good_path is not None
        and last_known_good_path.parent.name == last_known_good_generation
        and last_known_good_path.parent.parent.name == SEGMENTS_GENERATIONS_DIR
        else 0
    )
    old_generation_bytes = sum(int(item["bytes"]) for item in gc_candidates)
    active_reader_pin_count = sum(int(item["active_reader_pin_count"]) for item in generation_rows)
    expired_reader_pin_count = sum(int(item["expired_reader_pin_count"]) for item in generation_rows)
    publish_latency = pointer.get("publish_latency_ms")
    try:
        publish_latency_ms = float(publish_latency) if publish_latency is not None else None
    except (TypeError, ValueError):
        publish_latency_ms = None

    return {
        "pointer_exists": pointer_path.exists(),
        "pointer_error": pointer_error,
        "status": status_name,
        "fallback_used": fallback_used,
        "current_generation": current_generation,
        "last_known_good_generation": last_known_good_generation,
        "current_generation_exists": current_exists,
        "last_known_good_generation_exists": last_known_good_exists,
        "stable_compatibility_exists": stable_exists,
        "compatibility_path": pointer.get("compatibility_path") or pointer.get("stable"),
        "generation_count": len(generation_rows),
        "current_generation_bytes": current_bytes,
        "last_known_good_generation_bytes": last_known_good_bytes,
        "old_generation_count": len(gc_candidates),
        "old_generation_bytes": old_generation_bytes,
        "generation_gc_candidate_count": len(gc_candidates),
        "generation_gc_candidate_bytes": old_generation_bytes,
        "generation_gc_candidates": gc_candidates,
        "active_reader_pin_count": active_reader_pin_count,
        "expired_reader_pin_count": expired_reader_pin_count,
        "pointer_load_ms": pointer_load_ms,
        "publish_latency_ms": publish_latency_ms,
        "cleanup_policy": "reader_pin_ttl_contract",
        **writer_lease_diagnostics(segments_dir, ".rebuild.lock"),
    }


def resolve_sqlite_index_path(sqlite_or_pointer_path: Path) -> Path:
    """Resolve a SQLite index path through the optional generation pointer.

    The legacy `source_index.sqlite` path remains the compatibility anchor, but
    newer readers should follow the pointer first. If the current generation has
    been pruned, moved, or copied incompletely, fall back to last-known-good
    before returning the stable legacy path.
    """

    sqlite_or_pointer_path = Path(sqlite_or_pointer_path)
    pointer_path = index_pointer_path(sqlite_or_pointer_path)
    pointer = _load_pointer(pointer_path)
    for key in ("current", "last_known_good", "stable"):
        candidate = _candidate_from_pointer(pointer_path, pointer.get(key))
        if candidate and candidate.is_file():
            return candidate
    if sqlite_or_pointer_path.name == INDEX_POINTER_NAME:
        stable = _candidate_from_pointer(pointer_path, pointer.get("stable"))
        return stable or pointer_path.with_name(INDEX_SQLITE_NAME)
    return sqlite_or_pointer_path


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _unique_generation_sqlite_path(destination: Path) -> tuple[str, Path]:
    generations_dir = destination.parent / INDEX_GENERATIONS_DIR
    generations_dir.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        generation_id = f"gen_{stamp}_{os.getpid()}_{time.time_ns()}"
        generation_dir = generations_dir / generation_id
        try:
            generation_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return generation_id, generation_dir / destination.name


def _prune_published_sqlites(destination: Path, keep: set[Path]) -> None:
    # Generation directories are CoW reader targets. Until #581's reader-pin or
    # TTL-aware GC contract exists, the publish fast path only prunes legacy
    # flat version files and leaves generation cleanup to storage governance.
    keep_resolved = {path.resolve() for path in keep if path}
    versions_dir = destination.parent / INDEX_VERSIONS_DIR
    if not versions_dir.exists():
        return
    for candidate in sorted(versions_dir.glob(f"{destination.stem}-*.sqlite")):
        if candidate.resolve() in keep_resolved:
            continue
        try:
            remove_sqlite_artifact(candidate)
        except OSError:
            # A live reader may still be on an older version. Leaving it behind
            # is safer than turning cleanup into a failed publish on Windows.
            continue


@contextlib.contextmanager
def artifact_lease(
    output_dir: Path,
    lease_name: str,
    *,
    stale_after_seconds: int = DEFAULT_ARTIFACT_LEASE_STALE_SECONDS,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 0.05,
) -> Iterator[Path]:
    """Create a portable same-directory single-writer lease.

    The lease is advisory, but every AIppocampus writer that publishes generated
    artifacts should use it. We intentionally avoid platform file locks here:
    Windows locks are exactly what this layer is trying to route around, and a
    visible lease file gives future agents a recoverable interrupted-write
    boundary instead of an invisible OS handle.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    lease_path = output_dir / lease_name
    deadline = time.monotonic() + max(0.0, float(wait_timeout_seconds))
    payload = {
        "schema_version": 1,
        "kind": "aippocampus_artifact_writer_lease",
        "pid": os.getpid(),
        "created_at": utc_now(),
        "stale_after_seconds": int(stale_after_seconds),
    }
    while True:
        try:
            fd = os.open(str(lease_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            try:
                age = time.time() - lease_path.stat().st_mtime
            except OSError:
                continue
            if age > stale_after_seconds:
                try:
                    lease_path.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() < deadline:
                time.sleep(max(0.01, float(poll_interval_seconds)))
                continue
            raise ArtifactLeaseBusyError(
                lease_path,
                wait_timeout_seconds=float(wait_timeout_seconds),
            ) from exc
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            break

    try:
        yield lease_path
    finally:
        try:
            lease_path.unlink()
        except FileNotFoundError:
            pass


def publish_sqlite_backup(
    source: Path,
    destination: Path,
    *,
    busy_timeout_ms: int = DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
) -> dict:
    """Publish a built SQLite database without replacing the destination file.

    `Path.replace()` is atomic on POSIX, but Windows rejects it while another
    process has the old SQLite file open. SQLite's backup API writes through the
    database engine instead, so readers keep a consistent snapshot and later
    reads see the new index. WAL is part of the contract: without it, a long
    read transaction can block the publish path on Windows.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_con = sqlite3.connect(source, timeout=busy_timeout_ms / 1000)
    destination_con = sqlite3.connect(destination, timeout=busy_timeout_ms / 1000)
    journal_mode = ""
    try:
        destination_con.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        journal_mode = destination_con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        source_con.backup(destination_con)
        destination_con.commit()
    finally:
        destination_con.close()
        source_con.close()
    return {
        "publish_method": "sqlite_backup",
        "journal_mode": str(journal_mode).lower(),
        "busy_timeout_ms": int(busy_timeout_ms),
    }


def publish_sqlite_with_pointer(
    source: Path,
    destination: Path,
    *,
    busy_timeout_ms: int = DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
) -> dict:
    """Publish a SQLite index generation plus stable compatibility DB.

    New readers pin the current generation path for the duration of a query.
    The stable `source_index.sqlite` file is still refreshed through SQLite
    backup when possible so older callers that know only the legacy path
    continue to work.
    """

    started = time.perf_counter()
    destination.parent.mkdir(parents=True, exist_ok=True)
    pointer_path = index_pointer_path(destination)
    previous_pointer = _load_pointer(pointer_path)
    previous_good = _first_existing_pointer_candidate(pointer_path, previous_pointer)

    current_generation, current_path = _unique_generation_sqlite_path(destination)
    shutil.copy2(source, current_path)

    stable_publish: dict[str, object]
    stable_ok = True
    try:
        stable_publish = publish_sqlite_backup(
            source,
            destination,
            busy_timeout_ms=busy_timeout_ms,
        )
    except (OSError, sqlite3.Error) as exc:
        stable_ok = False
        stable_publish = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "busy_timeout_ms": int(busy_timeout_ms),
        }

    last_known_good = previous_good or current_path
    last_known_good_generation = _generation_id_for_path(pointer_path, last_known_good)
    if last_known_good == current_path:
        last_known_good_generation = current_generation
    publish_latency_ms = round((time.perf_counter() - started) * 1000, 3)
    pointer = {
        "schema_version": 1,
        "kind": "aippocampus_sqlite_index_pointer",
        "updated_at": utc_now(),
        "generation_layout": f"{INDEX_GENERATIONS_DIR}/<generation>/{destination.name}",
        "current_generation": current_generation,
        "last_known_good_generation": last_known_good_generation,
        "compatibility_path": _pointer_value(pointer_path, destination),
        "stable": _pointer_value(pointer_path, destination),
        "current": _pointer_value(pointer_path, current_path),
        "last_known_good": _pointer_value(pointer_path, last_known_good),
        "publish_status": "stable_updated" if stable_ok else "stable_locked_current_generation",
        "stable_publish": stable_publish,
        "publish_latency_ms": publish_latency_ms,
        "allowed_volatile_fields": [
            "updated_at",
            "publish_latency_ms",
            "publish_status",
            "stable_publish",
        ],
    }
    _write_json_atomic(pointer_path, pointer)
    _prune_published_sqlites(destination, {current_path, last_known_good})

    return {
        "publish_method": "sqlite_backup_wal" if stable_ok else "versioned_pointer_fallback",
        "pointer": str(pointer_path),
        "stable": str(destination),
        "current": str(current_path),
        "last_known_good": str(last_known_good),
        "current_generation": current_generation,
        "last_known_good_generation": last_known_good_generation,
        "stable_publish": stable_publish,
        "busy_timeout_ms": int(busy_timeout_ms),
        "publish_latency_ms": publish_latency_ms,
    }
