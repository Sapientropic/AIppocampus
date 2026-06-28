"""Shared changed-file CLI helpers for debt tooling."""

from __future__ import annotations

import argparse
from pathlib import Path


def add_changed_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help=(
            "Mark a repo-relative file as part of the changed surface. Repeat to "
            "make helper, broad-exception, compact-field, and giant-function debt "
            "acceptance-bearing for touched files only."
        ),
    )
    parser.add_argument(
        "--changed-file-list",
        action="append",
        default=[],
        help="Read repo-relative changed files from a newline-delimited manifest.",
    )


def collect_changed_file_arguments(args: argparse.Namespace) -> list[str]:
    changed_files = list(getattr(args, "changed_file", None) or [])
    for manifest in getattr(args, "changed_file_list", None) or []:
        path = Path(manifest)
        if not path.is_file():
            continue
        changed_files.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return changed_files
