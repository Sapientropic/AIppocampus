#!/usr/bin/env python3
"""Heuristic PR closeout audit for broad-issue false-done prevention."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1

CLOSING_REF_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
ISSUE_REF_RE = re.compile(r"#\d+\b")
EVIDENCE_LEVELS = (
    "contract_fixture",
    "scripted_proxy",
    "model_pilot",
    "behavior_run",
    "scale_run",
    "default_adoption",
)
EVIDENCE_LEVEL_RANK = {
    "contract_fixture": 0,
    "scripted_proxy": 0,
    "model_pilot": 2,
    "behavior_run": 3,
    "scale_run": 4,
    "default_adoption": 5,
}
EVIDENCE_LEVEL_RE = re.compile(
    r"^\s*evidence[_ -]?level\s*[:=-]\s*"
    r"(contract_fixture|scripted_proxy|model_pilot|behavior_run|scale_run|default_adoption)\b",
    re.I | re.M,
)
ISSUE_INTENT_RE = re.compile(
    r"^\s*issue[_ -]?intent\s*[:=-]\s*(?P<intent>.+)$",
    re.I | re.M,
)
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
BENCHMARK_SOURCE_SIDE_RE = re.compile(
    r"\b("
    r"longmemeval|benchmark|source[-_ ]side|semantic cache|source_semantic_cache|"
    r"line[-_ ]rerank|reranker|warming|warm ambient|attention router"
    r")\b",
    re.I,
)
SOURCE_SIDE_ORIENTATION_REQUIRED_RE = re.compile(
    r"\b("
    r"longmemeval|source_semantic_cache|semantic cache|source[-_ ]side "
    r"(?:semantic|warming|cache|worker|benchmark)|warm ambient|attention router"
    r")\b",
    re.I,
)
BENCHMARK_LOCAL_SCAFFOLD_RE = re.compile(
    r"\b("
    r"temporary provider prompt|provider prompt|benchmark[-_ ]local|"
    r"local scaffold|source route label|route_text|route label"
    r")\b",
    re.I,
)
AIPPOCAMPUS_ORIENTATION_RE = re.compile(
    r"\b("
    r"aippocampus orientation|active[-_ ]pull|agent[_ -]?recall|agent[_ -]?deepen|"
    r"route[-_ ]first|semantic_scope_builder|semantic scope builder|"
    r"warm_ambient|warm ambient|attention router"
    r")\b",
    re.I,
)
ISOLATED_EXPERIMENT_RE = re.compile(
    r"\b(isolated[_ -]?experiment|proxy[_ -]?baseline|narrow[_ -]?experiment)\b",
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
INTENT_LEVEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:live|model[- ]backed|provider|model output|external model)\b", re.I), "model_pilot"),
    (
        re.compile(
            r"\b(?:behavior|behaviour|agent behavior|user[- ]visible|usefulness|quality lift)\b",
            re.I,
        ),
        "behavior_run",
    ),
    (re.compile(r"\b(?:500q|100q|scale|scaled|source[- ]side|full run|larger run)\b", re.I), "scale_run"),
    (
        re.compile(r"\b(?:default adoption|default[- ]ready|default behavior|promot(?:e|ion).{0,40}default)\b", re.I),
        "default_adoption",
    ),
)


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


def _evidence_level(body: str) -> str | None:
    match = EVIDENCE_LEVEL_RE.search(body)
    return match.group(1).casefold() if match else None


def _intent_level_requirements(text: str) -> list[str]:
    levels: list[str] = []
    for pattern, level in INTENT_LEVEL_RULES:
        if pattern.search(text) and level not in levels:
            levels.append(level)
    levels.sort(key=lambda item: EVIDENCE_LEVEL_RANK[item])
    return levels


def _issue_intent_text_from_body(body: str) -> str:
    return "\n".join(match.group("intent").strip() for match in ISSUE_INTENT_RE.finditer(body))


def _normalize_issue_metadata(value: Any) -> dict[int, dict[str, Any]]:
    if not value:
        return {}
    if isinstance(value, Mapping):
        raw_items: list[tuple[Any, Any]] = list(value.items())
    elif isinstance(value, list):
        raw_items = []
        for item in value:
            if isinstance(item, Mapping):
                number = item.get("number")
                if number is not None:
                    raw_items.append((number, item))
    else:
        return {}
    normalized: dict[int, dict[str, Any]] = {}
    for key, item in raw_items:
        if not isinstance(item, Mapping):
            continue
        try:
            number = int(str(key).lstrip("#"))
        except ValueError:
            continue
        normalized[number] = dict(item)
    return normalized


def _issue_intent_levels(
    *,
    closing_issues: list[int],
    body: str,
    issue_metadata: Mapping[int, Mapping[str, Any]] | None,
) -> dict[str, list[str]]:
    levels: dict[str, list[str]] = {}
    body_intent = _issue_intent_text_from_body(body)
    if body_intent:
        levels["pr_body"] = _intent_level_requirements(body_intent)
    metadata = issue_metadata or {}
    for issue in closing_issues:
        item = metadata.get(issue)
        if not item:
            continue
        text = "\n".join(str(item.get(key) or "") for key in ("title", "body"))
        required = _intent_level_requirements(text)
        if required:
            levels[str(issue)] = required
    return {key: value for key, value in levels.items() if value}


def _flatten_required_levels(issue_intent_levels: Mapping[str, list[str]]) -> list[str]:
    required = sorted(
        {level for levels in issue_intent_levels.values() for level in levels},
        key=lambda item: EVIDENCE_LEVEL_RANK[item],
    )
    return required


def _evidence_level_satisfies(declared: str | None, required_levels: list[str]) -> bool:
    if not required_levels or not declared:
        return bool(not required_levels)
    required_rank = max(EVIDENCE_LEVEL_RANK[level] for level in required_levels)
    if "default_adoption" in required_levels and declared != "default_adoption":
        return False
    return EVIDENCE_LEVEL_RANK[declared] >= required_rank


def _honest_lower_evidence_followup(closeout_class: str | None, has_followup_pointer: bool) -> bool:
    return bool(has_followup_pointer and closeout_class in {"complete_with_followups", "blocker_recorded"})


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


def audit_pr_body(
    body: str,
    *,
    issue_metadata: Mapping[int, Mapping[str, Any]] | Mapping[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    text = _selected_task_text(str(body or ""))
    closing_issues = _unique_issue_numbers(CLOSING_REF_RE.findall(text))
    closeout_class = _closeout_class(text)
    evidence_level = _evidence_level(text)
    normalized_issue_metadata = _normalize_issue_metadata(issue_metadata)
    issue_intent_levels = _issue_intent_levels(
        closing_issues=closing_issues,
        body=text,
        issue_metadata=normalized_issue_metadata,
    )
    required_evidence_levels = _flatten_required_levels(issue_intent_levels)
    risky_terms = sorted({match.group(1).casefold() for match in RISKY_CLOSEOUT_RE.finditer(text)})
    has_followup_pointer = _has_followup_pointer(text)
    benchmark_source_side_terms = sorted(
        {match.group(1).casefold() for match in BENCHMARK_SOURCE_SIDE_RE.finditer(text)}
    )
    source_side_orientation_required_terms = sorted(
        {
            match.group(1).casefold()
            for match in SOURCE_SIDE_ORIENTATION_REQUIRED_RE.finditer(text)
        }
    )
    benchmark_local_scaffold_terms = sorted(
        {match.group(1).casefold() for match in BENCHMARK_LOCAL_SCAFFOLD_RE.finditer(text)}
    )
    has_aippocampus_orientation = bool(AIPPOCAMPUS_ORIENTATION_RE.search(text))
    has_isolated_experiment_label = bool(ISOLATED_EXPERIMENT_RE.search(text))
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

    if (
        closing_issues
        and source_side_orientation_required_terms
        and evidence_level in {"scale_run", "default_adoption"}
        and not has_aippocampus_orientation
    ):
        findings.append(
            {
                "kind": "missing_aippocampus_orientation",
                "severity": "error",
                "message": (
                    "Benchmark/source-side closeouts need an AIppocampus "
                    "orientation or deepen note before broad manual implementation."
                ),
                "closing_issues": closing_issues,
                "benchmark_terms": source_side_orientation_required_terms,
            }
        )

    if (
        closing_issues
        and source_side_orientation_required_terms
        and benchmark_local_scaffold_terms
        and not (has_isolated_experiment_label and has_followup_pointer)
    ):
        findings.append(
            {
                "kind": "benchmark_local_scaffold_closes_source_side",
                "severity": "error",
                "message": (
                    "Benchmark-local provider prompts or route-label scaffolds "
                    "cannot close source-side warming/capability issues unless "
                    "they are labeled isolated_experiment/proxy and a canonical "
                    "follow-up issue owns the remaining gap."
                ),
                "closing_issues": closing_issues,
                "benchmark_terms": source_side_orientation_required_terms,
                "scaffold_terms": benchmark_local_scaffold_terms,
            }
        )

    if (
        closing_issues
        and required_evidence_levels
        and not _evidence_level_satisfies(evidence_level, required_evidence_levels)
        and not _honest_lower_evidence_followup(closeout_class, has_followup_pointer)
    ):
        findings.append(
            {
                "kind": "evidence_level_mismatch" if evidence_level else "evidence_level_missing",
                "severity": "error",
                "message": (
                    "Closing issue intent asks for mature evidence, but the PR body "
                    "does not declare a matching evidence level or an honest follow-up closeout."
                ),
                "closing_issues": closing_issues,
                "declared_evidence_level": evidence_level,
                "required_evidence_levels": required_evidence_levels,
                "issue_intent_levels": issue_intent_levels,
            }
        )

    return {
        "kind": "aippocampus_closeout_audit",
        "schema_version": SCHEMA_VERSION,
        "ok": not findings,
        "closing_issues": closing_issues,
        "closeout_class": closeout_class,
        "evidence_level": evidence_level,
        "required_evidence_levels": required_evidence_levels,
        "issue_intent_levels": issue_intent_levels,
        "risk_terms": risky_terms,
        "benchmark_source_side_terms": benchmark_source_side_terms,
        "source_side_orientation_required_terms": source_side_orientation_required_terms,
        "benchmark_local_scaffold_terms": benchmark_local_scaffold_terms,
        "has_aippocampus_orientation": has_aippocampus_orientation,
        "has_isolated_experiment_label": has_isolated_experiment_label,
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
            "evidence_levels": list(EVIDENCE_LEVELS),
            "benchmark_source_side_orientation_required": True,
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


def _issue_metadata_from_args(args: argparse.Namespace) -> Any:
    if not args.issue_metadata_file:
        return None
    return json.loads(Path(args.issue_metadata_file).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--body-env")
    parser.add_argument("--body")
    parser.add_argument("--issue-metadata-file", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--github-annotations", action="store_true")
    args = parser.parse_args(argv)

    report = audit_pr_body(
        _body_from_args(args),
        issue_metadata=_issue_metadata_from_args(args),
    )
    if args.json_output or not args.github_annotations:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.github_annotations:
        for finding in report["findings"]:
            print(f"::error::{finding['message']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
