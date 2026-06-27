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
    "claim_safe_next_action:",
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
    "stage_safe_next_action:",
    "next_verification_command:",
)
OWNER_ROUTE_ISSUE_FIELDS = (
    "issue_url",
    "issue_refs",
    "current_issue_url",
    "current_issue",
    "successor_issue_url",
    "successor_issue",
)
OWNER_ROUTE_STATE_FIELDS = (
    "successor_issue_state",
    "current_issue_state",
    "owner_issue_state",
    "issue_state",
    "source_issue_state",
)
NO_ACTION_REASON_FIELDS = ("no_action_reason", "no_open_followup_reason")


def foreground_continuity_doc_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    ordered_docs = ("README.md", "docs/start-here.md")
    for rel_path in ordered_docs:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing recall-first public doc: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if rel_path == "README.md" and RECALL_FIRST_COMMAND not in text:
            issues.append(f"{rel_path} missing packaged recall-first command")
            continue
        if rel_path == "docs/start-here.md":
            if "README First Use Path" not in text:
                issues.append("docs/start-here.md missing README first-use route pointer")
            recall_idx = text.find("## First Recall")
        else:
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
    has_owner = bool(action.get("owner_path")) or any(action.get(field) for field in OWNER_ROUTE_ISSUE_FIELDS)
    has_next_surface = any(
        action.get(field)
        for field in ("command", "doc_path", "required_artifact", *NO_ACTION_REASON_FIELDS)
    )
    return bool(has_owner and has_next_surface and _owner_route_class(action) != "closed_historical_owner")


def _issue_state_values(mapping: dict[str, Any]) -> list[str]:
    return [
        str(mapping.get(field) or "").strip().casefold()
        for field in OWNER_ROUTE_STATE_FIELDS
        if mapping.get(field) not in (None, "", [], {})
    ]


def _has_no_action_reason(mapping: dict[str, Any]) -> bool:
    return any(mapping.get(field) not in (None, "", [], {}) for field in NO_ACTION_REASON_FIELDS)


def _owner_route_class(mapping: dict[str, Any]) -> str:
    if not (mapping.get("owner_path") or any(mapping.get(field) for field in OWNER_ROUTE_ISSUE_FIELDS)):
        return "none"
    states = _issue_state_values(mapping)
    if any(state == "open" or state.startswith("open_") for state in states):
        return "open_owner"
    if _has_no_action_reason(mapping):
        return "explicit_no_open_followup"
    if any("closed" in state or "historical" in state for state in states):
        return "closed_historical_owner"
    return "unknown_issue_state"


def _report_has_actionable_followup(report: dict[str, Any]) -> bool:
    if report.get("no_open_followup_reason"):
        return True
    owner_routes = report.get("owner_routes")
    if isinstance(owner_routes, (dict, list)) and owner_routes:
        return True
    if isinstance(owner_routes, str) and owner_routes.strip():
        return True
    for field in (
        "review_next_actions",
        "gap_next_actions",
        "issue_actions",
        "fidelity_gap_actions",
        "recommended_next_actions",
        "next_measurement_actions",
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
        "closed_historical_owner_route_reports": 0,
        "explicit_no_open_followup_reports": 0,
        "unknown_owner_route_reports": 0,
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
        route_classes = {
            _owner_route_class(item)
            for item in _walk_dicts(report)
            if _owner_route_class(item) != "none"
        }
        if "closed_historical_owner" in route_classes:
            metrics["closed_historical_owner_route_reports"] += 1
        if "explicit_no_open_followup" in route_classes or report.get("no_open_followup_reason"):
            metrics["explicit_no_open_followup_reports"] += 1
        if "unknown_issue_state" in route_classes:
            metrics["unknown_owner_route_reports"] += 1
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


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    dicts: list[dict[str, Any]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for child in value.values():
            dicts.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            dicts.extend(_walk_dicts(child))
    return dicts
