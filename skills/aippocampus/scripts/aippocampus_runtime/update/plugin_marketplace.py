"""Shared local marketplace paths and ownership checks for the Codex plugin."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from aippocampus_runtime.core import codex_home

PLUGIN_NAME = "aippocampus"
MARKETPLACE_NAME = "aippocampus-local"
MARKETPLACE_RELATIVE_MANIFEST = Path(".agents") / "plugins" / "marketplace.json"
MARKETPLACE_MARKER = ".aippocampus-owned-marketplace.json"


def default_marketplace_root(codex_home_path: Path | None = None) -> Path:
    return Path(codex_home_path or codex_home()).expanduser() / "aippocampus-marketplace"


def _local_source_path(value: object) -> Path | None:
    source = str(value or "").strip()
    if not source:
        return None
    if "://" in source or source.count("/") == 1 and "\\" not in source and ":" not in source:
        return None
    if source.startswith("\\\\?\\"):
        source = source[4:]
    return Path(source).expanduser()


def configured_marketplace_root(
    codex_home_path: Path | None = None,
    *,
    marketplace_name: str = MARKETPLACE_NAME,
) -> Path | None:
    config_path = Path(codex_home_path or codex_home()).expanduser() / "config.toml"
    if not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    marketplaces = data.get("marketplaces")
    if not isinstance(marketplaces, dict):
        return None
    config = marketplaces.get(marketplace_name)
    if not isinstance(config, dict):
        return None
    return _local_source_path(config.get("source"))


def marketplace_manifest_path(marketplace_root: Path) -> Path:
    return marketplace_root / MARKETPLACE_RELATIVE_MANIFEST


def owned_marketplace_manifest(
    marketplace_root: Path,
    *,
    marketplace_name: str = MARKETPLACE_NAME,
    plugin_name: str = PLUGIN_NAME,
) -> bool:
    marker = marketplace_root / MARKETPLACE_MARKER
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            return False
        return data.get("owner") == plugin_name and data.get("safe_to_remove") is True
    manifest = marketplace_manifest_path(marketplace_root)
    if not manifest.exists():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return False
    plugins = data.get("plugins")
    return (
        data.get("name") == marketplace_name
        and isinstance(plugins, list)
        and len(plugins) == 1
        and isinstance(plugins[0], dict)
        and plugins[0].get("name") == plugin_name
        and (plugins[0].get("source") or {}).get("path") == f"./plugins/{plugin_name}"
    )
