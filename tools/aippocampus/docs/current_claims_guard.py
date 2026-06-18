"""Current-claims snapshot and claim-boundary retirement guards."""

from __future__ import annotations

import re
from pathlib import Path

CURRENT_CLAIMS_SNAPSHOT_DOC = "docs/evidence/current-claims.md"
CURRENT_CLAIMS_FOREGROUND_BUDGET_CHARS = 3200
CURRENT_CLAIMS_FOREGROUND_TERMS = {
    "## Claim Reviewer Card": "current claims missing compact claim reviewer card",
    "current_status:": "current claims reviewer card missing current status",
    "can_say:": "current claims reviewer card missing can-say line",
    "cannot_say:": "current claims reviewer card missing cannot-say line",
    "owner_routes:": "current claims reviewer card missing owner routes",
    "claim_safe_next_action:": "current claims reviewer card missing claim safe next action",
    "next_verification_command:": (
        "current claims reviewer card missing next verification command"
    ),
    "## Detailed Evidence Index": (
        "current claims missing detailed evidence index boundary after reviewer card"
    ),
}

REQUIRED_CURRENT_CLAIMS_TERMS = {
    "## Current Claim Snapshot": "current claims snapshot missing current snapshot section",
    "metric_id": "current claims snapshot missing metric-id column",
    "run_date": "current claims snapshot missing run-date column",
    "source_report": "current claims snapshot missing source-report column",
    "claim_level": "current claims snapshot missing claim-level column",
    "cohort": "current claims snapshot missing cohort column",
    "supersedes": "current claims snapshot missing supersession column",
    "supports": "current claims snapshot missing supports/material-limits reporting term",
    "material_limits": "current claims snapshot missing material-limits reporting term",
    "cannot_claim": "current claims snapshot missing cannot-claim column",
    "semantic_sidecar.aggregate_materialized_rows": (
        "current claims snapshot missing semantic sidecar aggregate metric"
    ),
    "semantic_sidecar.strict_survival_snapshot": (
        "current claims snapshot missing historical strict sidecar metric"
    ),
    "semantic_sidecar.source_review_green_gate": (
        "current claims snapshot missing semantic sidecar green-review metric"
    ),
    "semantic_sidecar.source_review_diagnostic": (
        "current claims snapshot missing semantic sidecar diagnostic-review metric"
    ),
    "track_b.private_semantic_sidecar_required": (
        "current claims snapshot missing private Track B semantic-sidecar metric"
    ),
    "fts5.real_history_recall_2026_05_29": (
        "current claims snapshot missing dated FTS5 real-history metric"
    ),
    "demo_scenarios.claim_boundaries": (
        "current claims snapshot missing demo scenario claim-boundary pointer"
    ),
}

CANNOT_CLAIM_RETIREMENT_SECTION = "## Claim-Boundary Owner And Retirement Ledger"
CANNOT_CLAIM_RETIREMENT_REQUIRED_COLUMNS = (
    "Caveat",
    "Category",
    "Owner issue",
    "Retirement condition",
    "Next review",
)
CANNOT_CLAIM_RETIREMENT_CATEGORIES = {
    "actionable",
    "durable_non_goal",
    "research_blocked",
    "external_dependency",
}
CANNOT_CLAIM_RETIREMENT_REQUIRED_OWNER_ISSUES = {
    "#960": "continuous-memory negative result",
    "#963": "Track B top-k source-evidence misses",
    "#994": "E2E50 representative seed pack",
    "#1020": "Claude Code hooks",
    "#1021": "persistent Claude Code MCP config health",
    "#1022": "CJK recall quality beyond the first public fixture",
    "#575": "cognitive-load false positives / usefulness",
    "#663": "Episode/Arc gappy-chain overclaim risk",
}

CURRENT_CLAIMS_POINTER_DOCS = {
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "stage readiness missing current claims snapshot pointer"
    ),
    "docs/guides/demo-scenarios.md": "demo scenarios missing current claims snapshot pointer",
}

# These phrase guards are intentionally narrow. They block specific stale
# evidence claims that have already misled issue triage while avoiding broad
# scans for ordinary identifiers such as current_thread or current_frontier.
STALE_CURRENT_EVIDENCE_PHRASES = {
    "docs/evidence/readiness/stage-0-5-readiness.md": {
        "current strict sidecars at 2 threads/5 rows": (
            "stage readiness has stale semantic sidecar current wording: "
            "current strict sidecars at 2 threads/5 rows"
        ),
        "current strict materialization keeps only": (
            "stage readiness has stale semantic sidecar current wording: "
            "current strict materialization keeps only"
        ),
    },
    "docs/evidence/readiness/public-readiness-verification.md": {
        "current strict re-materialized sidecars intentionally contain only 5 rows across 2": (
            "public readiness ledger has stale semantic sidecar current wording: "
            "current strict re-materialized sidecars intentionally contain only 5 rows "
            "across 2"
        ),
    },
}


