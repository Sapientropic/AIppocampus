#!/usr/bin/env python3
"""Build portable JSONL, SQLite FTS, manifest, and graph files for a Codex rollout."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from aippocampuslib import (
    build_anchor_graph,
    codex_home,
    default_thread_index_dir,
    file_sha256,
    locate_rollout,
    normalize_rollout,
    now_utc,
    parse_anchor_file,
    public_session_meta,
    read_session_meta,
    resolve_artifact_path,
)
from artifact_publish import (
    DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
    artifact_lease,
    publish_sqlite_with_pointer,
    remove_sqlite_artifact,
    unique_temp_sqlite_path,
)
from retrieval import build_rag_chunks


def make_sqlite(
    index_path: Path,
    messages: list[dict],
    anchors: list[dict],
    turns: list[dict] | None = None,
    *,
    rag_cache: bool = True,
    rag_chunk_chars: int = 2800,
    publish_lock: bool = True,
    sqlite_busy_timeout_ms: int = DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
) -> dict:
    tmp_path = unique_temp_sqlite_path(index_path)
    remove_sqlite_artifact(tmp_path)
    con = sqlite3.connect(tmp_path)
    rag_status: dict[str, Any] = {
        "enabled": False,
        "chunk_count": 0,
        "chunk_chars": rag_chunk_chars,
        "fts_enabled": False,
        "fts_error": None,
    }
    try:
        con.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, line INTEGER, timestamp TEXT, role TEXT, "
            "kind TEXT, phase TEXT, turn_index INTEGER, is_final INTEGER, "
            "sha1 TEXT UNIQUE, text TEXT)"
        )
        con.executemany(
            "INSERT INTO messages "
            "(id, line, timestamp, role, kind, phase, turn_index, is_final, sha1, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    idx,
                    m["line"],
                    m.get("timestamp"),
                    m["role"],
                    m["kind"],
                    m.get("phase") or "",
                    m.get("turn_index"),
                    1 if m.get("is_final") else 0,
                    m["sha1"],
                    m["text"],
                )
                for idx, m in enumerate(messages, start=1)
            ],
        )
        con.execute(
            "CREATE TABLE turns ("
            "id INTEGER PRIMARY KEY, user_line INTEGER, user_timestamp TEXT, "
            "final_line INTEGER, final_timestamp TEXT, "
            "fallback_assistant_line INTEGER, fallback_assistant_timestamp TEXT, "
            "commentary_count INTEGER, tool_call_count INTEGER, tool_output_count INTEGER, "
            "start_line INTEGER, end_line INTEGER)"
        )
        con.executemany(
            "INSERT INTO turns "
            "(id, user_line, user_timestamp, final_line, final_timestamp, "
            "fallback_assistant_line, fallback_assistant_timestamp, commentary_count, "
            "tool_call_count, tool_output_count, start_line, end_line) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    turn["id"],
                    turn.get("user_line"),
                    turn.get("user_timestamp"),
                    turn.get("final_line"),
                    turn.get("final_timestamp"),
                    turn.get("fallback_assistant_line"),
                    turn.get("fallback_assistant_timestamp"),
                    int(turn.get("commentary_count") or 0),
                    int(turn.get("tool_call_count") or 0),
                    int(turn.get("tool_output_count") or 0),
                    turn.get("start_line"),
                    turn.get("end_line"),
                )
                for turn in (turns or [])
            ],
        )
        fts_enabled = False
        fts_error = None
        try:
            # Trigram FTS keeps Chinese phrases, mixed prose, and fuzzy remembered
            # snippets searchable without requiring embeddings.
            con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(text, tokenize='trigram')")
            con.executemany(
                "INSERT INTO messages_fts (rowid, text) VALUES (?, ?)",
                [(idx, m["text"]) for idx, m in enumerate(messages, start=1)],
            )
            fts_enabled = True
        except sqlite3.Error as exc:
            fts_error = str(exc)

        if rag_cache:
            chunks = build_rag_chunks(messages, anchors, max_chars=rag_chunk_chars)
            con.execute(
                "CREATE TABLE rag_chunks ("
                "id INTEGER PRIMARY KEY, start_message_id INTEGER, end_message_id INTEGER, "
                "start_line INTEGER, end_line INTEGER, roles TEXT, anchor_titles TEXT, "
                "summary TEXT, text TEXT, terms_json TEXT)"
            )
            con.executemany(
                "INSERT INTO rag_chunks "
                "(id, start_message_id, end_message_id, start_line, end_line, roles, anchor_titles, summary, text, terms_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk["id"],
                        chunk["start_message_id"],
                        chunk["end_message_id"],
                        chunk["start_line"],
                        chunk["end_line"],
                        chunk["roles"],
                        json.dumps(chunk["anchor_titles"], ensure_ascii=False),
                        chunk["summary"],
                        chunk["text"],
                        json.dumps(chunk["terms"], ensure_ascii=False),
                    )
                    for chunk in chunks
                ],
            )
            rag_status.update({"enabled": True, "chunk_count": len(chunks)})
            try:
                # Periodic RAG-lite cache: chunk-level FTS finds a relevant
                # neighborhood first, then search_rollout maps back to raw
                # message lines. This keeps recall cheap and portable.
                con.execute(
                    "CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(text, tokenize='trigram')"
                )
                con.executemany(
                    "INSERT INTO rag_chunks_fts (rowid, text) VALUES (?, ?)",
                    [(chunk["id"], chunk["text"]) for chunk in chunks],
                )
                rag_status["fts_enabled"] = True
            except sqlite3.Error as exc:
                rag_status["fts_error"] = str(exc)
        con.commit()
    finally:
        con.close()

    try:
        if publish_lock:
            with artifact_lease(index_path.parent, ".index-publish.lock"):
                publish_status = publish_sqlite_with_pointer(
                    tmp_path,
                    index_path,
                    busy_timeout_ms=sqlite_busy_timeout_ms,
                )
        else:
            publish_status = publish_sqlite_with_pointer(
                tmp_path,
                index_path,
                busy_timeout_ms=sqlite_busy_timeout_ms,
            )
    finally:
        remove_sqlite_artifact(tmp_path)
    return {
        "fts_enabled": fts_enabled,
        "fts_error": fts_error,
        "rag": rag_status,
        "publish": publish_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the CODEX_HOME global thread store; pass .aippocampus for project-local output.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--include-tools", action="store_true")
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument(
        "--no-rag-cache", action="store_true", help="Skip periodic local RAG-lite chunk cache."
    )
    parser.add_argument(
        "--rag-chunk-chars",
        type=int,
        default=2800,
        help="Approximate character budget per RAG-lite chunk.",
    )
    parser.add_argument(
        "--sqlite-busy-timeout-ms",
        type=int,
        default=DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
        help="SQLite busy timeout for publishing the stable compatibility index.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    output_dir = resolve_artifact_path(args.output_dir, cwd, default_thread_index_dir(cwd, rollout))
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_meta = read_session_meta(rollout) or {}
    meta = public_session_meta(raw_meta)
    messages, turns = normalize_rollout(rollout, include_tools=args.include_tools)

    with artifact_lease(output_dir, ".index-publish.lock"):
        messages_path = output_dir / "messages.jsonl"
        with messages_path.open("w", encoding="utf-8", newline="\n") as f:
            for m in messages:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

        sqlite_path = output_dir / "source_index.sqlite"
        anchor_path = Path(args.anchors)
        if not anchor_path.is_absolute():
            anchor_path = cwd / anchor_path
        anchors = parse_anchor_file(anchor_path)
        sqlite_status = make_sqlite(
            sqlite_path,
            messages,
            anchors,
            turns,
            rag_cache=not args.no_rag_cache,
            rag_chunk_chars=args.rag_chunk_chars,
            publish_lock=False,
            sqlite_busy_timeout_ms=args.sqlite_busy_timeout_ms,
        )
        sqlite_publish = sqlite_status.get("publish") or {}
        sqlite_current = sqlite_publish.get("current")
        sqlite_pointer = sqlite_publish.get("pointer")
        graph = build_anchor_graph(anchors, meta.get("id"))
        graph_path = output_dir / "graph.json"
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

        stat = rollout.stat()
        manifest = {
            "schema_version": 1,
            "created_at": now_utc(),
            "cwd": str(cwd),
            "artifact_scope": "global_thread_store"
            if args.output_dir is None
            else "explicit_output_dir",
            "storage_policy": {
                "default": "CODEX_HOME/aippocampus-registry/threads/<thread>/index",
                "legacy_project_local": ".aippocampus",
                "why": "Indexes are private generated recall artifacts; project-local output is explicit compatibility, not the default.",
            },
            "publish_policy": {
                "sqlite": "versioned_pointer_with_stable_backup",
                "writer_lease": ".index-publish.lock",
                "why": "Windows readers can hold the legacy SQLite file open; versioned indexes plus a pointer keep new readers moving while SQLite backup updates the stable compatibility file when possible.",
            },
            "source_rollout": str(rollout),
            "source_rollout_size": stat.st_size,
            "source_rollout_mtime": stat.st_mtime,
            "source_rollout_sha256": file_sha256(rollout) if args.hash_source else None,
            "anchor_file": str(anchor_path) if anchor_path.exists() else None,
            "anchor_mtime": anchor_path.stat().st_mtime if anchor_path.exists() else None,
            "anchor_sha256": file_sha256(anchor_path) if anchor_path.exists() else None,
            "session_meta": meta,
            "message_count": len(messages),
            "first_message_line": messages[0]["line"] if messages else None,
            "last_message_line": messages[-1]["line"] if messages else None,
            "turn_count": len(turns),
            "anchor_count": len(anchors),
            "graph": {"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])},
            "outputs": {
                "messages_jsonl": str(messages_path),
                "sqlite": str(sqlite_path),
                "sqlite_current": str(sqlite_current) if sqlite_current else str(sqlite_path),
                "sqlite_pointer": str(sqlite_pointer) if sqlite_pointer else None,
                "graph_json": str(graph_path),
            },
            "sqlite": sqlite_status,
            "rag": sqlite_status.get("rag"),
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"manifest: {manifest_path.resolve()}")
        print(f"messages: {messages_path.resolve()} ({len(messages)} messages)")
        print(f"sqlite: {sqlite_path.resolve()} (fts={sqlite_status['fts_enabled']})")
        if sqlite_status.get("rag", {}).get("enabled"):
            print(
                f"rag cache: {sqlite_status['rag']['chunk_count']} chunks (fts={sqlite_status['rag']['fts_enabled']})"
            )
        print(
            f"graph: {graph_path.resolve()} ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
