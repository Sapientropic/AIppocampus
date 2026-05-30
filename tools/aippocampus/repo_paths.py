#!/usr/bin/env python3
"""Repo-local import bootstrap for AIppocampus maintenance tools.

The installable runtime remains script-first under ``skills/aippocampus/scripts``.
This helper is only for repository-owned docs, smoke, and benchmark tools that
need to import those scripts while running from an uninstalled checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple


class RepoImportPaths(NamedTuple):
    repo_root: Path
    skill_root: Path
    skill_scripts: Path
    docs_tools: Path
    smoke_tools: Path
    benchmark_tools: Path


def discover_repo_root(anchor: Path | None = None) -> Path:
    start = (anchor or Path(__file__)).resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "skills" / "aippocampus" / "scripts").is_dir()
        ):
            return candidate
    raise RuntimeError(f"could not locate AIppocampus repo root from {start}")


def repo_import_paths(anchor: Path | None = None) -> RepoImportPaths:
    repo_root = discover_repo_root(anchor)
    return RepoImportPaths(
        repo_root=repo_root,
        skill_root=repo_root / "skills" / "aippocampus",
        skill_scripts=repo_root / "skills" / "aippocampus" / "scripts",
        docs_tools=repo_root / "tools" / "aippocampus" / "docs",
        smoke_tools=repo_root / "tools" / "aippocampus" / "smoke",
        benchmark_tools=repo_root / "benchmarks" / "aippocampus",
    )


def prepend_once(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def ensure_repo_imports(
    anchor: Path | None = None,
    *,
    include_smoke_tools: bool = False,
    include_docs_tools: bool = False,
    include_benchmark_tools: bool = False,
) -> RepoImportPaths:
    paths = repo_import_paths(anchor)
    entries = [paths.skill_scripts]
    if include_smoke_tools:
        entries.append(paths.smoke_tools)
    if include_docs_tools:
        entries.append(paths.docs_tools)
    if include_benchmark_tools:
        entries.append(paths.benchmark_tools)
    for entry in entries:
        prepend_once(entry)
    return paths


__all__ = [
    "RepoImportPaths",
    "discover_repo_root",
    "ensure_repo_imports",
    "repo_import_paths",
]
