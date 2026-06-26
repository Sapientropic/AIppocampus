"""Canonical source-backed JSON/JSONL and source-ref primitives.

These helpers sit at the source trust boundary. They keep malformed input loss
counted for detail/operator surfaces while avoiding raw malformed line content
or local paths in compact foreground output.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.io_integrity import atomic_write_json, atomic_write_jsonl

MAX_LOSS_LINE_NUMBERS = 20


@dataclass(frozen=True)
class JsonlReadResult:
    rows: list[dict[str, Any]]
    loss: dict[str, Any]


@dataclass(frozen=True)
class JsonReadResult:
    data: dict[str, Any]
    loss: dict[str, Any]


def empty_jsonl_loss() -> dict[str, Any]:
    return {
        "invalid_json_line_count": 0,
        "non_object_line_count": 0,
        "skipped_empty_line_count": 0,
        "unreadable_file_count": 0,
        "total_loss_count": 0,
        "invalid_json_line_numbers": [],
        "non_object_line_numbers": [],
        "warning_codes": [],
    }


def empty_json_loss() -> dict[str, Any]:
    return {
        "invalid_json_count": 0,
        "non_object_json_count": 0,
        "unreadable_file_count": 0,
        "missing_file_count": 0,
        "total_loss_count": 0,
        "warning_codes": [],
    }


def _finish_jsonl_loss(loss: dict[str, Any]) -> dict[str, Any]:
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


def _finish_json_loss(loss: dict[str, Any]) -> dict[str, Any]:
    total = (
        int(loss.get("invalid_json_count") or 0)
        + int(loss.get("non_object_json_count") or 0)
        + int(loss.get("unreadable_file_count") or 0)
        + int(loss.get("missing_file_count") or 0)
    )
    codes: list[str] = []
    if loss.get("invalid_json_count"):
        codes.append("invalid_json")
    if loss.get("non_object_json_count"):
        codes.append("non_object_json")
    if loss.get("unreadable_file_count"):
        codes.append("unreadable_json_file")
    if loss.get("missing_file_count"):
        codes.append("missing_json_file")
    clean = dict(loss)
    clean["total_loss_count"] = total
    clean["warning_codes"] = codes
    return clean


def iter_jsonl_dict_rows(
    path: Path,
    *,
    loss: dict[str, Any] | None = None,
) -> Iterable[dict[str, Any]]:
    for _, item in iter_jsonl_dict_rows_with_line_numbers(path, loss=loss):
        yield item


def iter_jsonl_dict_rows_with_line_numbers(
    path: Path,
    *,
    loss: dict[str, Any] | None = None,
) -> Iterable[tuple[int, dict[str, Any]]]:
    """Yield JSON object rows with line numbers and bounded loss counters."""

    counters = loss if loss is not None else empty_jsonl_loss()
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
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
                    line_numbers = counters.setdefault("invalid_json_line_numbers", [])
                    if isinstance(line_numbers, list) and len(line_numbers) < MAX_LOSS_LINE_NUMBERS:
                        line_numbers.append(line_no)
                    continue
                if not isinstance(item, dict):
                    counters["non_object_line_count"] = (
                        int(counters.get("non_object_line_count") or 0) + 1
                    )
                    line_numbers = counters.setdefault("non_object_line_numbers", [])
                    if isinstance(line_numbers, list) and len(line_numbers) < MAX_LOSS_LINE_NUMBERS:
                        line_numbers.append(line_no)
                    continue
                yield line_no, item
    except OSError:
        counters["unreadable_file_count"] = int(counters.get("unreadable_file_count") or 0) + 1
        return


def load_jsonl_dict_rows(path: Path) -> JsonlReadResult:
    loss = empty_jsonl_loss()
    rows = list(iter_jsonl_dict_rows(path, loss=loss))
    return JsonlReadResult(rows=rows, loss=_finish_jsonl_loss(loss))


def parse_jsonl_dict_rows_text(text: str, *, strict: bool = False) -> JsonlReadResult:
    """Parse already-read JSONL text through the same loss-accounting contract."""

    loss = empty_jsonl_loss()
    rows = [
        item
        for _, item in iter_jsonl_dict_rows_text_with_line_numbers(
            text,
            loss=loss,
            strict=strict,
        )
    ]
    finished_loss = _finish_jsonl_loss(loss)
    if strict and int(finished_loss.get("total_loss_count") or 0):
        rows = []
    return JsonlReadResult(rows=rows, loss=finished_loss)


def iter_jsonl_dict_rows_text_with_line_numbers(
    text: str,
    *,
    loss: dict[str, Any] | None = None,
    strict: bool = False,
) -> Iterable[tuple[int, dict[str, Any]]]:
    """Yield JSON object rows from in-memory JSONL text with bounded loss counters."""

    counters = loss if loss is not None else empty_jsonl_loss()
    for line_no, line in enumerate(text.splitlines(), start=1):
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
            line_numbers = counters.setdefault("invalid_json_line_numbers", [])
            if isinstance(line_numbers, list) and len(line_numbers) < MAX_LOSS_LINE_NUMBERS:
                line_numbers.append(line_no)
            if strict:
                return
            continue
        if not isinstance(item, dict):
            counters["non_object_line_count"] = (
                int(counters.get("non_object_line_count") or 0) + 1
            )
            line_numbers = counters.setdefault("non_object_line_numbers", [])
            if isinstance(line_numbers, list) and len(line_numbers) < MAX_LOSS_LINE_NUMBERS:
                line_numbers.append(line_no)
            if strict:
                return
            continue
        yield line_no, item


def load_jsonl_dict_rows_strict(path: Path) -> list[dict[str, Any]]:
    """Load JSONL object rows and fail with line context on malformed input."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no} is invalid JSON") from exc
            if not isinstance(item, dict):
                raise ValueError(f"line {line_no} is not a JSON object")
            rows.append(item)
    return rows


