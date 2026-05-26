#!/usr/bin/env python3
"""Shared helpers for Codex Desktop thread-memory indexing scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


def norm_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def iter_rollouts(home: Path) -> Iterable[Path]:
    sessions = home / "sessions"
    if sessions.exists():
        yield from sessions.rglob("rollout-*.jsonl")


def read_session_meta(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        item = json.loads(first)
    except Exception:
        return None
    if item.get("type") == "session_meta":
        return item.get("payload", {})
    return None


def public_session_meta(meta: dict | None) -> dict:
    if not meta:
        return {}
    keys = [
        "id",
        "timestamp",
        "cwd",
        "originator",
        "cli_version",
        "source",
        "thread_source",
        "model_provider",
    ]
    return {key: meta[key] for key in keys if key in meta}


def locate_rollout(cwd: str | Path, home: Path | None = None, latest: bool = False) -> Path:
    home = home or codex_home()
    target = norm_path(cwd)
    matches: list[tuple[float, Path]] = []
    latest_seen: tuple[float, Path] | None = None

    for path in iter_rollouts(home):
        try:
            stat = path.stat()
        except OSError:
            continue
        if latest_seen is None or stat.st_mtime > latest_seen[0]:
            latest_seen = (stat.st_mtime, path)
        meta = read_session_meta(path)
        if meta and meta.get("cwd") and norm_path(meta["cwd"]) == target:
            matches.append((stat.st_mtime, path))

    if matches:
        matches.sort(reverse=True, key=lambda x: x[0])
        return matches[0][1]
    if latest and latest_seen:
        return latest_seen[1]
    raise FileNotFoundError(f"no rollout found for cwd: {cwd}")


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError:
                continue


def message_phase(payload: dict) -> str:
    phase = payload.get("phase")
    return str(phase or "")


def extract_message(item: dict, include_tools: bool = False) -> dict | None:
    payload = item.get("payload") or {}
    typ = item.get("type")

    if typ == "event_msg":
        ptype = payload.get("type")
        if ptype == "user_message":
            return {"role": "user", "kind": "user_message", "phase": message_phase(payload), "text": payload.get("message") or ""}
        if ptype == "agent_message":
            return {"role": "assistant", "kind": "agent_message", "phase": message_phase(payload), "text": payload.get("message") or ""}
        if include_tools:
            return {"role": "event", "kind": ptype or "event_msg", "phase": message_phase(payload), "text": json.dumps(payload, ensure_ascii=False)}

    if typ == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = payload.get("role") or "message"
            if role not in {"user", "assistant"}:
                return None
            texts = []
            for part in payload.get("content") or []:
                if isinstance(part, dict):
                    texts.append(part.get("text") or "")
                    texts.append(part.get("input_text") or "")
                    texts.append(part.get("output_text") or "")
            text = "\n".join(t for t in texts if t)
            return {"role": role, "kind": "message", "phase": message_phase(payload), "text": text}
        if include_tools and ptype in {"function_call", "function_call_output", "web_search_call"}:
            return {"role": "tool", "kind": ptype, "phase": "tool", "text": json.dumps(payload, ensure_ascii=False)}

    return None


def tool_payload_kind(item: dict) -> str | None:
    if item.get("type") != "response_item":
        return None
    payload = item.get("payload") or {}
    ptype = payload.get("type")
    if ptype in {"function_call", "function_call_output", "web_search_call"}:
        return str(ptype)
    return None


def empty_turn(turn_index: int, line_no: int, timestamp: str | None) -> dict:
    return {
        "id": turn_index,
        "user_line": line_no,
        "user_timestamp": timestamp,
        "final_line": None,
        "final_timestamp": None,
        "fallback_assistant_line": None,
        "fallback_assistant_timestamp": None,
        "commentary_count": 0,
        "tool_call_count": 0,
        "tool_output_count": 0,
        "start_line": line_no,
        "end_line": line_no,
    }


def normalize_rollout(rollout: Path, include_tools: bool = False) -> tuple[list[dict], list[dict]]:
    """Return deduped visible messages plus turn summaries.

    Codex Desktop writes a user request as a stream of raw events: commentary,
    tool calls/outputs, and finally a final_answer. Long-term recall should
    prefer the user request plus final_answer, while audit/provenance tools can
    still inspect raw tool lines. For that reason this normalizer records tool
    counts and raw line spans in turns, but it does not put tool payload text in
    the default message index unless include_tools is explicitly requested.
    """

    seen: set[str] = set()
    messages: list[dict] = []
    turns: dict[int, dict] = {}
    current_turn = 0

    for line_no, item in iter_jsonl(rollout):
        timestamp = item.get("timestamp")
        tool_kind = tool_payload_kind(item)
        if current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no
            if tool_kind == "function_call":
                turns[current_turn]["tool_call_count"] += 1
            elif tool_kind in {"function_call_output", "web_search_call"}:
                turns[current_turn]["tool_output_count"] += 1

        msg = extract_message(item, include_tools=include_tools)
        if not msg or not msg.get("text"):
            continue
        text = msg["text"].lstrip()
        if msg["role"] == "user" and text.startswith("# AGENTS.md instructions"):
            continue

        phase = str(msg.get("phase") or "")
        digest = hashlib.sha1((msg["role"] + "\0" + phase + "\0" + msg["text"]).encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)

        if msg["role"] == "user":
            current_turn += 1
            turns[current_turn] = empty_turn(current_turn, line_no, timestamp)
        elif current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no

        turn_index = current_turn if current_turn else None
        is_final = msg["role"] == "assistant" and phase == "final_answer"

        if turn_index and turn_index in turns and msg["role"] == "assistant":
            turns[turn_index]["fallback_assistant_line"] = line_no
            turns[turn_index]["fallback_assistant_timestamp"] = timestamp
            if phase == "commentary":
                turns[turn_index]["commentary_count"] += 1
            if is_final:
                turns[turn_index]["final_line"] = line_no
                turns[turn_index]["final_timestamp"] = timestamp

        messages.append({
            "line": line_no,
            "timestamp": timestamp,
            "role": msg["role"],
            "kind": msg["kind"],
            "phase": phase,
            "turn_index": turn_index,
            "is_final": is_final,
            "sha1": digest,
            "text": msg["text"],
        })

    return messages, list(turns.values())


def iter_messages(rollout: Path, include_tools: bool = False) -> Iterable[dict]:
    messages, _ = normalize_rollout(rollout, include_tools=include_tools)
    yield from messages


def compact_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + " ... " + text[-half:].lstrip()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_anchor_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    anchors: list[dict] = []
    current: dict | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if current:
                anchors.append(current)
            current = {"title": line[3:].strip(), "keywords": [], "notes": [], "quotes": [], "sources": []}
            continue
        if not current or not line.startswith("- "):
            continue
        body = line[2:]
        key, sep, value = body.partition(":")
        value = value.strip() if sep else body.strip()
        low = key.strip().casefold()
        if low == "keywords":
            current["keywords"].extend([x.strip() for x in re.split(r"[,，]", value) if x.strip()])
        elif low == "note":
            current["notes"].append(value)
        elif low == "preserved phrase":
            current["quotes"].append(value)
        elif low == "source":
            current["sources"].append(value)
        else:
            current.setdefault("fields", {})[key.strip()] = value

    if current:
        anchors.append(current)
    return anchors


def build_anchor_graph(anchors: list[dict], session_id: str | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    thread_id = f"thread:{session_id or 'unknown'}"
    nodes[thread_id] = {"id": thread_id, "type": "thread", "label": session_id or "unknown thread"}

    def add_node(node_id: str, node_type: str, label: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label})

    def add_edge(src: str, dst: str, rel: str) -> None:
        edges.append({"source": src, "target": dst, "type": rel})

    for idx, anchor in enumerate(anchors, start=1):
        title = anchor.get("title") or f"Anchor {idx}"
        topic_id = f"topic:{hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]}"
        add_node(topic_id, "topic", title)
        add_edge(thread_id, topic_id, "HAS_TOPIC")
        for keyword in anchor.get("keywords", []):
            key_id = f"keyword:{hashlib.sha1(keyword.casefold().encode('utf-8')).hexdigest()[:12]}"
            add_node(key_id, "keyword", keyword)
            add_edge(topic_id, key_id, "HAS_KEYWORD")
        for source in anchor.get("sources", []):
            src_id = f"source:{hashlib.sha1(source.encode('utf-8')).hexdigest()[:12]}"
            add_node(src_id, "source", source)
            add_edge(topic_id, src_id, "CITES")
        for quote in anchor.get("quotes", []):
            quote_id = f"quote:{hashlib.sha1(quote.encode('utf-8')).hexdigest()[:12]}"
            add_node(quote_id, "quote", compact_text(quote, 120))
            add_edge(topic_id, quote_id, "PRESERVES")

    return {"nodes": list(nodes.values()), "edges": edges}
