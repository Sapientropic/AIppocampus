from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_clean_thread(root: Path, thread_key: str, rows: list[dict[str, Any]]) -> Path:
    clean_dir = root / "clean" / thread_key.replace(":", "-")
    clean_dir.mkdir(parents=True)
    messages_path = clean_dir / "messages.jsonl"
    messages_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return messages_path


def write_registry(root: Path, entries: list[dict[str, Any]]) -> Path:
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_path


def write_thread_registry(
    root: Path,
    thread_key: str,
    rows: list[dict[str, Any]],
    *,
    title: str = "Old ambient thread",
) -> Path:
    messages_path = write_clean_thread(root, thread_key, rows)
    return write_registry(
        root,
        [
            {
                "thread_key": thread_key,
                "title": title,
                "paths": {"clean_source_messages_jsonl": str(messages_path)},
            }
        ],
    )
