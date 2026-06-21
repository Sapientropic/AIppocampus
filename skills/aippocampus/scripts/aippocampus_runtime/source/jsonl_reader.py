"""Shared JSONL dict-reader with bounded loss accounting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonlReadResult:
    rows: list[dict[str, Any]]
    loss: dict[str, Any]


def empty_jsonl_loss() -> dict[str, Any]:
    return {
        "invalid_json_line_count": 0,
        "non_object_line_count": 0,
        "skipped_empty_line_count": 0,
        "unreadable_file_count": 0,
        "total_loss_count": 0,
        "warning_codes": [],
    }


def _finish_loss(loss: dict[str, Any]) -> dict[str, Any]:
    total = (
        int(loss.get("invalid_json_line_count") or 0)
        + int(loss.get("non_object_line_count") or 0)
        + int(loss.get("unreadable_file_count") or 0)
    )
    codes: list[str] = []
    if loss.get("invalid_json_line_count"):
        codes.append("invalid_json_lines")
    if loss.get("non_object_line_count"):
        codes.append("non_object_json_lines")
    if loss.get("unreadable_file_count"):
        codes.append("unreadable_jsonl_file")
    clean = dict(loss)
    clean["total_loss_count"] = total
    clean["warning_codes"] = codes
    return clean


def iter_jsonl_dict_rows(path: Path, *, loss: dict[str, Any] | None = None):
    """Yield JSON object rows and increment bounded loss counters.

    The helper intentionally does not retain malformed line text. Callers may
    include the aggregate counters in diagnostics, but compact foreground output
    should avoid raw local paths and source contents.
    """

    counters = loss if loss is not None else empty_jsonl_loss()
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    counters["skipped_empty_line_count"] = (
                        int(counters.get("skipped_empty_line_count") or 0) + 1
                    )
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    counters["invalid_json_line_count"] = (
                        int(counters.get("invalid_json_line_count") or 0) + 1
                    )
                    continue
                if not isinstance(item, dict):
                    counters["non_object_line_count"] = (
                        int(counters.get("non_object_line_count") or 0) + 1
                    )
                    continue
                yield item
    except OSError:
        counters["unreadable_file_count"] = int(counters.get("unreadable_file_count") or 0) + 1
        return


def load_jsonl_dict_rows(path: Path) -> JsonlReadResult:
    loss = empty_jsonl_loss()
    rows = list(iter_jsonl_dict_rows(path, loss=loss))
    return JsonlReadResult(rows=rows, loss=_finish_loss(loss))


def jsonl_loss_warning(
    loss: dict[str, Any],
    *,
    stage: str,
    path_label: str,
) -> dict[str, Any] | None:
    if int(loss.get("total_loss_count") or 0) <= 0:
        return None
    return {
        "code": "jsonl_read_degraded",
        "stage": stage,
        "path": path_label,
        "invalid_json_line_count": int(loss.get("invalid_json_line_count") or 0),
        "non_object_line_count": int(loss.get("non_object_line_count") or 0),
        "unreadable_file_count": int(loss.get("unreadable_file_count") or 0),
        "total_loss_count": int(loss.get("total_loss_count") or 0),
        "warning_codes": list(loss.get("warning_codes") or []),
        "message": "JSONL reader skipped malformed or unreadable rows; treat misses as degraded.",
    }
