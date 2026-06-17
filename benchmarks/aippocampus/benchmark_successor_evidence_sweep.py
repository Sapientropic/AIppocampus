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


def _issue_closeout_action(
    *,
    issue: int,
    manifest_closeout_allowed: bool,
    github_state_checked: bool,
) -> dict[str, object]:
    if not github_state_checked:
        return {
            "issue": issue,
            "manifest_decision": (
                "closeout_allowed"
                if manifest_closeout_allowed
                else "closeout_blocked"
            ),
            "live_state_checked": False,
            "issue_closeout_action_allowed": False,
            "next_action": "verify_live_issue_before_closeout",
            "command": f"gh issue view {issue} --json state,body,comments",
        }
    return {
        "issue": issue,
        "manifest_decision": (
            "closeout_allowed" if manifest_closeout_allowed else "closeout_blocked"
        ),
        "live_state_checked": True,
        "issue_closeout_action_allowed": manifest_closeout_allowed,
        "next_action": (
            "comment_closeout_evidence_after_human_review"
            if manifest_closeout_allowed
            else "keep_issue_open_and_update_blocker_path"
        ),
        "command": f"gh issue view {issue} --json state,body,comments",
    }


def add_issue_actions(report: dict[str, object]) -> dict[str, object]:
    coverage = report.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    github_state_checked = bool(coverage.get("github_state_checked"))
    issue_actions: list[dict[str, object]] = []
    rows = report.get("issues")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        issue = int(row.get("issue") or 0)
        manifest_closeout_allowed = bool(row.get("closeout_allowed"))
        action = _issue_closeout_action(
            issue=issue,
            manifest_closeout_allowed=manifest_closeout_allowed,
            github_state_checked=github_state_checked,
        )
        row["manifest_closeout_allowed"] = manifest_closeout_allowed
        row["closeout_allowed_scope"] = "manifest_only"
        row["live_state_checked"] = github_state_checked
        row["issue_closeout_action_allowed"] = action["issue_closeout_action_allowed"]
        row["next_action"] = action["next_action"]
        row["command"] = action["command"]
        issue_actions.append(action)
    report["issue_actions"] = issue_actions
    report["closeout_action_boundary"] = {
        "manifest_closeout_allowed_is_not_live_issue_closeout": True,
        "github_state_checked": github_state_checked,
        "required_before_closing_issue": (
            "run per-issue live verification command"
            if not github_state_checked
            else "human-review verified live state and closeout evidence"
        ),
    }
    return report


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
    add_issue_actions(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
