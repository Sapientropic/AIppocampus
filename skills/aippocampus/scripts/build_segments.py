#!/usr/bin/env python3
"""Build per-segment indexes for very large Codex rollout files.

The normal index remains the best default for small and medium threads. This
segmented layer exists for hundred-MB/GB rollout files where rebuilding or
querying one giant SQLite database becomes slow, fragile, or hard to refresh
incrementally.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import time
from pathlib import Path

from aippocampuslib import (
    codex_home,
    default_thread_segments_dir,
    file_sha256,
    locate_rollout,
    normalize_rollout,
    now_utc,
    parse_anchor_file,
    public_session_meta,
    read_session_meta,
    resolve_artifact_path,
)
from artifact_publish import artifact_lease
from build_index import make_sqlite

DEFAULT_SEGMENT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_MESSAGES = 1200
DEFAULT_REBUILD_LEASE_STALE_SECONDS = 6 * 60 * 60
REBUILD_LEASE_NAME = ".rebuild.lock"


def line_offsets(path: Path) -> tuple[dict[int, tuple[int, int]], int]:
    offsets: dict[int, tuple[int, int]] = {}
    pos = 0
    with path.open("rb") as f:
        for line_no, raw in enumerate(f, start=1):
            end = pos + len(raw)
            offsets[line_no] = (pos, end)
            pos = end
    return offsets, pos


def segment_groups(
    messages: list[dict],
    offsets: dict[int, tuple[int, int]],
    *,
    segment_bytes: int,
    max_messages: int,
) -> list[dict]:
    groups: list[dict] = []
    current: list[dict] = []
    start_offset = 0
    last_end = 0
    start_global_id = 1

    def flush() -> None:
        nonlocal current, start_offset, last_end, start_global_id
        if not current:
            return
        groups.append(
            {
                "start_global_id": start_global_id,
                "end_global_id": start_global_id + len(current) - 1,
                "start_line": current[0]["line"],
                "end_line": current[-1]["line"],
                "start_offset": start_offset,
                "end_offset": last_end,
                "raw_span_bytes": max(0, last_end - start_offset),
                "messages": current,
            }
        )
        start_global_id += len(current)
        current = []
        start_offset = 0
        last_end = 0

    for global_id, message in enumerate(messages, start=1):
        msg_start, msg_end = offsets.get(message["line"], (last_end, last_end))
        if not current:
            start_offset = msg_start
        proposed_span = max(0, msg_end - start_offset)
        if current and (proposed_span >= segment_bytes or len(current) >= max_messages):
            flush()
            start_offset = msg_start
        record = dict(message)
        record["global_id"] = global_id
        current.append(record)
        last_end = msg_end

    flush()
    return groups


def safe_clean_segment_dirs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        # Only remove directories created by this script. The segment manifest is
        # deliberately left until the new one is written so failed rebuilds do
        # not delete the last-known-good routing metadata.
        if child.is_dir() and child.name.startswith("seg-"):
            shutil.rmtree(child)


def new_rebuild_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rebuild_dir = output_dir / f".rebuild-{os.getpid()}-{int(time.time() * 1000)}"
    rebuild_dir.mkdir(parents=True, exist_ok=False)
    return rebuild_dir


def remap_staged_sqlite_status(status: dict, staging_dir: Path, final_dir: Path) -> dict:
    remapped = dict(status)
    publish = dict(remapped.get("publish") or {})

    def remap_path(value: object) -> object:
        if not isinstance(value, str) or not value:
            return value
        candidate = Path(value)
        if not candidate.is_absolute():
            return value
        try:
            relative = candidate.relative_to(staging_dir)
        except ValueError:
            return value
        return str(final_dir / relative)

    # Segment indexes are built in a hidden staging directory and then moved
    # into place. Keep status metadata pointed at the final segment directory so
    # future maintenance agents do not chase stale staging paths.
    for key in ("pointer", "stable", "current", "last_known_good"):
        publish[key] = remap_path(publish.get(key))
    remapped["publish"] = publish
    return remapped


@contextlib.contextmanager
def rebuild_lease(
    output_dir: Path, *, stale_after_seconds: int = DEFAULT_REBUILD_LEASE_STALE_SECONDS
):
    """Allow only one segment rebuild publisher per output directory.

    Windows can keep SQLite files locked while another process is still
    replacing segment dirs. The lease is deliberately a plain same-directory
    create-exclusive file so interrupted rebuilds are visible and stale locks
    can be recovered without relying on platform-specific file locking.
    """

    with artifact_lease(
        output_dir,
        REBUILD_LEASE_NAME,
        stale_after_seconds=stale_after_seconds,
    ) as lease_path:
        yield lease_path


def install_staged_segments(staging_dir: Path, output_dir: Path, manifest: dict) -> Path:
    """Publish a complete segment rebuild without breaking last-known-good data.

    Build failures must not delete the segment dirs referenced by the existing
    manifest. We therefore write into a hidden staging dir first, then move old
    `seg-*` dirs aside only after every new SQLite shard and the new manifest are
    ready. If the publish step fails, old dirs are restored before the exception
    escapes.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    stamp = f"{os.getpid()}-{int(time.time() * 1000)}"
    backup_dir = output_dir / f".previous-{stamp}"
    manifest_tmp = output_dir / f".manifest.json.tmp-{stamp}"
    staged_names = [
        child.name
        for child in staging_dir.iterdir()
        if child.is_dir() and child.name.startswith("seg-")
    ]

    try:
        old_segments = [
            child
            for child in output_dir.iterdir()
            if child.is_dir() and child.name.startswith("seg-")
        ]
        if old_segments:
            backup_dir.mkdir(parents=True, exist_ok=False)
        for child in old_segments:
            shutil.move(str(child), str(backup_dir / child.name))

        for name in staged_names:
            shutil.move(str(staging_dir / name), str(output_dir / name))

        manifest_tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest_tmp.replace(manifest_path)
    except Exception:
        for name in staged_names:
            published = output_dir / name
            if published.exists():
                shutil.rmtree(published)
        if backup_dir.exists():
            for child in backup_dir.iterdir():
                shutil.move(str(child), str(output_dir / child.name))
        raise
    finally:
        if manifest_tmp.exists():
            manifest_tmp.unlink()
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the CODEX_HOME global thread store; pass .aippocampus/segments for project-local output.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--include-tools", action="store_true")
    parser.add_argument("--segment-bytes", type=int, default=DEFAULT_SEGMENT_BYTES)
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    parser.add_argument("--no-rag-cache", action="store_true")
    parser.add_argument("--rag-chunk-chars", type=int, default=2800)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    output_dir = resolve_artifact_path(
        args.output_dir, cwd, default_thread_segments_dir(cwd, rollout)
    )
    anchor_path = Path(args.anchors)
    if not anchor_path.is_absolute():
        anchor_path = cwd / anchor_path

    if args.segment_bytes < 1024 * 1024:
        raise SystemExit("--segment-bytes must be at least 1 MiB")
    if args.max_messages < 50:
        raise SystemExit("--max-messages must be at least 50")

    with rebuild_lease(output_dir):
        staging_dir = new_rebuild_dir(output_dir)
        try:
            raw_meta = read_session_meta(rollout) or {}
            meta = public_session_meta(raw_meta)
            messages, turns = normalize_rollout(rollout, include_tools=args.include_tools)
            turns_by_id = {turn["id"]: turn for turn in turns}
            offsets, rollout_bytes = line_offsets(rollout)
            anchors = parse_anchor_file(anchor_path)
            groups = segment_groups(
                messages,
                offsets,
                segment_bytes=args.segment_bytes,
                max_messages=args.max_messages,
            )

            segment_entries: list[dict] = []
            for idx, group in enumerate(groups, start=1):
                segment_id = f"seg-{idx:04d}"
                build_segment_dir = staging_dir / segment_id
                final_segment_dir = output_dir / segment_id
                build_segment_dir.mkdir(parents=True, exist_ok=True)
                build_messages_path = build_segment_dir / "messages.jsonl"
                build_sqlite_path = build_segment_dir / "source_index.sqlite"
                final_messages_path = final_segment_dir / "messages.jsonl"
                final_sqlite_path = final_segment_dir / "source_index.sqlite"
                with build_messages_path.open("w", encoding="utf-8", newline="\n") as f:
                    for message in group["messages"]:
                        f.write(json.dumps(message, ensure_ascii=False) + "\n")
                segment_turn_ids = {
                    int(message["turn_index"])
                    for message in group["messages"]
                    if message.get("turn_index") is not None
                }
                segment_turns = [
                    turns_by_id[turn_id]
                    for turn_id in sorted(segment_turn_ids)
                    if turn_id in turns_by_id
                ]
                sqlite_status = make_sqlite(
                    build_sqlite_path,
                    group["messages"],
                    anchors,
                    segment_turns,
                    rag_cache=not args.no_rag_cache,
                    rag_chunk_chars=args.rag_chunk_chars,
                )
                sqlite_status = remap_staged_sqlite_status(
                    sqlite_status,
                    build_segment_dir,
                    final_segment_dir,
                )
                segment_entries.append(
                    {
                        "id": segment_id,
                        "dir": str(final_segment_dir),
                        "messages_jsonl": str(final_messages_path),
                        "sqlite": str(final_sqlite_path),
                        "start_global_id": group["start_global_id"],
                        "end_global_id": group["end_global_id"],
                        "start_line": group["start_line"],
                        "end_line": group["end_line"],
                        "start_offset": group["start_offset"],
                        "end_offset": group["end_offset"],
                        "raw_span_bytes": group["raw_span_bytes"],
                        "message_count": len(group["messages"]),
                        "sqlite_status": sqlite_status,
                    }
                )

            rollout_stat = rollout.stat()
            manifest = {
                "schema_version": 1,
                "created_at": now_utc(),
                "cwd": str(cwd),
                "artifact_scope": "global_thread_store"
                if args.output_dir is None
                else "explicit_output_dir",
                "source_rollout": str(rollout),
                "source_rollout_size": rollout_stat.st_size,
                "source_rollout_mtime": rollout_stat.st_mtime,
                "source_rollout_bytes_scanned": rollout_bytes,
                "anchor_file": str(anchor_path) if anchor_path.exists() else None,
                "anchor_mtime": anchor_path.stat().st_mtime if anchor_path.exists() else None,
                "anchor_sha256": file_sha256(anchor_path) if anchor_path.exists() else None,
                "include_tools": args.include_tools,
                "segment_bytes": args.segment_bytes,
                "max_messages": args.max_messages,
                "message_count": len(messages),
                "first_message_line": messages[0]["line"] if messages else None,
                "last_message_line": messages[-1]["line"] if messages else None,
                "turn_count": len(turns),
                "segment_count": len(segment_entries),
                "session_meta": meta,
                "segments": segment_entries,
            }
            manifest_path = install_staged_segments(staging_dir, output_dir, manifest)
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"segment manifest: {manifest_path.resolve()}")
        print(f"source rollout: {rollout} ({rollout_stat.st_size} bytes)")
        print(f"segments: {len(segment_entries)}")
        for item in segment_entries[:8]:
            print(
                f"- {item['id']}: messages {item['start_global_id']}-{item['end_global_id']} "
                f"| lines {item['start_line']}-{item['end_line']} "
                f"| {item['raw_span_bytes']} bytes"
            )
        if len(segment_entries) > 8:
            print(f"... {len(segment_entries) - 8} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
