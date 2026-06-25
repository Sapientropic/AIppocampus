#!/usr/bin/env python3
"""Explicit archival apply mode for subconscious staging maintenance."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows
from aippocampus_runtime.subconscious import staging_maintenance as maintenance


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def filesystem_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def strip_maintenance_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not str(key).startswith("_maintenance_")}


def write_archive_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    write_jsonl_dict_rows(
        path,
        (strip_maintenance_fields(row) for row in rows),
        sort_keys=True,
    )


def atomic_write_retained_queue_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    write_archive_rows(temp_path, rows)
    os.replace(temp_path, path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _resolve_manifest_relative_path(root: Path, relative_path: object) -> Path | None:
    text = str(relative_path or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _unique_archive_dir(root: Path, now_dt: datetime) -> Path:
    base = root / maintenance.ARCHIVE_DIR_NAME / filesystem_timestamp(now_dt)
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{suffix:02d}")
        suffix += 1
    return candidate


def _row_action_index(report: Mapping[str, Any]) -> dict[tuple[str, int], Mapping[str, Any]]:
    return {
        (str(action.get("queue") or ""), int(action.get("line_number") or 0)): action
        for action in report.get("row_actions") or []
        if isinstance(action, Mapping)
    }


def _manifest_row(
    action: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    archive_relative_path: str,
) -> dict[str, Any]:
    clean_row = strip_maintenance_fields(row)
    return {
        "queue": action.get("queue"),
        "line_number": action.get("line_number"),
        "stable_id": action.get("stable_id"),
        "id_format": action.get("id_format"),
        "status": action.get("status"),
        "created_at": action.get("created_at"),
        "reasons": action.get("reasons") or [],
        "archive_relative_path": archive_relative_path,
        "row_sha256": maintenance.json_fingerprint(clean_row),
        "preserved_reference_counts": maintenance.preserved_reference_counts(clean_row),
    }


def _write_archive_manifest(manifest_path: Path, manifest: Mapping[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_staging_archive_manifest(
    registry_dir: Path | str,
    manifest_path: Path | str,
) -> dict[str, Any]:
    root = Path(registry_dir).resolve()
    manifest_file = Path(manifest_path)
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "error_codes": ["invalid_archive_manifest"],
            "checked_archive_files": 0,
        }
    if not isinstance(manifest, dict) or manifest.get("kind") != maintenance.ARCHIVE_MANIFEST_KIND:
        errors.append("unexpected_archive_manifest_kind")

    expected_rows_by_queue: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in manifest.get("rows") or []:
        if isinstance(row, Mapping):
            expected_rows_by_queue[str(row.get("queue") or "")].append(row)

    checked_files = 0
    for archive_file in manifest.get("archive_files") or []:
        if not isinstance(archive_file, Mapping):
            errors.append("invalid_archive_file_entry")
            continue
        queue = str(archive_file.get("queue") or "")
        path = _resolve_manifest_relative_path(root, archive_file.get("relative_path"))
        if path is None:
            errors.append("archive_path_outside_registry")
            continue
        if not path.exists():
            errors.append("archive_file_missing")
            continue
        checked_files += 1
        if str(archive_file.get("sha256") or "") != file_sha256(path):
            errors.append("archive_file_hash_mismatch")
        if int(archive_file.get("byte_count") or 0) != path.stat().st_size:
            errors.append("archive_file_size_mismatch")
        rows = maintenance.load_staging_queue_rows(path)
        if int(archive_file.get("row_count") or 0) != len(rows):
            errors.append("archive_file_row_count_mismatch")
        expected_rows = expected_rows_by_queue.get(queue, [])
        expected_ids = [str(row.get("stable_id") or "") for row in expected_rows]
        actual_ids = [maintenance.stable_row_id(row) for row in rows]
        if expected_ids != actual_ids:
            errors.append("archive_file_row_id_mismatch")
        expected_hashes = [str(row.get("row_sha256") or "") for row in expected_rows]
        actual_hashes = [
            maintenance.json_fingerprint(strip_maintenance_fields(row)) for row in rows
        ]
        if expected_hashes != actual_hashes:
            errors.append("archive_row_hash_mismatch")

    return {
        "ok": not errors,
        "error_codes": unique_preserve(errors),
        "checked_archive_files": checked_files,
    }


def apply_staging_maintenance(
    registry_dir: Path | str,
    *,
    now: str | datetime | None = None,
    old_after_days: int = 30,
    pressure_thresholds: maintenance.StagingPressureThresholds | None = None,
    archive_dir: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(registry_dir).resolve()
    now_dt = maintenance.normalize_now(now)
    report = maintenance.analyze_staging_queues(
        root,
        now=now_dt,
        old_after_days=old_after_days,
        pressure_thresholds=pressure_thresholds,
    )
    action_index = _row_action_index(report)
    archive_root = Path(archive_dir).resolve() if archive_dir else _unique_archive_dir(root, now_dt)

    retained_by_queue: dict[str, list[dict[str, Any]]] = {}
    archive_files: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    retained_row_count = 0
    archived_row_count = 0

    for queue, filename in maintenance.QUEUE_FILES.items():
        retained_rows: list[dict[str, Any]] = []
        archived_rows: list[dict[str, Any]] = []
        for row in maintenance.load_staging_queue_rows(root / filename):
            line_number = int(row.get("_maintenance_line_number") or 0)
            action = action_index.get((queue, line_number))
            if action and action.get("maintenance_state") == "archive_candidate":
                archived_rows.append(row)
            else:
                retained_rows.append(row)
        retained_by_queue[queue] = retained_rows
        retained_row_count += len(retained_rows)
        archived_row_count += len(archived_rows)
        if not archived_rows:
            continue
        archive_root.mkdir(parents=True, exist_ok=True)
        archive_path = archive_root / f"{filename}.archive.jsonl"
        write_archive_rows(archive_path, archived_rows)
        relative_path = _safe_relative_path(archive_path, root)
        archive_files.append(
            {
                "queue": queue,
                "file_name": filename,
                "relative_path": relative_path,
                "row_count": len(archived_rows),
                "byte_count": archive_path.stat().st_size,
                "sha256": file_sha256(archive_path),
            }
        )
        for row in archived_rows:
            action = action_index[(queue, int(row.get("_maintenance_line_number") or 0))]
            manifest_rows.append(_manifest_row(action, row, archive_relative_path=relative_path))

    if archived_row_count == 0:
        report["mode"] = "apply"
        report["apply"] = {
            "manifest_verification": {
                "ok": True,
                "error_codes": [],
                "checked_archive_files": 0,
            },
            "archived_row_count": 0,
            "retained_row_count": retained_row_count,
            "queue_rewrite_status": "skipped_no_archive_candidates",
        }
        report["safety"] = {
            **report["safety"],
            "writes_enabled": True,
            "destructive_changes": False,
            "apply_boundary": "explicit_apply_no_archive_candidates",
        }
        return report

    manifest_path = archive_root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": maintenance.ARCHIVE_MANIFEST_KIND,
        "archive_status": "pending_verification",
        "created_at": now_utc(),
        "archived_at": isoformat_utc(now_dt),
        "old_after_days": int(old_after_days),
        "source_report_kind": maintenance.REPORT_KIND,
        "archive_files": archive_files,
        "rows": sorted(
            manifest_rows,
            key=lambda item: (str(item["queue"]), int(item["line_number"])),
        ),
        "archived_row_count": archived_row_count,
        "retained_row_count": retained_row_count,
        "compatibility": report["compatibility"],
        "safety": {
            "archive_before_queue_rewrite": True,
            "source_refs_preserved": True,
            "referenced_rows_archived": any(
                "referenced_by_promotion_candidate" in row.get("reasons", [])
                for row in manifest_rows
            ),
            "foreground_hook_safe": "apply_mode_is_explicit_cli_or_library_only",
        },
    }
    _write_archive_manifest(manifest_path, manifest)
    verification = verify_staging_archive_manifest(root, manifest_path)
    if verification["ok"]:
        manifest["archive_status"] = "verified"
        _write_archive_manifest(manifest_path, manifest)
        verification = verify_staging_archive_manifest(root, manifest_path)

    if not verification["ok"]:
        report["mode"] = "apply"
        report["apply"] = {
            "manifest_path": str(manifest_path),
            "manifest_verification": verification,
            "archived_row_count": archived_row_count,
            "retained_row_count": retained_row_count,
            "queue_rewrite_status": "skipped_manifest_verification_failed",
        }
        report["safety"] = {
            **report["safety"],
            "writes_enabled": True,
            "destructive_changes": False,
            "apply_boundary": "archive_written_queue_rewrite_skipped",
        }
        return report

    for queue, filename in maintenance.QUEUE_FILES.items():
        atomic_write_retained_queue_rows(root / filename, retained_by_queue[queue])

    report["mode"] = "apply"
    report["apply"] = {
        "archive_dir": str(archive_root),
        "manifest_path": str(manifest_path),
        "manifest_verification": verification,
        "archive_files": archive_files,
        "archived_row_count": archived_row_count,
        "retained_row_count": retained_row_count,
        "queue_rewrite_status": "applied",
    }
    report["safety"] = {
        **report["safety"],
        "writes_enabled": True,
        "destructive_changes": bool(archived_row_count),
        "apply_boundary": "explicit_apply_archive_manifest_then_rewrite_active_queue",
    }
    return report
