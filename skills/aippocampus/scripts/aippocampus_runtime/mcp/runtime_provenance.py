"""Sanitized MCP runtime provenance for foreground diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
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
    registry_root = Path(registry_dir).resolve() if registry_dir else core.aippocampus_registry_dir().resolve()
    registry_json = registry_root / "threads.json"
    registry_entry_count = 0
    if registry_json.is_file():
        try:
            import json

            registry_payload = json.loads(registry_json.read_text(encoding="utf-8"))
            if isinstance(registry_payload, dict):
                registry_entry_count = len(
                    [item for item in registry_payload.get("threads") or [] if isinstance(item, dict)]
                )
        except Exception:
            registry_entry_count = 0
    resolution = core.aippocampus_registry_resolution()
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
        "registry_mode": "explicit" if arguments.get("registry_dir") else "default_registry",
        "registry_resolution_source": resolution.get("source"),
        "registry_root_known": bool(registry_root),
        "registry_entries_available": registry_entry_count > 0,
        "registry_entry_count": registry_entry_count,
        "local_paths_serialized": False,
    }
    return redact_private_paths({key: value for key, value in payload.items() if value not in (None, "")})


def compact_runtime_provenance(value: Any) -> dict[str, Any] | None:
    """Keep foreground MCP provenance useful without turning compact recall into diagnostics."""

    if not isinstance(value, Mapping):
        return None
    keys = (
        "runtime",
        "clean_source_mode",
        "clean_source_available",
        "registry_mode",
        "registry_entries_available",
        "registry_entry_count",
        "local_paths_serialized",
    )
    return {key: item for key in keys if (item := value.get(key)) not in (None, "")}
