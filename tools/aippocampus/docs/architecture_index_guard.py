"""Guardrails for the docs/architecture folder index."""

from __future__ import annotations

import re
from pathlib import Path

ARCHITECTURE_INDEX_DOC = "docs/architecture/README.md"
ARCHITECTURE_INDEX_ROLES = {
    "current contract",
    "implementation map",
    "active design",
    "inventory",
    "research seed",
    "archive",
}
ARCHITECTURE_INDEX_ROLE_SECTIONS = {
    "## Current Contracts",
    "## Implementation Maps",
    "## Inventories",
    "## Active Designs",
    "## Research Seeds",
    "## Archives",
}


def _normalize_role(value: str) -> str:
    return " ".join(value.strip().strip("`.:").casefold().split())


def _architecture_doc_role(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines()[:8]:
        match = re.match(r"Role:\s*`?([^`.]+)`?\.?$", line.strip(), re.IGNORECASE)
        if match:
            return _normalize_role(match.group(1))
    return None


def architecture_index_issues(repo_root: Path) -> list[str]:
    architecture_dir = repo_root / "docs" / "architecture"
    if not architecture_dir.exists():
        return []
    index = repo_root / ARCHITECTURE_INDEX_DOC
    if not index.exists():
        return [f"missing architecture index: {ARCHITECTURE_INDEX_DOC}"]

    issues: list[str] = []
    rows: dict[str, str] = {}
    index_text = index.read_text(encoding="utf-8")
    for section in sorted(ARCHITECTURE_INDEX_ROLE_SECTIONS):
        if section not in index_text:
            issues.append(f"architecture index missing role section: {section}")

    pattern = re.compile(r"\|\s*\[[^\]]+\]\(([^)]+\.md)\)\s*\|\s*([^|]+?)\s*\|")
    for match in pattern.finditer(index_text):
        filename = Path(match.group(1)).name
        role = _normalize_role(match.group(2))
        rows[filename] = role
        if role not in ARCHITECTURE_INDEX_ROLES:
            issues.append(
                f"architecture index has unsupported role for {filename}: {role}; "
                f"use one of {sorted(ARCHITECTURE_INDEX_ROLES)}"
            )

    for doc in sorted(architecture_dir.glob("*.md")):
        if doc.name == "README.md":
            continue
        if doc.name not in rows:
            issues.append(f"architecture index missing docs/architecture/{doc.name}")
        doc_role = _architecture_doc_role(doc)
        if not doc_role:
            issues.append(f"architecture doc missing Role line: docs/architecture/{doc.name}")
            continue
        if doc_role not in ARCHITECTURE_INDEX_ROLES:
            issues.append(
                f"architecture doc has unsupported Role for {doc.name}: {doc_role}; "
                f"use one of {sorted(ARCHITECTURE_INDEX_ROLES)}"
            )
        elif doc.name in rows and doc_role != rows[doc.name]:
            issues.append(
                f"architecture doc Role mismatch for {doc.name}: doc has {doc_role}, "
                f"index has {rows[doc.name]}"
            )

    for filename in sorted(rows):
        if filename == "README.md":
            issues.append("architecture index should not classify its own README.md")
        elif not (architecture_dir / filename).exists():
            issues.append(f"architecture index references missing file: docs/architecture/{filename}")
    return issues