def load_jsonl_dict_rows_with_line_field(
    path: Path,
    *,
    line_field: str,
) -> JsonlReadResult:
    """Load JSONL rows and attach source line numbers for audit/detail flows."""

    loss = empty_jsonl_loss()
    rows: list[dict[str, Any]] = []
    for line_no, item in iter_jsonl_dict_rows_with_line_numbers(path, loss=loss):
        row = dict(item)
        row[str(line_field)] = line_no
        rows.append(row)
    return JsonlReadResult(rows=rows, loss=_finish_jsonl_loss(loss))


def write_jsonl_dict_rows(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    sort_keys: bool = False,
) -> None:
    atomic_write_jsonl(path, rows, sort_keys=sort_keys)


def append_jsonl_dict_rows(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    sort_keys: bool = False,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=sort_keys) + "\n")
            count += 1
    return count


def load_json_dict(path: Path, *, missing_is_loss: bool = False) -> JsonReadResult:
    loss = empty_json_loss()
    if not path.exists():
        if missing_is_loss:
            loss["missing_file_count"] = 1
        return JsonReadResult(data={}, loss=_finish_json_loss(loss))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if path.exists():
            loss["invalid_json_count"] = 1
        else:
            loss["unreadable_file_count"] = 1
        return JsonReadResult(data={}, loss=_finish_json_loss(loss))
    if not isinstance(raw, dict):
        loss["non_object_json_count"] = 1
        return JsonReadResult(data={}, loss=_finish_json_loss(loss))
    return JsonReadResult(data=raw, loss=_finish_json_loss(loss))


def write_json_atomic(
    path: Path,
    payload: Mapping[str, Any],
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> None:
    atomic_write_json(path, payload, indent=indent, sort_keys=sort_keys)


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
        "invalid_json_line_numbers": list(loss.get("invalid_json_line_numbers") or []),
        "non_object_line_numbers": list(loss.get("non_object_line_numbers") or []),
        "warning_codes": list(loss.get("warning_codes") or []),
        "message": "JSONL reader skipped malformed or unreadable rows; treat misses as degraded.",
    }


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    line = (
        ref.get("source_id")
        or ref.get("source_line")
        or ref.get("assistant_line")
        or ref.get("user_line")
        or ref.get("line")
        or ""
    )
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ref.get("turn_index") or ""),
        str(line),
    )


def source_ref_key_set(refs: Iterable[Mapping[str, Any]]) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for ref in refs:
        key = source_ref_key(ref)
        if any(key):
            keys.add(key)
    return keys


def source_ref_identity_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    """Return a full source-ref identity key for cache ids and local dedupe.

    `source_ref_key()` is the reopen/join key used by existing source indexes:
    when `source_id` is present it intentionally occupies the line slot. Some
    local caches and audit paths need a stable identity that preserves both
    `source_id` and the original line anchor. Bare historical `source_ref`
    strings are also identity-bearing even when they are not reopenable by the
    legacy join key. Keep that variant here instead of letting cache modules
    grow their own subtly different source-ref keys again.
    """

    thread_key, message_id, turn_id, line = source_ref_key(ref)
    source_id = str(ref.get("source_id") or ref.get("stable_source_id") or ref.get("source_ref") or "")
    if source_id and line == source_id:
        line = str(
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
            or ""
        )
    return (source_id, thread_key, message_id, turn_id, line)


def clean_source_ref(ref: Any, *, require_anchor: bool = True) -> dict[str, Any] | None:
    if not isinstance(ref, Mapping):
        return None
    thread_key, message_id, turn_id, line = source_ref_key(ref)
    if not thread_key:
        return None
    if require_anchor and not (message_id or turn_id or line):
        return None
    clean = {
        "thread_key": thread_key,
        "title": ref.get("title"),
        "project_label": ref.get("project_label"),
        "turn_id": ref.get("turn_id"),
        "turn_index": ref.get("turn_index"),
        "message_id": ref.get("message_id"),
        "source_id": ref.get("source_id"),
        "source_line": ref.get("source_line"),
        "assistant_line": ref.get("assistant_line"),
        "user_line": ref.get("user_line"),
        "line": ref.get("line"),
        "timestamp": ref.get("timestamp"),
        "source": ref.get("source"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def source_message_keys(thread_key: str, message: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    message_id = str(message.get("message_id") or message.get("id") or "")
    turn_id = str(message.get("turn_id") or "")
    turn_index = str(message.get("turn_index") or "")
    line = str(message.get("source_line") or message.get("line") or "")
    keys = [
        (thread_key, message_id, turn_id, line),
        (thread_key, message_id, "", line),
        (thread_key, message_id, turn_id, ""),
        (thread_key, message_id, "", ""),
        (thread_key, "", turn_id, line),
        (thread_key, "", turn_id, ""),
        (thread_key, "", turn_index, line),
        (thread_key, "", turn_index, ""),
        (thread_key, "", "", line),
    ]
    return [key for key in keys if any(key[1:])]


def merge_source_refs(
    existing: Iterable[Any],
    incoming: Iterable[Any],
    *,
    limit: int = 8,
    require_anchor: bool = False,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in [*list(existing or []), *list(incoming or [])]:
        ref = clean_source_ref(raw, require_anchor=require_anchor)
        if not ref:
            continue
        key = source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def parse_utc(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
