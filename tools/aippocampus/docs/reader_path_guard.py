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
        "guides/ten-minute-public-path.md": (
            "start-here missing 10-minute public path"
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
        "docs/guides/ten-minute-public-path.md": "llms.txt missing 10-minute path doc",
        "uvx aippocampus agent recall": "llms.txt missing executable first-recall command",
        "uvx aippocampus mcp status --json": "llms.txt missing compact MCP readiness command",
        "uvx aippocampus mcp list-tools": "llms.txt missing full MCP schema fallback",
    },
}

CLAUDE_CODE_HOOK_FRONTDOORS = (
    "README.md",
    "llms.txt",
    "docs/guides/coding-agent-memory.md",
    "docs/guides/setup/claude-code-mcp.md",
    "docs/guides/public-api.md",
    "docs/guides/ecosystem-integration-matrix.md",
    "docs/guides/install-guide.md",
)

CLAUDE_CODE_HOOK_DENIALS = (
    "no aippocampus claude hooks",
    "not aippocampus claude hook",
    "does not have aippocampus claude hook",
)


def claude_code_hook_drift_issues(repo_root: Path) -> list[str]:
    denial_refs: list[str] = []
    install_refs: list[str] = []
    for rel_path in CLAUDE_CODE_HOOK_FRONTDOORS:
        path = repo_root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        lowered = text.casefold()
        if any(phrase in lowered for phrase in CLAUDE_CODE_HOOK_DENIALS):
            denial_refs.append(rel_path)
        if "aippocampus hooks claude-code install --json" in text:
            install_refs.append(rel_path)
    if not denial_refs or not install_refs:
        return []
    return [
        "Claude Code hook docs disagree: "
        f"denial in {', '.join(denial_refs)} while install appears in "
        f"{', '.join(install_refs)}"
    ]


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
    issues.extend(claude_code_hook_drift_issues(repo_root))
    return issues