def current_claims_snapshot_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    snapshot = repo_root / CURRENT_CLAIMS_SNAPSHOT_DOC
    if not snapshot.exists():
        issues.append(f"missing current claims snapshot: {CURRENT_CLAIMS_SNAPSHOT_DOC}")
    else:
        text = snapshot.read_text(encoding="utf-8")
        for term, issue in REQUIRED_CURRENT_CLAIMS_TERMS.items():
            if term not in text:
                issues.append(issue)
        issues.extend(cannot_claim_retirement_issues(text))
        issues.extend(current_claims_foreground_issues(repo_root))

    for rel_path, issue in CURRENT_CLAIMS_POINTER_DOCS.items():
        path = repo_root / rel_path
        if path.exists() and CURRENT_CLAIMS_SNAPSHOT_DOC not in path.read_text(encoding="utf-8"):
            issues.append(issue)

    for rel_path, phrases in STALE_CURRENT_EVIDENCE_PHRASES.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        normalized_text = " ".join(text.split())
        for phrase, issue in phrases.items():
            if phrase in text or phrase in normalized_text:
                issues.append(issue)

    return issues


def current_claims_foreground_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    snapshot = repo_root / CURRENT_CLAIMS_SNAPSHOT_DOC
    if not snapshot.exists():
        return [f"missing current claims snapshot: {CURRENT_CLAIMS_SNAPSHOT_DOC}"]
    text = snapshot.read_text(encoding="utf-8")
    foreground = text[:CURRENT_CLAIMS_FOREGROUND_BUDGET_CHARS]
    for term, issue in CURRENT_CLAIMS_FOREGROUND_TERMS.items():
        if term not in foreground:
            issues.append(issue)
    return issues


def _plain_markdown_cell(cell: str) -> str:
    return cell.strip().strip("`").strip()


def _is_blank_markdown_cell(cell: str) -> bool:
    return _plain_markdown_cell(cell) in {"", "-", "n/a", "N/A"}


def _current_claims_table_after_section(
    text: str,
    section: str,
) -> tuple[list[str], list[dict[str, str]]] | None:
    lines = text.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == section:
            start_index = index + 1
            break
    if start_index is None:
        return None

    table_lines: list[str] = []
    for line in lines[start_index:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
    if len(table_lines) < 2:
        return [], []

    headers = [
        _plain_markdown_cell(cell)
        for cell in table_lines[0].strip("|").split("|")
    ]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [
            _plain_markdown_cell(cell)
            for cell in line.strip("|").split("|")
        ]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells, strict=True)))
    return headers, rows


def cannot_claim_retirement_issues(text: str) -> list[str]:
    issues: list[str] = []
    parsed = _current_claims_table_after_section(text, CANNOT_CLAIM_RETIREMENT_SECTION)
    if parsed is None:
        return ["current claims snapshot missing claim-boundary owner/retirement ledger"]

    headers, rows = parsed
    if not rows:
        issues.append("current claims claim-boundary owner/retirement ledger has no rows")

    for column in CANNOT_CLAIM_RETIREMENT_REQUIRED_COLUMNS:
        if column not in headers:
            issues.append(f"current claims cannot-claim ledger missing column: {column}")

    categories_seen: set[str] = set()
    owner_issue_cells: list[str] = []
    for row in rows:
        caveat = row.get("Caveat", "unknown caveat")
        category = row.get("Category", "").strip("`")
        categories_seen.add(category)
        if category and category not in CANNOT_CLAIM_RETIREMENT_CATEGORIES:
            issues.append(
                f"current claims cannot-claim ledger has unsupported category for {caveat}: "
                f"{category}"
            )

        owner_issue = row.get("Owner issue", "")
        owner_issue_cells.append(owner_issue)
        retirement_condition = row.get("Retirement condition", "")

        if category == "actionable":
            if _is_blank_markdown_cell(owner_issue) or not re.search(
                r"(?:#|\bissues/)\d+\b",
                owner_issue,
            ):
                issues.append(
                    f"current claims actionable cannot-claim missing owner issue: {caveat}"
                )
            if _is_blank_markdown_cell(retirement_condition):
                issues.append(
                    "current claims actionable cannot-claim missing retirement "
                    f"condition: {caveat}"
                )

    if "durable_non_goal" not in categories_seen:
        issues.append(
            "current claims cannot-claim ledger missing durable_non_goal category row"
        )

    owner_issue_text = "\n".join(owner_issue_cells)
    for issue_ref, caveat in CANNOT_CLAIM_RETIREMENT_REQUIRED_OWNER_ISSUES.items():
        if issue_ref not in owner_issue_text:
            issues.append(
                f"current claims cannot-claim ledger missing owner issue {issue_ref}: "
                f"{caveat}"
            )
    return issues
