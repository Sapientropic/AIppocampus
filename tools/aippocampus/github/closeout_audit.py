#!/usr/bin/env python3
"""Heuristic PR closeout audit for broad-issue false-done prevention."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

CLOSING_REF_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
ISSUE_REF_RE = re.compile(r"#\d+\b")
CLOSEOUT_CLASS_RE = re.compile(
    r"\bcloseout(?:[ _-]class)?\s*[:=-]\s*"
    r"(complete_with_followups|complete|blocker_recorded|narrow_slice_only)\b",
    re.I,
)
CHECKED_CLOSEOUT_CLASS_RE = re.compile(
    r"^\s*[-*]\s*\[[xX]\]\s*`?"
    r"(complete_with_followups|complete|blocker_recorded|narrow_slice_only)`?\b",
    re.I | re.M,
)
UNCHECKED_TASK_RE = re.compile(r"^\s*[-*]\s*\[\s\]\s+")
TASK_CONTINUATION_RE = re.compile(r"^\s{2,}\S")
TASK_OR_MARKDOWN_BOUNDARY_RE = re.compile(r"^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?|#{1,6}\s+)")
RISKY_CLOSEOUT_RE = re.compile(
    r"\b("
    r"diagnostic[- ]only|failure report|blocker(?: recorded)?|not measured|"
    r"not default|(?:cannot|can't) claim (?:broad|product|sota|default|"
    r"private[- ]history|live|general|universal|full|complete|issue|acceptance|quality)|"
    r"not proof|not proven|"
    r"narrow slice|partial slice|slice only|opt[- ]in only"
    r")\b",
    re.I,
)
FOLLOWUP_RE = re.compile(
    r"\b("
    r"remaining[_ -]?gap|followup[_ -]?issue|follow[- ]up issue|"
    r"tracked by|continues in|superseded by|opened #|see #"
    r")\b",
    re.I,
)
FOLLOWUP_SECTION_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?:remaining[_ -]?gap|followup[_ -]?issue|follow[- ]up issue|"
    r"remaining\s+gap\s*/\s*follow[- ]up\s+issue)\s*:?\s*(?P<rest>.*)$",
    re.I,
)
MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")


def _unique_issue_numbers(matches: list[str]) -> list[int]:
    seen: set[int] = set()
    values: list[int] = []
    for item in matches:
        number = int(item)
        if number in seen:
            continue
        seen.add(number)
        values.append(number)
    return values


def _closeout_class(body: str) -> str | None:
    match = CLOSEOUT_CLASS_RE.search(body)
    if match:
        return match.group(1).casefold()
    checked_match = CHECKED_CLOSEOUT_CLASS_RE.search(body)
    return checked_match.group(1).casefold() if checked_match else None


def _has_followup_pointer(body: str) -> bool:
    in_followup_section = False
    for line in body.splitlines():
        stripped = line.strip()
        section_match = FOLLOWUP_SECTION_RE.match(line)
        if section_match:
            # A template heading such as "Remaining gap / follow-up issue:" is
            # only a pointer after a real issue ref is filled on that line or
            # below it. Never borrow the PR's broad "Closes #..." reference.
            in_followup_section = True
            rest = section_match.group("rest")
            if ISSUE_REF_RE.search(rest) and not CLOSING_REF_RE.search(rest):
                return True
            continue

        if FOLLOWUP_RE.search(line) and ISSUE_REF_RE.search(line) and not CLOSING_REF_RE.search(line):
            return True

        if in_followup_section:
            if MARKDOWN_HEADING_RE.match(line):
                in_followup_section = False
                continue
            if not stripped:
                continue
            if ISSUE_REF_RE.search(line) and not CLOSING_REF_RE.search(line):
                return True

    return False


def _selected_task_text(body: str) -> str:
    """Ignore unchecked PR-template task rows so default options do not become claims."""

    selected_lines: list[str] = []
    skipping_unchecked_task = False
    for line in body.splitlines():
        if UNCHECKED_TASK_RE.match(line):
            skipping_unchecked_task = True
            continue
        if skipping_unchecked_task:
            is_wrapped_continuation = bool(
                TASK_CONTINUATION_RE.match(line) and not TASK_OR_MARKDOWN_BOUNDARY_RE.match(line)
            )
            if is_wrapped_continuation:
                continue
            skipping_unchecked_task = False
        selected_lines.append(line)
    return "\n".join(selected_lines)


def audit_pr_body(body: str) -> dict[str, Any]:
    text = _selected_task_text(str(body or ""))
    closing_issues = _unique_issue_numbers(CLOSING_REF_RE.findall(text))
    closeout_class = _closeout_class(text)
    risky_terms = sorted({match.group(1).casefold() for match in RISKY_CLOSEOUT_RE.finditer(text)})
    has_followup_pointer = _has_followup_pointer(text)
    findings: list[dict[str, Any]] = []

    if closing_issues and closeout_class == "narrow_slice_only":
        findings.append(
            {
                "kind": "narrow_slice_closes_issue",
                "severity": "error",
                "message": "Closeout class narrow_slice_only must use relates-to wording, not closing keywords.",
                "closing_issues": closing_issues,
            }
        )

    if closing_issues and closeout_class == "blocker_recorded" and not has_followup_pointer:
        findings.append(
            {
                "kind": "blocker_closeout_missing_followup",
                "severity": "error",
                "message": "Blocker-recorded closeouts need a follow-up issue or remaining_gap pointer.",
                "closing_issues": closing_issues,
            }
        )

    if closing_issues and risky_terms and not has_followup_pointer:
        findings.append(
            {
                "kind": "risky_closeout_missing_followup",
                "severity": "error",
                "message": (
                    "PR body uses a closing keyword with diagnostic/blocker/partial-scope "
                    "language but no remaining_gap or followup_issue pointer."
                ),
                "closing_issues": closing_issues,
                "risk_terms": risky_terms,
            }
        )

    return {
        "kind": "aippocampus_closeout_audit",
        "schema_version": SCHEMA_VERSION,
        "ok": not findings,
        "closing_issues": closing_issues,
        "closeout_class": closeout_class,
        "risk_terms": risky_terms,
        "has_followup_pointer": has_followup_pointer,
        "findings": findings,
        "policy": {
            "closing_keywords": ["closes", "fixes", "resolves"],
            "closeout_classes": [
                "complete",
                "complete_with_followups",
                "blocker_recorded",
                "narrow_slice_only",
            ],
            "heuristic_only": True,
        },
    }


def _body_from_args(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8")
    if args.body_env:
        return os.environ.get(args.body_env, "")
    if args.body is not None:
        return args.body
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--body-env")
    parser.add_argument("--body")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--github-annotations", action="store_true")
    args = parser.parse_args(argv)

    report = audit_pr_body(_body_from_args(args))
    if args.json_output or not args.github_annotations:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.github_annotations:
        for finding in report["findings"]:
            print(f"::error::{finding['message']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
