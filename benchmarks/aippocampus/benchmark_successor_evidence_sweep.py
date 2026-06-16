#!/usr/bin/env python3
"""Emit the proxy-successor evidence sweep report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _paths

_paths.ensure_paths()

from aippocampus_runtime.ops.successor_evidence import (
    build_successor_evidence_sweep_report,
    load_github_successor_issue_state,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--github-live",
        action="store_true",
        help="Validate the successor inventory against live GitHub issue state via gh.",
    )
    parser.add_argument("--repo", default="Sapientropic/AIppocampus")
    args = parser.parse_args(argv)
    issue_state = (
        load_github_successor_issue_state(repo=args.repo)
        if args.github_live
        else None
    )
    report = build_successor_evidence_sweep_report(
        Path(args.repo_root),
        issue_state=issue_state,
        github_state_checked=args.github_live,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
