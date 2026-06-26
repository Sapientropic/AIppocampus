#!/usr/bin/env python3
"""Create or append a concise checkpoint candidate from recent thread messages."""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    codex_home,
    compact_text,
    default_thread_checkpoint_state_path,
    default_thread_index_dir,
    now_utc,
    resolve_artifact_path,
)
from aippocampus_runtime.source.io_kernel import (
    load_json_dict,
    load_jsonl_dict_rows_with_line_field,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
KNOWN_TERMS = [
    "Graphify",
    "SQLite FTS",
    "aippocampus",
    "graphify-corpus",
    "外置海马体",
    "海马体",
    "长线程",
    "压缩",
    "锚点",
    "图谱",
    "AGI",
    "2028",
]


def run_build_index(cwd: Path, index_dir: Path, anchors: Path) -> None:
    cmd = [
        sys.executable,
        "-m", "aippocampus_runtime.recall.index_builder",
        "--cwd",
        str(cwd),
        "--output-dir",
        str(index_dir),
        "--anchors",
        str(anchors),
    ]
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)


def read_messages(path: Path) -> list[dict]:
    messages = []
    for item in load_jsonl_dict_rows_with_line_field(path, line_field="_source_line").rows:
        idx = item.pop("_source_line", None)
        item.setdefault("id", idx)
        messages.append(item)
    return messages


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    counts: collections.Counter[str] = collections.Counter()
    for term in KNOWN_TERMS:
        if term.casefold() in text.casefold():
            counts[term] += 5
    for match in re.findall(r"`([^`]{2,48})`", text):
        counts[match.strip()] += 3
    for match in re.findall(r"\b[A-Za-z][A-Za-z0-9_.:-]{3,}\b", text):
        if match.casefold() not in {"http", "https", "true", "false", "none", "null"}:
            counts[match] += 1
    for match in re.findall(
        r"[\u4e00-\u9fffA-Za-z0-9-]{0,16}(?:记忆|海马体|图谱|线程|压缩|锚点|索引|导出|导入|机制|飞升|机仆|对话|自我)[\u4e00-\u9fffA-Za-z0-9-]{0,16}",
        text,
    ):
        if 2 <= len(match) <= 36:
            counts[match] += 2
    return [key for key, _ in counts.most_common(limit)]


def append_anchor(path: Path, candidate: dict) -> None:
    created = not path.exists()
    lines = []
    if created:
        lines.extend(
            [
                "# Thread Anchors",
                "",
                "Concise index for recovering important context from this long Codex thread.",
                "",
            ]
        )
    lines.extend(
        [
            f"## {candidate['title']}",
            f"- Date: {candidate['date']}",
        ]
    )
    if candidate["keywords"]:
        lines.append(f"- Keywords: {','.join(candidate['keywords'])}")
    for note in candidate["notes"]:
        lines.append(f"- Note: {note}")
    for quote in candidate["quotes"]:
        lines.append(f"- Preserved phrase: {quote}")
    for source in candidate["sources"]:
        lines.append(f"- Source: {source}")
    lines.append("")

    prefix = ""
    if path.exists() and path.stat().st_size > 0:
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n\n"):
            prefix = "\n" if existing.endswith("\n") else "\n\n"

    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(prefix + "\n".join(lines))


def portable_source_path(path: Path, cwd: Path) -> str:
    """Return a source path suitable for anchors that may be exported later."""
    try:
        return path.resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return "$CODEX_HOME/" + path.resolve().relative_to(codex_home().resolve()).as_posix()
    except ValueError:
        # Keep anchors free of machine-specific absolute paths even when callers
        # point the index outside the workspace and outside CODEX_HOME.
        return path.name


def update_state(path: Path, candidate: dict, appended: bool, total_messages: int) -> None:
    old = load_json_dict(path).data
    state = dict(old)
    state.update(
        {
            "updated_at": now_utc(),
            "last_checked_message_count": total_messages,
            "last_checked_line": candidate["line_range"]["end"],
            "last_candidate": candidate,
        }
    )
    if appended:
        state["last_captured_message_count"] = total_messages
        state["last_captured_line"] = candidate["line_range"]["end"]
        state["last_captured_at"] = now_utc()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--index-dir", default=None, help="Defaults to the AIppocampus registry thread store."
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument(
        "--state", default=None, help="Defaults to the global thread store's checkpoint state."
    )
    parser.add_argument("--recent", type=int, default=24)
    parser.add_argument("--title")
    parser.add_argument("--keywords")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument(
        "--append", action="store_true", help="Append the candidate to thread-anchors.md."
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Use the existing messages.jsonl without rebuilding.",
    )
    parser.add_argument("--no-state", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    index_dir = resolve_artifact_path(args.index_dir, cwd, default_thread_index_dir(cwd))
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    state_path = resolve_artifact_path(args.state, cwd, default_thread_checkpoint_state_path(cwd))

    if not args.no_build:
        run_build_index(cwd, index_dir, anchors)

    messages_path = index_dir / "messages.jsonl"
    messages = read_messages(messages_path)
    recent = messages[-max(1, args.recent) :]
    if not recent:
        raise RuntimeError("no messages available for checkpoint")

    text = "\n".join(m.get("text", "") for m in recent)
    keywords = [x.strip() for x in (args.keywords or "").split(",") if x.strip()]
    if not keywords:
        keywords = extract_keywords(text)

    first_line = recent[0].get("line")
    last_line = recent[-1].get("line")
    title = args.title or f"Checkpoint {now_utc()[:16]} lines {first_line}-{last_line}"
    date = now_utc()[:10]

    user_snippets = [
        compact_text(m.get("text", ""), 220) for m in recent if m.get("role") == "user"
    ][-3:]
    notes = list(args.note)
    if not notes:
        notes.append(
            f"Candidate checkpoint generated from recent normalized messages, rollout lines {first_line}-{last_line}."
        )
        for snippet in user_snippets:
            notes.append(f"Recent user focus: {snippet}")

    quotes = user_snippets[:2]
    candidate: dict[str, Any] = {
        "title": title,
        "date": date,
        "keywords": keywords,
        "notes": notes,
        "quotes": quotes,
        "sources": [
            f"{portable_source_path(index_dir / 'messages.jsonl', cwd)} lines {first_line}-{last_line}",
        ],
        "line_range": {"start": first_line, "end": last_line},
        "message_count": len(recent),
        "total_message_count": len(messages),
    }

    if args.append:
        append_anchor(anchors, candidate)
    if not args.no_state:
        update_state(state_path, candidate, args.append, len(messages))

    result = {
        "appended": args.append,
        "anchor_file": str(anchors),
        "state": None if args.no_state else str(state_path),
        "candidate": candidate,
    }
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "appended" if args.append else "suggested"
        print(f"checkpoint {mode}: {candidate['title']}")
        print(f"keywords: {', '.join(keywords)}")
        for note in notes:
            print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
