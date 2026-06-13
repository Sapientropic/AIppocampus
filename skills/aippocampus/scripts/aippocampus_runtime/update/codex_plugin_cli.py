"""Codex plugin CLI compatibility helpers for the local installer."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def codex_base(codex_command: str | list[str] | None = None) -> list[str]:
    if isinstance(codex_command, list):
        return list(codex_command)
    command = str(codex_command or "codex")
    if os.name != "nt" or Path(command).suffix:
        return [command]
    # Python's shell=False process creation can find the extensionless npm shim
    # before the runnable Windows launcher. Prefer explicit wrappers so plugin
    # install works outside PowerShell alias expansion.
    for candidate in (f"{command}.cmd", f"{command}.exe", f"{command}.bat"):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    return [command]


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def run_text(
    runner: CommandRunner,
    command: list[str],
    *,
    allow_already_registered: bool = False,
    allow_non_git_marketplace: bool = False,
) -> dict[str, Any]:
    proc = runner(command)
    output = (proc.stdout or "") + (proc.stderr or "")
    output_lower = output.casefold()
    already_registered = "already" in output_lower and any(
        word in output_lower for word in ("marketplace", "registered", "exists", "configured")
    )
    non_git_marketplace = "not configured as a git marketplace" in output_lower
    allowed_failure = (allow_already_registered and already_registered) or (
        allow_non_git_marketplace and non_git_marketplace
    )
    if proc.returncode != 0 and not allowed_failure:
        tail = output.strip()[-1200:]
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(command[:4])}; {tail}"
        )
    return {
        "ok": proc.returncode == 0 or allowed_failure,
        "returncode": proc.returncode,
        "already_registered": already_registered,
        "skipped_non_git": non_git_marketplace,
        "stdout_tail": (proc.stdout or "").strip()[-1200:],
        "stderr_tail": (proc.stderr or "").strip()[-1200:],
        "command": command[:4],
    }


def installed_cache_dir(
    codex_home_path: Path,
    *,
    marketplace_name: str,
    plugin_name: str,
    version: str,
) -> Path:
    if not version:
        raise ValueError("plugin package manifest is missing a version")
    return codex_home_path / "plugins" / "cache" / marketplace_name / plugin_name / version


def remove_installed_cache(
    codex_home_path: Path,
    *,
    marketplace_name: str,
    plugin_name: str,
) -> bool:
    cache_root = codex_home_path.resolve() / "plugins" / "cache" / marketplace_name / plugin_name
    if not cache_root.exists():
        return False
    if not path_is_under(cache_root, codex_home_path / "plugins" / "cache"):
        raise ValueError("refusing to remove plugin cache outside Codex cache root")
    shutil.rmtree(cache_root)
    return True
