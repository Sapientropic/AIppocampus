"""Plugin cache status projection for the local update facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.update.plugin_cache import (
    build_plugin_cache_status,
    installed_cache_auto_resolution,
    unique_installed_cache_root,
)
from aippocampus_runtime.update.plugin_marketplace import configured_marketplace_root


def enrich_plugin_cache_status(
    plugin: dict[str, Any],
    *,
    repo_root: Path,
    codex_home_path: Path,
    default_plugin_output: Path,
    plugin_output: Path | None = None,
    plugin_marketplace_dir: Path | None = None,
    plugin_installed_dir: Path | str | None = None,
) -> dict[str, Any]:
    output = plugin_output or repo_root / default_plugin_output
    installed_arg_auto = (
        str(plugin_installed_dir).strip().casefold() == "auto"
        if plugin_installed_dir is not None
        else False
    )
    if installed_arg_auto:
        resolved_installed_dir = unique_installed_cache_root(codex_home_path)
    elif plugin_installed_dir is not None:
        resolved_installed_dir = Path(plugin_installed_dir)
    else:
        resolved_installed_dir = None
    resolved_marketplace_dir = plugin_marketplace_dir
    if resolved_marketplace_dir is not None:
        marketplace_dir_source = "explicit_argument"
    else:
        resolved_marketplace_dir = configured_marketplace_root(codex_home_path)
        marketplace_dir_source = (
            "configured_codex_marketplace"
            if resolved_marketplace_dir is not None
            else "not_configured"
        )
    cache_status = build_plugin_cache_status(
        source_root=repo_root / "plugins" / "aippocampus",
        package_root=output,
        codex_home_path=codex_home_path,
        marketplace_dir=resolved_marketplace_dir,
        installed_dir=resolved_installed_dir,
    )
    plugin.update(
        {
            "source_plugin_version": cache_status["source_plugin_version"],
            "package_plugin_version": cache_status["package_plugin_version"],
            "local_marketplace": cache_status["local_marketplace"],
            "local_marketplace_source": marketplace_dir_source,
            "installed_cache": cache_status["installed_cache"],
            "auto_detected_installed_cache_count": cache_status[
                "auto_detected_installed_cache_count"
            ],
            # owner: plugin status projection; removal: follows plugin_cache's
            # legacy-cache detector sunset; default/exposure: count only, no
            # local cache root paths.
            "ignored_legacy_cache_count": cache_status["ignored_legacy_cache_count"],
            "installed_cache_auto_resolution": cache_status[
                "installed_cache_auto_resolution"
            ],
            "plugin_cache_recommended_actions": cache_status["recommended_actions"],
            "cache_boundary": cache_status["boundary"],
        }
    )
    if installed_arg_auto:
        plugin["explicit_installed_cache_auto_resolution"] = installed_cache_auto_resolution(
            codex_home_path
        )
    return plugin
