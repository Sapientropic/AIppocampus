"""Privacy-safe diagnostics for remaining host/path compatibility surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def registry_legacy_alias_diagnostics(
    registry_resolution: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not registry_resolution:
        return []
    source = str(registry_resolution.get("source") or "")
    if source not in {
        "CODEX_HOME/aippocampus-registry",
        "default_CODEX_HOME/aippocampus-registry",
    }:
        return []
    return [
        {
            "alias": source,
            "canonical": "AIPPOCAMPUS_REGISTRY_DIR or AIPPOCAMPUS_HOME/registry",
            "surface": "registry_storage",
            "compatibility": "legacy_path_fallback",
            "status": "active",
            "value_printed": False,
            "local_paths_included": False,
        }
    ]


def project_local_path_diagnostics(
    *,
    workspace: Path | str | None,
    paths: Mapping[str, Path | str | None] | None,
) -> list[dict[str, Any]]:
    if workspace is None or not paths:
        return []
    cwd = Path(workspace).resolve()
    active_surfaces: list[str] = []
    for surface, raw_path in paths.items():
        if raw_path is None:
            continue
        try:
            rel = Path(raw_path).resolve().relative_to(cwd)
        except (OSError, ValueError):
            continue
        if rel.parts and rel.parts[0] == ".aippocampus":
            active_surfaces.append(surface)
    if not active_surfaces:
        return []
    return [
        {
            "alias": ".aippocampus/",
            "canonical": "AIppocampus registry storage or explicit export path",
            "surface": "project_local_output",
            "compatibility": "explicit_export_debug_only",
            "status": "active",
            "path_surfaces": sorted(set(active_surfaces)),
            "value_printed": False,
            "local_paths_included": False,
        }
    ]


def legacy_alias_diagnostics(
    *,
    registry_resolution: Mapping[str, Any] | None = None,
    workspace: Path | str | None = None,
    project_local_paths: Mapping[str, Path | str | None] | None = None,
) -> dict[str, Any]:
    path_active = [
        *registry_legacy_alias_diagnostics(registry_resolution),
        *project_local_path_diagnostics(workspace=workspace, paths=project_local_paths),
    ]
    return {
        "checked": True,
        "active": path_active,
        "active_count": len(path_active),
        "value_printed": False,
        "local_paths_included": False,
        "inventory": "docs/architecture/ops/legacy-alias-inventory.md",
    }
