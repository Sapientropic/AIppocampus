"""Installable reference documentation guardrails."""

from __future__ import annotations

import re
from pathlib import Path


def installable_reference_tracker_identity_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for path in sorted((repo_root / "skills" / "aippocampus" / "references").glob("*.md")):
        rel_path = path.relative_to(repo_root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if re.search(r"#[0-9]{3,}", line):
                issues.append(
                    f"{rel_path}:{line_number} uses a private tracker number as running prose; "
                    "use a stable concept name and move provenance to repo-local docs"
                )
    return issues
