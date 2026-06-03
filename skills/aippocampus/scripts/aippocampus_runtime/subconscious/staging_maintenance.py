#!/usr/bin/env python3
"""Maintenance reporting and explicit archival for local-private staging queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.registry.api import registry_paths, unique_preserve

REPORT_KIND = "aippocampus_subconscious_staging_maintenance_report"
ARCHIVE_MANIFEST_KIND = "aippocampus_subconscious_staging_archive_manifest"
EDGE_KIND = "aippocampus_subconscious_edge"
JOB_KIND = "aippocampus_subconscious_job_finding"
ARCHIVE_DIR_NAME = "subconscious_staging_archives"
DEFAULT_RECENT_EDGE_TAIL_BYTES = 256 * 1024
DEFAULT_MAX_RECENT_TAIL_ROWS = 512
DEFAULT_PRESSURE_MAX_ROWS = 5_000
DEFAULT_PRESSURE_MAX_BYTES = 32 * 1024 * 1024

QUEUE_FILES = {
    "subconscious_edges": "subconscious_edges.jsonl",
    "subconscious_jobs": "subconscious_jobs.jsonl",
}
REFERENCE_FILES = (
    "promotion_candidates.jsonl",
    "working_memory.jsonl",
    "dream_queue.jsonl",
    "dream_findings.jsonl",
    "question_pair_confirmation_requests.jsonl",
    "question_pair_confirmation_artifacts.jsonl",
)
IDENTIFIER_FIELDS = (
    "fingerprint",
    "finding_id",
    "source_finding_id",
    "edge_id",
    "question_cluster_id",
    "theme_cluster_id",
    "queue_item_id",
)
REFERENCE_COUNT_FIELDS = (
    "source_refs",
    "source_finding_ids",
    "resolved_source_finding_ids",
    "source_question_link_ids",
    "promotion_trace",
    "dream_refs",
    "dream_reference_ids",
    "question_refs",
    "review_refs",
    "audit_provenance",
    "private_audit_provenance",
)
ARCHIVE_STATUSES = {
    "rejected",
    "ignored",
    "suppressed",
    "noise",
    "weak",
    "failed",
    "expired",
}
MATERIALIZED_STATUSES = {"promoted", "materialized", "accepted", "routed"}


@dataclass(frozen=True)
class StagingPressureThresholds:
    max_rows: int = DEFAULT_PRESSURE_MAX_ROWS
    max_bytes: int = DEFAULT_PRESSURE_MAX_BYTES


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def default_pressure_thresholds() -> StagingPressureThresholds:
    return StagingPressureThresholds(
        max_rows=_env_int(
            "AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_ROWS",
            DEFAULT_PRESSURE_MAX_ROWS,
        ),
        max_bytes=_env_int(
            "AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_BYTES",
            DEFAULT_PRESSURE_MAX_BYTES,
        ),
    )


def parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_now(value: str | datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = parse_utc(value)
    if parsed:
        return parsed
    return datetime.now(timezone.utc)


def iter_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                item = dict(item)
                item["_maintenance_line_number"] = line_number
                rows.append(item)
    return rows


def iter_recent_jsonl_tail(
    path: Path,
    *,
    max_bytes: int = DEFAULT_RECENT_EDGE_TAIL_BYTES,
    max_rows: int = DEFAULT_MAX_RECENT_TAIL_ROWS,
) -> list[dict[str, Any]]:
    """Read a bounded JSONL tail for recent previews.

    The recent edge tool is model-facing context, not an audit report. It uses a
    byte tail so old corrupt or massive staging prefixes cannot make a
    foreground-adjacent tool scan the whole private queue.
    """

    if not path.exists() or max_bytes <= 0:
        return []
    size = path.stat().st_size
    start = max(0, size - int(max_bytes))
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read(int(max_bytes))
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-max(1, int(max_rows)) :]


def json_fingerprint(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_row_id(row: Mapping[str, Any]) -> str:
    for field in IDENTIFIER_FIELDS:
        value = str(row.get(field) or "").strip()
        if value:
            return value
    edge_payload = {
        "kind": row.get("kind"),
        "src": row.get("src"),
        "dst": row.get("dst"),
        "edge_type": row.get("edge_type"),
        "job": row.get("job"),
        "finding_kind": row.get("finding_kind"),
        "title": row.get("title"),
        "question_text": row.get("question_text"),
        "source_refs": row.get("source_refs") or [],
    }
    return f"sid_{json_fingerprint(edge_payload)[:24]}"


def identifier_format(value: str) -> str:
    text = str(value or "")
    if text.startswith("sf_"):
        return "legacy_sf"
    if len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text):
        return "sha256_hex"
    if text.startswith("sid_"):
        return "derived"
    return "other"


def row_sort_key(row: Mapping[str, Any]) -> tuple[str, int]:
    created = str(row.get("created_at") or "")
    return (created, int(row.get("_maintenance_line_number") or 0))


def public_count_value(value: Any) -> int:
    if isinstance(value, list | tuple | set):
        return len(value)
    if isinstance(value, dict):
        return 1 if value else 0
    return 1 if value else 0


def preserved_reference_counts(row: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in REFERENCE_COUNT_FIELDS:
        count = public_count_value(row.get(field))
        if count:
            counts[field] = count
    return counts


def iter_reference_ids(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, list | tuple | set):
        for item in value:
            yield from iter_reference_ids(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).endswith("_finding_id") or str(key).endswith("_finding_ids"):
                yield from iter_reference_ids(item)
            elif key in {
                "source_finding_id",
                "source_finding_ids",
                "resolved_source_finding_ids",
                "canonical_finding_id",
                "duplicate_finding_ids",
                "finding_id",
                "source_question_link_ids",
            }:
                yield from iter_reference_ids(item)


def referenced_finding_ids(root: Path) -> set[str]:
    referenced: set[str] = set()
    for name in REFERENCE_FILES:
        for row in iter_jsonl_rows(root / name):
            referenced.update(iter_reference_ids(row))
    return {item for item in referenced if item}


def queue_pressure(
    path: Path,
    *,
    row_count: int | None = None,
    thresholds: StagingPressureThresholds | None = None,
) -> dict[str, Any]:
    active_thresholds = thresholds or default_pressure_thresholds()
    rows = row_count if row_count is not None else len(iter_jsonl_rows(path))
    byte_count = path.stat().st_size if path.exists() else 0
    reasons: list[str] = []
    if active_thresholds.max_rows >= 0 and rows > active_thresholds.max_rows:
        reasons.append("row_threshold_exceeded")
    if active_thresholds.max_bytes >= 0 and byte_count > active_thresholds.max_bytes:
        reasons.append("byte_threshold_exceeded")
    return {
        "file_name": path.name,
        "row_count": int(rows),
        "byte_count": int(byte_count),
        "thresholds": {
            "max_rows": int(active_thresholds.max_rows),
            "max_bytes": int(active_thresholds.max_bytes),
        },
        "warning": bool(reasons),
        "warning_reasons": reasons,
        "pressure_level": "warning" if reasons else "ok",
    }


def aggregate_backpressure(pressures: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(item) for item in pressures]
    reasons = unique_preserve(
        [
            str(reason)
            for item in materialized
            for reason in item.get("warning_reasons") or []
            if str(reason)
        ]
    )
    return {
        "warning": bool(reasons),
        "warning_reasons": reasons,
        "queues": materialized,
    }


def classify_row(
    row: Mapping[str, Any],
    *,
    stable_id: str,
    duplicate_archive_ids: set[tuple[str, int]],
    referenced_ids: set[str],
    now: datetime,
    old_after_days: int,
    queue: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    line = int(row.get("_maintenance_line_number") or 0)
    status = str(row.get("status") or "staging").casefold()
    created_at = parse_utc(row.get("created_at"))
    is_old = bool(
        created_at and (now - created_at).days >= max(0, int(old_after_days))
    )
    if stable_id in referenced_ids:
        return "review", ["referenced_by_promotion_candidate"]
    if (queue, line) in duplicate_archive_ids:
        reasons.append("duplicate_older_than_kept")
    if status in ARCHIVE_STATUSES:
        reasons.append(f"status_{status}")
    if status in MATERIALIZED_STATUSES:
        reasons.append("materialized_or_promoted")
    if is_old and (status in ARCHIVE_STATUSES or (queue, line) in duplicate_archive_ids):
        reasons.append("older_than_retention_window")
    if reasons:
        return "archive_candidate", unique_preserve(reasons)
    if is_old:
        return "review", ["old_staging_row_needs_review"]
    if not preserved_reference_counts(row).get("source_refs"):
        return "review", ["missing_source_refs"]
    return "active", ["recent_source_backed_staging"]


def analyze_staging_queues(
    registry_dir: Path | str,
    *,
    now: str | datetime | None = None,
    old_after_days: int = 30,
    pressure_thresholds: StagingPressureThresholds | None = None,
) -> dict[str, Any]:
    root = Path(registry_dir)
    now_dt = normalize_now(now)
    thresholds = pressure_thresholds or default_pressure_thresholds()
    referenced_ids = referenced_finding_ids(root)
    records: list[dict[str, Any]] = []
    duplicate_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    compatibility: Counter[str] = Counter()
    queue_rows: dict[str, list[dict[str, Any]]] = {}

    for queue, filename in QUEUE_FILES.items():
        rows = iter_jsonl_rows(root / filename)
        queue_rows[queue] = rows
        for row in rows:
            stable_id = stable_row_id(row)
            id_format = identifier_format(stable_id)
            compatibility[f"{id_format}_id_count"] += 1
            record = {
                "queue": queue,
                "row": row,
                "line_number": int(row.get("_maintenance_line_number") or 0),
                "stable_id": stable_id,
                "id_format": id_format,
            }
            records.append(record)
            duplicate_index[(queue, stable_id)].append(record)

    duplicate_archive_ids: set[tuple[str, int]] = set()
    duplicate_groups: list[dict[str, Any]] = []
    for (queue, stable_id), group in duplicate_index.items():
        if len(group) <= 1:
            continue
        ordered = sorted(group, key=lambda item: row_sort_key(item["row"]), reverse=True)
        kept = ordered[0]
        archive_lines = sorted(int(item["line_number"]) for item in ordered[1:])
        duplicate_archive_ids.update((queue, line) for line in archive_lines)
        duplicate_groups.append(
            {
                "queue": queue,
                "stable_id": stable_id,
                "id_format": kept["id_format"],
                "lines": sorted(int(item["line_number"]) for item in group),
                "kept_line": int(kept["line_number"]),
                "archive_candidate_lines": archive_lines,
                "reason": "same_stable_id",
            }
        )

    row_actions: list[dict[str, Any]] = []
    queue_counts: dict[str, Counter[str]] = {queue: Counter() for queue in QUEUE_FILES}
    for record in records:
        row_map = cast(Mapping[str, Any], record["row"])
        queue = str(record["queue"])
        line_number = int(cast(Any, record["line_number"]))
        state, reasons = classify_row(
            row_map,
            stable_id=str(record["stable_id"]),
            duplicate_archive_ids=duplicate_archive_ids,
            referenced_ids=referenced_ids,
            now=now_dt,
            old_after_days=old_after_days,
            queue=queue,
        )
        queue_counts[queue][state] += 1
        row_actions.append(
            {
                "queue": queue,
                "line_number": line_number,
                "stable_id": record["stable_id"],
                "id_format": record["id_format"],
                "status": str(row_map.get("status") or "staging"),
                "created_at": row_map.get("created_at"),
                "maintenance_state": state,
                "reasons": reasons,
                "preserved_reference_counts": preserved_reference_counts(row_map),
            }
        )

    pressures = [
        queue_pressure(root / filename, row_count=len(queue_rows[queue]), thresholds=thresholds)
        for queue, filename in QUEUE_FILES.items()
    ]
    queues: dict[str, Any] = {}
    for queue, filename in QUEUE_FILES.items():
        counts = queue_counts[queue]
        queues[queue] = {
            "file_name": filename,
            "row_count": len(queue_rows[queue]),
            "active_count": int(counts.get("active", 0)),
            "review_count": int(counts.get("review", 0)),
            "archive_candidate_count": int(counts.get("archive_candidate", 0)),
            "status_counts": dict(
                sorted(
                    Counter(str(row.get("status") or "staging") for row in queue_rows[queue]).items()
                )
            ),
        }

    rows_with_source_refs = [
        action for action in row_actions if action["preserved_reference_counts"].get("source_refs")
    ]
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "mode": "dry_run",
        "old_after_days": int(old_after_days),
        "queues": queues,
        "row_actions": sorted(
            row_actions,
            key=lambda item: (str(item["queue"]), int(item["line_number"])),
        ),
        "duplicate_groups": sorted(
            duplicate_groups,
            key=lambda item: (str(item["queue"]), str(item["stable_id"])),
        ),
        "referenced_finding_id_count": len(referenced_ids),
        "compatibility": {
            "legacy_sf_id_count": int(compatibility.get("legacy_sf_id_count", 0)),
            "sha256_hex_id_count": int(compatibility.get("sha256_hex_id_count", 0)),
            "derived_id_count": int(compatibility.get("derived_id_count", 0)),
            "other_id_count": int(compatibility.get("other_id_count", 0)),
        },
        "backpressure": aggregate_backpressure(pressures),
        "safety": {
            "destructive_changes": False,
            "writes_enabled": False,
            "source_refs_preserved": all(
                action["preserved_reference_counts"].get("source_refs", 0) > 0
                for action in rows_with_source_refs
            ),
            "apply_boundary": "dry_run_only_no_archive_or_delete",
        },
    }


def default_registry_dir(registry_dir: str | None = None, registry: str | None = None) -> Path:
    if registry_dir:
        return Path(registry_dir).resolve()
    if registry:
        return Path(registry).resolve().parent
    registry_path, _ = registry_paths(None)
    return registry_path.resolve().parent


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report subconscious staging queue maintenance state.")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--old-after-days", type=int, default=30)
    parser.add_argument("--row-threshold", type=int)
    parser.add_argument("--byte-threshold", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Archive candidate rows with a manifest and rewrite active staging queues.",
    )
    parser.add_argument(
        "--archive-dir",
        help="Optional archive directory for --apply; defaults under the registry dir.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = default_registry_dir(args.registry_dir, args.registry)
    defaults = default_pressure_thresholds()
    thresholds = StagingPressureThresholds(
        max_rows=defaults.max_rows if args.row_threshold is None else int(args.row_threshold),
        max_bytes=defaults.max_bytes if args.byte_threshold is None else int(args.byte_threshold),
    )
    if args.apply:
        # Keep the default dry-run owner acyclic: apply-mode owns archive IO and
        # is loaded only when an operator explicitly asks for writes.
        from importlib import import_module

        archive = import_module("aippocampus_runtime.subconscious.staging_archive")
        report = archive.apply_staging_maintenance(
            root,
            old_after_days=args.old_after_days,
            pressure_thresholds=thresholds,
            archive_dir=args.archive_dir,
        )
    else:
        report = analyze_staging_queues(
            root,
            old_after_days=args.old_after_days,
            pressure_thresholds=thresholds,
        )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"subconscious staging maintenance: {report['mode']}")
        for queue, data in report["queues"].items():
            print(
                f"{queue}: rows={data['row_count']} active={data['active_count']} "
                f"review={data['review_count']} archive_candidates={data['archive_candidate_count']}"
            )
        if args.apply:
            applied = report.get("apply") or {}
            print(
                f"apply: archived={applied.get('archived_row_count', 0)} "
                f"retained={applied.get('retained_row_count', 0)} "
                f"manifest={applied.get('manifest_path', '')}"
            )
        if report["backpressure"]["warning"]:
            print("warning: " + ", ".join(report["backpressure"]["warning_reasons"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
