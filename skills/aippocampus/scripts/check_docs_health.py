#!/usr/bin/env python3
"""Lightweight guardrails for keeping AIppocampus docs maintainable."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MAX_SKILL_LINES = 220
MAX_SKILL_WORDS = 2600
MAX_SKILL_CODE_FENCES = 2

REQUIRED_REFERENCES = [
    "ambient-hooks.md",
    "retrieval-and-storage.md",
    "maintenance-and-operations.md",
    "subconscious-jobs.md",
]

REQUIRED_PROJECT_DOCS = [
    "docs/README.md",
    "docs/roadmap.md",
    "docs/next-iteration-plan.md",
    "docs/gb-scale-roadmap.md",
    "docs/wukong-mining-notes.md",
    "docs/technical-differentiation-analysis.md",
]

REQUIRED_PRIVATE_GITIGNORE_PATTERNS = [
    ".aippocampus/",
    "aippocampus-registry/",
    "thread-anchors.md",
]

ORIGIN_PHRASES = [
    "生命还能变成什么，而我能不能在变化后仍然是我。",
]


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def find_repo_root(skill_root: Path) -> Path | None:
    for candidate in [skill_root.parent.parent, *skill_root.parents]:
        if (candidate / "README.md").exists() and (candidate / "skills" / skill_root.name).exists():
            return candidate
    return None


def check_repo_docs(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    metrics: dict[str, Any] = {"repo_docs_checked": True}

    origin_stub = repo_root / "docs" / "origin.md"
    if origin_stub.exists():
        issues.append("docs/origin.md duplicates the origin essay; link docs/the-unfinished-map.md instead")

    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        issues.append("missing .gitignore for private generated memory artifacts")
    else:
        ignored = {
            line.strip().strip("/")
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for pattern in REQUIRED_PRIVATE_GITIGNORE_PATTERNS:
            if pattern.strip("/") not in ignored:
                issues.append(f"private generated artifact is not gitignored: {pattern}")

    essay = repo_root / "docs" / "the-unfinished-map.md"
    if not essay.exists():
        issues.append("missing canonical origin essay: docs/the-unfinished-map.md")
        return issues, metrics

    markdown_files = [
        path
        for path in repo_root.rglob("*.md")
        if ".git" not in path.parts and "__pycache__" not in path.parts
    ]
    metrics["repo_markdown_files"] = len(markdown_files)
    for phrase in ORIGIN_PHRASES:
        owners = [
            path.relative_to(repo_root).as_posix()
            for path in markdown_files
            if phrase in path.read_text(encoding="utf-8")
        ]
        if owners != ["docs/the-unfinished-map.md"]:
            issues.append(
                f"origin phrase should live only in docs/the-unfinished-map.md; found in {owners}"
            )
    return issues, metrics


def check_docs(root: Path) -> dict[str, Any]:
    root = root.resolve()
    skill_path = root / "SKILL.md"
    issues: list[str] = []

    if not skill_path.exists():
        return {
            "ok": False,
            "issues": [f"missing {skill_path}"],
            "metrics": {},
        }

    text = skill_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    word_count = count_words(text)
    code_fence_count = text.count("```")
    metrics = {
        "skill_lines": len(lines),
        "skill_words": word_count,
        "skill_code_fences": code_fence_count,
        "required_references": len(REQUIRED_REFERENCES),
    }

    if len(lines) > MAX_SKILL_LINES:
        issues.append(f"SKILL.md has {len(lines)} lines; keep it <= {MAX_SKILL_LINES}")
    if word_count > MAX_SKILL_WORDS:
        issues.append(f"SKILL.md has {word_count} words; keep it <= {MAX_SKILL_WORDS}")
    if code_fence_count > MAX_SKILL_CODE_FENCES:
        issues.append(
            f"SKILL.md has {code_fence_count} code-fence markers; move command dumps to references"
        )

    references_dir = root / "references"
    for filename in REQUIRED_REFERENCES:
        ref_path = references_dir / filename
        if not ref_path.exists():
            issues.append(f"missing reference: references/{filename}")
        if filename not in text:
            issues.append(f"SKILL.md does not link references/{filename}")

    if "changelog" in text.lower() and "Do not append changelog-style notes" not in text:
        issues.append("SKILL.md mentions changelog without the stable-entrypoint guardrail")

    repo_root = find_repo_root(root)
    if repo_root:
        for rel_path in REQUIRED_PROJECT_DOCS:
            if not (repo_root / rel_path).exists():
                issues.append(f"missing project doc: {rel_path}")
        repo_issues, repo_metrics = check_repo_docs(repo_root)
        issues.extend(repo_issues)
        metrics.update(repo_metrics)
    else:
        metrics["repo_docs_checked"] = False

    return {
        "ok": not issues,
        "issues": issues,
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="AIppocampus skill root. Defaults to this script's parent skill directory.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    result = check_docs(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"docs health: {status}")
        for key, value in result["metrics"].items():
            print(f"{key}: {value}")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
