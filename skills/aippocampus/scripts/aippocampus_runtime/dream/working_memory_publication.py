"""Reader-safe Dream working-memory publication.

Foreground recall must never wait for the detached Dream writer lock. Writers
can publish a complete generation and atomically swap a small pointer; readers
use the pointed generation, fall back to the previous valid generation, or
fail open to legacy JSONL rows with diagnostics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.io_mtime_cache import load_jsonl_objects

POINTER_KIND = "aippocampus_dream_working_memory_publication_pointer"
WORKING_MEMORY_KIND = "aippocampus_working_memory"
GENERATION_DIR_SUFFIX = ".generations"
POINTER_SUFFIX = ".pointer.json"
WRITER_LOCK_NAME = "dream_sleep_cycle_write.lock"


def generation_dir(path: Path) -> Path:
    return path.with_suffix(path.suffix + GENERATION_DIR_SUFFIX)


def pointer_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + POINTER_SUFFIX)


def writer_lock_path(path: Path) -> Path:
    return path.parent / WRITER_LOCK_NAME


def relative_to_parent(path: Path, parent: Path) -> str:
    return path.resolve().relative_to(parent.resolve()).as_posix()


def stable_generation_name(rows: Iterable[Mapping[str, Any]], *, created_at: str) -> str:
    raw = json.dumps(list(rows), ensure_ascii=False, sort_keys=True) + "\n" + created_at
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]
    return f"working-memory-{digest}.jsonl"


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def read_pointer(path: Path) -> dict[str, Any]:
    pointer = pointer_path(path)
    if not pointer.exists():
        return {}
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_published_path(path: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return path.parent / candidate


def publish_working_memory_snapshot(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    materialized = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("kind") == WORKING_MEMORY_KIND
    ]
    created = created_at or now_utc()
    directory = generation_dir(path)
    generation = directory / stable_generation_name(materialized, created_at=created)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in materialized)
    write_text_atomic(generation, body)

    previous = read_pointer(path)
    previous_current = previous.get("current")
    new_pointer = {
        "schema_version": 1,
        "kind": POINTER_KIND,
        "updated_at": created,
        "current": relative_to_parent(generation, path.parent),
        "last_known_good": previous_current or previous.get("last_known_good"),
        "row_count": len(materialized),
        "source_boundary": {
            "dream_working_memory_snapshot_not_source_truth": True,
            "source_reopen_required_for_claims": True,
            "reader_must_not_wait_for_writer_lock": True,
        },
    }
    write_text_atomic(pointer_path(path), json.dumps(new_pointer, ensure_ascii=False, indent=2) + "\n")
    return new_pointer


def read_jsonl_rows(path: Path, *, strict: bool = False) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    cached = load_jsonl_objects(path, strict=strict)
    if cached is not None:
        return cached
    rows: list[dict[str, Any]] = []
    invalid = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                if strict:
                    return [], invalid
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows, invalid


def working_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("kind") == WORKING_MEMORY_KIND]


def diagnostic(
    *,
    status: str,
    path: Path,
    row_count: int = 0,
    invalid_line_count: int = 0,
    writer_in_progress: bool = False,
    diagnostics: Iterable[str] = (),
) -> dict[str, Any]:
    reasons = list(dict.fromkeys(str(item) for item in diagnostics if str(item)))
    if writer_in_progress:
        reasons.append("writer_in_progress")
    if invalid_line_count:
        reasons.append("invalid_tail_skipped")
    if not row_count and status == "no_working_memory":
        reasons.append("no_working_memory")
    return {
        "kind": "aippocampus_working_memory_reader_diagnostic",
        "status": status,
        "path": str(path),
        "row_count": row_count,
        "invalid_line_count": invalid_line_count,
        "writer_in_progress": writer_in_progress,
        "diagnostics": list(dict.fromkeys(reasons)),
        "reader_lock_policy": "non_blocking_no_writer_lock_wait",
    }


def load_published_working_memory(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    pointer = read_pointer(path)
    if not pointer:
        return None
    writer_active = writer_lock_path(path).exists()
    current = resolve_published_path(path, pointer.get("current"))
    current_invalid = 0
    invalid_reasons: list[str] = []
    if current:
        if current.exists():
            current_rows, current_invalid = read_jsonl_rows(current, strict=True)
        else:
            current_rows, current_invalid = [], 1
            invalid_reasons.append("current_generation_missing")
        if not current_invalid:
            rows = working_rows(current_rows)
            return rows, diagnostic(
                status="published_generation_loaded",
                path=path,
                row_count=len(rows),
                writer_in_progress=writer_active,
            )
    last_good = resolve_published_path(path, pointer.get("last_known_good"))
    if last_good:
        fallback_rows, fallback_invalid = read_jsonl_rows(last_good, strict=True)
        if not fallback_invalid:
            rows = working_rows(fallback_rows)
            return rows, diagnostic(
                status="last_known_good_used",
                path=path,
                row_count=len(rows),
                invalid_line_count=current_invalid if current else 0,
                writer_in_progress=writer_active,
                diagnostics=(
                    "current_generation_invalid",
                    *invalid_reasons,
                    "last_known_good_used",
                ),
            )
    return [], diagnostic(
        status="no_working_memory",
        path=path,
        invalid_line_count=current_invalid if current else 0,
        writer_in_progress=writer_active,
        diagnostics=("current_generation_invalid", *invalid_reasons),
    )


def load_working_memory_with_diagnostics(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    published = load_published_working_memory(path)
    if published is not None:
        return published

    writer_active = writer_lock_path(path).exists()
    if not path.exists():
        return [], diagnostic(
            status="no_working_memory",
            path=path,
            writer_in_progress=writer_active,
        )
    rows, invalid = read_jsonl_rows(path, strict=False)
    working = working_rows(rows)
    status = "legacy_jsonl_loaded" if working else "no_working_memory"
    return working, diagnostic(
        status=status,
        path=path,
        row_count=len(working),
        invalid_line_count=invalid,
        writer_in_progress=writer_active,
    )


def load_working_memory(path: Path) -> list[dict[str, Any]]:
    rows, _ = load_working_memory_with_diagnostics(path)
    return rows
