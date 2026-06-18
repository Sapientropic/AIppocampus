"""Small process-local mtime cache for prompt hot-path file loaders."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

_CACHE: dict[tuple[str, int, int, str], Any] = {}
_READ_COUNTS: dict[str, int] = {}


def clear_mtime_cache() -> None:
    _CACHE.clear()
    _READ_COUNTS.clear()


def read_count(path: Path | str) -> int:
    return int(_READ_COUNTS.get(str(Path(path).resolve()), 0))


def _signature(path: Path, label: str) -> tuple[str, int, int, str] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size), label)


def load_cached(path: Path | str, *, label: str, parser: Callable[[str], Any]) -> Any | None:
    target = Path(path)
    key = _signature(target, label)
    if key is None:
        return None
    if key not in _CACHE:
        text = target.read_text(encoding="utf-8")
        _READ_COUNTS[str(target.resolve())] = read_count(target) + 1
        _CACHE[key] = parser(text)
    return copy.deepcopy(_CACHE[key])


def load_json_object(path: Path | str) -> dict[str, Any] | None:
    def parse(text: str) -> dict[str, Any] | None:
        data = json.loads(text)
        return data if isinstance(data, dict) else None

    return load_cached(path, label="json_object", parser=parse)


def load_jsonl_objects(path: Path | str, *, strict: bool = False) -> tuple[list[dict[str, Any]], int] | None:
    def parse(text: str) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        invalid = 0
        for line in text.splitlines():
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

    return load_cached(path, label=f"jsonl_objects:strict={strict}", parser=parse)
