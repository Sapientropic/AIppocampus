#!/usr/bin/env python3
"""No-write smoke for progressive recall navigation arm comparison."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from repo_paths import ensure_repo_imports

ensure_repo_imports(Path(__file__))

from aippocampus_runtime.ops import (
    issue_route_quality,  # noqa: E402
    recall_navigation_comparison,  # noqa: E402
    recall_navigation_comparison_fixtures,  # noqa: E402
)


def _github_issue_payload(*, repo: str, issue: int) -> dict[str, object]:
    proc = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(issue),
            "--repo",
            repo,
            "--comments",
            "--json",
            "number,title,body,comments,url",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "number": issue,
            "title": "",
            "body": "",
            "comments": [],
            "url": "",
            "gh_error": proc.stderr.strip()[:240],
        }
    payload = json.loads(proc.stdout or "{}")
    return payload if isinstance(payload, dict) else {}


def _attach_live_github_route_quality(
    report: dict[str, object],
    *,
    repo: str,
    issue: int,
    parent_issue: int,
) -> None:
    payload = _github_issue_payload(repo=repo, issue=issue)
    live_quality = issue_route_quality.evaluate_same_thread_issue_comment_route_quality(
        payload,
        expected_issue_number=issue,
        expected_parent_issue_number=parent_issue,
        mode="live_github_public",
    )
    route = live_quality.get("route") if isinstance(live_quality.get("route"), dict) else {}
    precise = live_quality.get("agent_behavior") == "uses_precise_current_thread_route"
    report["live_same_thread_issue_comment_route_quality"] = live_quality
    boundary = report.get("comparison_boundary")
    if isinstance(boundary, dict):
        boundary["live_same_thread_issue_comment_route_quality_requested"] = True
        boundary["cannot_claim_live_same_thread_issue_comment_route_quality"] = not precise
    readouts = report.get("issue_readouts")
    if isinstance(readouts, dict):
        readout = readouts.get("github_786")
        if isinstance(readout, dict):
            readout["same_thread_issue_comment_live_smoke_measured"] = True
            readout["live_same_thread_issue_comment_route_quality"] = (
                "measured_precise_route" if precise else "broad_scent_only"
            )
            readout["same_thread_issue_comment_live_manual_query_count"] = route.get(
                "manual_query_invention_count"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic no-write recall navigation comparison smoke."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--github-issue",
        type=int,
        default=0,
        help="Optionally fetch a public GitHub issue/comment route-quality sample via gh.",
    )
    parser.add_argument("--github-parent-issue", type=int, default=791)
    parser.add_argument("--github-repo", default="Sapientropic/AIppocampus")
    args = parser.parse_args(argv)
    report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
    if args.github_issue:
        _attach_live_github_route_quality(
            report,
            repo=args.github_repo,
            issue=args.github_issue,
            parent_issue=args.github_parent_issue,
        )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(recall_navigation_comparison.render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
