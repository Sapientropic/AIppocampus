#!/usr/bin/env python3
"""Heuristic PR closeout audit for broad-issue false-done prevention."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1

CLOSING_REF_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
ISSUE_REF_RE = re.compile(r"#\d+\b")
COMMIT_REF_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
PULL_REQUEST_REF_RE = re.compile(r"(?:pull/\d+|PR\s*#?\d+|pull request\s*#?\d+)", re.I)
LITERAL_TEMPLATE_RE = re.compile(r"\$(?:branch|commit|sha|pr|issue)\b|\$\{[^}]+\}", re.I)
MALFORMED_COMMIT_REF_RE = re.compile(r"\^\[?[0-9a-f]{6,40}\b|\[[0-9a-f]{6,40}\b", re.I)
CLOSEOUT_COMMENT_RE = re.compile(
    r"\b(closeout|verification|verified|commit|merged|pr\s*#?\d+|pull request)\b|"
    r"(验证|已验证|合并|提交|关闭)",
    re.I,
)
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
DEFAULT_RUNTIME_CHANGE_RE = re.compile(
    r"\b("
    r"runtime default change|default behavior change|"
    r"default routing change|default adoption change|changed default routing|"
    r"changed default behavior|hook foreground behavior changed|ranking default changed|"
    r"policy gate default changed"
    r")\b",
    re.I,
)
DEFAULT_RUNTIME_CHANGE_FIELD_RE = re.compile(
    r"^\s*-?\s*Runtime/default policy change:[ \t]*(?P<value>.*)$",
    re.I | re.M,
)
BENCHMARK_ADOPTION_OUTCOME_RE = re.compile(
    r"\b("
    r"runtime_policy_adoption_gate_ok\s*[:=]\s*true|"
    r"default_adoption_gate_ok\s*[:=]\s*true|"
    r"adoption_action\s*[:=]\s*allow_default_adoption|"
    r"adoption_scope\s*[:=]"
    r")",
    re.I,
)
BENCHMARK_ADOPTION_FIELD_RE = re.compile(
    r"^\s*-?\s*Benchmark outcome card or gate:[ \t]*(?P<value>.*)$",
    re.I | re.M,
)
NON_BENCHMARK_ADOPTION_RATIONALE_RE = re.compile(
    r"\b("
    r"not benchmark[- ]gated|benchmark[- ]gated\s*[:=]\s*no|"
    r"human override|override rationale|small internal refactor|contract[- ]only default"
    r")\b",
    re.I,
)
NON_BENCHMARK_ADOPTION_RATIONALE_FIELD_RE = re.compile(
    r"^\s*-?\s*Non[- ]benchmark rationale(?:\s*/\s*override)?:[ \t]*(?P<value>.*)$",
    re.I | re.M,
)
DIAGNOSTIC_DEFAULT_AUTHORITY_RE = re.compile(
    r"\bdiagnostic[- ]only\b.{0,120}\b("
    r"authorize|allow|approve|promote|default adoption|default behavior|default routing"
    r")\b|\b(default adoption|default behavior|default routing)\b.{0,120}\bdiagnostic[- ]only\b",
    re.I | re.S,
)
RECALL_FOLLOWTHROUGH_FAMILY_RE = re.compile(
    r"\b("
    r"agent[_ -]?recall|apw|associative path|mcp|foreground action|"
    r"source[-_ ]open|source open|source anchor|opened source|deepen"
    r")\b",
    re.I,
)
COMPACT_DETAIL_FAMILY_RE = re.compile(
    r"\b(compact|detail|operator|foreground projection|foreground surface|projection)\b",
    re.I,
)
CLEANUP_DEBT_FAMILY_RE = re.compile(
    r"\b("
    r"cleanup|test[-_ ]debt|guard[-_ ]debt|debt removed|compatibility cleanup|"
    r"compatibility|compat field|retire|delete|deleted|migrated|duplicate helper|"
    r"field[-_ ]only|guard framework|red[- ]light"
    r")\b",
    re.I,
)
BENCHMARK_SYNTHETIC_FAMILY_RE = re.compile(
    r"\b(benchmark|synthetic|fixture|scripted proxy|contract fixture|proxy result)\b",
    re.I,
)
FOLLOWTHROUGH_CHAIN_RE = re.compile(
    r"agent[_ -]?recall.{0,240}"
    r"(?:agent[_ -]?(?:deepen|open)|deepen/open|opened source).{0,240}"
    r"(?:opened source anchor hits|source anchor hits|anchor hits)",
    re.I | re.S,
)
COMPACT_OUTPUT_EVIDENCE_RE = re.compile(
    r"\b(?:compact|default)\b.{0,100}\b(?:output|surface|payload|card|stdout|json)\b",
    re.I | re.S,
)
DETAIL_OUTPUT_EVIDENCE_RE = re.compile(
    r"\b(?:detail|operator|full)\b.{0,100}\b(?:output|surface|payload|diagnostic|stdout|json)\b",
    re.I | re.S,
)
DEBT_REMOVED_EVIDENCE_RE = re.compile(
    r"\b("
    r"debt removed|deleted path|deleted test|deleted helper|removed path|"
    r"migrated path|migrated caller|before/after inventory|before inventory|"
    r"after inventory|remaining owner issue|remaining owner #|remaining debt"
    r")\b",
    re.I,
)
FIELD_ONLY_EVIDENCE_RE = re.compile(
    r"\b("
    r"selector (?:exists|emitted|present)|route_count|field exists|field present|"
    r"schema valid|json snapshot|snapshot updated|payload contains|source_backed\s*[:=]\s*true"
    r")\b",
    re.I,
)
SYNTHETIC_ONLY_EVIDENCE_RE = re.compile(
    r"\b(synthetic fixture|fixture[- ]only|scripted proxy|contract fixture|payload fixture)\b",
    re.I,
)
WIRED_READY_USEFUL_RE = re.compile(r"\b(wired|ready|useful|foreground action)\b", re.I)
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


def _node_list(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        nodes = value.get("nodes")
        return list(nodes) if isinstance(nodes, list) else []
    return list(value) if isinstance(value, list) else []


def _comment_bodies(value: Any) -> list[str]:
    bodies: list[str] = []
    for item in _node_list(value):
        if isinstance(item, Mapping):
            body = item.get("body")
        else:
            body = item
        if isinstance(body, str) and body.strip():
            bodies.append(body)
    return bodies


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _closed_pr_numbers(value: Any) -> list[int]:
    numbers: list[int] = []
    for item in _node_list(value):
        if not isinstance(item, Mapping):
            continue
        number = _coerce_int(item.get("number"))
        if number is not None:
            numbers.append(number)
    return sorted(set(numbers))


def _issue_number(raw: Mapping[str, Any]) -> int:
    return _coerce_int(raw.get("number")) or 0


def _closed_issue_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if isinstance(value.get("issues"), list):
            return [item for item in value["issues"] if isinstance(item, Mapping)]
        repository = value.get("repository")
        if isinstance(repository, Mapping):
            return _closed_issue_rows(repository.get("issues"))
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return [item for item in nodes if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def audit_closed_issue_traceability(
    issues: list[Mapping[str, Any]] | Mapping[str, Any],
    *,
    window_start: str | None = None,
    window_end: str | None = None,
) -> dict[str, Any]:
    """Audit already-closed issues for source-reachable closeout evidence.

    The audit is intentionally additive: malformed comments are findings, not a
    reason to reopen product work. Future agents need stable PR/commit/comment
    trails, while historical issue comments remain immutable public history.
    """

    rows = _closed_issue_rows(issues)
    findings: list[dict[str, Any]] = []
    malformed_comment_issue_count = 0
    missing_pr_or_commit_reference_count = 0
    missing_closeout_comment_count = 0
    issues_with_closed_pr_count = 0
    issues_with_commit_reference_count = 0
    issues_with_closeout_comment_count = 0

    for raw in rows:
        number = _issue_number(raw)
        if not number:
            continue
        comments = _comment_bodies(raw.get("comments"))
        joined_comments = "\n\n".join(comments)
        closed_prs = _closed_pr_numbers(raw.get("closedByPullRequestsReferences"))
        has_closed_pr = bool(closed_prs)
        has_commit_ref = bool(COMMIT_REF_RE.search(joined_comments))
        has_pr_ref = bool(PULL_REQUEST_REF_RE.search(joined_comments))
        has_closeout_comment = any(CLOSEOUT_COMMENT_RE.search(body) for body in comments)
        malformed_terms: list[str] = []
        if LITERAL_TEMPLATE_RE.search(joined_comments):
            malformed_terms.append("literal_template_variable")
        if MALFORMED_COMMIT_REF_RE.search(joined_comments):
            malformed_terms.append("malformed_commit_reference")

        if has_closed_pr:
            issues_with_closed_pr_count += 1
        if has_commit_ref:
            issues_with_commit_reference_count += 1
        if has_closeout_comment:
            issues_with_closeout_comment_count += 1

        if malformed_terms:
            malformed_comment_issue_count += 1
            findings.append(
                {
                    "kind": "malformed_closeout_comment",
                    "severity": "warning",
                    "issue": number,
                    "terms": sorted(set(malformed_terms)),
                    "message": "Closed issue has a malformed or templated closeout comment.",
                }
            )
        if not (has_closed_pr or has_commit_ref or has_pr_ref):
            missing_pr_or_commit_reference_count += 1
            findings.append(
                {
                    "kind": "missing_pr_or_commit_reference",
                    "severity": "warning",
                    "issue": number,
                    "message": (
                        "Closed issue has no closedByPullRequestsReferences and no "
                        "obvious PR/commit reference in recent comments."
                    ),
                }
            )
        if not has_closeout_comment:
            missing_closeout_comment_count += 1
            findings.append(
                {
                    "kind": "missing_closeout_comment",
                    "severity": "warning",
                    "issue": number,
                    "message": "Closed issue has no obvious closeout/evidence comment.",
                }
            )

    return {
        "kind": "aippocampus_closed_issue_traceability_audit",
        "schema_version": SCHEMA_VERSION,
        "ok": not findings,
        "window": {"start": window_start, "end": window_end},
        "summary": {
            "closed_issue_count": len([raw for raw in rows if _issue_number(raw)]),
            "issues_with_closed_pr_count": issues_with_closed_pr_count,
            "issues_with_commit_reference_count": issues_with_commit_reference_count,
            "issues_with_closeout_comment_count": issues_with_closeout_comment_count,
            "missing_pr_or_commit_reference_count": missing_pr_or_commit_reference_count,
            "missing_closeout_comment_count": missing_closeout_comment_count,
            "malformed_comment_issue_count": malformed_comment_issue_count,
            "finding_count": len(findings),
        },
        "findings": findings,
        "expected_closeout_comment_shape": {
            "issue_scope": "Name the issue slice and whether it is complete, follow-up-owned, or blocker-recorded.",
            "pr_or_commit": "Link a PR or stable commit SHA; never leave literal template variables.",
            "verification": "List focused commands or evidence artifacts that actually cover the scope.",
            "material_limits": "State cannot-claim boundaries when evidence is public, synthetic, diagnostic, or partial.",
            "followup_routing": "Link remaining-gap issues instead of implying broad completion.",
        },
        "policy": {
            "additive_only": True,
            "do_not_reopen_for_comment_shape_alone": True,
            "do_not_rewrite_existing_comments": True,
        },
    }


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


def _field_has_substantive_value(match: re.Match[str]) -> bool:
    value = match.group("value").strip().strip("`").casefold()
    return value not in {"", "no", "none", "n/a", "not applicable", "not_applicable"}


def _default_runtime_change_signal(body: str, evidence_level: str | None) -> bool:
    if evidence_level == "default_adoption":
        return True
    if any(_field_has_substantive_value(match) for match in DEFAULT_RUNTIME_CHANGE_FIELD_RE.finditer(body)):
        return True
    return bool(DEFAULT_RUNTIME_CHANGE_RE.search(body))


def _has_benchmark_adoption_outcome(body: str) -> bool:
    if any(_field_has_substantive_value(match) for match in BENCHMARK_ADOPTION_FIELD_RE.finditer(body)):
        return True
    return bool(BENCHMARK_ADOPTION_OUTCOME_RE.search(body))


def _has_non_benchmark_adoption_rationale(body: str) -> bool:
    if any(
        _field_has_substantive_value(match)
        for match in NON_BENCHMARK_ADOPTION_RATIONALE_FIELD_RE.finditer(body)
    ):
        return True
    return bool(NON_BENCHMARK_ADOPTION_RATIONALE_RE.search(body))


def _issue_family_text(
    *,
    issue: int,
    body: str,
    issue_metadata: Mapping[int, Mapping[str, Any]],
) -> str:
    metadata = issue_metadata.get(issue) or {}
    issue_intent = _issue_intent_text_from_body(body)
    if metadata:
        return "\n".join(
            [
                issue_intent,
                str(metadata.get("title") or ""),
                str(metadata.get("body") or ""),
            ]
        )
    return issue_intent


def _high_risk_families_for_text(text: str) -> list[str]:
    families: list[str] = []
    if RECALL_FOLLOWTHROUGH_FAMILY_RE.search(text):
        families.append("recall_mcp_apw_source_open")
    if COMPACT_DETAIL_FAMILY_RE.search(text):
        families.append("compact_detail_projection")
    if CLEANUP_DEBT_FAMILY_RE.search(text):
        families.append("cleanup_test_guard_debt")
    if BENCHMARK_SYNTHETIC_FAMILY_RE.search(text):
        families.append("benchmark_or_synthetic")
    return families


def _high_risk_issue_families(
    *,
    closing_issues: list[int],
    body: str,
    issue_metadata: Mapping[int, Mapping[str, Any]],
) -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for issue in closing_issues:
        issue_text = _issue_family_text(issue=issue, body=body, issue_metadata=issue_metadata)
        issue_families = _high_risk_families_for_text(issue_text)
        if issue_families:
            families[str(issue)] = issue_families
    return families


def _flatten_high_risk_families(high_risk_issue_families: Mapping[str, list[str]]) -> set[str]:
    return {family for families in high_risk_issue_families.values() for family in families}


def _evidence_shape(body: str) -> dict[str, bool]:
    return {
        "has_recall_deepen_open_anchor_chain": bool(FOLLOWTHROUGH_CHAIN_RE.search(body)),
        "has_compact_output_evidence": bool(COMPACT_OUTPUT_EVIDENCE_RE.search(body)),
        "has_detail_or_operator_output_evidence": bool(DETAIL_OUTPUT_EVIDENCE_RE.search(body)),
        "has_debt_removed_evidence": bool(DEBT_REMOVED_EVIDENCE_RE.search(body)),
        "has_field_only_evidence_terms": bool(FIELD_ONLY_EVIDENCE_RE.search(body)),
        "has_synthetic_only_evidence_terms": bool(SYNTHETIC_ONLY_EVIDENCE_RE.search(body)),
        "has_wired_ready_useful_claim": bool(WIRED_READY_USEFUL_RE.search(body)),
    }


def _fetch_github_issue_metadata(
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
            continue
        if isinstance(payload, Mapping):
            out[number] = {
                "number": number,
                "title": payload.get("title") or "",
                "body": payload.get("body") or "",
            }
    return out


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
    high_risk_issue_families = _high_risk_issue_families(
        closing_issues=closing_issues,
        body=text,
        issue_metadata=normalized_issue_metadata,
    )
    high_risk_families = _flatten_high_risk_families(high_risk_issue_families)
    evidence_shape = _evidence_shape(text)
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
    default_runtime_change_signal = _default_runtime_change_signal(text, evidence_level)
    has_benchmark_adoption_outcome = _has_benchmark_adoption_outcome(text)
    has_non_benchmark_adoption_rationale = _has_non_benchmark_adoption_rationale(text)
    diagnostic_default_authority = bool(DIAGNOSTIC_DEFAULT_AUTHORITY_RE.search(text))
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

    if (
        closing_issues
        and diagnostic_default_authority
        and not has_non_benchmark_adoption_rationale
    ):
        findings.append(
            {
                "kind": "diagnostic_outcome_authorizes_default",
                "severity": "error",
                "message": (
                    "Diagnostic-only benchmark results cannot silently authorize "
                    "runtime/default behavior changes. Cite a passing adoption "
                    "outcome card or state an explicit non-benchmark override."
                ),
                "closing_issues": closing_issues,
            }
        )

    if (
        closing_issues
        and default_runtime_change_signal
        and not has_benchmark_adoption_outcome
        and not has_non_benchmark_adoption_rationale
    ):
        findings.append(
            {
                "kind": "missing_benchmark_adoption_outcome",
                "severity": "error",
                "message": (
                    "Runtime/default behavior changes need a cited benchmark "
                    "outcome card or an explicit non-benchmark rationale."
                ),
                "closing_issues": closing_issues,
            }
        )

    if (
        closing_issues
        and "recall_mcp_apw_source_open" in high_risk_families
        and not evidence_shape["has_recall_deepen_open_anchor_chain"]
    ):
        findings.append(
            {
                "kind": "missing_recall_source_followthrough",
                "severity": "error",
                "message": (
                    "Closing recall/MCP/APW/source-open work needs a real "
                    "`agent recall -> agent deepen/open -> opened source anchor hits` chain."
                ),
                "closing_issues": closing_issues,
                "high_risk_issue_families": high_risk_issue_families,
            }
        )

    if (
        closing_issues
        and "compact_detail_projection" in high_risk_families
        and not (
            evidence_shape["has_compact_output_evidence"]
            and evidence_shape["has_detail_or_operator_output_evidence"]
        )
    ):
        findings.append(
            {
                "kind": "missing_compact_detail_evidence_split",
                "severity": "error",
                "message": (
                    "Closing compact/detail projection work needs separate compact/default "
                    "and detail/operator evidence, not only a JSON snapshot."
                ),
                "closing_issues": closing_issues,
                "high_risk_issue_families": high_risk_issue_families,
            }
        )

    if (
        closing_issues
        and "cleanup_test_guard_debt" in high_risk_families
        and not evidence_shape["has_debt_removed_evidence"]
    ):
        findings.append(
            {
                "kind": "missing_debt_removed_evidence",
                "severity": "error",
                "message": (
                    "Closing cleanup/test-debt/guard-debt work needs deleted or migrated "
                    "paths, before/after inventory, or a remaining owner issue."
                ),
                "closing_issues": closing_issues,
                "high_risk_issue_families": high_risk_issue_families,
            }
        )

    if (
        closing_issues
        and high_risk_families
        and evidence_shape["has_field_only_evidence_terms"]
        and not evidence_shape["has_recall_deepen_open_anchor_chain"]
    ):
        findings.append(
            {
                "kind": "field_only_evidence_closes_high_risk",
                "severity": "error",
                "message": (
                    "Field presence, route counts, selectors, or JSON snapshots do not "
                    "prove high-risk AIppocampus product follow-through."
                ),
                "closing_issues": closing_issues,
                "high_risk_issue_families": high_risk_issue_families,
            }
        )

    if (
        closing_issues
        and high_risk_families
        and evidence_shape["has_synthetic_only_evidence_terms"]
        and evidence_shape["has_wired_ready_useful_claim"]
        and not evidence_shape["has_recall_deepen_open_anchor_chain"]
    ):
        findings.append(
            {
                "kind": "synthetic_only_evidence_overclaims_high_risk",
                "severity": "error",
                "message": (
                    "Synthetic fixtures or scripted proxies cannot by themselves support "
                    "wired/ready/useful closeout claims for high-risk AIppocampus work."
                ),
                "closing_issues": closing_issues,
                "high_risk_issue_families": high_risk_issue_families,
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
        "high_risk_issue_families": high_risk_issue_families,
        "evidence_shape": evidence_shape,
        "has_aippocampus_orientation": has_aippocampus_orientation,
        "has_isolated_experiment_label": has_isolated_experiment_label,
        "default_runtime_change_signal": default_runtime_change_signal,
        "has_benchmark_adoption_outcome": has_benchmark_adoption_outcome,
        "has_non_benchmark_adoption_rationale": has_non_benchmark_adoption_rationale,
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
            "runtime_default_changes_need_benchmark_outcome_or_rationale": True,
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


def _issue_metadata_from_args(args: argparse.Namespace, body: str) -> Any:
    metadata: Any = None
    if args.issue_metadata_file:
        metadata = json.loads(Path(args.issue_metadata_file).read_text(encoding="utf-8"))
    if args.github_repo:
        closing_issues = _unique_issue_numbers(CLOSING_REF_RE.findall(_selected_task_text(body)))
        fetched = _fetch_github_issue_metadata(
            repo=args.github_repo,
            issue_numbers=closing_issues,
            token=os.environ.get(args.github_token_env) if args.github_token_env else None,
        )
        existing = _normalize_issue_metadata(metadata)
        existing.update(fetched)
        return existing
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--body-env")
    parser.add_argument("--body")
    parser.add_argument("--issue-metadata-file", type=Path)
    parser.add_argument(
        "--github-repo",
        help="Fetch closing issue title/body metadata from this owner/repo for high-risk family detection.",
    )
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument(
        "--closed-issues-file",
        type=Path,
        help="Audit an exported GitHub closed-issue JSON payload instead of a PR body.",
    )
    parser.add_argument("--closed-window-start")
    parser.add_argument("--closed-window-end")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--github-annotations", action="store_true")
    args = parser.parse_args(argv)

    if args.closed_issues_file:
        report = audit_closed_issue_traceability(
            json.loads(args.closed_issues_file.read_text(encoding="utf-8")),
            window_start=args.closed_window_start,
            window_end=args.closed_window_end,
        )
    else:
        body = _body_from_args(args)
        report = audit_pr_body(
            body,
            issue_metadata=_issue_metadata_from_args(args, body),
        )
    if args.json_output or not args.github_annotations:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.github_annotations:
        for finding in report["findings"]:
            print(f"::error::{finding['message']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
