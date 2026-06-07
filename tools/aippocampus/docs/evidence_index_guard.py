"""Guardrails for the docs/evidence folder index."""

from __future__ import annotations

from pathlib import Path

EVIDENCE_INDEX_DOC = "docs/evidence/README.md"

REQUIRED_EVIDENCE_INDEX_TERMS = {
    "current claim snapshot": "evidence README missing current claim snapshot lane",
    "product and human evidence": "evidence README missing product/human evidence lane",
    "dated verification ledger": "evidence README missing dated verification ledger lane",
    "not the canonical status page": (
        "evidence README missing non-canonical ledger boundary"
    ),
    "docs/evidence/current-claims.md": "evidence README missing current claims pointer",
    "docs/evidence/magic-moments.md": "evidence README missing magic moments pointer",
    "docs/evidence/readiness/proof-slice-maturity.md": (
        "evidence README missing proof-slice maturity pointer"
    ),
    "docs/evidence/readiness/public-readiness-verification.md": (
        "evidence README missing public readiness ledger pointer"
    ),
    "docs/evidence/benchmark-evidence-map.md": (
        "evidence README missing benchmark map pointer"
    ),
}


def evidence_index_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    evidence_index = repo_root / EVIDENCE_INDEX_DOC
    if not evidence_index.exists():
        return [f"missing evidence README: {EVIDENCE_INDEX_DOC}"]

    text = evidence_index.read_text(encoding="utf-8")
    lower_text = text.casefold()
    for term, issue in REQUIRED_EVIDENCE_INDEX_TERMS.items():
        if term.casefold() not in lower_text:
            issues.append(issue)

    docs_readme = repo_root / "docs" / "README.md"
    if docs_readme.exists() and "evidence/README.md" not in docs_readme.read_text(
        encoding="utf-8"
    ):
        issues.append("docs README missing evidence README pointer")
    return issues
