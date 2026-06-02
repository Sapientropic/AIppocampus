"""Provider-neutral registry storage path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def aippocampus_home() -> Path | None:
    env = os.environ.get("AIPPOCAMPUS_HOME")
    return Path(env) if env else None


def legacy_codex_home(home: Path | None = None) -> Path:
    if home is not None:
        return home
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else Path.home() / ".codex"


def aippocampus_registry_resolution(home: Path | None = None) -> dict[str, Any]:
    """Resolve generated AIppocampus registry storage without moving data.

    `AIPPOCAMPUS_REGISTRY_DIR` is the exact provider-neutral registry root.
    `AIPPOCAMPUS_HOME` is an optional broader home concept whose registry lives
    under `registry/`. Legacy Codex homes remain a fallback only, so existing
    users keep their data while new non-Codex setups can avoid importing Codex
    host helpers just to resolve AIppocampus storage.
    """

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
    legacy_home = legacy_codex_home(home)
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
