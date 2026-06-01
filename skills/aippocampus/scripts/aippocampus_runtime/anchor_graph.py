"""Thread-anchor parsing and graph construction helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.text import compact_text


def parse_anchor_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    anchors: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if current:
                anchors.append(current)
            current = {
                "title": line[3:].strip(),
                "keywords": [],
                "notes": [],
                "quotes": [],
                "sources": [],
            }
            continue
        if not current or not line.startswith("- "):
            continue
        body = line[2:]
        key, sep, value = body.partition(":")
        value = value.strip() if sep else body.strip()
        low = key.strip().casefold()
        if low == "keywords":
            current["keywords"].extend(
                [x.strip() for x in re.split(r"[,，]", value) if x.strip()]
            )
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


def build_anchor_graph(anchors: list[dict[str, Any]], session_id: str | None = None) -> dict:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    thread_id = f"thread:{session_id or 'unknown'}"
    nodes[thread_id] = {
        "id": thread_id,
        "type": "thread",
        "label": session_id or "unknown thread",
    }

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
            key_id = (
                f"keyword:{hashlib.sha1(keyword.casefold().encode('utf-8')).hexdigest()[:12]}"
            )
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
