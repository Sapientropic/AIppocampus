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
from typing import Iterator

DEFAULT_ARTIFACT_LEASE_STALE_SECONDS = 6 * 60 * 60
DEFAULT_SQLITE_BUSY_TIMEOUT_MS = 30_000
INDEX_POINTER_NAME = "source_index.pointer.json"
INDEX_SQLITE_NAME = "source_index.sqlite"
INDEX_VERSIONS_DIR = "versions"


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
    if sqlite_or_pointer_path.parent.name == INDEX_VERSIONS_DIR:
        return sqlite_or_pointer_path.parent.parent / INDEX_POINTER_NAME
    return sqlite_or_pointer_path.with_name(INDEX_POINTER_NAME)


def _load_pointer(pointer_path: Path) -> dict:
    if not pointer_path.exists():
        return {}
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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


def resolve_sqlite_index_path(sqlite_or_pointer_path: Path) -> Path:
    """Resolve a SQLite index path through the optional version pointer.

    The legacy `source_index.sqlite` path remains the compatibility anchor, but
    newer readers should follow the pointer first. If the current version has
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


def _unique_versioned_sqlite_path(destination: Path) -> Path:
    versions_dir = destination.parent / INDEX_VERSIONS_DIR
    versions_dir.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        candidate = versions_dir / f"{destination.stem}-{stamp}-{os.getpid()}-{time.time_ns()}.sqlite"
        if not candidate.exists():
            return candidate


def _prune_versioned_sqlites(destination: Path, keep: set[Path]) -> None:
    versions_dir = destination.parent / INDEX_VERSIONS_DIR
    if not versions_dir.exists():
        return
    keep_resolved = {path.resolve() for path in keep if path}
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
        except FileExistsError:
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
            raise RuntimeError(
                f"artifact writer lease already held: {lease_path}. "
                "Wait for the current writer or remove the stale lease after verification."
            )
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
    """Publish a SQLite index as a versioned artifact plus stable compatibility DB.

    The versioned copy gives new readers an immutable current target even when
    the legacy `source_index.sqlite` file is pinned by an old Windows reader.
    The stable file is still updated through SQLite backup when possible so
    older callers that know only the legacy path continue to work.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    pointer_path = index_pointer_path(destination)
    previous_pointer = _load_pointer(pointer_path)
    previous_good = _first_existing_pointer_candidate(pointer_path, previous_pointer)

    current_path = _unique_versioned_sqlite_path(destination)
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

    last_known_good = previous_good or (destination if destination.is_file() else current_path)
    pointer = {
        "schema_version": 1,
        "kind": "aippocampus_sqlite_index_pointer",
        "updated_at": utc_now(),
        "stable": _pointer_value(pointer_path, destination),
        "current": _pointer_value(pointer_path, current_path),
        "last_known_good": _pointer_value(pointer_path, last_known_good),
        "publish_status": "stable_updated" if stable_ok else "stable_locked_current_versioned",
        "stable_publish": stable_publish,
    }
    _write_json_atomic(pointer_path, pointer)
    _prune_versioned_sqlites(destination, {current_path, last_known_good})

    return {
        "publish_method": "sqlite_backup_wal" if stable_ok else "versioned_pointer_fallback",
        "pointer": str(pointer_path),
        "stable": str(destination),
        "current": str(current_path),
        "last_known_good": str(last_known_good),
        "stable_publish": stable_publish,
        "busy_timeout_ms": int(busy_timeout_ms),
    }
