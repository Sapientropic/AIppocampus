#!/usr/bin/env python3
"""Small public-safe provenance stamps for closeout-oriented reports."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return None


def git_worktree_evidence(repo_root: str | Path) -> dict[str, Any]:
    """Return a compact git state stamp without absolute paths.

    Readiness and dogfood reports are often pasted into issue closeouts. A
    passing probe from a dirty worktree can still be useful engineering
    evidence, but it is not clean-main closeout evidence unless the closeout
    explicitly says so. Keep this as report metadata rather than a runtime gate
    so exploratory diagnostics remain cheap and non-blocking.
    """

    root = Path(repo_root).resolve()
    head_proc = _run_git(root, ["rev-parse", "--short=12", "HEAD"])
    status_proc = _run_git(root, ["status", "--porcelain=v1"])
    head = head_proc.stdout.strip() if head_proc and head_proc.returncode == 0 else ""
    status_lines = (
        [line for line in status_proc.stdout.splitlines() if line.strip()]
        if status_proc and status_proc.returncode == 0
        else []
    )
    dirty_paths: list[str] = []
    for line in status_lines:
        raw_path = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", 1)[-1].strip()
        dirty_paths.append(raw_path.replace("\\", "/"))
    dirty = bool(dirty_paths)
    runtime_or_test_prefixes = (
        "skills/aippocampus/scripts/",
        "tests/aippocampus/",
        "tools/aippocampus/",
        "benchmarks/aippocampus/",
    )
    untracked_runtime_or_test = [
        path
        for line, path in zip(status_lines, dirty_paths, strict=False)
        if line.startswith("??") and path.startswith(runtime_or_test_prefixes)
    ]
    payload: dict[str, Any] = {
        "git_head": head,
        "git_dirty": dirty,
        "dirty_path_count": len(dirty_paths),
        "untracked_runtime_or_test_count": len(untracked_runtime_or_test),
        "evidence_scope": "dirty_worktree" if dirty else "clean_worktree",
        "clean_main_closeout_evidence": not dirty,
    }
    if dirty:
        payload["dirty_paths"] = dirty_paths[:40]
        payload["evidence_warning"] = {
            "code": "dirty_worktree_evidence",
            "message": (
                "Report ran on a dirty worktree; use as local validation evidence, "
                "not clean-main closeout evidence unless explicitly accepted."
            ),
            "acceptance_bearing": False,
        }
    return payload


__all__ = ["git_worktree_evidence"]
