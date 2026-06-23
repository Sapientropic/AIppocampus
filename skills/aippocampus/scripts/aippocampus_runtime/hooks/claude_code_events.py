"""Claude Code hook event-log readers with loss accounting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    malformed_line_count = 0
    unsupported_row_count = 0
    try:
        with event_log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed_line_count += 1
                    continue
                if not isinstance(item, dict):
                    unsupported_row_count += 1
                    continue
                event_name = str(item.get("hook_event_name") or item.get("event") or "")
                if event_name:
                    seen.add(event_name)
                else:
                    unsupported_row_count += 1
    except OSError as exc:
        return {
            "status": "unavailable",
            "events": [],
            "event_count": 0,
            "malformed_line_count": malformed_line_count,
            "unsupported_row_count": unsupported_row_count,
            "error_code": type(exc).__name__,
            "error_message": str(exc),
        }
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
