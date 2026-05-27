#!/usr/bin/env python3
"""Fan out a query across segmented thread indexes and merge top-k hits."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from aippocampuslib import default_thread_segments_dir
from retrieval import (
    expanded_terms_from_anchors,
    graph_neighbors,
    match_anchors,
    search_hybrid_index,
    search_rag_chunks,
    split_query_terms,
)
from search_rollout import auto_graph_path, resolve_anchor_path, search_index_literal

SCRIPT_DIR = Path(__file__).resolve().parent


def manifest_path(cwd: Path, segments_dir: str | None, *, prefer_existing: bool = True) -> Path:
    if segments_dir:
        path = Path(segments_dir)
        if not path.is_absolute():
            path = cwd / path
        return path / "manifest.json"
    global_manifest = default_thread_segments_dir(cwd) / "manifest.json"
    legacy_manifest = cwd / ".aippocampus" / "segments" / "manifest.json"
    if prefer_existing and not global_manifest.exists() and legacy_manifest.exists():
        return legacy_manifest
    return global_manifest


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_segments(cwd: Path, rollout: str | None, manifest: Path, force: bool) -> None:
    if manifest.exists() and not force:
        return
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_segments.py"),
        "--cwd",
        str(cwd),
        "--output-dir",
        str(manifest.parent),
    ]
    if rollout:
        cmd.extend(["--rollout", rollout])
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)


def segment_sort_key(result: dict) -> tuple[float, int, int]:
    final_bonus = 12.0 if result.get("phase") == "final_answer" or result.get("is_final") else 0.0
    commentary_penalty = -4.0 if result.get("phase") == "commentary" else 0.0
    return (
        -(float(result.get("score") or 0.0) + final_bonus + commentary_penalty),
        int(result.get("line") or 10**12),
        int(result.get("segment_ordinal") or 10**6),
    )


def merge_topk(results: list[dict], limit: int) -> list[dict]:
    """Merge per-shard hits without letting one dense recap shard dominate.

    Segment-local SQLite row ids collide, so this intentionally avoids
    retrieval.diversify_results, whose duplicate guard assumes one monolithic
    index. The merge keeps high-score hits first, then applies light penalties
    for same-segment and near-line repeats so early source evidence and later
    summaries can both surface.
    """

    if not results:
        return []
    pool = sorted(results, key=segment_sort_key)
    selected: list[dict] = []
    seen: set[tuple[str, int, int]] = set()

    def key(item: dict) -> tuple[str, int, int]:
        return (str(item.get("segment_id")), int(item.get("id") or 0), int(item.get("line") or 0))

    def add(item: dict | None) -> None:
        if not item:
            return
        item_key = key(item)
        if item_key in seen:
            return
        selected.append(item)
        seen.add(item_key)

    add(pool[0])
    literal_hits = [item for item in pool if (item.get("signals") or {}).get("literal_hits", 0) > 0]
    add(
        min(
            (item for item in literal_hits if item.get("role") == "user"),
            key=lambda item: item.get("line") or 10**12,
            default=None,
        )
    )
    add(min(literal_hits, key=lambda item: item.get("line") or 10**12, default=None))
    add(
        max(
            (item for item in pool if item.get("role") == "assistant"),
            key=lambda item: (
                (12.0 if item.get("phase") == "final_answer" or item.get("is_final") else 0.0)
                + float(item.get("score") or 0)
            ),
            default=None,
        )
    )

    while len(selected) < min(limit, len(pool)):
        selected_segments = {str(item.get("segment_id")) for item in selected}
        selected_lines = [int(item.get("line") or 0) for item in selected]
        best = None
        best_value = None
        for item in pool:
            if key(item) in seen:
                continue
            value = float(item.get("score") or 0.0)
            if str(item.get("segment_id")) in selected_segments:
                value -= 7.0
            if item.get("phase") == "final_answer" or item.get("is_final"):
                value += 12.0
            if item.get("phase") == "commentary":
                value -= 4.0
            line = int(item.get("line") or 0)
            if any(abs(line - other) < 25 for other in selected_lines):
                value -= 8.0
            if (item.get("signals") or {}).get("literal_hits", 0) > 0 and item.get(
                "role"
            ) == "user":
                value += 3.0
            if best_value is None or value > best_value:
                best = item
                best_value = value
        add(best)
        if best is None:
            break
    return selected[:limit]


def annotate_segment_result(result: dict, segment: dict, ordinal: int) -> dict:
    item = dict(result)
    item["segment_id"] = segment["id"]
    item["segment_ordinal"] = ordinal
    item["segment_start_line"] = segment.get("start_line")
    item["segment_end_line"] = segment.get("end_line")
    item["global_id_range"] = [segment.get("start_global_id"), segment.get("end_global_id")]
    signals = dict(item.get("signals") or {})
    signals["segment_id"] = segment["id"]
    item["signals"] = signals
    if item.get("context"):
        for ctx in item["context"]:
            ctx["segment_id"] = segment["id"]
    return item


def annotate_rag_chunk(chunk: dict, segment: dict, ordinal: int) -> dict:
    item = dict(chunk)
    item["segment_id"] = segment["id"]
    item["segment_ordinal"] = ordinal
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+", help="Literal clues or recall prompt.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--segments-dir",
        default=None,
        help="Defaults to global segments, with project-local legacy fallback.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--build-segments", action="store_true")
    parser.add_argument("--mode", choices=["literal", "ranked", "hybrid"], default="hybrid")
    parser.add_argument("--context", type=int, default=0)
    parser.add_argument("--per-segment", type=int, default=12)
    parser.add_argument("--candidate-max", type=int, default=120)
    parser.add_argument("--rag-context", type=int, default=6)
    parser.add_argument("--show-anchors", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--max", type=int, default=30)
    parser.add_argument("--snippet-chars", type=int, default=700)
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    manifest = manifest_path(cwd, args.segments_dir, prefer_existing=not args.build_segments)
    ensure_segments(cwd, args.rollout, manifest, args.build_segments)
    data = load_manifest(manifest)
    if not data:
        raise SystemExit(f"segment manifest not found: {manifest}")

    anchor_path = resolve_anchor_path(str(cwd), args.anchors)
    query_terms = split_query_terms(args.patterns)
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    expanded_terms = (
        expanded_terms_from_anchors(query_terms, anchors) if args.mode == "hybrid" else query_terms
    )
    graph = (
        graph_neighbors(auto_graph_path(str(cwd)), expanded_terms) if args.mode == "hybrid" else []
    )

    raw_results: list[dict] = []
    rag_context: list[dict] = []
    segment_errors: list[dict] = []
    for ordinal, segment in enumerate(data.get("segments") or [], start=1):
        index = Path(segment["sqlite"])
        if not index.exists():
            segment_errors.append({"segment_id": segment.get("id"), "error": "sqlite missing"})
            continue
        try:
            if args.mode == "literal":
                hits = search_index_literal(
                    index, args.patterns, args.per_segment, args.snippet_chars
                )
            else:
                if args.mode == "hybrid" and args.rag_context > 0:
                    for chunk in search_rag_chunks(
                        index,
                        query_terms,
                        expanded_terms,
                        anchors,
                        limit=max(1, args.rag_context // 2),
                        candidate_limit=max(24, args.candidate_max // 2),
                        snippet_chars=max(args.snippet_chars, 900),
                    ):
                        rag_context.append(annotate_rag_chunk(chunk, segment, ordinal))
                hits = search_hybrid_index(
                    index,
                    query_terms,
                    expanded_terms,
                    anchors if args.mode == "hybrid" else [],
                    limit=args.per_segment,
                    candidate_limit=args.candidate_max,
                    snippet_chars=args.snippet_chars,
                    context_radius=args.context,
                )
            raw_results.extend(annotate_segment_result(hit, segment, ordinal) for hit in hits)
        except Exception as exc:
            segment_errors.append({"segment_id": segment.get("id"), "error": str(exc)})

    results = merge_topk(raw_results, args.max)
    rag_context.sort(
        key=lambda item: (-float(item.get("score") or 0.0), int(item.get("start_line") or 10**12))
    )
    rag_context = rag_context[: args.rag_context]

    payload = {
        "source": str(manifest),
        "mode": f"segmented-{args.mode}",
        "segment_count": int(data.get("segment_count") or len(data.get("segments") or [])),
        "query_terms": query_terms,
        "expanded_terms": expanded_terms,
        "matched_anchors": anchors,
        "graph_neighbors": graph,
        "rag_context": rag_context,
        "matches": results,
        "segment_errors": segment_errors,
    }

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"source: {manifest}")
        print(f"mode: {payload['mode']} ({payload['segment_count']} segments)")
        if args.mode == "hybrid":
            print(f"query terms: {', '.join(query_terms) or '(none)'}")
            print(f"expanded terms: {', '.join(expanded_terms) or '(none)'}")
        if args.show_anchors and anchors:
            print("\nmatched anchors:")
            for anchor in anchors:
                print(f"- score {anchor['score']} | {anchor['title']}")
        if args.show_anchors and graph:
            print("\ngraph neighbors:")
            for node in graph:
                marker = "*" if node.get("matched") else "-"
                print(f"{marker} {node.get('type')}: {node.get('label')}")
        if rag_context:
            print("\nrag context:")
            for chunk in rag_context:
                print(
                    f"- score {chunk['score']} | {chunk['segment_id']} chunk {chunk['id']} | "
                    f"lines {chunk['start_line']}-{chunk['end_line']}"
                )
                print(f"  {chunk['summary']}")
        if segment_errors:
            print("\nsegment errors:")
            for item in segment_errors:
                print(f"- {item['segment_id']}: {item['error']}")
        for item in results:
            score = f" score {item['score']} |" if item.get("score") is not None else ""
            print(
                f"\n- {item['segment_id']} id {item.get('id')} |{score} "
                f"line {item['line']} | {item['timestamp']} | {item['role']} | {item['kind']}"
                f"{' | phase=' + str(item.get('phase')) if item.get('phase') else ''}"
                f"{' | turn=' + str(item.get('turn_index')) if item.get('turn_index') is not None else ''}"
            )
            if item.get("score") is not None:
                compact_signals = {
                    k: v for k, v in (item.get("signals") or {}).items() if k != "fts_rank"
                }
                print(f"  signals: {compact_signals}")
            print(f"  {item['snippet']}")
            if item.get("context"):
                print("  context:")
                for ctx in item["context"]:
                    ctx_phase = f"/{ctx.get('phase')}" if ctx.get("phase") else ""
                    ctx_turn = (
                        f" turn={ctx.get('turn_index')}"
                        if ctx.get("turn_index") is not None
                        else ""
                    )
                    print(
                        f"    - {ctx['segment_id']} id {ctx['id']} | line {ctx['line']} | {ctx['role']}{ctx_phase}{ctx_turn}: {ctx['snippet']}"
                    )
    return 0 if results or anchors or rag_context else 1


if __name__ == "__main__":
    raise SystemExit(main())
