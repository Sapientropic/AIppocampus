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
    "research/historical",
}


def architecture_index_issues(repo_root: Path) -> list[str]:
    architecture_dir = repo_root / "docs" / "architecture"
    if not architecture_dir.exists():
        return []
    index = repo_root / ARCHITECTURE_INDEX_DOC
    if not index.exists():
        return [f"missing architecture index: {ARCHITECTURE_INDEX_DOC}"]

    issues: list[str] = []
    rows: dict[str, str] = {}
    pattern = re.compile(r"\|\s*\[[^\]]+\]\(([^)]+\.md)\)\s*\|\s*([^|]+?)\s*\|")
    for match in pattern.finditer(index.read_text(encoding="utf-8")):
        filename = Path(match.group(1)).name
        role = " ".join(match.group(2).strip().casefold().split())
        rows[filename] = role
        if role not in ARCHITECTURE_INDEX_ROLES:
            issues.append(
                f"architecture index has unsupported role for {filename}: {role}; "
                f"use one of {sorted(ARCHITECTURE_INDEX_ROLES)}"
            )

    for doc in sorted(architecture_dir.glob("*.md")):
        if doc.name != "README.md" and doc.name not in rows:
            issues.append(f"architecture index missing docs/architecture/{doc.name}")

    for filename in sorted(rows):
        if filename == "README.md":
            issues.append("architecture index should not classify its own README.md")
        elif not (architecture_dir / filename).exists():
            issues.append(f"architecture index references missing file: docs/architecture/{filename}")
    return issues
