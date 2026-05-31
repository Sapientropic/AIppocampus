#!/usr/bin/env python3
"""Source-ref resolution helpers for question tracking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.search import iter_clean_messages


@dataclass(frozen=True)
class SourceRefIndex:
    keys: frozenset[tuple[str, str, str, str]]
    thread_count: int
    message_count: int

    def resolves(self, ref: Mapping[str, Any]) -> bool:
        thread_key, message_id, turn_anchor, line = source_ref_key(ref)
        if not thread_key:
            return False
        if message_id:
            candidates = [
                (thread_key, message_id, turn_anchor, line),
                (thread_key, message_id, "", line),
                (thread_key, message_id, turn_anchor, ""),
                (thread_key, message_id, "", ""),
            ]
            return any(key in self.keys for key in candidates if any(key[1:]))
        if turn_anchor:
            candidates = [(thread_key, "", turn_anchor, line), (thread_key, "", turn_anchor, "")]
            return any(key in self.keys for key in candidates)
        if line:
            return (thread_key, "", "", line) in self.keys
        return False


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    line = (
        ref.get("source_line")
        or ref.get("assistant_line")
        or ref.get("user_line")
        or ref.get("line")
        or ""
    )
    return (
        str(ref.get("thread_key") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ref.get("turn_index") or ""),
        str(line),
    )


def message_source_keys(thread_key: str, message: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    message_id = str(message.get("message_id") or message.get("id") or "")
    turn_id = str(message.get("turn_id") or "")
    turn_index = str(message.get("turn_index") or "")
    line = str(message.get("source_line") or "")
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


def build_source_ref_index(registry_path: Path | None) -> SourceRefIndex | None:
    if registry_path is None or not registry_path.exists():
        return None
    registry = load_registry(registry_path)
    keys: set[tuple[str, str, str, str]] = set()
    thread_count = 0
    message_count = 0
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        thread_key = str(entry.get("thread_key") or "")
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        if not thread_key or not messages_path_value:
            continue
        messages_path = Path(messages_path_value)
        if not messages_path.exists():
            continue
        thread_count += 1
        for message in iter_clean_messages(messages_path):
            message_count += 1
            keys.update(message_source_keys(thread_key, message))
    if not keys:
        return None
    return SourceRefIndex(frozenset(keys), thread_count, message_count)


def clean_source_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    thread_key, message_id, turn_id, line = source_ref_key(ref)
    if not thread_key or not (message_id or turn_id or line):
        return None
    clean = {
        "thread_key": thread_key,
        "title": ref.get("title"),
        "project_label": ref.get("project_label"),
        "turn_id": ref.get("turn_id"),
        "turn_index": ref.get("turn_index"),
        "message_id": ref.get("message_id"),
        "source_line": ref.get("source_line"),
        "assistant_line": ref.get("assistant_line"),
        "user_line": ref.get("user_line"),
        "line": ref.get("line"),
        "timestamp": ref.get("timestamp"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def compact_source_refs(
    values: Any, *, limit: int = 12, source_index: SourceRefIndex | None = None
) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in values or []:
        clean = clean_source_ref(item)
        if not clean:
            continue
        if source_index is not None and not source_index.resolves(clean):
            continue
        key = source_ref_key(clean)
        if key in seen:
            continue
        seen.add(key)
        refs.append(clean)
    return tuple(refs[:limit])
