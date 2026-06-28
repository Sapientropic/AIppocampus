"""Claude Code hook event-log readers with loss accounting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows


def read_observed_event_log(event_log_path: Path | None) -> dict[str, Any]:
    if event_log_path is None:
        return {
            "status": "not_configured",
            "events": [],
            "event_count": 0,
            "malformed_line_count": 0,
            "unsupported_row_count": 0,
        }
    if not event_log_path.exists():
        return {
            "status": "missing",
            "events": [],
            "event_count": 0,
            "malformed_line_count": 0,
            "unsupported_row_count": 0,
        }
    seen: set[str] = set()
    result = load_jsonl_dict_rows(event_log_path)
    loss = result.loss
    malformed_line_count = int(loss.get("invalid_json_line_count") or 0)
    unsupported_row_count = int(loss.get("non_object_line_count") or 0)
    if int(loss.get("unreadable_file_count") or 0):
        return {
            "status": "unavailable",
            "events": [],
            "event_count": 0,
            "malformed_line_count": malformed_line_count,
            "unsupported_row_count": unsupported_row_count,
            "error_code": "unreadable_jsonl_file",
            "error_message": "event log could not be read",
        }
    for item in result.rows:
        event_name = str(item.get("hook_event_name") or item.get("event") or "")
        if event_name:
            seen.add(event_name)
        else:
            unsupported_row_count += 1
    return {
        "status": "loaded_with_loss"
        if malformed_line_count or unsupported_row_count
        else "loaded",
        "events": sorted(seen),
        "event_count": len(seen),
        "malformed_line_count": malformed_line_count,
        "unsupported_row_count": unsupported_row_count,
    }


def read_observed_events(event_log_path: Path | None) -> set[str]:
    return set(read_observed_event_log(event_log_path).get("events") or [])
