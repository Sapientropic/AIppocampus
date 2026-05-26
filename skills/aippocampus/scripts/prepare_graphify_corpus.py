#!/usr/bin/env python3
"""Prepare a Graphify-ready corpus from a Codex thread-memory index."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from aippocampuslib import file_sha256, now_utc


SCRIPT_DIR = Path(__file__).resolve().parent
MARKER = ".thread-memory-graphify-corpus"


def rel_to_cwd(path: Path, cwd: Path) -> str:
    try:
        return str(path.resolve().relative_to(cwd.resolve()))
    except ValueError:
        return str(path.resolve())


def run_build_index(cwd: Path, index_dir: Path, anchors: Path) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_index.py"),
        "--cwd",
        str(cwd),
        "--output-dir",
        str(index_dir),
        "--anchors",
        str(anchors),
        "--json",
    ]
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def reset_output_dir(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)
        return
    marker = path / MARKER
    if marker.exists():
        shutil.rmtree(path)
        path.mkdir(parents=True)
        return
    if any(path.iterdir()):
        raise FileExistsError(
            f"refusing to replace non-managed output directory: {path}. "
            f"Delete it manually or choose a different --output."
        )
    path.mkdir(parents=True, exist_ok=True)


def read_messages(path: Path) -> list[dict]:
    messages = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))
    return messages


def render_message(msg: dict) -> str:
    phase = msg.get("phase") or ""
    turn = msg.get("turn_index")
    suffix = []
    if phase:
        suffix.append(f"phase {phase}")
    if turn is not None:
        suffix.append(f"turn {turn}")
    title = (
        f"## Message {msg.get('id', '?')} | line {msg.get('line')} | "
        f"{msg.get('timestamp')} | {msg.get('role')} / {msg.get('kind')}"
        f"{' | ' + ' | '.join(suffix) if suffix else ''}"
    )
    return f"{title}\n\n{msg.get('text', '').rstrip()}\n\n"


def write_message_chunks(messages: list[dict], output_dir: Path, max_chars: int) -> list[Path]:
    chunks_dir = output_dir / "messages"
    chunks_dir.mkdir(parents=True)
    written: list[Path] = []
    current: list[str] = []
    current_chars = 0
    chunk_no = 1

    def flush() -> None:
        nonlocal current, current_chars, chunk_no
        if not current:
            return
        path = chunks_dir / f"messages-{chunk_no:04d}.md"
        header = [
            "# Thread Messages",
            "",
            "Generated from normalized Codex rollout messages.",
            "Each message keeps the original rollout line so future agents can recover provenance.",
            "",
        ]
        path.write_text("\n".join(header) + "".join(current), encoding="utf-8", newline="\n")
        written.append(path)
        current = []
        current_chars = 0
        chunk_no += 1

    for idx, msg in enumerate(messages, start=1):
        msg = dict(msg)
        msg["id"] = idx
        rendered = render_message(msg)
        if current and current_chars + len(rendered) > max_chars:
            flush()
        current.append(rendered)
        current_chars += len(rendered)
    flush()
    return written


def write_readme(path: Path, manifest: dict, files: list[Path], cwd: Path) -> None:
    lines = [
        "# Thread Memory Graphify Corpus",
        "",
        "This folder is prepared by `$aippocampus` so `$graphify` can build a deeper reusable graph when needed.",
        "",
        "It is intentionally separate from `.aippocampus/graph.json`: that file is a lightweight anchor graph; this corpus is input for a fuller Graphify pass.",
        "",
        "## Contents",
        "",
        f"- Source cwd: {manifest.get('cwd')}",
        f"- Source rollout: {manifest.get('source_rollout')}",
        f"- Message count: {manifest.get('message_count')}",
        f"- Anchor count: {manifest.get('anchor_count')}",
        f"- Created: {now_utc()}",
        "",
        "## Suggested Commands",
        "",
        "```powershell",
        "$runtime = python \"$env:CODEX_HOME\\skills\\graphify\\scripts\\ensure_graphify.py\" | ConvertFrom-Json",
        "& $runtime.python \"$env:CODEX_HOME\\skills\\graphify\\scripts\\detect_corpus.py\" \"$PWD\\.aippocampus\\graphify-corpus\"",
        "# Then use the Graphify skill on this folder when a deep graph/report is worth the extra cost.",
        "```",
        "",
        "## Files",
        "",
    ]
    for file in files:
        lines.append(f"- `{rel_to_cwd(file, cwd)}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--index-dir", default=".aippocampus")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--output", default=".aippocampus/graphify-corpus")
    parser.add_argument("--max-chars-per-chunk", type=int, default=60000)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    index_dir = Path(args.index_dir)
    if not index_dir.is_absolute():
        index_dir = cwd / index_dir
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = cwd / output_dir

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    if not manifest_path.exists() or not messages_path.exists():
        manifest = run_build_index(cwd, index_dir, anchors)
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    reset_output_dir(output_dir)
    (output_dir / MARKER).write_text(now_utc() + "\n", encoding="utf-8")

    files: list[Path] = []
    for source, name in [
        (anchors, "thread-anchors.md"),
        (manifest_path, "thread-index-manifest.json"),
        (index_dir / "graph.json", "thread-anchor-graph.json"),
    ]:
        if source.exists():
            target = output_dir / name
            shutil.copy2(source, target)
            files.append(target)

    messages = read_messages(messages_path)
    files.extend(write_message_chunks(messages, output_dir, args.max_chars_per_chunk))

    corpus_manifest = {
        "schema_version": 1,
        "created_at": now_utc(),
        "cwd": str(cwd),
        "source_index_manifest": str(manifest_path),
        "source_index_manifest_sha256": file_sha256(manifest_path),
        "message_count": len(messages),
        "anchor_count": manifest.get("anchor_count"),
        "chunk_count": len([p for p in files if p.name.startswith("messages-")]),
    }
    corpus_manifest_path = output_dir / "corpus_manifest.json"
    corpus_manifest_path.write_text(
        json.dumps(corpus_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    files.append(corpus_manifest_path)

    readme = output_dir / "README.md"
    write_readme(readme, manifest, files, cwd)
    files.insert(0, readme)

    result = {
        "graphify_corpus": str(output_dir),
        "message_count": len(messages),
        "chunk_count": corpus_manifest["chunk_count"],
        "files": [str(p) for p in files],
    }
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"graphify corpus: {output_dir}")
        print(f"messages: {len(messages)}")
        print(f"chunks: {result['chunk_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
