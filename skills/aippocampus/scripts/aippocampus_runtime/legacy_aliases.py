"""Privacy-safe diagnostics for legacy env and path fallbacks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class LegacyEnvAlias:
    alias: str
    canonical: str
    surface: str
    compatibility: str


LEGACY_ENV_ALIASES: tuple[LegacyEnvAlias, ...] = (
    LegacyEnvAlias(
        "THREAD_MEMORY_REGISTRY_DIR",
        "AIPPOCAMPUS_REGISTRY_DIR",
        "registry_storage",
        "migration_only",
    ),
    LegacyEnvAlias(
        "CODEX_MEMORY_VAULT",
        "AIPPOCAMPUS_VAULT",
        "vault_projection",
        "migration_only",
    ),
    LegacyEnvAlias(
        "CODEX_MEMORY_STYLE_SOURCE",
        "AIPPOCAMPUS_STYLE_SOURCE",
        "vault_projection",
        "migration_only",
    ),
    LegacyEnvAlias(
        "CODEX_MEMORY_SCRIPT_SOURCE",
        "AIPPOCAMPUS_SCRIPT_SOURCE",
        "vault_projection",
        "migration_only",
    ),
    LegacyEnvAlias(
        "CODEX_MEMORY_SITE_MARK",
        "AIPPOCAMPUS_SITE_MARK",
        "vault_projection",
        "migration_only",
    ),
    LegacyEnvAlias(
        "CODEX_MEMORY_SITE_TITLE",
        "AIPPOCAMPUS_SITE_TITLE",
        "vault_projection",
        "migration_only",
    ),
    LegacyEnvAlias(
        "DEEPSEEK_BASE_URL",
        "AIPPOCAMPUS_DEEPSEEK_BASE_URL",
        "model_routing",
        "migration_only",
    ),
    LegacyEnvAlias(
        "DEEPSEEK_MODEL",
        "AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL",
        "model_routing",
        "migration_only",
    ),
    LegacyEnvAlias(
        "DEEPSEEK_PRO_MODEL",
        "AIPPOCAMPUS_DEEPSEEK_PRO_MODEL",
        "model_routing",
        "migration_only",
    ),
    LegacyEnvAlias(
        "DEEPSEEK_API_KEY",
        "AIPPOCAMPUS_DEEPSEEK_API_KEY",
        "model_routing",
        "migration_only",
    ),
    LegacyEnvAlias(
        "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK",
        "AIPPOCAMPUS_SUBCONSCIOUS_HOOK",
        "subconscious_scheduler",
        "typo_compatibility",
    ),
)


def _configured(env: Mapping[str, str], name: str) -> bool:
    return bool(str(env.get(name) or "").strip())


def _env_alias_entry(alias: LegacyEnvAlias, *, active: bool) -> dict[str, Any]:
    return {
        "alias": alias.alias,
        "canonical": alias.canonical,
        "surface": alias.surface,
        "compatibility": alias.compatibility,
        "status": "active" if active else "shadowed_by_canonical",
        "value_printed": False,
        "local_paths_included": False,
    }


def env_legacy_alias_diagnostics(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Report legacy env fallback usage without reading or printing values."""

    current_env = env if env is not None else os.environ
    active: list[dict[str, Any]] = []
    shadowed: list[dict[str, Any]] = []
    for alias in LEGACY_ENV_ALIASES:
        if not _configured(current_env, alias.alias):
            continue
        canonical_configured = _configured(current_env, alias.canonical)
        entry = _env_alias_entry(alias, active=not canonical_configured)
        if canonical_configured:
            shadowed.append(entry)
        else:
            active.append(entry)
    return {
        "checked": True,
        "active": active,
        "shadowed": shadowed,
        "active_count": len(active),
        "shadowed_count": len(shadowed),
        "value_printed": False,
        "local_paths_included": False,
    }


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
    env: Mapping[str, str] | None = None,
    registry_resolution: Mapping[str, Any] | None = None,
    workspace: Path | str | None = None,
    project_local_paths: Mapping[str, Path | str | None] | None = None,
) -> dict[str, Any]:
    env_report = env_legacy_alias_diagnostics(env)
    path_active = [
        *registry_legacy_alias_diagnostics(registry_resolution),
        *project_local_path_diagnostics(workspace=workspace, paths=project_local_paths),
    ]
    active = [*env_report["active"], *path_active]
    return {
        "checked": True,
        "active": active,
        "shadowed": env_report["shadowed"],
        "active_count": len(active),
        "shadowed_count": env_report["shadowed_count"],
        "value_printed": False,
        "local_paths_included": False,
        "inventory": "docs/architecture/ops/legacy-alias-inventory.md",
    }
