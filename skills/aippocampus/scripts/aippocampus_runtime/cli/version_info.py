"""Version metadata helpers for the public CLI facade."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by older runtimes.
    tomllib = None  # type: ignore[assignment]

SCRIPT_DIR = Path(__file__).resolve().parents[2]
PLUGIN_MANIFEST_RELATIVE = Path("plugins") / "aippocampus" / ".codex-plugin" / "plugin.json"

def _find_project_root(start: Path = SCRIPT_DIR) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _pyproject_version(root: Path | None) -> str | None:
    if root is None:
        return None
    if tomllib is None:
        return None
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except Exception:
        return None
    project = data.get("project") if isinstance(data, dict) else None
    return str(project.get("version") or "") if isinstance(project, dict) else None


def _distribution_version() -> str | None:
    try:
        return importlib.metadata.version("aippocampus")
    except importlib.metadata.PackageNotFoundError:
        return None


def version_payload() -> dict[str, Any]:
    root = _find_project_root()
    pyproject = _pyproject_version(root)
    plugin = _json_file(root / PLUGIN_MANIFEST_RELATIVE) if root else None
    plugin_version = str((plugin or {}).get("version") or "") or None
    active_version = pyproject or _distribution_version() or plugin_version or "unknown"
    versions = {
        "active": active_version,
        "pyproject": pyproject,
        "installed_distribution": _distribution_version(),
        "plugin_manifest": plugin_version,
    }
    known = {value for value in versions.values() if value}
    return {
        "kind": "aippocampus_version",
        "ok": bool(active_version and active_version != "unknown"),
        "version": active_version,
        "versions": versions,
        "metadata_consistent": len(known) <= 1,
        "source_checkout_available": root is not None,
        "runtime": {
            "facade": "aippocampus_runtime.cli.facade",
            "python": Path(sys.executable).name,
        },
    }


def render_version_text(payload: dict[str, Any]) -> str:
    version = payload.get("version") or "unknown"
    suffix = "" if payload.get("metadata_consistent") else " (metadata mismatch)"
    return f"AIppocampus {version}{suffix}"


