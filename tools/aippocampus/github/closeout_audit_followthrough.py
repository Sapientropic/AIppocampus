#!/usr/bin/env python3
"""Follow-through helpers for closeout audit.

The closeout audit CLI owns issue/PR semantics. GitHub closed-window retrieval
and copy-pasteable command checks are deliberately split here so adding another
traceability path does not keep growing the main audit script.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Pattern

GITHUB_REMOTE_RE = re.compile(r"github\.com[:/](?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$", re.I)
PLACEHOLDER_COMMAND_TOKEN_RE = re.compile(
    r"(\.\.\.|<[^>\n]+>|\{[^}\n]+\}|\$(?:branch|commit|sha|pr|issue|changed_files)\b|\$\{[^}\n]+\})",
    re.I,
)


def _issue_number(raw: Mapping[str, Any]) -> int:
    value = raw.get("number")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def closed_at_in_window(
    raw: Mapping[str, Any],
    *,
    window_start: str | None,
    window_end: str | None,
) -> bool:
    closed_at = str(raw.get("closedAt") or raw.get("closed_at") or "").strip()
    if not closed_at:
        return True
    if window_start and closed_at < window_start:
        return False
    if window_end and closed_at > window_end:
        return False
    return True


def guard_command_lines(body: str, *, guard_command_re: Pattern[str]) -> list[str]:
    return [
        line.strip()
        for line in body.splitlines()
        if guard_command_re.search(line)
    ]


def placeholder_guard_commands(body: str, *, guard_command_re: Pattern[str]) -> list[str]:
    return [
        line
        for line in guard_command_lines(body, guard_command_re=guard_command_re)
        if PLACEHOLDER_COMMAND_TOKEN_RE.search(line)
    ]


def has_replayable_guard_command(body: str, *, guard_command_re: Pattern[str]) -> bool:
    return any(
        not PLACEHOLDER_COMMAND_TOKEN_RE.search(line)
        for line in guard_command_lines(body, guard_command_re=guard_command_re)
    )


def missing_body_env_report(body_env: str, *, schema_version: int) -> dict[str, Any]:
    env_name = str(body_env or "").strip()
    message = (
        f"--body-env {env_name} was requested, but the environment variable was empty; "
        "provide --body-file/--body or use --closed-window-start/--closed-window-end."
    )
    return {
        "kind": "aippocampus_closeout_audit",
        "schema_version": schema_version,
        "ok": False,
        "status": "not_audited",
        "closing_issues": [],
        "closeout_class": "not_audited",
        "high_risk_families": [],
        "evidence_shape": {},
        "performance_evidence_shape": {},
        "findings": [
            {
                "kind": "audit_input_missing",
                "severity": "blocker",
                "message": message,
                "closing_issues": [],
                "recovery": {
                    "body_env": env_name,
                    "accepted_inputs": [
                        "--body-file <path>",
                        "--body <text>",
                        "--closed-window-start <iso> --closed-window-end <iso>",
                    ],
                },
            }
        ],
        "policy": {
            "empty_body_env_is_not_audit_evidence": True,
            "heuristic_only": True,
        },
    }


def pr_body_from_gh(pr_number: str, *, repo: str | None) -> tuple[str, str | None]:
    clean_pr = str(pr_number or "").strip().lstrip("#")
    if not clean_pr:
        return "", "missing_pr_number"
    clean_repo = str(repo or "").strip() or infer_github_repo_from_origin()
    if not clean_repo:
        return "", "missing_github_repo_for_pr_body"
    try:
        completed = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                clean_pr,
                "--repo",
                clean_repo,
                "--json",
                "body",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", f"gh_pr_view_failed:{exc}"
    if completed.returncode != 0:
        return "", (completed.stderr or completed.stdout or "gh pr view failed").strip()
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return "", f"gh_pr_view_json_error:{exc}"
    if not isinstance(payload, Mapping):
        return "", "gh_pr_view_body_not_object"
    body = str(payload.get("body") or "")
    if not body.strip():
        return "", "gh_pr_view_body_empty"
    return body, None


def missing_pr_body_report(
    pr_number: str,
    *,
    github_repo: str | None,
    schema_version: int,
    error: str,
) -> dict[str, Any]:
    clean_pr = str(pr_number or "").strip().lstrip("#")
    repo = str(github_repo or "").strip() or infer_github_repo_from_origin()
    next_command = (
        f"python tools/aippocampus/github/closeout_audit.py --pr {clean_pr or '<number>'} --json"
        + (f" --github-repo {repo}" if repo else " --github-repo <owner/repo>")
    )
    detail_command = next_command + " --detail full"
    return {
        "kind": "aippocampus_closeout_audit",
        "schema_version": schema_version,
        "ok": False,
        "status": "not_audited",
        "closing_issues": [],
        "closeout_class": "not_audited",
        "high_risk_families": [],
        "evidence_shape": {},
        "performance_evidence_shape": {},
        "findings": [
            {
                "kind": "pr_body_audit_not_run",
                "severity": "blocker",
                "message": "PR closeout audit has not been run on the actual PR body.",
                "closing_issues": [],
                "recovery": {
                    "reason": error,
                    "next_command": next_command,
                    "detail_command": detail_command,
                },
            }
        ],
        "policy": {
            "actual_pr_body_required": True,
            "heuristic_only": True,
        },
    }


def compact_audit_report(report: Mapping[str, Any], *, detail_command: str | None) -> dict[str, Any]:
    findings = list(report.get("findings") or [])
    status = str(report.get("status") or "").strip()
    return {
        "kind": "aippocampus_closeout_audit_compact",
        "schema_version": report.get("schema_version"),
        "ok": report.get("ok"),
        "status": status or ("pass" if report.get("ok") else "fail"),
        "closing_issues": report.get("closing_issues") or [],
        "blocker_count": len(findings),
        "blockers": [
            {
                "kind": item.get("kind"),
                "severity": item.get("severity"),
                "message": item.get("message"),
                "closing_issues": item.get("closing_issues"),
            }
            for item in findings
        ],
        "detail_command": detail_command,
    }


def infer_github_repo_from_origin() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    match = GITHUB_REMOTE_RE.search((completed.stdout or "").strip())
    if not match:
        return None
    return match.group("repo").removesuffix(".git")


def fetch_github_issue_metadata(
    *,
    repo: str,
    issue_numbers: list[int],
    token: str | None = None,
) -> dict[int, dict[str, Any]]:
    if not repo or not issue_numbers:
        return {}
    out: dict[int, dict[str, Any]] = {}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "aippocampus-closeout-audit",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for number in issue_numbers:
        url = f"https://api.github.com/repos/{repo}/issues/{number}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            fallback = _fetch_github_issue_metadata_with_gh(repo=repo, number=number)
            if fallback is not None:
                out[number] = fallback
            continue
        if isinstance(payload, Mapping):
            out[number] = {
                "number": number,
                "title": payload.get("title") or "",
                "body": payload.get("body") or "",
                "labels": payload.get("labels") or [],
            }
    return out


def _fetch_github_issue_metadata_with_gh(
    *,
    repo: str,
    number: int,
) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                repo,
                "--json",
                "title,body,labels",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return {
        "number": number,
        "title": payload.get("title") or "",
        "body": payload.get("body") or "",
        "labels": payload.get("labels") or [],
    }


def _fetch_closed_issue_detail_with_gh(repo: str, number: int) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                repo,
                "--comments",
                "--json",
                "number,title,body,closedAt,comments,labels,url",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def fetch_closed_issues_for_window(
    *,
    repo: str,
    window_start: str | None,
    window_end: str | None,
) -> tuple[dict[str, Any], str, str | None]:
    if not repo:
        return {"issues": []}, "failed", "missing_github_repo"
    if not (window_start or window_end):
        return {"issues": []}, "failed", "missing_closed_window"
    start_date = str(window_start or "").strip()[:10]
    end_date = str(window_end or window_start or "").strip()[:10]
    search = f"closed:{start_date}..{end_date}" if start_date and end_date else f"closed:{start_date or end_date}"
    try:
        completed = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "closed",
                "--limit",
                "100",
                "--search",
                search,
                "--json",
                "number,title,body,closedAt,comments,labels,url",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"issues": []}, "failed", f"gh_issue_list_failed:{exc}"
    if completed.returncode != 0:
        error = completed.stderr or completed.stdout or "gh issue list failed"
        return {"issues": []}, "failed", error
    try:
        raw_rows = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"issues": []}, "failed", f"gh_issue_list_json_error:{exc}"
    if not isinstance(raw_rows, list):
        return {"issues": []}, "failed", "gh_issue_list_not_array"
    rows = [
        row
        for row in raw_rows
        if isinstance(row, Mapping)
        and _issue_number(row)
        and closed_at_in_window(row, window_start=window_start, window_end=window_end)
    ]
    issues: list[dict[str, Any]] = []
    for row in rows:
        number = _issue_number(row)
        detail = _fetch_closed_issue_detail_with_gh(repo, number)
        issues.append(detail or dict(row))
    status = "ok" if issues else "ok_no_closed_issues_in_window"
    return {"issues": issues}, status, None
