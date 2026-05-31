#!/usr/bin/env python3
"""Search a Codex rollout JSONL or thread-memory SQLite index."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from aippocampus_runtime.artifacts.publish import (
    index_pointer_path,
    resolve_sqlite_index_path,
)
from aippocampus_runtime.core import (
    compact_text,
    default_thread_index_dir,
    iter_messages,
    locate_rollout,
)
from aippocampus_runtime.recall.retrieval import (
    diversify_results,
    expanded_terms_from_anchors,
    graph_neighbors,
    match_anchors,
    message_select_columns,
    search_hybrid_index,
    search_rag_chunks,
    split_query_terms,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RolloutSearchOptions:
    patterns: Sequence[str]
    cwd: str | Path = os.getcwd()
    rollout: str | Path | None = None
    index: str | Path | None = None
    anchors: str | Path = "thread-anchors.md"
    build_index: bool = False
    no_index: bool = False
    include_tools: bool = False
    mode: str = "hybrid"
    context: int = 0
    candidate_max: int = 160
    diversity: str = "balanced"
    rag_context: int = 3
    max_results: int = 30
    snippet_chars: int = 700


def auto_index_path(cwd: str, rollout: Path | None = None, *, prefer_existing: bool = True) -> Path:
    root = Path(cwd).resolve()
    global_index = default_thread_index_dir(root, rollout) / "source_index.sqlite"
    preferred = root / ".aippocampus" / "source_index.sqlite"
    if prefer_existing:
        for candidate in (global_index, preferred):
            if candidate.exists() or index_pointer_path(candidate).exists():
                resolved = resolve_sqlite_index_path(candidate)
                if resolved.exists():
                    return resolved
    legacy = root / ".thread-memory-index" / "thread_index.sqlite"
    if prefer_existing and legacy.exists():
        return legacy
    return global_index


def auto_graph_path(cwd: str, rollout: Path | None = None, *, prefer_existing: bool = True) -> Path:
    root = Path(cwd).resolve()
    global_graph = default_thread_index_dir(root, rollout) / "graph.json"
    preferred = root / ".aippocampus" / "graph.json"
    if prefer_existing:
        if global_graph.exists():
            return global_graph
        if preferred.exists():
            return preferred
    legacy = root / ".thread-memory-index" / "graph.json"
    if prefer_existing and legacy.exists():
        return legacy
    return global_graph


def resolve_anchor_path(cwd: str, anchors: str) -> Path:
    path = Path(anchors)
    if not path.is_absolute():
        path = Path(cwd).resolve() / path
    return path


def ensure_index(cwd: str, rollout: Path | None, index: Path, *, force: bool = False) -> None:
    if index.exists() and not force:
        return
    # A finished Codex turn writes the final answer to the raw rollout after
    # any in-turn maintenance commands have already rebuilt indexes. When the
    # caller explicitly asks to build the index, refresh it even if SQLite
    # already exists so the last final_answer is not hidden behind a "fresh
    # enough" cached index.
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_index.py"),
        "--cwd",
        cwd,
        "--output-dir",
        str(index.parent),
    ]
    if rollout:
        cmd.extend(["--rollout", str(rollout)])
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)


def fts_query(patterns: list[str]) -> str:
    phrases = []
    for pattern in patterns:
        # Treat user input as literal recall clues, not as raw FTS syntax.
        cleaned = pattern.replace('"', '""').strip()
        if cleaned:
            phrases.append(f'"{cleaned}"')
    return " OR ".join(phrases)


def search_index_literal(
    index: Path, patterns: list[str], limit: int, snippet_chars: int
) -> list[dict]:
    con = sqlite3.connect(index)
    con.row_factory = sqlite3.Row
    try:
        query = fts_query(patterns)
        rows = []
        try:
            if query:
                rows = con.execute(
                    f"""
                    SELECT {message_select_columns(con, "m")}
                    FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    WHERE messages_fts MATCH ?
                    ORDER BY m.id
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
        except sqlite3.Error:
            rows = []

        if not rows:
            where = " OR ".join(["text LIKE ?" for _ in patterns])
            params = [f"%{p}%" for p in patterns] + [limit]
            rows = con.execute(
                f"SELECT {message_select_columns(con)} FROM messages WHERE {where} ORDER BY id LIMIT ?",
                params,
            ).fetchall()

        return [
            {
                "id": row["id"],
                "line": row["line"],
                "timestamp": row["timestamp"],
                "role": row["role"],
                "kind": row["kind"],
                "phase": row["phase"] or "",
                "turn_index": row["turn_index"],
                "is_final": bool(row["is_final"]),
                "score": None,
                "signals": {"mode": "literal"},
                "snippet": compact_text(row["text"], snippet_chars),
            }
            for row in rows
        ]
    finally:
        con.close()


