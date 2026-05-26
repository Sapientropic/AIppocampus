#!/usr/bin/env python3
"""Export a portable bundle for a Codex Desktop thread."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from aippocampuslib import codex_home, default_thread_index_dir, locate_rollout, read_session_meta, resolve_artifact_path


SCRIPT_DIR = Path(__file__).resolve().parent


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_build_index(cwd: Path, rollout: Path, index_dir: Path, anchors: Path, hash_source: bool) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_index.py"),
        "--cwd",
        str(cwd),
        "--rollout",
        str(rollout),
        "--output-dir",
        str(index_dir),
        "--anchors",
        str(anchors),
        "--json",
    ]
    if hash_source:
        cmd.append("--hash-source")
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def write_handoff(path: Path, manifest: dict, include_raw: bool) -> None:
    lines = [
        "# AIppocampus Bundle",
        "",
        "Use `$aippocampus` in a Codex thread to import or search this bundle.",
        "",
        f"- Created: {manifest.get('created_at')}",
        f"- Source cwd: {manifest.get('cwd')}",
        f"- Message count: {manifest.get('message_count')}",
        f"- Anchor count: {manifest.get('anchor_count')}",
        f"- Graph nodes: {manifest.get('graph', {}).get('node_count')}",
        f"- Raw rollout included: {'yes' if include_raw else 'no'}",
        "",
        "Suggested recovery commands:",
        "",
        "```powershell",
        "python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\import_bundle.py\" \"<this zip>\"",
        "python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\search_rollout.py\" \"keyword\" --index \"<extracted>\\source_index.sqlite\"",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--output")
    parser.add_argument("--work-dir", default=None, help="Defaults to the global thread store's index directory.")
    parser.add_argument("--no-raw", action="store_true", help="Do not include raw rollout JSONL.")
    parser.add_argument("--hash-source", action="store_true")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    work_dir = resolve_artifact_path(args.work_dir, cwd, default_thread_index_dir(cwd, rollout))
    work_dir.mkdir(parents=True, exist_ok=True)
    bundle_root = work_dir / "bundle"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    index_dir = bundle_root / "index"
    manifest = run_build_index(cwd, rollout, index_dir, anchors, args.hash_source)
    meta = read_session_meta(rollout) or {}
    bundle_name = args.output or f"aippocampus-bundle-{meta.get('id', 'thread')}-{timestamp_slug()}.zip"
    output = Path(bundle_name)
    if not output.is_absolute():
        output = cwd / output

    if anchors.exists():
        shutil.copy2(anchors, bundle_root / "thread-anchors.md")
    if not args.no_raw:
        shutil.copy2(rollout, bundle_root / "rollout.jsonl")

    write_handoff(bundle_root / "handoff.md", manifest, include_raw=not args.no_raw)

    bundle_manifest = dict(manifest)
    bundle_manifest["bundle_schema_version"] = 1
    bundle_manifest["raw_rollout_included"] = not args.no_raw
    bundle_manifest["bundle_files"] = {
        "handoff": "handoff.md",
        "anchors": "thread-anchors.md" if anchors.exists() else None,
        "raw_rollout": "rollout.jsonl" if not args.no_raw else None,
        "index_dir": "index",
    }
    (bundle_root / "bundle_manifest.json").write_text(
        json.dumps(bundle_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in bundle_root.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(bundle_root))

    print(json.dumps({"bundle": str(output), "size": output.stat().st_size, "source_rollout": str(rollout)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
