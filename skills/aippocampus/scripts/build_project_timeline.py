#!/usr/bin/env python3
"""Build a project-level recent-turn timeline from registered clean source."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, now_utc
from build_associations import extract_terms_from_text, source_text_is_noise
from build_clean_source import SCOPE_LABEL_ORDER
from registry import load_registry, registry_paths, unique_preserve
from semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

TIMELINE_SCHEMA_VERSION = 1
DEFAULT_MAX_PER_PROJECT = 80
DEFAULT_MAX_PER_LIFE_LABEL = 80
DEFAULT_MAX_TURNS_PER_THREAD = 3
LIFE_RECURRING_MARKERS = (
    "焦虑",
    "困惑",
    "问题",
    "点子",
    "想法",
    "灵感",
    "喜欢",
    "不喜欢",
    "读到",
    "文章",
    "生活",
    "偏好",
    "anxiety",
    "question",
    "idea",
    "spark",
    "preference",
)
TOPIC_MARKERS = [
    "T-Sense",
    "Go runtime",
    "Go sidecar",
    "本地核心运行时",
    "本地核心",
    "本地底座",
    "底座",
    "runtime abstraction",
    "Telegram",
    "Telethon",
    "gotd",
    "gogram",
    "Jackie",
    "AIppocampus",
    "clean-source",
    "重写",
    "搜索",
    "归档",
    "记忆",
    "线程",
    "市场",
]


def default_timeline_path(registry_path: Path) -> Path:
    return registry_path.resolve().parent / "project_timeline.json"


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def resolve_registry_member_path(
    value: str | None, registry_path: Path | None = None
) -> Path | None:
    if not value:
        return None
    path = Path(str(value).replace("\\", "/"))
    if path.is_absolute() or registry_path is None:
        return path
    if path.drive or ".." in path.parts:
        return None

    # Public bundles keep registry/threads.json beside clean-source/ and index/
    # at the bundle root. Machine registries usually store absolute paths, but
    # portable examples and exports need relative paths to remain useful after
    # moving between machines.
    registry_root = registry_path.resolve().parent
    bundle_root = registry_root.parent
    candidates = [(registry_root, registry_root / path)]
    if bundle_root != registry_root:
        candidates.append((bundle_root, bundle_root / path))
    for root, candidate in candidates:
        resolved = candidate.resolve()
        resolved_root = root.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            continue
        if resolved.exists():
            return resolved
    return candidates[0][1]


def sortable_turn_value(turn: dict[str, Any]) -> tuple[int, int]:
    turn_index = turn.get("turn_index")
    line = (
        turn.get("assistant_line")
        or turn.get("user_line")
        or turn.get("raw_end_line")
        or turn.get("end_line")
        or 0
    )
    try:
        turn_int = int(str(turn_index)) if turn_index is not None else 0
    except ValueError:
        turn_int = 0
    try:
        line_int = int(line)
    except (TypeError, ValueError):
        line_int = 0
    return turn_int, line_int


def messages_for_turn(
    turn: dict[str, Any],
    messages_by_id: dict[str, dict[str, Any]],
    by_turn_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message_id in turn.get("message_ids") or []:
        match = messages_by_id.get(str(message_id))
        if match:
            out.append(match)
    if out:
        return out
    return list(by_turn_id.get(str(turn.get("turn_id") or ""), []))


def topic_terms_for_text(text: str) -> list[str]:
    marker_hits = [marker for marker in TOPIC_MARKERS if marker.casefold() in text.casefold()]
    life_hits = [
        marker for marker in LIFE_RECURRING_MARKERS if marker.casefold() in text.casefold()
    ]
    latin_phrases = [
        phrase.strip()
        for phrase in re.findall(
            r"[A-Za-z][A-Za-z0-9_.+-]*(?:\s+[A-Za-z][A-Za-z0-9_.+-]*){0,3}", text
        )
        if len(phrase.strip()) >= 3
    ]
    mined = extract_terms_from_text(text)
    return unique_preserve(marker_hits + life_hits + latin_phrases + mined, limit=12)


def canonical_scope_labels(values: list[Any]) -> list[str]:
    present = {str(value) for value in values if isinstance(value, str)}
    return [label for label in SCOPE_LABEL_ORDER if label in present]


def scope_labels_for_turn(turn: dict[str, Any], turn_messages: list[dict[str, Any]]) -> list[str]:
    labels: list[Any] = []
    labels.extend(turn.get("scope_labels") or [])
    for message in turn_messages:
        labels.extend(message.get("scope_labels") or [])
    return canonical_scope_labels(labels)


def semantic_scope_labels_for_turn(turn_messages: list[dict[str, Any]]) -> list[str]:
    labels: list[Any] = []
    for message in turn_messages:
        labels.extend(message.get("semantic_scope_labels") or [])
    return canonical_scope_labels(labels)


def source_refs_for_messages(
    turn_messages: list[dict[str, Any]], *, thread_key: str | None = None
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for message in turn_messages:
        refs.append(
            {
                "thread_key": thread_key,
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "source_id": message.get("source_id"),
                "clean_ordinal": message.get("clean_ordinal"),
                "source_line": message.get("source_line"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
            }
        )
    return refs


def timeline_project_key(entry: dict[str, Any]) -> str:
    return str(
        entry.get("project_key")
        or f"project:{entry.get('project_label') or entry.get('workspace_name') or 'unknown'}"
    )


def latest_turns_for_entry(
    entry: dict[str, Any],
    *,
    registry_path: Path | None = None,
    max_turns: int = DEFAULT_MAX_TURNS_PER_THREAD,
) -> list[dict[str, Any]]:
    paths = entry.get("paths") or {}
    messages_path_value = paths.get("clean_source_messages_jsonl")
    if not messages_path_value:
        return []
    messages_path = resolve_registry_member_path(str(messages_path_value), registry_path)
    if messages_path is None:
        return []
    semantic_sidecar = load_semantic_scope_labels(messages_path.parent)
    messages = []
    for item in iter_jsonl(messages_path):
        semantic_labels = semantic_labels_for_message(item, semantic_sidecar)
        if semantic_labels:
            item = dict(item)
            item["semantic_scope_labels"] = semantic_labels
            item["scope_labels"] = merged_scope_labels(
                list(item.get("scope_labels") or []), semantic_labels
            )
        messages.append(item)
    if not messages:
        return []
    turns_path_value = paths.get("clean_source_turns_jsonl")
    turns_path = (
        resolve_registry_member_path(str(turns_path_value), registry_path)
        if turns_path_value
        else None
    )
    turns = iter_jsonl(turns_path) if turns_path else []
    if not turns:
        seen_turn_ids = unique_preserve(
            [str(item.get("turn_id") or "") for item in messages if item.get("turn_id")]
        )
        turns = [{"turn_id": turn_id} for turn_id in seen_turn_ids]

    messages_by_id = {
        str(item.get("message_id") or item.get("id")): item
        for item in messages
        if item.get("message_id") or item.get("id")
    }
    by_turn_id: dict[str, list[dict[str, Any]]] = {}
    for item in messages:
        by_turn_id.setdefault(str(item.get("turn_id") or ""), []).append(item)

    rows: list[dict[str, Any]] = []
    for turn in sorted(turns, key=sortable_turn_value, reverse=True):
        turn_messages = messages_for_turn(turn, messages_by_id, by_turn_id)
        if not turn_messages:
            continue
        user = next((item for item in turn_messages if item.get("role") == "user"), None)
        assistant = next(
            (
                item
                for item in turn_messages
                if item.get("role") == "assistant" and item.get("is_final")
            ),
            None,
        )
        if assistant is None:
            assistant = next(
                (item for item in turn_messages if item.get("role") == "assistant"), None
            )

        user_text = str((user or {}).get("text") or "")
        assistant_text = str((assistant or {}).get("text") or "")
        if not user_text.strip() and not assistant_text.strip():
            continue
        if user_text and source_text_is_noise(user_text) and not assistant_text:
            continue

        timestamp = (
            (assistant or {}).get("timestamp")
            or (user or {}).get("timestamp")
            or (entry.get("session_meta") or {}).get("timestamp")
            or entry.get("created_at")
            or entry.get("updated_at")
        )
        topic_terms = topic_terms_for_text(user_text + " " + assistant_text)
        scope_labels = scope_labels_for_turn(turn, turn_messages)
        semantic_scope_labels = semantic_scope_labels_for_turn(turn_messages)
        rows.append(
            {
                "thread_key": entry.get("thread_key"),
                "title": entry.get("title")
                or entry.get("workspace_name")
                or entry.get("thread_key"),
                "project_key": timeline_project_key(entry),
                "project_label": entry.get("project_label") or entry.get("workspace_name"),
                "timestamp": timestamp,
                "turn_id": turn.get("turn_id") or (user or assistant or {}).get("turn_id"),
                "turn_index": turn.get("turn_index")
                if turn.get("turn_index") is not None
                else (user or assistant or {}).get("turn_index"),
                "user_line": (user or {}).get("source_line") or turn.get("user_line"),
                "assistant_line": (assistant or {}).get("source_line")
                or turn.get("assistant_line"),
                "assistant_phase": (assistant or {}).get("phase")
                or turn.get("assistant_phase")
                or "",
                "user": compact_text(user_text, 320),
                "assistant": compact_text(assistant_text, 420),
                "scope_labels": scope_labels,
                "semantic_scope_labels": semantic_scope_labels,
                "topic_terms": topic_terms[:12],
                "source_refs": source_refs_for_messages(
                    turn_messages, thread_key=str(entry.get("thread_key") or "")
                ),
            }
        )
        if len(rows) >= max_turns:
            break
    return rows


def build_life_wide_timeline(
    rows: list[dict[str, Any]], *, max_per_label: int = DEFAULT_MAX_PER_LIFE_LABEL
) -> dict[str, Any]:
    label_groups: dict[str, list[dict[str, Any]]] = {label: [] for label in SCOPE_LABEL_ORDER}
    for row in rows:
        for label in row.get("scope_labels") or []:
            if label in label_groups:
                label_groups[label].append(row)

    labels: dict[str, dict[str, Any]] = {}
    for label in SCOPE_LABEL_ORDER:
        group_rows = label_groups[label]
        if not group_rows:
            continue
        group_rows.sort(
            key=lambda item: (
                str(item.get("timestamp") or ""),
                int(item.get("turn_index") or 0),
                int(item.get("assistant_line") or item.get("user_line") or 0),
            ),
            reverse=True,
        )
        term_counter: Counter[str] = Counter()
        for row in group_rows:
            for term in row.get("topic_terms") or []:
                term_counter[str(term)] += 1
        recurring_terms = [
            {"term": term, "count": count}
            for term, count in sorted(
                term_counter.items(), key=lambda item: (-item[1], item[0].casefold())
            )
            if count >= 2
        ][:12]
        labels[label] = {
            "scope_label": label,
            "turn_count": len(group_rows),
            "thread_count": len(
                {row.get("thread_key") for row in group_rows if row.get("thread_key")}
            ),
            "project_count": len(
                {
                    row.get("project_key") or row.get("project_label")
                    for row in group_rows
                    if row.get("project_key") or row.get("project_label")
                }
            ),
            "recurring_terms": recurring_terms,
            "latest_turns": group_rows[: max(1, int(max_per_label))],
        }

    return {
        "schema_version": 1,
        "kind": "aippocampus_life_wide_timeline",
        "source": "clean_source_scope_labels",
        "boundary": "Navigation sidecar only; exact claims still require clean-source source_refs.",
        "label_count": len(labels),
        "labels": labels,
    }


def build_project_timeline(
    registry_path: Path,
    *,
    max_per_project: int = DEFAULT_MAX_PER_PROJECT,
    max_per_life_label: int = DEFAULT_MAX_PER_LIFE_LABEL,
    max_turns_per_thread: int = DEFAULT_MAX_TURNS_PER_THREAD,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    projects: dict[str, dict[str, Any]] = {}
    life_rows: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        project_key = timeline_project_key(entry)
        project = projects.setdefault(
            str(project_key),
            {
                "project_key": project_key,
                "project_label": entry.get("project_label")
                or entry.get("workspace_name")
                or "unknown",
                "project_tags": unique_preserve(
                    [
                        entry.get("project_label") or "",
                        entry.get("workspace_name") or "",
                        *list(entry.get("project_tags") or []),
                    ],
                    limit=32,
                ),
                "thread_count": 0,
                "latest_turns": [],
            },
        )
        project["thread_count"] += 1
        entry_turns = latest_turns_for_entry(
            entry, registry_path=registry_path, max_turns=max_turns_per_thread
        )
        project["latest_turns"].extend(entry_turns)
        life_rows.extend([turn for turn in entry_turns if turn.get("scope_labels")])

    for project in projects.values():
        project["latest_turns"].sort(
            key=lambda item: (
                str(item.get("timestamp") or ""),
                int(item.get("turn_index") or 0),
                int(item.get("assistant_line") or item.get("user_line") or 0),
            ),
            reverse=True,
        )
        project["latest_turns"] = project["latest_turns"][: max(1, int(max_per_project))]

    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "kind": "aippocampus_project_timeline",
        "updated_at": now_utc(),
        "source_registry": str(registry_path),
        "project_count": len(projects),
        "projects": dict(
            sorted(
                projects.items(),
                key=lambda item: str(item[1].get("project_label") or item[0]).casefold(),
            )
        ),
        "life_wide": build_life_wide_timeline(life_rows, max_per_label=max_per_life_label),
    }


def save_project_timeline(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--output")
    parser.add_argument("--max-per-project", type=int, default=DEFAULT_MAX_PER_PROJECT)
    parser.add_argument("--max-per-life-label", type=int, default=DEFAULT_MAX_PER_LIFE_LABEL)
    parser.add_argument("--max-turns-per-thread", type=int, default=DEFAULT_MAX_TURNS_PER_THREAD)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    output_path = (
        Path(args.output).resolve() if args.output else default_timeline_path(registry_path)
    )
    result = build_project_timeline(
        registry_path,
        max_per_project=args.max_per_project,
        max_per_life_label=args.max_per_life_label,
        max_turns_per_thread=args.max_turns_per_thread,
    )
    save_project_timeline(output_path, result)
    payload = {"output": str(output_path), **result}
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"project timeline: {output_path}")
        print(f"projects: {result['project_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
