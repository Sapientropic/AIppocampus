"""Docs-health guard for legacy env and path alias inventory coverage."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

LEGACY_ALIAS_INVENTORY_DOC = "docs/architecture/legacy-alias-inventory.md"

LEGACY_ALIAS_POINTER_DOCS = {
    "docs/README.md": (
        "architecture/legacy-alias-inventory.md",
        "docs README missing legacy alias inventory pointer",
    ),
    "docs/guides/public-api.md": (
        "../architecture/legacy-alias-inventory.md",
        "public API doc missing legacy alias inventory pointer",
    ),
}

LEGACY_ENV_ALIAS_RE = re.compile(
    r"\b(?:CODEX_MEMORY|THREAD_MEMORY)_[A-Z0-9_]+\b"
    r"|\bAIIPPOCAMPUS_SUBCONSCIOUS_HOOK\b"
    r"|\bDEEPSEEK_(?:BASE_URL|MODEL|PRO_MODEL|API_KEY)\b"
)

LEGACY_PATH_ALIAS_PATTERNS = {
    "CODEX_HOME/aippocampus-registry": re.compile(
        r"(?:\$?CODEX_HOME|default_CODEX_HOME)/aippocampus-registry"
    ),
    ".aippocampus/": re.compile(r"(?<![\w.-])\.aippocampus(?:[/\\]|\b)"),
}

LEGACY_ALIAS_SCAN_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".json",
}

LEGACY_ALIAS_SCAN_FILENAMES = {
    ".env.example",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
}

LEGACY_ALIAS_SCAN_ROOTS = (
    ".env.example",
    ".github",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "docs",
    "skills",
    "tools",
)

LEGACY_ALIAS_GREP_NEEDLES = (
    "CODEX_MEMORY_",
    "THREAD_MEMORY_",
    "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_PRO_MODEL",
    "DEEPSEEK_API_KEY",
    "CODEX_HOME/aippocampus-registry",
    "default_CODEX_HOME/aippocampus-registry",
    ".aippocampus",
)

LEGACY_ALIAS_SCAN_EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
    "reviews",
}


def legacy_alias_scan_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    candidates = git_legacy_alias_scan_candidates(repo_root)
    if not candidates:
        candidates = fallback_legacy_alias_scan_candidates(repo_root)

    for path in candidates:
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            continue
        rel_parts = rel.parts
        rel_posix = rel.as_posix()
        if rel_posix.startswith("docs/archive/"):
            continue
        if any(part in LEGACY_ALIAS_SCAN_EXCLUDED_PARTS for part in rel_parts):
            continue
        if path.name in LEGACY_ALIAS_SCAN_FILENAMES or path.suffix in LEGACY_ALIAS_SCAN_SUFFIXES:
            paths.append(path)
    return paths


def git_legacy_alias_scan_candidates(repo_root: Path) -> list[Path]:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                *LEGACY_ALIAS_SCAN_ROOTS,
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    return [repo_root / line.strip() for line in proc.stdout.splitlines() if line.strip()]


def fallback_legacy_alias_scan_candidates(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for root_name in LEGACY_ALIAS_SCAN_ROOTS:
        root = repo_root / root_name
        if root.is_file():
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    return candidates


def legacy_alias_tokens_from_text(text: str) -> tuple[set[str], set[str]]:
    aliases = {match.group(0) for match in LEGACY_ENV_ALIAS_RE.finditer(text)}
    path_aliases = {
        alias for alias, pattern in LEGACY_PATH_ALIAS_PATTERNS.items() if pattern.search(text)
    }
    return aliases, path_aliases


def git_legacy_alias_tokens(repo_root: Path) -> tuple[set[str], set[str]] | None:
    roots = [root for root in LEGACY_ALIAS_SCAN_ROOTS if (repo_root / root).exists()]
    if not roots:
        return None
    grep_command = [
        "git",
        "-C",
        str(repo_root),
        "grep",
        "-I",
        "-n",
        "-F",
    ]
    for needle in LEGACY_ALIAS_GREP_NEEDLES:
        grep_command.extend(["-e", needle])
    grep_command.extend(["--", *roots])
    try:
        proc = subprocess.run(
            grep_command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode not in {0, 1}:
        return None

    aliases: set[str] = set()
    path_aliases: set[str] = set()
    for raw_line in proc.stdout.splitlines():
        try:
            rel_path, _line_no, text = raw_line.split(":", maxsplit=2)
        except ValueError:
            continue
        if rel_path.startswith("docs/archive/"):
            continue
        text_aliases, text_path_aliases = legacy_alias_tokens_from_text(text)
        aliases.update(text_aliases)
        path_aliases.update(text_path_aliases)

    untracked = git_untracked_legacy_alias_scan_candidates(repo_root, roots)
    file_aliases, file_path_aliases = legacy_alias_tokens_from_files(untracked, repo_root=repo_root)
    aliases.update(file_aliases)
    path_aliases.update(file_path_aliases)
    return aliases, path_aliases


def git_untracked_legacy_alias_scan_candidates(repo_root: Path, roots: list[str]) -> list[Path]:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                *roots,
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [repo_root / line.strip() for line in proc.stdout.splitlines() if line.strip()]


def legacy_alias_tokens_from_files(
    paths: list[Path],
    *,
    repo_root: Path,
) -> tuple[set[str], set[str]]:
    aliases: set[str] = set()
    path_aliases: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            continue
        if rel.as_posix().startswith("docs/archive/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text_aliases, text_path_aliases = legacy_alias_tokens_from_text(text)
        aliases.update(text_aliases)
        path_aliases.update(text_path_aliases)
    return aliases, path_aliases


def legacy_alias_inventory_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    inventory_path = repo_root / LEGACY_ALIAS_INVENTORY_DOC
    if not inventory_path.exists():
        return [f"missing legacy alias inventory: {LEGACY_ALIAS_INVENTORY_DOC}"]

    inventory_text = inventory_path.read_text(encoding="utf-8")
    for rel_path, (pointer, issue) in LEGACY_ALIAS_POINTER_DOCS.items():
        path = repo_root / rel_path
        if path.exists() and pointer not in path.read_text(encoding="utf-8"):
            issues.append(issue)

    scanned_tokens = git_legacy_alias_tokens(repo_root)
    if scanned_tokens is None:
        aliases, path_aliases = legacy_alias_tokens_from_files(
            legacy_alias_scan_paths(repo_root),
            repo_root=repo_root,
        )
    else:
        aliases, path_aliases = scanned_tokens

    for alias in sorted(aliases | path_aliases):
        if f"`{alias}`" not in inventory_text:
            issues.append(
                f"legacy/provider-specific env or path missing inventory classification: {alias}; "
                f"update {LEGACY_ALIAS_INVENTORY_DOC}"
            )
    return issues
