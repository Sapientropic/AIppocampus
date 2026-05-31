#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus core helpers."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aippocampus_runtime.core import *  # noqa: F403

try:
    from aippocampus_runtime import core as _core
except ModuleNotFoundError:
    # Prompt/lifecycle hooks can momentarily run after only the top-level hook
    # files and this compatibility helper were copied into Codex home. Keep this
    # fallback intentionally tiny: the package owner remains the real API, while
    # the half-installed hook path can still write/skip safely instead of
    # crashing before the lazy recall runtime import gets a chance to degrade.
    def now_utc() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def codex_home() -> Path:
        env = os.environ.get("CODEX_HOME")
        return Path(env) if env else Path.home() / ".codex"

    def aippocampus_home() -> Path | None:
        env = os.environ.get("AIPPOCAMPUS_HOME")
        return Path(env) if env else None

    def aippocampus_registry_resolution(home: Path | None = None) -> dict[str, Any]:
        env = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        if env:
            return {
                "path": str(Path(env)),
                "source": "AIPPOCAMPUS_REGISTRY_DIR",
                "legacy_fallback": False,
            }
        legacy_env = os.environ.get("THREAD_MEMORY_REGISTRY_DIR")
        if legacy_env:
            return {
                "path": str(Path(legacy_env)),
                "source": "THREAD_MEMORY_REGISTRY_DIR",
                "legacy_fallback": True,
            }
        aippo_home = aippocampus_home()
        if aippo_home:
            return {
                "path": str(aippo_home / "registry"),
                "source": "AIPPOCAMPUS_HOME/registry",
                "legacy_fallback": False,
            }
        legacy_home = home or codex_home()
        return {
            "path": str(legacy_home / "aippocampus-registry"),
            "source": (
                "CODEX_HOME/aippocampus-registry"
                if os.environ.get("CODEX_HOME") or home
                else "default_CODEX_HOME/aippocampus-registry"
            ),
            "legacy_fallback": True,
        }

    def aippocampus_registry_dir(home: Path | None = None) -> Path:
        return Path(str(aippocampus_registry_resolution(home)["path"]))
else:
    sys.modules[__name__] = _core
