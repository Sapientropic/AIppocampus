#!/usr/bin/env python3
"""Build portable JSONL, SQLite FTS, manifest, and graph files for a transcript source."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import (
    DEFAULT_ARTIFACT_LEASE_WAIT_SECONDS,
    DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
    artifact_lease,
    publish_sqlite_with_pointer,
    remove_sqlite_artifact,
    unique_temp_sqlite_path,
)
from aippocampus_runtime.core import (
    build_anchor_graph,
    codex_home,
    default_thread_index_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    parse_anchor_file,
    resolve_artifact_path,
)
from aippocampus_runtime.io_integrity import atomic_write_json, atomic_write_jsonl
from aippocampus_runtime.recall.retrieval import build_rag_chunks
from aippocampus_runtime.safety import project_clean_source_row
from conversation_sources import create_conversation_provider

CODE_FENCE_RE = re.compile(r"^\s*```([A-Za-z0-9_.+-]*)?", re.MULTILINE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", re.MULTILINE)
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
WARNING_RE = re.compile(
    r"(\bwarning\b|\bcaution\b|\bwarn\b|⚠|注意|警告|重要)",
    re.IGNORECASE,
)


def unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def has_markdown_table(text: str) -> bool:
    lines = text.splitlines()
    for idx, line in enumerate(lines[:-1]):
        if "|" not in line:
            continue
        if TABLE_SEPARATOR_RE.match(lines[idx + 1] or ""):
            return True
    return False


def message_feature_row(
    message_id: int,
    message: dict[str, Any],
    *,
    source_created_at: str | None = None,
    source_updated_at: str | None = None,
    last_active_at: str | None = None,
) -> tuple[Any, ...]:
    """Project hot deterministic recall cues into a scalar sidecar row.

    D5/D6 structure and time recall should stay source-backed: these fields are
    only searchable projections of the raw message, never replacement evidence.
    Keep common filters scalar/indexed here; reserve metadata_json for cold
    debugging attributes so recall does not drift into JSON scans on the hot path.
    """

    text = str(message.get("text") or "")
    code_languages = unique_preserve(
        [(match.group(1) or "").strip().casefold() for match in CODE_FENCE_RE.finditer(text)]
    )
    message_timestamp = message.get("timestamp")
    active_timestamp = message_timestamp or last_active_at or source_updated_at or source_created_at
    sha1 = str(message.get("sha1") or "")
    # Repeated short turns can legitimately share a text hash, so keep the
    # hash as a navigation cue but include the SQLite row id for a stable handle.
    source_ref = (
        f"message_sha1:{sha1[:16]}#message_id:{message_id}"
        if sha1
        else f"message_id:{message_id}"
    )
    metadata = {
        "feature_version": 1,
        "source_projection": "deterministic_message_features",
    }
    return (
        message_id,
        message.get("line"),
        source_ref,
        message.get("role") or "",
        message.get("phase") or "",
        1 if message.get("is_final") else 0,
        1 if CODE_FENCE_RE.search(text) else 0,
        json.dumps(code_languages, ensure_ascii=False),
        1 if WARNING_RE.search(text) else 0,
        1 if LIST_RE.search(text) else 0,
        1 if has_markdown_table(text) else 0,
        len(HEADING_RE.findall(text)),
        len(text.splitlines()) if text else 0,
        message_timestamp,
        source_created_at,
        source_updated_at,
        active_timestamp,
        json.dumps(metadata, ensure_ascii=False),
    )


def make_sqlite(
    index_path: Path,
    messages: list[dict],
    anchors: list[dict],
    turns: list[dict] | None = None,
    *,
    rag_cache: bool = True,
    rag_chunk_chars: int = 2800,
    publish_lock: bool = True,
    publish_wait_timeout_seconds: float = DEFAULT_ARTIFACT_LEASE_WAIT_SECONDS,
    sqlite_busy_timeout_ms: int = DEFAULT_SQLITE_BUSY_TIMEOUT_MS,
    source_created_at: str | None = None,
    source_updated_at: str | None = None,
    last_active_at: str | None = None,
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
            "sha1 TEXT, text TEXT)"
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
        con.execute("CREATE INDEX idx_messages_sha1 ON messages(sha1)")
        con.execute(
            "CREATE TABLE message_features ("
            "message_id INTEGER PRIMARY KEY REFERENCES messages(id), "
            "line INTEGER, source_ref TEXT, role TEXT, phase TEXT, is_final INTEGER, "
            "has_code_block INTEGER, code_languages_json TEXT, has_warning INTEGER, "
            "has_list INTEGER, has_table INTEGER, heading_count INTEGER, line_count INTEGER, "
            "message_timestamp TEXT, thread_created_at TEXT, thread_updated_at TEXT, "
            "active_timestamp TEXT, metadata_json TEXT)"
        )
        con.executemany(
            "INSERT INTO message_features "
            "(message_id, line, source_ref, role, phase, is_final, has_code_block, "
            "code_languages_json, has_warning, has_list, has_table, heading_count, "
            "line_count, message_timestamp, thread_created_at, thread_updated_at, "
            "active_timestamp, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                message_feature_row(
                    idx,
                    m,
                    source_created_at=source_created_at,
                    source_updated_at=source_updated_at,
                    last_active_at=last_active_at,
                )
                for idx, m in enumerate(messages, start=1)
            ],
        )
        con.execute(
            "CREATE INDEX idx_message_features_code_block "
            "ON message_features(has_code_block) WHERE has_code_block = 1"
        )
        con.execute(
            "CREATE INDEX idx_message_features_warning "
            "ON message_features(has_warning) WHERE has_warning = 1"
        )
        con.execute(
            "CREATE INDEX idx_message_features_list "
            "ON message_features(has_list) WHERE has_list = 1"
        )
        con.execute(
            "CREATE INDEX idx_message_features_table "
            "ON message_features(has_table) WHERE has_table = 1"
        )
        con.execute(
            "CREATE INDEX idx_message_features_role_phase_final "
            "ON message_features(role, phase, is_final)"
        )
        con.execute(
            "CREATE INDEX idx_message_features_active_timestamp "
            "ON message_features(active_timestamp)"
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
            with artifact_lease(
                index_path.parent,
                ".index-publish.lock",
                wait_timeout_seconds=publish_wait_timeout_seconds,
            ):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--provider",
        default="codex",
        help="Conversation source provider: codex, claude-code, or generic-jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the AIppocampus registry thread store; pass .aippocampus for project-local output.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--include-tools", action="store_true")
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument(
        "--redaction-profile",
        default="raw-private",
        help="Project source text before writing index artifacts; public-export is safe for bundles.",
    )
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
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    provider = create_conversation_provider(args.provider, codex_home_dir=codex_home())
    rollout = Path(args.rollout) if args.rollout else None
    if rollout is None:
        rollout = locate_rollout(cwd, codex_home()) if provider.name == "codex" else provider.locate_current(cwd).path
    output_dir = resolve_artifact_path(args.output_dir, cwd, default_thread_index_dir(cwd, rollout))
    output_dir.mkdir(parents=True, exist_ok=True)

    meta = provider.read_metadata(rollout) or {}
    messages, turns = provider.read_normalized_messages(rollout, include_tools=args.include_tools)
    redaction_profile = str(args.redaction_profile or "raw-private")
    messages = [
        project_clean_source_row(message, profile=redaction_profile, project_root=cwd)
        for message in messages
    ]

    with artifact_lease(
        output_dir,
        ".index-publish.lock",
        wait_timeout_seconds=DEFAULT_ARTIFACT_LEASE_WAIT_SECONDS,
    ):
        messages_path = output_dir / "messages.jsonl"
        atomic_write_jsonl(messages_path, messages)

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
            source_created_at=meta.get("created_at") or meta.get("createdAt"),
            source_updated_at=meta.get("updated_at") or meta.get("updatedAt"),
            last_active_at=meta.get("last_active_at") or meta.get("lastActiveAt"),
        )
        sqlite_publish = sqlite_status.get("publish") or {}
        sqlite_current = sqlite_publish.get("current")
        sqlite_pointer = sqlite_publish.get("pointer")
        graph = build_anchor_graph(anchors, meta.get("id"))
        graph_path = output_dir / "graph.json"
        atomic_write_json(graph_path, graph)

        stat = rollout.stat()
        manifest = {
            "schema_version": 1,
            "created_at": now_utc(),
            "cwd": str(cwd),
            "artifact_scope": "global_thread_store"
            if args.output_dir is None
            else "explicit_output_dir",
            "storage_policy": {
                "default": "AIPPOCAMPUS_REGISTRY_DIR or AIPPOCAMPUS_HOME/registry, with legacy CODEX_HOME fallback",
                "explicit_project_local_output": ".aippocampus",
                "why": "Indexes are private generated recall artifacts; project-local output is explicit compatibility, not the default.",
            },
            "publish_policy": {
                "sqlite": "generation_pointer_with_stable_backup",
                "writer_lease": ".index-publish.lock",
                "why": "Windows readers can hold the legacy SQLite file open; generation indexes plus a pointer keep new readers moving while SQLite backup updates the stable compatibility file when possible.",
            },
            "source_rollout": str(rollout),
            "source_provider": provider.name,
            "source_thread_key": provider.thread_key(rollout, meta),
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
            "redaction_profile": redaction_profile,
            "privacy_boundary": {
                "source_text_profile": redaction_profile,
                "canonical_clean_source_replaced": False,
                "raw_source_text_emitted": redaction_profile == "raw-private",
                "projection_policy": "aippocampus_runtime.safety.project_clean_source_text",
            },
        }
        manifest_path = output_dir / "manifest.json"
        atomic_write_json(manifest_path, manifest)

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
