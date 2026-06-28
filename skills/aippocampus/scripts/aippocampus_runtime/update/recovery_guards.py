"""Update recovery/readiness guards for explicit local apply flows.

The update CLI discovers paths and performs writes, but foreground recovery
cards live here so apply/status do not grow separate dirty-worktree semantics.
Dirty worktrees are acceptance-bearing for local sync: agents must inspect or
force explicitly instead of silently overwriting user edits.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

WritePathResolver = Callable[[str, argparse.Namespace], dict[str, Path]]
DirtyOverlapResolver = Callable[[list[Path]], list[dict[str, Any]]]


def dirty_worktree_recovery(
    surface: str,
    write_paths: dict[str, Path],
    overlaps: list[dict[str, Any]],
    *,
    schema_version: int,
) -> dict[str, Any]:
    dirty_paths = sorted(
        {str(item.get("dirty_path") or "") for item in overlaps if item.get("dirty_path")}
    )
    git_roots = sorted(
        {str(item.get("git_root") or "") for item in overlaps if item.get("git_root")}
    )
    return {
        "schema_version": schema_version,
        "kind": "aippocampus_update_recovery",
        "mode": "apply_recovery",
        "ok": False,
        "status": "blocked_dirty_worktree",
        "surface": surface,
        "dirty_worktree_detected": True,
        "dirty_paths": dirty_paths,
        "git_roots": git_roots,
        "would_write": {key: str(value) for key, value in write_paths.items()},
        "safe_next_actions": [
            {
                "label": "inspect dirty worktree",
                "command": "git status --short",
                "mutation_risk": "read_only",
            },
            {
                "label": "preview update plan",
                "command": "aippocampus update plan --json",
                "mutation_risk": "read_only",
            },
        ],
        "override": "rerun with --force-dirty-worktree only after human review",
        "override_used": False,
        "safety": {
            "no_write_happened": True,
            "auto_stash": False,
            "auto_cleanup": False,
        },
    }


def dirty_worktree_blocker(
    surface: str,
    args: argparse.Namespace,
    *,
    write_paths_for_surface: WritePathResolver,
    dirty_overlaps: DirtyOverlapResolver,
    schema_version: int,
) -> dict[str, Any] | None:
    write_paths = write_paths_for_surface(surface, args)
    if not write_paths:
        return None
    overlaps = dirty_overlaps(list(write_paths.values()))
    if not overlaps:
        return None
    return dirty_worktree_recovery(
        surface,
        write_paths,
        overlaps,
        schema_version=schema_version,
    )


def status_dirty_worktree_guards(
    args: argparse.Namespace,
    surfaces: list[str],
    *,
    write_paths_for_surface: WritePathResolver,
    dirty_overlaps: DirtyOverlapResolver,
    schema_version: int,
) -> dict[str, dict[str, Any]]:
    guards: dict[str, dict[str, Any]] = {}
    if getattr(args, "force_dirty_worktree", False):
        return guards
    for surface in surfaces:
        blocker = dirty_worktree_blocker(
            surface,
            args,
            write_paths_for_surface=write_paths_for_surface,
            dirty_overlaps=dirty_overlaps,
            schema_version=schema_version,
        )
        if blocker is None:
            continue
        guards[surface] = {
            "status": "blocked_dirty_worktree",
            "dirty_worktree_detected": True,
            "dirty_paths": list(blocker.get("dirty_paths") or []),
            "would_write": {
                str(key): "path_redacted"
                for key in (blocker.get("would_write") or {}).keys()
            },
            "safe_next_actions": list(blocker.get("safe_next_actions") or []),
            "override": blocker.get("override"),
            "safety": blocker.get("safety") or {},
        }
    return guards


__all__ = [
    "dirty_worktree_blocker",
    "dirty_worktree_recovery",
    "status_dirty_worktree_guards",
]
