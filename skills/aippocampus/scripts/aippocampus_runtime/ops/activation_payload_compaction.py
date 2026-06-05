"""Intentional maintenance runner for activation payload compaction.

Dead-letter reports identify activation surfaces that should stop resurfacing;
owner-specific compaction is the separate physical payload step. This operator
keeps that step explicit and apply-gated so foreground hooks never mutate owner
files as a side effect of recall.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.dream.working_memory_compaction import (
    compact_dream_working_memory_payloads_from_dead_letter_manifest,
)
from aippocampus_runtime.recall.active_recall_lock_compaction import (
    compact_active_recall_lock_payloads_from_dead_letter_manifest,
)
from aippocampus_runtime.recall.ambient_cache_compaction import (
    compact_ambient_cache_payloads_from_dead_letter_manifest,
)
from aippocampus_runtime.recall.semantic_trigger_compaction import (
    compact_semantic_trigger_payloads_from_dead_letter_manifest,
)

RUN_SCHEMA_VERSION = 1
RUN_KIND = "aippocampus_activation_payload_compaction_run"


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            for row in rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            json.dump(dict(data), handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _missing_owner_report(owner: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "status": "skipped",
        "skip_reason": "owner_path_missing",
        "metrics": {"payload_compacted_count": 0, "unsafe_update_count": 0, "skipped_count": 1},
    }


def _not_requested_report(owner: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "status": "not_requested",
        "metrics": {"payload_compacted_count": 0, "unsafe_update_count": 0, "skipped_count": 0},
    }


def _owner_metrics(report: Mapping[str, Any]) -> Mapping[str, Any]:
    metrics = report.get("metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _run_ambient_cache(
    path: Path | None,
    dead_letter_manifest: Mapping[str, Any],
    *,
    apply: bool,
    compacted_at: str | None,
) -> dict[str, Any]:
    if path is None:
        return _not_requested_report("ambient_cache")
    if not path.exists():
        return _missing_owner_report("ambient_cache")
    if apply:
        return compact_ambient_cache_payloads_from_dead_letter_manifest(
            path,
            dict(dead_letter_manifest),
            compacted_at=compacted_at,
        )
    with tempfile.TemporaryDirectory() as tmp:
        dry_run_path = Path(tmp) / path.name
        shutil.copyfile(path, dry_run_path)
        return compact_ambient_cache_payloads_from_dead_letter_manifest(
            dry_run_path,
            dict(dead_letter_manifest),
            compacted_at=compacted_at,
        )


def _run_working_memory(
    path: Path | None,
    dead_letter_manifest: Mapping[str, Any],
    *,
    apply: bool,
    compacted_at: str | None,
) -> dict[str, Any]:
    if path is None:
        return _not_requested_report("working_memory")
    if not path.exists():
        return _missing_owner_report("working_memory")
    rows = _load_jsonl(path)
    next_rows, report = compact_dream_working_memory_payloads_from_dead_letter_manifest(
        rows,
        dead_letter_manifest,
        compacted_at=compacted_at,
    )
    if apply and _safe_int(_owner_metrics(report).get("payload_compacted_count")) > 0:
        _write_jsonl_atomic(path, next_rows)
    return report


def _run_semantic_triggers(
    path: Path | None,
    dead_letter_manifest: Mapping[str, Any],
    *,
    apply: bool,
    compacted_at: str | None,
) -> dict[str, Any]:
    if path is None:
        return _not_requested_report("semantic_triggers")
    if not path.exists():
        return _missing_owner_report("semantic_triggers")
    rows = _load_jsonl(path)
    next_rows, report = compact_semantic_trigger_payloads_from_dead_letter_manifest(
        rows,
        dead_letter_manifest,
        compacted_at=compacted_at,
    )
    if apply and _safe_int(_owner_metrics(report).get("payload_compacted_count")) > 0:
        _write_jsonl_atomic(path, next_rows)
    return report


def _run_active_recall_locks(
    path: Path | None,
    dead_letter_manifest: Mapping[str, Any],
    *,
    apply: bool,
    compacted_at: str | None,
) -> dict[str, Any]:
    if path is None:
        return _not_requested_report("active_recall_locks")
    if not path.exists():
        return _missing_owner_report("active_recall_locks")
    store = _load_json(path)
    next_store, report = compact_active_recall_lock_payloads_from_dead_letter_manifest(
        store,
        dead_letter_manifest,
        compacted_at=compacted_at,
    )
    if apply and _safe_int(_owner_metrics(report).get("payload_compacted_count")) > 0:
        _write_json_atomic(path, next_store)
    return report


def _total_metric(owner_reports: Mapping[str, Mapping[str, Any]], key: str) -> int:
    return sum(_safe_int(_owner_metrics(report).get(key)) for report in owner_reports.values())


def _owner_count_run(owner_reports: Mapping[str, Mapping[str, Any]]) -> int:
    return sum(
        1
        for report in owner_reports.values()
        if report.get("status") not in {"not_requested", "skipped"}
    )


def run_activation_payload_compaction(
    *,
    dead_letter_manifest_path: Path | str,
    ambient_cache_path: Path | str | None = None,
    working_memory_path: Path | str | None = None,
    semantic_triggers_path: Path | str | None = None,
    active_recall_locks_path: Path | str | None = None,
    apply: bool = False,
    compacted_at: str | None = None,
) -> dict[str, Any]:
    """Run owner compaction against an explicit dead-letter apply manifest.

    The returned report is public-safe by construction: it contains owner names,
    hash ids, counts, reason codes, provenance hashes, and policy flags, but not
    raw activation payloads, source refs, or local filesystem paths.
    """

    manifest = _load_json(Path(dead_letter_manifest_path))
    owner_reports: dict[str, dict[str, Any]] = {
        "ambient_cache": _run_ambient_cache(
            Path(ambient_cache_path) if ambient_cache_path is not None else None,
            manifest,
            apply=apply,
            compacted_at=compacted_at,
        ),
        "working_memory": _run_working_memory(
            Path(working_memory_path) if working_memory_path is not None else None,
            manifest,
            apply=apply,
            compacted_at=compacted_at,
        ),
        "semantic_triggers": _run_semantic_triggers(
            Path(semantic_triggers_path) if semantic_triggers_path is not None else None,
            manifest,
            apply=apply,
            compacted_at=compacted_at,
        ),
        "active_recall_locks": _run_active_recall_locks(
            Path(active_recall_locks_path) if active_recall_locks_path is not None else None,
            manifest,
            apply=apply,
            compacted_at=compacted_at,
        ),
    }
    compacted_count = _total_metric(owner_reports, "payload_compacted_count")
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "kind": RUN_KIND,
        "ok": True,
        "status": "compacted" if compacted_count else "no_changes",
        "applied": apply,
        "write_mode": "apply_owner_payload_compaction" if apply else "no_write_dry_run",
        "owners": owner_reports,
        "metrics": {
            "owner_count_requested": sum(
                1
                for value in [
                    ambient_cache_path,
                    working_memory_path,
                    semantic_triggers_path,
                    active_recall_locks_path,
                ]
                if value is not None
            ),
            "owner_count_run": _owner_count_run(owner_reports),
            "payload_compacted_count": compacted_count,
            "unsafe_update_count": _total_metric(owner_reports, "unsafe_update_count"),
            "skipped_count": _total_metric(owner_reports, "skipped_count"),
        },
        "contract": {
            "dead_letter_manifest_required": True,
            "owner_paths_explicit": True,
            "apply_required_for_writes": True,
            "dry_run_default": True,
            "foreground_hook_mutation": False,
            "clean_source_mutation": False,
            "raw_rollout_mutation": False,
            "truth_status_changed": False,
            "source_refs_preserved": True,
            "row_transform_only_for_jsonl_owners": True,
            "json_owner_transform_only_for_active_recall_locks": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "raw_activation_payload_serialized": False,
            "source_refs_serialized": False,
            "local_paths_serialized": False,
            "candidate_identity": "surface_id_hash_only",
        },
        "remaining_boundary": {
            "semantic_trigger_seed_files_mutated": False,
            "semantic_trigger_promotion_candidates_mutated": False,
            "active_recall_lock_lifecycle_fully_closed": False,
            "owner_lifecycle_fully_closed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dead-letter-manifest", required=True)
    parser.add_argument("--ambient-cache")
    parser.add_argument("--working-memory")
    parser.add_argument("--semantic-triggers")
    parser.add_argument("--active-recall-locks")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--compacted-at")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = run_activation_payload_compaction(
        dead_letter_manifest_path=args.dead_letter_manifest,
        ambient_cache_path=args.ambient_cache,
        working_memory_path=args.working_memory,
        semantic_triggers_path=args.semantic_triggers,
        active_recall_locks_path=args.active_recall_locks,
        apply=args.apply,
        compacted_at=args.compacted_at,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        metrics = report["metrics"]
        print(
            "activation payload compaction "
            f"{report['status']} "
            f"owners={metrics['owner_count_run']} "
            f"payloads={metrics['payload_compacted_count']} "
            f"mode={report['write_mode']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RUN_KIND",
    "run_activation_payload_compaction",
    "main",
]
