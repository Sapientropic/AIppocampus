"""Docs-health guards for foreground continuity and benchmark report routing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RECALL_FIRST_COMMAND = 'aippocampus agent recall "old decision or handoff cue" --json'
PUBLIC_EXAMPLE_DOC_INTERNAL_COMMAND_MARKERS = (
    "skills/aippocampus/scripts",
    "skills\\aippocampus\\scripts",
    "aippocampus_runtime.",
    "aippocampus_cli.py",
    "search_clean_source.py",
)
REPORT_ROUTER_TASK_CARD_DOCS = (
    "docs/evidence/benchmarks/reports/README.md",
    "docs/evidence/benchmarks/reports/longmemeval/README.md",
    "docs/evidence/benchmarks/reports/public-longitudinal/README.md",
    "docs/evidence/benchmarks/reports/public-reliability/README.md",
)
REPORT_ROUTER_TASK_CARD_TERMS = (
    "## Report Router Task Card",
    "current_claim_owner:",
    "latest_promoted_report:",
    "safe_next_action:",
    "historical_boundary:",
)
CURRENTNESS_CARD_DOCS = (
    "docs/evidence/readiness/stage-0-5-readiness.md",
    "docs/evidence/readiness/public-readiness-verification.md",
    "docs/planning/next-iteration-plan.md",
    "docs/planning/README.md",
)
CURRENTNESS_CARD_TERMS = (
    "## Currentness Card",
    "page_last_structural_review:",
    "latest_numeric_claim_source:",
    "current_status:",
    "remaining_gaps:",
    "owner_routes:",
    "next_verification_command:",
)


def foreground_continuity_doc_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    ordered_docs = ("README.md", "docs/start-here.md")
    for rel_path in ordered_docs:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing recall-first public doc: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if RECALL_FIRST_COMMAND not in text:
            issues.append(f"{rel_path} missing packaged recall-first command")
            continue
        recall_idx = text.index(RECALL_FIRST_COMMAND)
        for marker in ("aippocampus vault sync --json", "aippocampus self-note append"):
            marker_idx = text.find(marker)
            if marker_idx >= 0 and marker_idx < recall_idx:
                issues.append(f"{rel_path} presents {marker} before first recall")
        if rel_path == "docs/start-here.md":
            first_recall_idx = text.find("## First Recall")
            see_memory_idx = text.find("## See And Add To Memory")
            if first_recall_idx < 0:
                issues.append("docs/start-here.md missing First Recall section")
            elif see_memory_idx >= 0 and see_memory_idx < first_recall_idx:
                issues.append("docs/start-here.md puts write/sync memory before First Recall")

    examples_dir = repo_root / "examples"
    if examples_dir.exists():
        for path in sorted(examples_dir.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            rel_path = path.relative_to(repo_root).as_posix()
            for marker in PUBLIC_EXAMPLE_DOC_INTERNAL_COMMAND_MARKERS:
                if marker in text:
                    issues.append(
                        f"public example doc uses internal runtime command marker {marker}: "
                        f"{rel_path}"
                    )
                    break
    return issues


def benchmark_report_router_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path in REPORT_ROUTER_TASK_CARD_DOCS:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"benchmark report router missing task card doc: {rel_path}")
            continue
        foreground = path.read_text(encoding="utf-8")[:2200]
        for term in REPORT_ROUTER_TASK_CARD_TERMS:
            if term not in foreground:
                issues.append(f"{rel_path} missing report router task-card term: {term}")
    return issues


def currentness_card_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path in CURRENTNESS_CARD_DOCS:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"currentness-card doc missing: {rel_path}")
            continue
        foreground = path.read_text(encoding="utf-8")[:2400]
        for term in CURRENTNESS_CARD_TERMS:
            if term not in foreground:
                issues.append(f"{rel_path} missing currentness-card term: {term}")
    return issues


def _top_level_cannot_claim_count(report: Any) -> int:
    if not isinstance(report, dict):
        return 0
    value = report.get("cannot_claim")
    if isinstance(value, list):
        return sum(1 for item in value if item not in (None, "", [], {}))
    return 1 if value not in (None, "", [], {}) else 0


def _action_has_owner(action: Any) -> bool:
    if not isinstance(action, dict):
        return False
    has_owner = bool(action.get("owner_path")) or any(
        action.get(field)
        for field in (
            "issue_url",
            "issue_refs",
            "current_issue_url",
            "current_issue",
            "successor_issue_url",
            "successor_issue",
        )
    )
    has_next_surface = any(
        action.get(field)
        for field in (
            "command",
            "doc_path",
            "required_artifact",
            "no_action_reason",
            "no_open_followup_reason",
        )
    )
    return bool(has_owner and has_next_surface)


def _report_has_actionable_followup(report: dict[str, Any]) -> bool:
    if report.get("no_open_followup_reason"):
        return True
    for field in (
        "review_next_actions",
        "gap_next_actions",
        "issue_actions",
        "fidelity_gap_actions",
    ):
        actions = report.get(field)
        if isinstance(actions, dict):
            actions = [actions]
        if isinstance(actions, list) and any(_action_has_owner(action) for action in actions):
            return True
    return False


def benchmark_report_followup_warnings(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    reports_dir = repo_root / "docs" / "evidence" / "benchmarks" / "reports"
    warnings: list[str] = []
    missing_followup_reports: list[str] = []
    metrics: dict[str, Any] = {
        "json_reports_checked": 0,
        "high_cannot_claim_reports": 0,
        "high_cannot_claim_reports_missing_followup": 0,
        "missing_followup_reports": missing_followup_reports,
    }
    if not reports_dir.exists():
        return warnings, metrics
    for path in sorted(reports_dir.rglob("*.json")):
        metrics["json_reports_checked"] += 1
        rel_path = path.relative_to(repo_root).as_posix()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(
                "benchmark report JSON could not be parsed for followup scan: "
                f"{rel_path}: {type(exc).__name__}"
            )
            continue
        cannot_claim_count = _top_level_cannot_claim_count(report)
        if cannot_claim_count < 4:
            continue
        metrics["high_cannot_claim_reports"] += 1
        if not isinstance(report, dict) or not _report_has_actionable_followup(report):
            metrics["high_cannot_claim_reports_missing_followup"] += 1
            missing_followup_reports.append(rel_path)
    if missing_followup_reports:
        examples = ", ".join(missing_followup_reports[:3])
        suffix = "" if len(missing_followup_reports) <= 3 else ", ..."
        warnings.append(
            "benchmark report followup scan found "
            f"{len(missing_followup_reports)} historical high-cannot_claim reports "
            "without actionable followup/no-action reason; warning-only until "
            f"those artifacts are cleaned. examples: {examples}{suffix}"
        )
    return warnings, metrics
