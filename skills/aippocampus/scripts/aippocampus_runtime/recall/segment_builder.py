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

from aippocampus_runtime.artifacts.publish import artifact_lease
from aippocampus_runtime.core import (
    codex_home,
    default_thread_segments_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    parse_anchor_file,
    public_session_meta,
    read_session_meta,
    resolve_artifact_path,
)
from aippocampus_runtime.recall.index_builder import make_sqlite
from aippocampus_runtime.source.rollout import normalize_rollout

DEFAULT_SEGMENT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_MESSAGES = 1200
DEFAULT_REBUILD_LEASE_STALE_SECONDS = 6 * 60 * 60
REBUILD_LEASE_NAME = ".rebuild.lock"
SEGMENTS_POINTER_NAME = "segments.pointer.json"
SEGMENTS_GENERATIONS_DIR = "generations"
TURN_BOUNDARY_POLICY = "bounded_complete_turn"
TURN_BOUNDARY_PARTIAL_POLICY = "forced_partial_turn"
TURN_BOUNDARY_PARTIAL_REASON = "turn_exceeds_bounded_overshoot"
TURN_BOUNDARY_OVERSHOOT_MULTIPLIER = 2


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
    max_turn_span = max(1, int(segment_bytes)) * TURN_BOUNDARY_OVERSHOOT_MULTIPLIER
    max_turn_messages = max(1, int(max_messages)) * TURN_BOUNDARY_OVERSHOOT_MULTIPLIER

    def turn_index(message: dict | None) -> int | None:
        if not isinstance(message, dict):
            return None
        value = message.get("turn_index")
        return value if isinstance(value, int) else None

    def same_turn(left: dict | None, right: dict | None) -> bool:
        left_turn = turn_index(left)
        right_turn = turn_index(right)
        return left_turn is not None and left_turn == right_turn

    def flush() -> None:
        nonlocal current, start_offset, last_end, start_global_id
        if not current:
            return
        first_global_id = int(current[0]["global_id"])
        last_global_id = int(current[-1]["global_id"])
        previous_message = messages[first_global_id - 2] if first_global_id > 1 else None
        next_message = messages[last_global_id] if last_global_id < len(messages) else None
        starts_partial = same_turn(previous_message, current[0])
        ends_partial = same_turn(current[-1], next_message)
        partial_turn_indices = sorted(
            {
                turn
                for turn in (turn_index(current[0]), turn_index(current[-1]))
                if turn is not None
                and (
                    (starts_partial and turn == turn_index(current[0]))
                    or (ends_partial and turn == turn_index(current[-1]))
                )
            }
        )
        raw_span_bytes = max(0, last_end - start_offset)
        partial_reason = TURN_BOUNDARY_PARTIAL_REASON if partial_turn_indices else None
        groups.append(
            {
                "start_global_id": start_global_id,
                "end_global_id": start_global_id + len(current) - 1,
                "start_line": current[0]["line"],
                "end_line": current[-1]["line"],
                "start_offset": start_offset,
                "end_offset": last_end,
                "raw_span_bytes": raw_span_bytes,
                "start_turn_index": turn_index(current[0]),
                "end_turn_index": turn_index(current[-1]),
                "starts_with_partial_turn": starts_partial,
                "ends_with_partial_turn": ends_partial,
                "partial_turn_indices": partial_turn_indices,
                "turn_boundary_policy": (
                    TURN_BOUNDARY_PARTIAL_POLICY if partial_turn_indices else TURN_BOUNDARY_POLICY
                ),
                "partial_turn_reason": partial_reason,
                "budget_overshoot_bytes": max(0, raw_span_bytes - int(segment_bytes)),
                "budget_overshoot_messages": max(0, len(current) - int(max_messages)),
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
        budget_exceeded = current and (
            proposed_span >= int(segment_bytes) or len(current) >= int(max_messages)
        )
        allow_turn_overshoot = (
            budget_exceeded
            and same_turn(current[-1], message)
            and proposed_span <= max_turn_span
            and len(current) + 1 <= max_turn_messages
        )
        if budget_exceeded and not allow_turn_overshoot:
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


def new_generation_dir(output_dir: Path) -> Path:
    generations_dir = output_dir / SEGMENTS_GENERATIONS_DIR
    generations_dir.mkdir(parents=True, exist_ok=True)
    while True:
        generation_id = f"gen_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}_{os.getpid()}_{time.time_ns()}"
        generation_dir = generations_dir / generation_id
        try:
            generation_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return generation_dir


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


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _pointer_value(pointer_path: Path, path: Path) -> str:
    try:
        return path.relative_to(pointer_path.parent).as_posix()
    except ValueError:
        return str(path)


def _load_segments_pointer(pointer_path: Path) -> dict:
    if not pointer_path.exists():
        return {}
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _candidate_from_pointer(pointer_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = pointer_path.parent / candidate
    return candidate


def _first_existing_manifest_candidate(pointer_path: Path, pointer: dict) -> Path | None:
    for key in ("current", "last_known_good"):
        candidate = _candidate_from_pointer(pointer_path, pointer.get(key))
        if candidate and candidate.is_file():
            return candidate
    return None


def _generation_id_for_manifest(pointer_path: Path, manifest_path: Path | None) -> str | None:
    if manifest_path is None:
        return None
    try:
        relative = manifest_path.relative_to(pointer_path.parent)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == SEGMENTS_GENERATIONS_DIR and parts[1].startswith("gen_"):
        return parts[1]
    return None


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


def install_staged_segments(
    staging_dir: Path,
    output_dir: Path,
    generation_dir: Path,
    manifest: dict,
) -> Path:
    """Publish a complete segment generation without breaking last-known-good data.

    Build failures must not delete segment dirs referenced by an existing
    manifest or pointer. We therefore write into a hidden staging dir first,
    move the new shards into a fresh generation, write the compatibility
    manifest, and only then atomically swing `segments.pointer.json`.
    """

    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    generation_dir.mkdir(parents=True, exist_ok=True)
    compatibility_manifest_path = output_dir / "manifest.json"
    pointer_path = output_dir / SEGMENTS_POINTER_NAME
    previous_pointer = _load_segments_pointer(pointer_path)
    previous_good = _first_existing_manifest_candidate(pointer_path, previous_pointer)
    had_compatibility_manifest = compatibility_manifest_path.exists()
    compatibility_manifest_bytes = (
        compatibility_manifest_path.read_bytes() if had_compatibility_manifest else b""
    )
    staged_names = [
        child.name
        for child in staging_dir.iterdir()
        if child.is_dir() and child.name.startswith("seg-")
    ]

    try:
        for name in staged_names:
            shutil.move(str(staging_dir / name), str(generation_dir / name))

        generation_manifest_path = generation_dir / "manifest.json"
        generation_manifest = dict(manifest)
        generation_manifest["generation_id"] = generation_dir.name
        generation_manifest["generation_layout"] = (
            f"{SEGMENTS_GENERATIONS_DIR}/<generation>/seg-*"
        )
        _write_json_atomic(generation_manifest_path, generation_manifest)
        _write_json_atomic(compatibility_manifest_path, generation_manifest)

        last_known_good = previous_good or generation_manifest_path
        last_known_good_generation = _generation_id_for_manifest(pointer_path, last_known_good)
        if last_known_good == generation_manifest_path:
            last_known_good_generation = generation_dir.name
        pointer = {
            "schema_version": 1,
            "kind": "aippocampus_segments_pointer",
            "created_at": generation_manifest.get("created_at"),
            "updated_at": now_utc(),
            "generation_layout": f"{SEGMENTS_GENERATIONS_DIR}/<generation>/manifest.json",
            "current_generation": generation_dir.name,
            "last_known_good_generation": last_known_good_generation,
            "compatibility_path": "manifest.json",
            "stable": _pointer_value(pointer_path, compatibility_manifest_path),
            "current": _pointer_value(pointer_path, generation_manifest_path),
            "last_known_good": _pointer_value(pointer_path, last_known_good),
            "source_rollout_size": generation_manifest.get("source_rollout_size"),
            "source_rollout_mtime": generation_manifest.get("source_rollout_mtime"),
            "source_rollout_sha256": generation_manifest.get("source_rollout_sha256"),
            "segment_count": generation_manifest.get("segment_count"),
            "publish_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "allowed_volatile_fields": [
                "created_at",
                "updated_at",
                "publish_latency_ms",
                "source_rollout_mtime",
            ],
        }
        _write_json_atomic(pointer_path, pointer)
    except Exception:
        if had_compatibility_manifest:
            compatibility_manifest_path.write_bytes(compatibility_manifest_bytes)
        else:
            with contextlib.suppress(FileNotFoundError):
                compatibility_manifest_path.unlink()
        shutil.rmtree(generation_dir, ignore_errors=True)
        raise

    return generation_manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the AIppocampus registry thread store; pass .aippocampus/segments for project-local output.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--include-tools", action="store_true")
    parser.add_argument("--segment-bytes", type=int, default=DEFAULT_SEGMENT_BYTES)
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    parser.add_argument("--no-rag-cache", action="store_true")
    parser.add_argument("--rag-chunk-chars", type=int, default=2800)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

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
        generation_dir = new_generation_dir(output_dir)
        staging_dir = new_rebuild_dir(output_dir)
        publish_complete = False
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
                final_segment_dir = generation_dir / segment_id
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
                        "start_turn_index": group.get("start_turn_index"),
                        "end_turn_index": group.get("end_turn_index"),
                        "starts_with_partial_turn": bool(
                            group.get("starts_with_partial_turn")
                        ),
                        "ends_with_partial_turn": bool(group.get("ends_with_partial_turn")),
                        "partial_turn_indices": list(group.get("partial_turn_indices") or []),
                        "turn_boundary_policy": group.get("turn_boundary_policy"),
                        "partial_turn_reason": group.get("partial_turn_reason"),
                        "budget_overshoot_bytes": int(group.get("budget_overshoot_bytes") or 0),
                        "budget_overshoot_messages": int(
                            group.get("budget_overshoot_messages") or 0
                        ),
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
                "source_rollout_sha256": file_sha256(rollout),
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
            manifest_path = install_staged_segments(
                staging_dir,
                output_dir,
                generation_dir,
                manifest,
            )
            publish_complete = True
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
            if not publish_complete:
                shutil.rmtree(generation_dir, ignore_errors=True)

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
