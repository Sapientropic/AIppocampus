#!/usr/bin/env python3
"""Report health and recommended maintenance for a long Codex thread."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aippocampuslib import (
    codex_home,
    default_thread_checkpoint_state_path,
    default_thread_clean_source_dir,
    default_thread_graphify_corpus_dir,
    default_thread_index_dir,
    default_thread_segments_dir,
    file_sha256,
    iter_messages,
    locate_rollout,
    parse_anchor_file,
    resolve_artifact_path,
)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def count_messages(rollout: Path) -> tuple[int, int | None]:
    count = 0
    last_line = None
    for msg in iter_messages(rollout):
        count += 1
        last_line = msg["line"]
    return count, last_line


def action(action_id: str, severity: str, reason: str, command: str) -> dict:
    return {"id": action_id, "severity": severity, "reason": reason, "command": command}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--index-dir", default=None, help="Defaults to the CODEX_HOME global thread store.")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--graphify-corpus", default=None, help="Defaults to the global thread store's graphify-corpus.")
    parser.add_argument("--segments-dir", default=None, help="Defaults to the global thread store's segments directory.")
    parser.add_argument("--checkpoint-state", default=None, help="Defaults to the global thread store's checkpoint state.")
    parser.add_argument("--clean-source-dir", default=None, help="Defaults to the global thread store's clean-source directory.")
    parser.add_argument("--max-stale-messages", type=int, default=25)
    parser.add_argument("--max-stale-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--checkpoint-messages", type=int, default=30)
    parser.add_argument("--deep-graph-messages", type=int, default=1000)
    parser.add_argument("--deep-graph-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--segment-threshold-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--exit-code", action="store_true", help="Exit 2 when maintenance is recommended.")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = locate_rollout(cwd, codex_home())
    index_dir = resolve_artifact_path(args.index_dir, cwd, default_thread_index_dir(cwd, rollout))
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    graphify_corpus = resolve_artifact_path(args.graphify_corpus, cwd, default_thread_graphify_corpus_dir(cwd, rollout))
    segments_dir = resolve_artifact_path(args.segments_dir, cwd, default_thread_segments_dir(cwd, rollout))
    checkpoint_state = resolve_artifact_path(args.checkpoint_state, cwd, default_thread_checkpoint_state_path(cwd, rollout))
    clean_source_dir = resolve_artifact_path(args.clean_source_dir, cwd, default_thread_clean_source_dir(cwd, rollout))
    rollout_stat = rollout.stat()
    current_message_count, last_line = count_messages(rollout)
    current_anchor_count = len(parse_anchor_file(anchors))
    current_anchor_sha = file_sha256(anchors) if anchors.exists() else None

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    sqlite_path = index_dir / "source_index.sqlite"
    manifest = load_json(manifest_path)

    index_reasons: list[str] = []
    if not manifest:
        index_reasons.append("index manifest is missing")
    if not messages_path.exists():
        index_reasons.append("messages.jsonl is missing")
    if not sqlite_path.exists():
        index_reasons.append("source_index.sqlite is missing")
    indexed_messages = int(manifest.get("message_count") or 0)
    indexed_bytes = int(manifest.get("source_rollout_size") or 0)
    indexed_last_line = manifest.get("last_message_line")
    message_delta = max(0, current_message_count - indexed_messages)
    byte_delta = max(0, rollout_stat.st_size - indexed_bytes)
    if manifest and message_delta >= args.max_stale_messages:
        index_reasons.append(f"{message_delta} new messages since last index")
    if manifest and byte_delta >= args.max_stale_bytes:
        index_reasons.append(f"{byte_delta} new rollout bytes since last index")
    if manifest and current_anchor_sha and manifest.get("anchor_sha256") != current_anchor_sha:
        index_reasons.append("thread-anchors.md changed since last index")
    rag_manifest = manifest.get("rag") or {}
    if manifest and not rag_manifest.get("enabled"):
        index_reasons.append("rag-lite chunk cache is missing from index manifest")

    index_stale = bool(index_reasons)

    clean_manifest_path = clean_source_dir / "manifest.json"
    clean_messages_path = clean_source_dir / "messages.jsonl"
    clean_turns_path = clean_source_dir / "turns.jsonl"
    clean_manifest = load_json(clean_manifest_path)
    clean_reasons: list[str] = []
    if not clean_manifest:
        clean_reasons.append("clean-source manifest is missing")
    if not clean_messages_path.exists():
        clean_reasons.append("clean-source messages.jsonl is missing")
    if not clean_turns_path.exists():
        clean_reasons.append("clean-source turns.jsonl is missing")
    try:
        clean_schema = int(clean_manifest.get("schema_version") or 0)
    except (TypeError, ValueError):
        clean_schema = 0
    if clean_manifest and clean_schema < 2:
        clean_reasons.append("clean-source schema is older than v2 upgrade contract")
    if clean_manifest and clean_schema >= 2 and not clean_manifest.get("upgrade_contract"):
        clean_reasons.append("clean-source upgrade contract is missing")
    clean_indexed_bytes = int(clean_manifest.get("source_rollout_size") or 0)
    clean_byte_delta = max(0, rollout_stat.st_size - clean_indexed_bytes)
    if clean_manifest and clean_byte_delta >= args.max_stale_bytes:
        clean_reasons.append(f"{clean_byte_delta} new rollout bytes since clean-source build")
    clean_source_stale = bool(clean_reasons)

    corpus_manifest_path = graphify_corpus / "corpus_manifest.json"
    corpus_manifest = load_json(corpus_manifest_path)
    current_manifest_sha = file_sha256(manifest_path) if manifest_path.exists() else None
    graphify_reasons: list[str] = []
    if not graphify_corpus.exists():
        graphify_reasons.append("graphify corpus is missing")
    elif not corpus_manifest:
        graphify_reasons.append("graphify corpus_manifest.json is missing")
    elif current_manifest_sha and corpus_manifest.get("source_index_manifest_sha256") != current_manifest_sha:
        graphify_reasons.append("graphify corpus was prepared from an older index manifest")
    if index_stale:
        graphify_reasons.append("index is stale, so prepared corpus may be stale too")
    graphify_stale = bool(graphify_reasons)

    segments_manifest_path = segments_dir / "manifest.json"
    segments_manifest = load_json(segments_manifest_path)
    segments_reasons: list[str] = []
    segments_needed = rollout_stat.st_size >= args.segment_threshold_bytes
    segments_message_delta = 0
    segments_byte_delta = 0
    if segments_needed and not segments_manifest:
        segments_reasons.append("segment manifest is missing for a large rollout")
    if segments_manifest:
        segment_rollout_size = int(segments_manifest.get("source_rollout_size") or 0)
        segment_message_count = int(segments_manifest.get("message_count") or 0)
        segments_byte_delta = max(0, rollout_stat.st_size - segment_rollout_size)
        segments_message_delta = max(0, current_message_count - segment_message_count)
        # Rollout files grow during any live interaction, including the health
        # check itself. Do not mark shards stale for one fresh message or a tiny
        # tool output; use the same stale thresholds as the main index so hooks
        # do not rebuild segments on every turn.
        if segments_message_delta >= args.max_stale_messages:
            segments_reasons.append(f"{segments_message_delta} new messages since segmented index build")
        if segments_byte_delta >= args.max_stale_bytes:
            segments_reasons.append(f"{segments_byte_delta} new rollout bytes since segmented index build")
        if current_anchor_sha and segments_manifest.get("anchor_sha256") != current_anchor_sha:
            segments_reasons.append("thread-anchors.md changed since segmented index build")
        missing_segment_indexes = [
            item.get("id") or "unknown"
            for item in segments_manifest.get("segments") or []
            if not Path(str(item.get("sqlite") or "")).exists()
        ]
        if missing_segment_indexes:
            segments_reasons.append(
                "segment sqlite file(s) missing: " + ", ".join(missing_segment_indexes[:6])
            )
    segments_stale = bool(segments_reasons)

    checkpoint = load_json(checkpoint_state)
    captured_count = int(checkpoint.get("last_captured_message_count") or 0)
    checked_count = int(checkpoint.get("last_checked_message_count") or 0)
    checkpoint_delta = current_message_count - captured_count
    checkpoint_due = captured_count == 0 or checkpoint_delta >= args.checkpoint_messages

    deep_graph_recommended = (
        current_message_count >= args.deep_graph_messages
        or rollout_stat.st_size >= args.deep_graph_bytes
    )

    actions = []
    if index_stale:
        severity = "critical" if not manifest else "warning"
        actions.append(action(
            "build_index",
            severity,
            "; ".join(index_reasons),
            f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\build_index.py\" --cwd \"{cwd}\"",
        ))
    if clean_source_stale:
        actions.append(action(
            "build_clean_source",
            "warning" if clean_manifest else "critical",
            "; ".join(clean_reasons),
            f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\build_clean_source.py\" --cwd \"{cwd}\"",
        ))
    if checkpoint_due:
        actions.append(action(
            "checkpoint",
            "suggestion",
            f"{checkpoint_delta} messages since the last captured checkpoint",
            f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\checkpoint.py\" --cwd \"{cwd}\"",
        ))
    if graphify_stale:
        actions.append(action(
            "prepare_graphify_corpus",
            "info",
            "; ".join(graphify_reasons),
            f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\prepare_graphify_corpus.py\" --cwd \"{cwd}\"",
        ))
    if segments_stale:
        severity = "warning" if segments_manifest else "info"
        actions.append(action(
            "build_segments",
            severity,
            "; ".join(segments_reasons),
            f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\build_segments.py\" --cwd \"{cwd}\"",
        ))
    if deep_graph_recommended:
        actions.append(action(
            "consider_graphify",
            "info",
            "thread size crossed the deep graph threshold",
            f"Use $graphify on \"{graphify_corpus}\" when conceptual navigation is worth the cost.",
        ))

    result = {
        "ok": not any(a["severity"] in {"critical", "warning"} for a in actions),
        "cwd": str(cwd),
        "rollout": {
            "path": str(rollout),
            "size": rollout_stat.st_size,
            "message_count": current_message_count,
            "last_message_line": last_line,
        },
        "anchors": {
            "path": str(anchors),
            "exists": anchors.exists(),
            "count": current_anchor_count,
            "sha256": current_anchor_sha,
        },
        "index": {
            "dir": str(index_dir),
            "manifest": str(manifest_path),
            "exists": bool(manifest),
            "stale": index_stale,
            "reasons": index_reasons,
            "indexed_message_count": indexed_messages,
            "indexed_last_message_line": indexed_last_line,
            "current_last_message_line": last_line,
            "message_delta": message_delta,
            "byte_delta": byte_delta,
            "rag": rag_manifest,
        },
        "clean_source": {
            "dir": str(clean_source_dir),
            "manifest": str(clean_manifest_path),
            "exists": bool(clean_manifest),
            "stale": clean_source_stale,
            "reasons": clean_reasons,
            "message_count": int(clean_manifest.get("message_count") or 0) if clean_manifest else 0,
            "turn_count": int(clean_manifest.get("turn_count") or 0) if clean_manifest else 0,
            "byte_delta": clean_byte_delta,
        },
        "checkpoint": {
            "state": str(checkpoint_state),
            "due": checkpoint_due,
            "last_checked_message_count": checked_count,
            "last_captured_message_count": captured_count,
            "message_delta": checkpoint_delta,
        },
        "graphify": {
            "corpus": str(graphify_corpus),
            "exists": graphify_corpus.exists(),
            "stale": graphify_stale,
            "reasons": graphify_reasons,
            "deep_graph_recommended": deep_graph_recommended,
        },
        "segments": {
            "dir": str(segments_dir),
            "manifest": str(segments_manifest_path),
            "needed": segments_needed,
            "exists": bool(segments_manifest),
            "stale": segments_stale,
            "reasons": segments_reasons,
            "segment_count": int(segments_manifest.get("segment_count") or 0) if segments_manifest else 0,
            "message_delta": segments_message_delta,
            "byte_delta": segments_byte_delta,
        },
        "recommended_actions": actions,
    }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "needs maintenance"
        print(f"thread memory health: {status}")
        print(f"rollout: {rollout} ({rollout_stat.st_size} bytes, {current_message_count} messages)")
        if index_stale:
            print("index: stale")
        elif message_delta or byte_delta:
            print(f"index: fresh window ({message_delta} unindexed messages, {byte_delta} new bytes below threshold)")
        else:
            print("index: fresh")
        if rag_manifest:
            print(f"rag cache: {rag_manifest.get('chunk_count', 0)} chunks")
        print(f"clean source: {'stale' if clean_source_stale else 'fresh'}")
        if segments_manifest:
            print(f"segments: {'stale' if segments_stale else 'fresh'} ({result['segments']['segment_count']} shards)")
        elif segments_needed:
            print("segments: missing")
        else:
            print("segments: not needed yet")
        print(f"checkpoint: {'due' if checkpoint_due else 'not due'}")
        print(f"graphify corpus: {'stale' if graphify_stale else 'fresh'}")
        if actions:
            print("\nrecommended actions:")
            for item in actions:
                print(f"- {item['id']} [{item['severity']}]: {item['reason']}")

    if args.exit_code and actions:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
