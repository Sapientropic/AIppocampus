"""Sanitized MCP runtime provenance for foreground diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.privacy import redact_private_paths


def _package_version() -> str:
    for name in ("aippocampus", "aippocampus-runtime"):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return "source-tree"


def _git_head(cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _git_root(cwd: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def mcp_runtime_provenance(
    arguments: dict[str, Any],
    *,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
) -> dict[str, Any]:
    cwd = core.canonical_path(str(arguments.get("cwd") or os.getcwd()))
    clean_source = Path(clean_source_dir).resolve() if clean_source_dir else None
    source_available = bool(clean_source and (clean_source / "messages.jsonl").is_file())
    registry_root = Path(registry_dir).resolve() if registry_dir else None
    payload = {
        "runtime": "mcp_stdio_handler",
        "package_version": _package_version(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "cwd_is_git_worktree": _git_root(cwd),
        "git_head": _git_head(cwd),
        "clean_source_mode": (
            "explicit" if arguments.get("clean_source_dir") else "resolved_default"
        ),
        "clean_source_available": source_available,
        "registry_mode": "explicit" if arguments.get("registry_dir") else "cwd_or_default",
        "registry_root_known": bool(registry_root),
        "local_paths_serialized": False,
    }
    return redact_private_paths({key: value for key, value in payload.items() if value not in (None, "")})