def search_rollout_stream(
    rollout: Path, patterns: list[str], include_tools: bool, limit: int, snippet_chars: int
) -> list[dict]:
    regexes = [re.compile(p, re.IGNORECASE) for p in patterns]
    results = []
    for msg in iter_messages(rollout, include_tools=include_tools):
        text = msg["text"]
        if not any(r.search(text) for r in regexes):
            continue
        results.append(
            {
                "line": msg["line"],
                "timestamp": msg["timestamp"],
                "role": msg["role"],
                "kind": msg["kind"],
                "phase": msg.get("phase") or "",
                "turn_index": msg.get("turn_index"),
                "is_final": bool(msg.get("is_final")),
                "score": None,
                "signals": {"mode": "stream"},
                "snippet": compact_text(text, snippet_chars),
            }
        )
        if len(results) >= limit:
            break
    return results


def search_rollout_payload(options: RolloutSearchOptions) -> dict:
    patterns = list(options.patterns)
    cwd = str(Path(options.cwd).resolve())
    rollout = Path(options.rollout) if options.rollout else None
    index = (
        Path(options.index)
        if options.index
        else auto_index_path(cwd, rollout, prefer_existing=not options.build_index)
    )
    anchor_path = resolve_anchor_path(cwd, str(options.anchors))

    source = None
    results: list[dict]
    query_terms = split_query_terms(patterns)
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    expanded_terms = (
        expanded_terms_from_anchors(query_terms, anchors)
        if options.mode == "hybrid"
        else query_terms
    )
    graph = (
        graph_neighbors(
            auto_graph_path(cwd, rollout, prefer_existing=not options.build_index), expanded_terms
        )
        if options.mode == "hybrid"
        else []
    )
    rag_context: list[dict] = []

    if not options.no_index:
        if options.build_index:
            ensure_index(cwd, rollout, index, force=True)
        index = resolve_sqlite_index_path(index)
        if index.exists():
            source = str(index)
            if options.mode == "literal":
                results = search_index_literal(
                    index, patterns, options.max_results, options.snippet_chars
                )
            else:
                if options.mode == "hybrid" and options.rag_context > 0:
                    rag_context = search_rag_chunks(
                        index,
                        query_terms,
                        expanded_terms,
                        anchors,
                        limit=options.rag_context,
                        candidate_limit=max(40, options.candidate_max // 2),
                        snippet_chars=max(options.snippet_chars, 900),
                    )
                results = search_hybrid_index(
                    index,
                    query_terms,
                    expanded_terms,
                    anchors if options.mode == "hybrid" else [],
                    limit=options.max_results,
                    candidate_limit=options.candidate_max,
                    snippet_chars=options.snippet_chars,
                    context_radius=options.context,
                )
                if options.mode == "hybrid":
                    results = diversify_results(
                        results, options.max_results, anchors, mode=options.diversity
                    )
        else:
            rollout = rollout or locate_rollout(cwd)
            source = str(rollout)
            results = search_rollout_stream(
                rollout,
                patterns,
                options.include_tools,
                options.max_results,
                options.snippet_chars,
            )
    else:
        rollout = rollout or locate_rollout(cwd)
        source = str(rollout)
        results = search_rollout_stream(
            rollout,
            patterns,
            options.include_tools,
            options.max_results,
            options.snippet_chars,
        )

    return {
        "source": source,
        "mode": options.mode if not options.no_index else "stream",
        "query_terms": query_terms,
        "expanded_terms": expanded_terms,
        "matched_anchors": anchors,
        "graph_neighbors": graph,
        "rag_context": rag_context,
        "matches": results,
    }


def options_from_args(args: argparse.Namespace) -> RolloutSearchOptions:
    return RolloutSearchOptions(
        patterns=args.patterns,
        rollout=args.rollout,
        cwd=args.cwd,
        index=args.index,
        anchors=args.anchors,
        build_index=args.build_index,
        no_index=args.no_index,
        include_tools=args.include_tools,
        mode=args.mode,
        context=args.context,
        candidate_max=args.candidate_max,
        diversity=args.diversity,
        rag_context=args.rag_context,
        max_results=args.max,
        snippet_chars=args.snippet_chars,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+", help="Literal clues or regex patterns to search.")
    parser.add_argument("--rollout", help="Explicit rollout JSONL path.")
    parser.add_argument("--cwd", default=os.getcwd(), help="Workspace cwd used to locate rollout.")
    parser.add_argument(
        "--index",
        help="SQLite index path. Defaults to the global thread store, with project-local legacy fallback.",
    )
    parser.add_argument(
        "--anchors",
        default="thread-anchors.md",
        help="Anchor file used for hybrid query expansion.",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build/rebuild the global default index before searching unless --index is provided.",
    )
    parser.add_argument(
        "--no-index", action="store_true", help="Force streaming JSONL regex search."
    )
    parser.add_argument("--include-tools", action="store_true")
    parser.add_argument("--mode", choices=["literal", "ranked", "hybrid"], default="hybrid")
    parser.add_argument(
        "--context",
        type=int,
        default=0,
        help="Include N neighboring normalized messages around each hit in JSON/text output.",
    )
    parser.add_argument(
        "--candidate-max",
        type=int,
        default=160,
        help="Internal candidate pool for ranked/hybrid search.",
    )
    parser.add_argument(
        "--diversity",
        choices=["none", "balanced", "early"],
        default="balanced",
        help="Reorder hybrid hits to avoid one recap cluster crowding out source-diverse evidence.",
    )
    parser.add_argument(
        "--rag-context",
        type=int,
        default=3,
        help="Return N RAG-lite chunk hits alongside message hits in hybrid mode.",
    )
    parser.add_argument(
        "--show-anchors",
        action="store_true",
        help="Print matched anchors and graph neighbors before message hits.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--max", type=int, default=30)
    parser.add_argument("--snippet-chars", type=int, default=700)
    args = parser.parse_args()

    payload = search_rollout_payload(options_from_args(args))
    query_terms = payload["query_terms"]
    expanded_terms = payload["expanded_terms"]
    anchors = payload["matched_anchors"]
    graph = payload["graph_neighbors"]
    rag_context = payload["rag_context"]
    results = payload["matches"]

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"source: {payload['source']}")
        print(f"mode: {payload['mode']}")
        if args.mode == "hybrid":
            print(f"query terms: {', '.join(query_terms) or '(none)'}")
            print(f"expanded terms: {', '.join(expanded_terms) or '(none)'}")
        if args.show_anchors and anchors:
            print("\nmatched anchors:")
            for anchor in anchors:
                print(f"- score {anchor['score']} | {anchor['title']}")
                if anchor.get("matched_terms"):
                    print(f"  matched: {', '.join(anchor['matched_terms'])}")
        if args.show_anchors and graph:
            print("\ngraph neighbors:")
            for node in graph:
                marker = "*" if node.get("matched") else "-"
                print(f"{marker} {node.get('type')}: {node.get('label')}")
        if rag_context:
            print("\nrag context:")
            for chunk in rag_context:
                print(
                    f"- score {chunk['score']} | chunk {chunk['id']} | "
                    f"lines {chunk['start_line']}-{chunk['end_line']}"
                )
                if chunk.get("anchor_titles"):
                    print(f"  anchors: {', '.join(chunk['anchor_titles'])}")
                print(f"  {chunk['summary']}")
        for r in results:
            row_id = f" id {r['id']} |" if "id" in r else ""
            score = f" score {r['score']} |" if r.get("score") is not None else ""
            phase = f" | phase={r.get('phase')}" if r.get("phase") else ""
            turn = f" | turn={r.get('turn_index')}" if r.get("turn_index") is not None else ""
            print(
                f"\n-{row_id}{score} line {r['line']} | {r['timestamp']} | {r['role']} | {r['kind']}{phase}{turn}"
            )
            signals = r.get("signals") or {}
            if r.get("score") is not None:
                compact_signals = {k: v for k, v in signals.items() if k != "fts_rank"}
                print(f"  signals: {compact_signals}")
            print(f"  {r['snippet']}")
            if r.get("context"):
                print("  context:")
                for ctx in r["context"]:
                    ctx_phase = f"/{ctx.get('phase')}" if ctx.get("phase") else ""
                    ctx_turn = (
                        f" turn={ctx.get('turn_index')}"
                        if ctx.get("turn_index") is not None
                        else ""
                    )
                    print(
                        f"    - id {ctx['id']} | line {ctx['line']} | {ctx['role']}{ctx_phase}{ctx_turn}: {ctx['snippet']}"
                    )
    return 0 if results or anchors else 1


if __name__ == "__main__":
    raise SystemExit(main())
