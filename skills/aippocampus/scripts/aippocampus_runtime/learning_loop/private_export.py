"""Opt-in private-history export for learning-loop replay.

This module is the boundary between raw local history and the replay harness.
It may read an operator-selected rollout or clean-source behavior-event file,
but it only writes scrubbed categorical behavior rows suitable for replay.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.behavior_events import extract_rollout_behavior_events

SCHEMA_VERSION = 1
EXPORT_REPORT_KIND = "aippocampus_learning_loop_private_replay_export_report"

ALLOWED_KEYS = {
    "kind",
    "event_id",
    "timestamp",
    "turn_index",
    "event_kind",
    "hard_event_kind",
    "tool_payload_kind",
    "tool_name",
    "command_class",
    "tool_intent",
    "command_family",
    "target_class",
    "failure_family",
    "exit_code",
    "status",
    "target_fingerprint",
    "path_category_fingerprint",
    "workspace_or_environment_profile",
    "scope",
    "freshness_window",
    "source_refs",
    "sequence_index",
    "expected_local_red",
    "path_count",
    "path_categories",
    "path_extensions",
    "path_fingerprints",
    "generated_file",
    "generated_file_reason",
    "critical_operation_family",
}
RAW_BLOCKED_KEYS = {
    "args",
    "arguments",
    "command",
    "content",
    "input",
    "output",
    "prompt",
    "raw_text",
    "stderr",
    "stdout",
    "tool_args",
    "tool_input",
    "tool_output",
    "tool_response",
}
LOCAL_PATH_SENTINELS = ("E:/", "C:/", "\\Users\\", "/Users/", "/home/", "/tmp/")


def _stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _refs(row: Mapping[str, Any], *, source_label: str) -> list[dict[str, Any]]:
    refs = row.get("source_refs")
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        clean = []
        for item in refs:
            if not isinstance(item, Mapping):
                continue
            ref = {
                key: item.get(key)
                for key in ("thread_key", "source_id", "message_id", "turn_id", "turn_index", "line", "source_line")
                if item.get(key) not in (None, "", [])
            }
            if ref:
                clean.append(ref)
        if clean:
            return clean[:4]
    line = row.get("line") or row.get("source_line")
    turn = row.get("turn_index")
    ref = {"source_id": source_label}
    if line not in (None, ""):
        ref["line"] = line
    if turn not in (None, ""):
        ref["turn_index"] = turn
    return [ref]


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        if any(sentinel.replace("\\", "/") in normalized for sentinel in LOCAL_PATH_SENTINELS):
            return "redacted_local_value:" + hashlib.sha256(
                normalized.casefold().encode("utf-8")
            ).hexdigest()[:16]
        return normalized
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_value(val) for key, val in value.items()}
    return value


def sanitize_events_for_private_replay(
    events: Iterable[Mapping[str, Any]],
    *,
    source_label: str = "private_sanitized_history",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            continue
        row = {
            key: _safe_value(value)
            for key, value in event.items()
            if key in ALLOWED_KEYS and key not in RAW_BLOCKED_KEYS
        }
        row["kind"] = "behavior_event"
        row["event_id"] = str(row.get("event_id") or _stable_id("private_event", index, event.get("line")))
        row["sequence_index"] = int(row.get("sequence_index") or index)
        row["source_refs"] = _refs(event, source_label=source_label)
        row.setdefault("scope", "project_or_task_family")
        row.setdefault("workspace_or_environment_profile", "private_sanitized_history")
        row.setdefault("freshness_window", "recent")
        rows.append(row)
    return rows


def validate_private_replay_export(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    encoded = json.dumps(materialized, ensure_ascii=False, sort_keys=True)
    blocked_key_count = sum(1 for row in materialized for key in row if key in RAW_BLOCKED_KEYS)
    local_path_leak_count = sum(1 for sentinel in LOCAL_PATH_SENTINELS if sentinel in encoded)
    missing_source_ref_count = sum(1 for row in materialized if not row.get("source_refs"))
    return {
        "kind": EXPORT_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": blocked_key_count == 0 and local_path_leak_count == 0 and missing_source_ref_count == 0,
        "event_count": len(materialized),
        "blocked_raw_key_count": blocked_key_count,
        "local_path_leak_count": local_path_leak_count,
        "missing_source_ref_count": missing_source_ref_count,
        "privacy_boundary": {
            "raw_rollout_text_serialized": False,
            "raw_stdout_stderr_serialized": False,
            "full_commands_serialized": False,
            "local_paths_serialized": False,
        },
    }


def load_behavior_event_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [
            dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        rows = payload.get("events") or payload.get("behavior_events") or payload.get("rows") or []
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def export_private_replay_events(
    *,
    output: Path,
    clean_source_events: Path | None = None,
    rollout: Path | None = None,
    source_label: str = "private_sanitized_history",
) -> dict[str, Any]:
    if clean_source_events is None and rollout is None:
        raise ValueError("export requires --clean-source-events or --rollout")
    raw_rows = (
        extract_rollout_behavior_events(rollout)
        if rollout is not None
        else load_behavior_event_rows(clean_source_events)  # type: ignore[arg-type]
    )
    rows = sanitize_events_for_private_replay(raw_rows, source_label=source_label)
    validation = validate_private_replay_export(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    return {
        **validation,
        "wrote": True,
        "input_origin": "raw_rollout_sanitized" if rollout is not None else "clean_source_events_sanitized",
        "output_private_artifact": True,
    }


__all__ = [
    "export_private_replay_events",
    "load_behavior_event_rows",
    "sanitize_events_for_private_replay",
    "validate_private_replay_export",
]
