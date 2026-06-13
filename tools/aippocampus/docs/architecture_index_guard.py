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
ARCHITECTURE_INDEX_REQUIRED_TERMS = {
    "architecture-overview.md": "architecture index missing source-backed kernel contract pointer",
    "source-shape-runtime-spine.md": "architecture index missing source-shape spine pointer",
    "runtime-script-map.md": "architecture index missing runtime script map pointer",
    "architecture-debt-register.md": "architecture index missing architecture debt register pointer",
    "## Topic Layers": "architecture index missing topic layer section",
    "## Roles": "architecture index missing role legend",
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


def _linked_architecture_paths(index_text: str) -> set[str]:
    links: set[str] = set()
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", index_text):
        target = match.group(1).split("#", maxsplit=1)[0]
        if not target or "://" in target:
            continue
        if target.endswith("/"):
            links.add(target.rstrip("/") + "/README.md")
        elif target.endswith(".md"):
            links.add(target)
    return links


def architecture_index_issues(repo_root: Path) -> list[str]:
    architecture_dir = repo_root / "docs" / "architecture"
    if not architecture_dir.exists():
        return []
    index = repo_root / ARCHITECTURE_INDEX_DOC
    if not index.exists():
        return [f"missing architecture index: {ARCHITECTURE_INDEX_DOC}"]

    issues: list[str] = []
    index_text = index.read_text(encoding="utf-8")
    for term, issue in ARCHITECTURE_INDEX_REQUIRED_TERMS.items():
        if term not in index_text:
            issues.append(issue)

    linked_paths = _linked_architecture_paths(index_text)

    for child_dir in sorted(path for path in architecture_dir.iterdir() if path.is_dir()):
        readme = child_dir / "README.md"
        rel_readme = readme.relative_to(architecture_dir).as_posix()
        if not readme.exists():
            issues.append(f"architecture topic folder missing README: docs/architecture/{rel_readme}")
        elif rel_readme not in linked_paths:
            issues.append(f"architecture index missing topic folder: docs/architecture/{rel_readme}")

    for doc in sorted(architecture_dir.rglob("*.md")):
        rel_doc = doc.relative_to(architecture_dir).as_posix()
        if rel_doc == "README.md" or rel_doc.endswith("/README.md"):
            continue
        doc_role = _architecture_doc_role(doc)
        if not doc_role:
            issues.append(f"architecture doc missing Role line: docs/architecture/{rel_doc}")
            continue
        if doc_role not in ARCHITECTURE_INDEX_ROLES:
            issues.append(
                f"architecture doc has unsupported Role for {rel_doc}: {doc_role}; "
                f"use one of {sorted(ARCHITECTURE_INDEX_ROLES)}"
            )

    return issues
