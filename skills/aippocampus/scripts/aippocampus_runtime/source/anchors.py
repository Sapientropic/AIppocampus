#!/usr/bin/env python3
"""Append a concise memory anchor to thread-anchors.md in the current workspace."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="thread-anchors.md")
    parser.add_argument("--title", required=True)
    parser.add_argument("--keywords", default="")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--quote", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args()

    path = Path(args.file)
    created = not path.exists()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
            f"## {args.title}",
            f"- Date: {now}",
        ]
    )
    if args.keywords:
        lines.append(f"- Keywords: {args.keywords}")
    for note in args.note:
        lines.append(f"- Note: {note}")
    for quote in args.quote:
        lines.append(f"- Preserved phrase: {quote}")
    for source in args.source:
        lines.append(f"- Source: {source}")
    lines.append("")

    prefix = ""
    if path.exists() and path.stat().st_size > 0:
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n\n"):
            prefix = "\n" if existing.endswith("\n") else "\n\n"

    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(prefix + "\n".join(lines))
    print(str(path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
