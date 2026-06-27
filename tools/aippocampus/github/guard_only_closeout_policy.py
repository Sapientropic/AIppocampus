from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

GUARD_CONTRACT_LIST_EVIDENCE_RE = re.compile(
    r"\b("
    r"contract list|guard contracts?|owner[-_ ]layer contracts?|runtime owner[-_ ]layer contracts?|"
    r"agent[-_ ]slop guard report"
    r")\b|\bMCP projection\b.{0,180}\bsource IO\b.{0,180}\bregistry\b.{0,180}\block\b",
    re.I | re.S,
)
DEBT_RESOLUTION_EVIDENCE_RE = re.compile(
    r"\b("
    r"debt removed|deleted path|deleted test|deleted helper|removed path|"
    r"migrated path|migrated caller|merged duplicate|merged helper|"
    r"centralized (?:in|into)|central owner|owner helper|"
    r"hidden from (?:compact|default|foreground)|moved behind (?:detail|operator)|"
    r"before/after inventory|before inventory|after inventory|"
    r"remaining owner issue|remaining owner #|remaining debt"
    r")\b",
    re.I,
)
GUARD_OR_REPORT_ONLY_CLOSEOUT_RE = re.compile(
    r"\b("
    r"guard[- ]only|report[- ]only|test[- ]only|diagnostic[- ]only guard|"
    r"red[- ]light only|adds? (?:a )?(?:guard|report|red[- ]light|test)|"
    r"adds? (?:a\s+)?(?:new\s+)?(?:guard|report|red[- ]light|test)|"
    r"added (?:a\s+)?(?:new\s+)?(?:guard|report|red[- ]light|test)"
    r")\b",
    re.I,
)
EXPLICIT_GUARD_ONLY_RE = re.compile(
    r"^\s*(?:[-*]\s*)?guard[- ]only\s*[:=-]\s*(?:yes|true)\b|\bguard[- ]only closeout\b",
    re.I | re.M,
)
GUARD_ONLY_CONDITION_RE = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"(?:promotion|promote|park|downgrade|retirement|retire|removal|remove|sunset)"
    r"(?:\s+(?:condition|criteria))?\s*[:=-]\s*\S",
    re.I | re.M,
)


def evidence_shape(body: str) -> dict[str, bool]:
    return {
        "has_guard_contract_list_evidence": bool(GUARD_CONTRACT_LIST_EVIDENCE_RE.search(body)),
        "has_debt_resolution_evidence": bool(DEBT_RESOLUTION_EVIDENCE_RE.search(body)),
        "has_guard_or_report_only_signal": bool(GUARD_OR_REPORT_ONLY_CLOSEOUT_RE.search(body)),
        "has_explicit_guard_only_label": bool(EXPLICIT_GUARD_ONLY_RE.search(body)),
        "has_guard_only_promotion_or_retirement_condition": bool(
            GUARD_ONLY_CONDITION_RE.search(body)
        ),
    }


def guard_tooling_closeout_finding(
    *,
    closing_issues: Sequence[int],
    high_risk_families: set[str],
    high_risk_issue_families: Mapping[str, Sequence[str]],
    evidence_shape: Mapping[str, bool],
) -> dict[str, Any] | None:
    if not closing_issues or "guard_tooling_contract" not in high_risk_families:
        return None
    missing_guard_evidence: list[str] = []
    if not evidence_shape["has_guard_contract_list_evidence"]:
        missing_guard_evidence.append("contract_list")
    if not evidence_shape["has_guard_command_evidence"]:
        missing_guard_evidence.append("guard_command")
    if (
        evidence_shape["has_guard_or_report_only_signal"]
        and not evidence_shape["has_debt_resolution_evidence"]
        and not (
            evidence_shape["has_explicit_guard_only_label"]
            and evidence_shape["has_guard_only_promotion_or_retirement_condition"]
        )
    ):
        missing_guard_evidence.append("guard_only_condition_or_debt_resolution")
    if not missing_guard_evidence:
        return None
    return {
        "kind": "missing_guard_tooling_closeout_evidence",
        "severity": "error",
        "message": (
            "Guard-tooling closeouts need the owner-contract list and "
            "the command agents should run before claiming cleanup."
        ),
        "closing_issues": list(closing_issues),
        "high_risk_issue_families": dict(high_risk_issue_families),
        "missing_evidence": missing_guard_evidence,
    }


def cleanup_debt_closeout_finding(
    *,
    closing_issues: Sequence[int],
    high_risk_families: set[str],
    high_risk_issue_families: Mapping[str, Sequence[str]],
    evidence_shape: Mapping[str, bool],
) -> dict[str, Any] | None:
    if (
        not closing_issues
        or "cleanup_test_guard_debt" not in high_risk_families
        or evidence_shape["has_debt_resolution_evidence"]
    ):
        return None
    explicit_guard_only_ok = bool(
        evidence_shape["has_guard_or_report_only_signal"]
        and evidence_shape["has_explicit_guard_only_label"]
        and evidence_shape["has_guard_only_promotion_or_retirement_condition"]
        and "guard_tooling_contract" in high_risk_families
    )
    if explicit_guard_only_ok:
        return None
    if evidence_shape["has_guard_or_report_only_signal"]:
        return {
            "kind": "guard_report_only_closeout_missing_debt_resolution",
            "severity": "error",
            "message": (
                "Guard/report-only closeouts cannot close cleanup or guard-debt "
                "issues unless they name deleted/merged/hidden/centralized debt, "
                "or explicitly declare guard-only work with a promotion/park/remove condition."
            ),
            "closing_issues": list(closing_issues),
            "high_risk_issue_families": dict(high_risk_issue_families),
        }
    return {
        "kind": "missing_debt_removed_evidence",
        "severity": "error",
        "message": (
            "Closing cleanup/test-debt/guard-debt work needs deleted or migrated "
            "paths, before/after inventory, or a remaining owner issue."
        ),
        "closing_issues": list(closing_issues),
        "high_risk_issue_families": dict(high_risk_issue_families),
    }
