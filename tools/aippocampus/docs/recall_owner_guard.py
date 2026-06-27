"""Docs-health guard for recall runtime owner classification."""

from __future__ import annotations

import re
from pathlib import Path

OWNER_MAP = "docs/architecture/recall/owner-map.md"
RECALL_RUNTIME_DIR = "skills/aippocampus/scripts/aippocampus_runtime/recall"
REQUIRED_OWNER_HEADINGS = {
    "### Prompt Recall",
    "### Ambient",
    "### Active Recall And Locks",
    "### APW And Route Walking",
    "### Semantic",
    "### Source Open And Deepen",
    "### Foreground Projection",
    "### Scoring And Retrieval",
    "### Feedback",
    "### Continuity And Life Cues",
    "### Background Findings",
    "### Diagnostics And Recovery",
}
REQUIRED_FEEDBACK_PACKAGE_TERMS = {
    "`feedback/__init__.py`",
    "`feedback/associative_path.py`",
    "`feedback/capture.py`",
    "`feedback/events.py`",
    "`feedback/outcome.py`",
    "No flat compatibility wrappers",
}
FLAT_PY_RE = re.compile(r"`(?P<name>[A-Za-z_][A-Za-z0-9_]*\.py)`")


def _flat_recall_modules(repo_root: Path) -> set[str]:
    recall_dir = repo_root / RECALL_RUNTIME_DIR
    if not recall_dir.exists():
        return set()
    return {
        path.name
        for path in recall_dir.glob("*.py")
        if path.name != "__init__.py"
    }


def _documented_flat_modules(text: str) -> set[str]:
    return {match.group("name") for match in FLAT_PY_RE.finditer(text)}


def recall_owner_map_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    owner_map = repo_root / OWNER_MAP
    if not owner_map.exists():
        return [f"missing recall owner map: {OWNER_MAP}"]

    text = owner_map.read_text(encoding="utf-8")
    for heading in sorted(REQUIRED_OWNER_HEADINGS):
        if heading not in text:
            issues.append(f"recall owner map missing owner family: {heading.removeprefix('### ')}")
    for term in sorted(REQUIRED_FEEDBACK_PACKAGE_TERMS):
        if term not in text:
            issues.append(f"recall owner map missing feedback boundary term: {term}")

    flat_modules = _flat_recall_modules(repo_root)
    documented = _documented_flat_modules(text)
    missing = sorted(flat_modules - documented)
    stale = sorted(
        name
        for name in documented - flat_modules
        if not (repo_root / RECALL_RUNTIME_DIR / "feedback" / name).exists()
    )
    for name in missing:
        issues.append(
            f"flat recall module missing owner classification in {OWNER_MAP}: {name}"
        )
    for name in stale:
        issues.append(
            f"recall owner map lists missing flat module or package file: {name}"
        )
    return issues


__all__ = ["recall_owner_map_issues"]
