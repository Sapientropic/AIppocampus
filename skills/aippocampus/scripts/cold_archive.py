#!/usr/bin/env python3
"""Create a non-destructive cold archive for a Codex thread rollout."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
from pathlib import Path

from retention_report import build_report, markdown_report, human_bytes
from aippocampuslib import (
    codex_home,
    default_thread_cold_archive_dir,
    default_thread_index_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    read_session_meta,
    resolve_artifact_path,
)


def slugify(value: str, fallback: str = "thread") -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return value[:96] or fallback


def gzip_copy(source: Path, target: Path, *, compresslevel: int = 6) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, gzip.open(target, "wb", compresslevel=compresslevel) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)


def copy_if_exists(source: Path, target: Path) -> str | None:
    if not source.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--index-dir", default=None, help="Defaults to the CODEX_HOME global thread store.")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--output-dir", default=None, help="Defaults to the global thread store's cold-archives directory.")
    parser.add_argument("--compresslevel", type=int, default=6)
    parser.add_argument("--include-normalized-messages", action="store_true", default=True)
    parser.add_argument("--no-normalized-messages", action="store_false", dest="include_normalized_messages")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    index_dir = resolve_artifact_path(args.index_dir, cwd, default_thread_index_dir(cwd, rollout))
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    output_dir = resolve_artifact_path(args.output_dir, cwd, default_thread_cold_archive_dir(cwd, rollout))

    meta = read_session_meta(rollout) or {}
    session_id = slugify(str(meta.get("id") or rollout.stem), fallback=rollout.stem)
    archive_dir = output_dir / f"{session_id}-{now_utc().replace(':', '').replace('-', '')}"
    archive_dir.mkdir(parents=True, exist_ok=False)

    report = build_report(cwd, rollout, index_dir=index_dir, anchors=anchors, top=12, hash_rollout=True)
    (archive_dir / "retention_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (archive_dir / "retention_report.md").write_text(markdown_report(report), encoding="utf-8")

    raw_gz = archive_dir / "raw_rollout.jsonl.gz"
    gzip_copy(rollout, raw_gz, compresslevel=args.compresslevel)

    files: dict[str, str | None] = {
        "raw_rollout_gzip": str(raw_gz),
        "retention_report_json": str(archive_dir / "retention_report.json"),
        "retention_report_markdown": str(archive_dir / "retention_report.md"),
        "thread_anchors": copy_if_exists(anchors, archive_dir / "thread-anchors.md"),
        "index_manifest": copy_if_exists(index_dir / "manifest.json", archive_dir / "index_manifest.json"),
        "anchor_graph": copy_if_exists(index_dir / "graph.json", archive_dir / "graph.json"),
        "segments_manifest": copy_if_exists(index_dir / "segments" / "manifest.json", archive_dir / "segments_manifest.json"),
        "graphify_corpus_manifest": copy_if_exists(index_dir / "graphify-corpus" / "corpus_manifest.json", archive_dir / "graphify_corpus_manifest.json"),
    }

    if args.include_normalized_messages:
        messages = index_dir / "messages.jsonl"
        if messages.exists():
            messages_gz = archive_dir / "messages.jsonl.gz"
            gzip_copy(messages, messages_gz, compresslevel=args.compresslevel)
            files["normalized_messages_gzip"] = str(messages_gz)

    rollout_size = rollout.stat().st_size
    raw_gz_size = raw_gz.stat().st_size
    manifest = {
        "schema_version": 1,
        "created_at": now_utc(),
        "cwd": str(cwd),
        "source_rollout": str(rollout),
        "source_rollout_size": rollout_size,
        "source_rollout_sha256": report["rollout"]["sha256"],
        "archive_dir": str(archive_dir),
        "archive_policy": {
            "non_destructive": True,
            "live_rollout_deleted": False,
            "live_rollout_rewritten": False,
            "why": "The active Codex Desktop rollout is app-owned session state; this archive copies and compresses it but does not mutate it.",
        },
        "compression": {
            "format": "gzip",
            "compresslevel": args.compresslevel,
            "raw_gzip_size": raw_gz_size,
            "raw_gzip_sha256": file_sha256(raw_gz),
            "raw_gzip_human_size": human_bytes(raw_gz_size),
            "ratio": round(raw_gz_size / rollout_size, 4) if rollout_size else None,
            "saved_bytes_vs_raw": max(0, rollout_size - raw_gz_size),
        },
        "files": files,
        "next_steps": [
            "Review retention_report.md before deleting or moving any live files.",
            "If UI lag is the problem, prefer moving day-to-day work to a fresh thread and recalling this archive via registry/segments.",
            "Only remove generated indexes or old screenshots after confirming the raw rollout, anchors, and this cold archive exist.",
        ],
    }
    (archive_dir / "cold_archive_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"cold archive: {archive_dir}")
        print(f"raw rollout: {human_bytes(rollout_size)}")
        print(f"gzip copy: {human_bytes(raw_gz_size)} (ratio {manifest['compression']['ratio']})")
        print("live rollout: not modified")
        print(f"report: {archive_dir / 'retention_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
