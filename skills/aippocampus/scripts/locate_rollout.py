#!/usr/bin/env python3
"""Locate the Codex Desktop rollout JSONL for a workspace cwd."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aippocampuslib import public_session_meta  # noqa: E402


def norm(path: str) -> str:
    return str(Path(path).resolve()).casefold()


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


def iter_rollouts(home: Path):
    sessions = home / "sessions"
    if not sessions.exists():
        return
    yield from sessions.rglob("rollout-*.jsonl")


def read_session_meta(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        item = json.loads(first)
        if item.get("type") == "session_meta":
            return item.get("payload", {})
    except Exception:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd(), help="Workspace cwd to match.")
    parser.add_argument("--codex-home", default=str(codex_home()))
    parser.add_argument("--latest", action="store_true", help="Return latest rollout if no cwd match.")
    args = parser.parse_args()

    home = Path(args.codex_home)
    target = norm(args.cwd)
    matches = []
    latest = None

    for path in iter_rollouts(home) or []:
        try:
            stat = path.stat()
        except OSError:
            continue
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
        meta = read_session_meta(path)
        if not meta:
            continue
        cwd = meta.get("cwd")
        if cwd and norm(cwd) == target:
            matches.append((stat.st_mtime, path, meta, stat.st_size))

    if matches:
        matches.sort(reverse=True, key=lambda x: x[0])
        _, path, meta, size = matches[0]
        print(json.dumps({"path": str(path), "size": size, "session_meta": public_session_meta(meta)}, ensure_ascii=False, indent=2))
        return 0

    if args.latest and latest:
        _, path = latest
        meta = read_session_meta(path)
        print(json.dumps({"path": str(path), "size": path.stat().st_size, "session_meta": public_session_meta(meta), "matched_cwd": False}, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps({"error": "no rollout found", "cwd": args.cwd, "codex_home": str(home)}, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
