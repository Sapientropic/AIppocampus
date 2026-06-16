"""Reader-path diagnostics for the public docs entry flow."""

from __future__ import annotations

from pathlib import Path

REQUIRED_READER_PATH_TERMS = {
    "README.md": {
        "docs/start-here.md": "root README missing docs/start-here.md reader-path pointer",
    },
    "docs/README.md": {
        "start-here.md": "docs README missing start-here reader-path pointer",
        "start-here.md#first-recall": "docs README missing first-recall reader path",
        "start-here.md#coding-agent-user": "docs README missing coding-agent reader path",
        "start-here.md#maintainer": "docs README missing maintainer reader path",
        "start-here.md#benchmark-or-claim-reviewer": (
            "docs README missing benchmark reviewer reader path"
        ),
        "start-here.md#continuity-and-research-reader": (
            "docs README missing continuity/research reader path"
        ),
    },
    "docs/start-here.md": {
        "aippocampus agent recall": "start-here missing executable first-recall command",
        "aippocampus agent deepen --request 1 --last-recall --json": (
            "start-here missing executable deepen command"
        ),
        "guides/public-api.md#ten-minute-public-path": (
            "start-here missing 10-minute public API path"
        ),
        "guides/install-guide.md#first-recall-path": (
            "start-here missing first-recall install path"
        ),
        "guides/coding-agent-memory.md": "start-here missing coding-agent path",
        "architecture/README.md": "start-here missing maintainer architecture path",
        "evidence/current-claims.md": "start-here missing current-claims path",
        "research/README.md": "start-here missing research path",
    },
    "llms.txt": {
        "uvx aippocampus agent recall": "llms.txt missing executable first-recall command",
        "uvx aippocampus mcp status --json": "llms.txt missing compact MCP readiness command",
        "uvx aippocampus mcp list-tools": "llms.txt missing full MCP schema fallback",
    },
}


def reader_path_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path, required_terms in REQUIRED_READER_PATH_TERMS.items():
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing reader-path doc: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for term, issue in required_terms.items():
            if term not in text:
                issues.append(issue)
    return issues
