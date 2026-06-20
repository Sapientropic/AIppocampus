"""Compact Journey sidecar materialization.

Live Journey replay can contain waypoint-level source texture. Ordinary Task
Orientation only needs a tiny route-producer sidecar, so this module owns the
write/update path for ``journeys.jsonl`` without bloating ``journey.live``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.journey import tracking
from aippocampus_runtime.journey.live import create_journey_from_live_navigation_rows

SIDECAR_MATERIALIZATION_KIND = "aippocampus_live_journey_sidecar_materialization"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def _sidecar_source_refs(value: object) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in tracking.normalize_source_refs(value):
        refs.append(
            {
                key: val
                for key, val in dict(ref).items()
                if key
                in {
                    "thread_key",
                    "thread_id",
                    "message_id",
                    "turn_id",
                    "source_id",
                    "source_line",
                    "line",
                    "project_label",
                }
                and val not in {None, ""}
            }
        )
    return [ref for ref in refs if ref]


def _safe_sidecar_text(value: Any, *, fallback: str, limit: int) -> str:
    text = compact_text(str(value or "").strip(), limit)
    if not text or tracking.looks_like_private_payload(text):
        return fallback
    return text


def compact_journey_sidecar_row(journey_row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the default-orientation Journey row without full waypoints."""

    source_refs = _sidecar_source_refs(
        journey_row.get("current_frontier_source_refs") or journey_row.get("source_refs") or []
    )
    row = {
        "schema_version": tracking.SCHEMA_VERSION,
        "kind": tracking.JOURNEY_KIND,
        "journey_id": str(journey_row.get("journey_id") or ""),
        "path_label": _safe_sidecar_text(
            journey_row.get("path_label"),
            fallback="source-backed Journey route",
            limit=120,
        ),
        "core_inquiry": _safe_sidecar_text(
            journey_row.get("core_inquiry"),
            fallback="Reopen source-backed Journey route before continuing.",
            limit=220,
        ),
        "current_frontier": _safe_sidecar_text(
            journey_row.get("current_frontier"),
            fallback="Reopen the attached source route before continuing this Journey.",
            limit=260,
        ),
        "current_frontier_kind": str(
            journey_row.get("current_frontier_kind") or tracking.FRONTIER_KIND
        ),
        "source_refs": source_refs,
        "current_frontier_source_refs": source_refs[:4],
        "active_questions": [
            _safe_sidecar_text(item, fallback="source-backed open question", limit=160)
            for item in list(journey_row.get("active_questions") or [])[:4]
        ],
        "first_seen": str(journey_row.get("first_seen") or ""),
        "last_seen": str(journey_row.get("last_seen") or ""),
        "expires_at": str(journey_row.get("expires_at") or ""),
        "status": str(journey_row.get("status") or "traveling"),
        "materialized_from_live_candidates": True,
        "truth_boundary": (
            "Journey sidecars are navigation candidates; exact claims require attached source refs."
        ),
        "privacy_boundary": {
            "full_waypoints_serialized": False,
            "raw_live_rows_serialized": False,
            "local_paths_serialized": False,
            "source_reopen_required_before_claims": True,
        },
    }
    return {key: value for key, value in row.items() if value not in (None, "", [])}


def materialize_live_journey_sidecar(
    *,
    rows: Iterable[Mapping[str, Any]],
    output_path: str | Path,
    path_label: str,
    core_inquiry: str,
    as_of: str | None = None,
    status: str | None = None,
    min_threads: int = tracking.MIN_JOURNEY_THREADS,
) -> dict[str, Any]:
    """Create or update a compact ``journeys.jsonl`` row from live candidates."""

    result = create_journey_from_live_navigation_rows(
        path_label=path_label,
        core_inquiry=core_inquiry,
        rows=rows,
        as_of=as_of,
        min_threads=min_threads,
    )
    target = Path(output_path).expanduser().resolve()
    if not result.get("created") or not isinstance(result.get("journey"), Mapping):
        return {
            "kind": SIDECAR_MATERIALIZATION_KIND,
            "status": str(result.get("reason") or "not_materialized"),
            "created": False,
            "output_label": "journeys.jsonl",
            "metrics": result.get("metrics") or {},
            "privacy_boundary": {
                "raw_live_rows_serialized": False,
                "future_rows_serialized": False,
                "local_paths_serialized": False,
            },
        }
    journey_row = dict(result["journey"])
    if status in {"traveling", "camped", "arrived", "abandoned"}:
        journey_row["status"] = status
    compact_row = compact_journey_sidecar_row(journey_row)
    existing = [
        row
        for row in _read_jsonl(target)
        if str(row.get("journey_id") or "") != str(compact_row.get("journey_id") or "")
    ]
    _write_jsonl(target, [*existing, compact_row])
    return {
        "kind": SIDECAR_MATERIALIZATION_KIND,
        "status": "materialized",
        "created": True,
        "output_label": "journeys.jsonl",
        "journey_id": compact_row.get("journey_id"),
        "metrics": {
            **dict(result.get("metrics") or {}),
            "sidecar_row_count": len(existing) + 1,
            "full_waypoint_rows_serialized": 0,
        },
        "privacy_boundary": {
            "raw_live_rows_serialized": False,
            "full_waypoints_serialized": False,
            "future_rows_serialized": False,
            "local_paths_serialized": False,
            "source_reopen_required_before_claims": True,
        },
    }


__all__ = [
    "compact_journey_sidecar_row",
    "materialize_live_journey_sidecar",
]
