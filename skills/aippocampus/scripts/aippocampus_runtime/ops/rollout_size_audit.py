#!/usr/bin/env python3
"""Audit where Codex Desktop rollout bytes are coming from.

This is intentionally a byte-level diagnostic, not a memory index builder.
Long threads can look "mysteriously" huge because the raw rollout stores more
than user-visible prose: event envelopes, tool calls, tool outputs, images or
large JSON payloads, and sometimes injected workspace instructions. The report
keeps those buckets separate so future agents do not guess from vibes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    codex_home,
    compact_text,
    locate_rollout,
)
from aippocampus_runtime.source.rollout import extract_message, iter_messages

AGENTS_PREFIX = "# AGENTS.md instructions"


def payload_subtype(item: dict[str, Any]) -> tuple[str, str, str]:
    """Return stable classification fields for a raw rollout item."""
    item_type = str(item.get("type") or "unknown")
    payload = item.get("payload") or {}
    payload_type = str(payload.get("type") or "")
    role = str(payload.get("role") or "")

    if item_type == "response_item" and payload_type == "message":
        content = payload.get("content") or []
        if content and isinstance(content[0], dict):
            part_types = sorted(
                {str(part.get("type") or "") for part in content if isinstance(part, dict)}
            )
            if part_types:
                payload_type += ":" + ",".join(part_types)
    return item_type, payload_type, role


def extract_visible_text(item: dict[str, Any], *, include_tools: bool = True) -> str:
    msg = extract_message(item, include_tools=include_tools)
    if msg:
        return msg.get("text") or ""
    payload = item.get("payload") or {}
    if isinstance(payload, dict):
        for key in ("message", "text", "output", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return ""


def line_class(item: dict[str, Any]) -> str:
    item_type, payload_type, role = payload_subtype(item)
    text = extract_visible_text(item, include_tools=True).lstrip()

    if text.startswith(AGENTS_PREFIX):
        return "injected_agents_md"
    if item_type == "session_meta":
        return "session_meta"
    if item_type == "event_msg":
        if payload_type in {"user_message", "agent_message"}:
            return f"visible_{payload_type}"
        return f"event_{payload_type or 'unknown'}"
    if item_type == "response_item":
        if payload_type.startswith("message"):
            return f"response_message_{role or 'unknown'}"
        if payload_type in {"function_call", "function_call_output", "web_search_call"}:
            return f"tool_{payload_type}"
        return f"response_{payload_type or 'unknown'}"
    return item_type


def image_payload_bytes(item: dict[str, Any]) -> tuple[int, int]:
    """Return (image_count, encoded_image_url_bytes) for common rollout shapes."""
    payload = item.get("payload") or {}
    count = 0
    byte_count = 0

    for value in payload.get("images") or []:
        if isinstance(value, str):
            count += 1
            byte_count += len(value.encode("utf-8"))

    if payload.get("type") == "message":
        for part in payload.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "input_image":
                continue
            value = part.get("image_url")
            if isinstance(value, str):
                count += 1
                byte_count += len(value.encode("utf-8"))
    return count, byte_count


def pct(part: int, total: int) -> float:
    return round((part * 100.0 / total), 2) if total else 0.0


def audit_rollout(rollout: Path, *, top: int = 15) -> dict[str, Any]:
    total_size = rollout.stat().st_size
    by_type: Counter[str] = Counter()
    by_subtype: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    counts_by_class: Counter[str] = Counter()
    large_lines: list[dict[str, Any]] = []
    injected_agents = {"count": 0, "bytes": 0}
    embedded_images = {"count": 0, "url_bytes": 0, "carrier_line_bytes": 0}
    compaction = {"count": 0, "bytes": 0, "replacement_history_items": 0, "max_line_bytes": 0}

    message_hashes: Counter[str] = Counter()
    duplicate_visible_bytes = 0
    visible_message_bytes = 0

    with rollout.open("rb") as f:
        for line_no, raw in enumerate(f, start=1):
            line_bytes = len(raw)
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                by_class["invalid_json"] += line_bytes
                counts_by_class["invalid_json"] += 1
                continue

            item_type, payload_type, role = payload_subtype(item)
            subtype_key = "/".join(x for x in (item_type, payload_type, role) if x)
            cls = line_class(item)
            text = extract_visible_text(item, include_tools=True)

            by_type[item_type] += line_bytes
            by_subtype[subtype_key or item_type] += line_bytes
            by_class[cls] += line_bytes
            counts_by_class[cls] += 1

            image_count, image_bytes = image_payload_bytes(item)
            if image_count:
                embedded_images["count"] += image_count
                embedded_images["url_bytes"] += image_bytes
                embedded_images["carrier_line_bytes"] += line_bytes

            if item.get("type") == "compacted":
                payload = item.get("payload") or {}
                history = payload.get("replacement_history") if isinstance(payload, dict) else None
                compaction["count"] += 1
                compaction["bytes"] += line_bytes
                compaction["max_line_bytes"] = max(compaction["max_line_bytes"], line_bytes)
                if isinstance(history, list):
                    compaction["replacement_history_items"] += len(history)

            if text.lstrip().startswith(AGENTS_PREFIX):
                injected_agents["count"] += 1
                injected_agents["bytes"] += line_bytes

            msg = extract_message(item, include_tools=False)
            if msg and msg.get("text"):
                digest = hashlib.sha1(
                    (msg["role"] + "\0" + msg["text"]).encode("utf-8")
                ).hexdigest()
                text_bytes = len(msg["text"].encode("utf-8"))
                visible_message_bytes += text_bytes
                if message_hashes[digest]:
                    duplicate_visible_bytes += text_bytes
                message_hashes[digest] += 1

            large_lines.append(
                {
                    "line": line_no,
                    "bytes": line_bytes,
                    "class": cls,
                    "type": item_type,
                    "payload_type": payload_type,
                    "role": role,
                    "timestamp": item.get("timestamp"),
                    "excerpt": compact_text(text, 180) if text else "",
                }
            )

    large_lines.sort(key=lambda row: row["bytes"], reverse=True)
    indexed_messages = list(iter_messages(rollout))
    indexed_text_bytes = sum(len(m["text"].encode("utf-8")) for m in indexed_messages)

    def counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
        return [
            {"key": key, "bytes": value, "percent": pct(value, total_size)}
            for key, value in counter.most_common()
        ]

    return {
        "rollout": str(rollout),
        "size_bytes": total_size,
        "line_count": sum(counts_by_class.values()),
        "visible_indexed_messages": len(indexed_messages),
        "visible_indexed_text_bytes": indexed_text_bytes,
        "visible_indexed_text_percent": pct(indexed_text_bytes, total_size),
        "visible_message_text_bytes_before_dedup": visible_message_bytes,
        "duplicate_visible_message_text_bytes": duplicate_visible_bytes,
        "duplicate_visible_message_text_percent": pct(duplicate_visible_bytes, total_size),
        "injected_agents_md": injected_agents,
        "embedded_images": {
            **embedded_images,
            "url_percent": pct(embedded_images["url_bytes"], total_size),
            "carrier_line_percent": pct(embedded_images["carrier_line_bytes"], total_size),
        },
        "compaction": {
            **compaction,
            "percent": pct(compaction["bytes"], total_size),
            "avg_replacement_history_items": round(
                compaction["replacement_history_items"] / compaction["count"], 2
            )
            if compaction["count"]
            else 0,
        },
        "by_type": counter_rows(by_type),
        "by_subtype": counter_rows(by_subtype),
        "by_class": [
            {
                "key": key,
                "count": counts_by_class[key],
                "bytes": value,
                "percent": pct(value, total_size),
            }
            for key, value in by_class.most_common()
        ],
        "largest_lines": large_lines[:top],
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"rollout: {report['rollout']}")
    print(f"size: {report['size_bytes']} bytes")
    print(f"raw lines: {report['line_count']}")
    print(
        "indexed visible text: "
        f"{report['visible_indexed_text_bytes']} bytes "
        f"({report['visible_indexed_text_percent']}%) across "
        f"{report['visible_indexed_messages']} deduped messages"
    )
    injected = report["injected_agents_md"]
    print(f"AGENTS injections: {injected['count']} lines, {injected['bytes']} bytes")
    compaction = report["compaction"]
    print(
        "compaction snapshots: "
        f"{compaction['count']} lines, {compaction['bytes']} bytes "
        f"({compaction['percent']}%), max line {compaction['max_line_bytes']} bytes, "
        f"avg replacement_history {compaction['avg_replacement_history_items']}"
    )
    images = report["embedded_images"]
    print(
        "embedded images: "
        f"{images['count']} image payloads, {images['url_bytes']} URL/data bytes "
        f"({images['url_percent']}%), carrier lines {images['carrier_line_bytes']} bytes "
        f"({images['carrier_line_percent']}%)"
    )
    print(
        "duplicate visible message text before index dedupe: "
        f"{report['duplicate_visible_message_text_bytes']} bytes "
        f"({report['duplicate_visible_message_text_percent']}%)"
    )

    print("\nby class:")
    for row in report["by_class"][:20]:
        print(f"- {row['key']}: {row['bytes']} bytes ({row['percent']}%), count={row['count']}")

    print("\nlargest lines:")
    for row in report["largest_lines"]:
        detail = "/".join(x for x in (row["type"], row["payload_type"], row["role"]) if x)
        print(f"- line {row['line']}: {row['bytes']} bytes [{row['class']}] {detail}")
        if row["excerpt"]:
            print(f"  {row['excerpt']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    report = audit_rollout(rollout, top=args.top)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
