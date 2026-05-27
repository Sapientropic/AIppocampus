#!/usr/bin/env python3
"""Locate the Codex Desktop rollout JSONL for a workspace cwd."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aippocampuslib import (  # noqa: E402
    codex_home,
    locate_rollout,
    norm_path,
    public_session_meta,
    read_session_meta,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd(), help="Workspace cwd to match.")
    parser.add_argument("--codex-home", default=str(codex_home()))
    parser.add_argument(
        "--latest", action="store_true", help="Return latest rollout if no cwd match."
    )
    args = parser.parse_args()

    home = Path(args.codex_home)
    try:
        path = locate_rollout(args.cwd, home, latest=args.latest)
    except FileNotFoundError:
        print(
            json.dumps(
                {"error": "no rollout found", "cwd": args.cwd, "codex_home": str(home)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    meta = read_session_meta(path)
    matched_cwd = bool(meta and meta.get("cwd") and norm_path(meta["cwd"]) == norm_path(args.cwd))
    payload = {
        "path": str(path),
        "size": path.stat().st_size,
        "session_meta": public_session_meta(meta),
    }
    if not matched_cwd:
        payload["matched_cwd"] = False
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
