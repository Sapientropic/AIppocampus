"""Codex plugin marketplace/cache diagnostics for local update readiness."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.io_integrity import prepared_directory_replace
from aippocampus_runtime.source.io_kernel import load_json_dict
from aippocampus_runtime.update import status_actions

PLUGIN_NAME = "aippocampus"
MARKETPLACE_NAME = "aippocampus-local"
MANIFEST_RELATIVE = Path(".codex-plugin") / "plugin.json"
IGNORED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
}
IGNORED_SUFFIXES = (".pyc", ".pyo")


def _ignored_name(name: str) -> bool:
    return name in IGNORED_DIR_NAMES or name.endswith(".egg-info") or name.endswith(IGNORED_SUFFIXES)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_fingerprint(root: Path | None) -> str | None:
    if root is None or not root.exists():
        return None
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() == ".mcp.json":
            # Installed Codex plugin caches may keep a host-specific MCP launch
            # command. MCP readiness is audited separately, so cache freshness
            # ignores this file instead of forcing a stale package verdict.
            continue
        if any(_ignored_name(part) for part in rel.parts):
            continue
        rows.append(f"{rel.as_posix()}:{_file_hash(path)}")
    digest = hashlib.sha256("\n".join(rows).encode("utf-8"))
    return digest.hexdigest()


def _load_manifest_object(path: Path) -> Mapping[str, Any] | None:
    result = load_json_dict(path, missing_is_loss=True)
    if result.loss.get("total_loss_count"):
        return None
    return result.data


def _mcp_server_config(root: Path | None) -> Mapping[str, Any] | None:
    if root is None:
        return None
    data = _load_manifest_object(root / ".mcp.json")
    if data is None:
        return None
    server = (data.get("mcpServers") or {}).get(PLUGIN_NAME)
    return server if isinstance(server, Mapping) else None


def _current_mcp_server_config(server: Mapping[str, Any] | None) -> bool:
    if server is None:
        return False
    command = str(server.get("command") or "")
    args = [str(item) for item in server.get("args") or []]
    command_name = Path(command).name.casefold()
    if command_name in {"aippocampus", "aippocampus.exe"}:
        return args[:1] == ["mcp"]
    if len(args) >= 2 and args[0] == "-m":
        module_name = args[1]
        if module_name == "aippocampus_runtime.cli.facade":
            return len(args) >= 3 and args[2] == "mcp"
        if module_name == "aippocampus_runtime.mcp.server":
            return True
    return False


def _mcp_launch_kind(command: str, args: list[str]) -> str:
    command_name = Path(command).name.casefold()
    if command_name in {"aippocampus", "aippocampus.exe"}:
        return "console_script"
    if len(args) >= 2 and args[0] == "-m":
        return "python_module"
    if Path(command).is_absolute():
        return "absolute_command"
    return "host_command"


def _mcp_launch_info(root: Path | None) -> dict[str, Any]:
    server = _mcp_server_config(root)
    if server is None:
        return {
            "exists": False,
            "current": False,
            "command": None,
            "args": [],
            "command_kind": None,
        }
    command = str(server.get("command") or "")
    args = [str(item) for item in server.get("args") or []]
    env = server.get("env")
    env_keys = {str(key) for key in env} if isinstance(env, Mapping) else set()
    return {
        "exists": True,
        "current": _current_mcp_server_config(server),
        "command": command or None,
        "args": args,
        "command_kind": _mcp_launch_kind(command, args) if command else None,
        "uses_console_script": Path(command).name.casefold()
        in {"aippocampus", "aippocampus.exe"},
        "uses_python_module": len(args) >= 2 and args[0] == "-m",
        "uses_absolute_command": Path(command).is_absolute() if command else False,
        "env_key_count": len(env_keys),
        "codex_home_env_present": "CODEX_HOME" in env_keys,
        "registry_dir_env_present": "AIPPOCAMPUS_REGISTRY_DIR" in env_keys,
        "claim_boundary": "installed-cache MCP launch shape is host setup evidence, not recall quality evidence",
    }


def _manifest_info(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {
            "status": "not_configured",
            "exists": False,
            "version": None,
            "manifest_hash": None,
            "tree_hash": None,
        }
    manifest = root / MANIFEST_RELATIVE
    if not root.exists():
        return {
            "status": "missing",
            "exists": False,
            "root_path": str(root),
            "version": None,
            "manifest_hash": None,
            "tree_hash": None,
            "mcp_launch": _mcp_launch_info(root),
        }
    data = _load_manifest_object(manifest)
    if data is None:
        return {
            "status": "missing_manifest",
            "exists": True,
            "root_path": str(root),
            "version": None,
            "manifest_hash": None,
            "tree_hash": _tree_fingerprint(root),
            "mcp_launch": _mcp_launch_info(root),
        }
    return {
        "status": "present",
        "exists": True,
        "root_path": str(root),
        "name": str(data.get("name") or ""),
        "version": str(data.get("version") or ""),
        "manifest_hash": _file_hash(manifest),
        "tree_hash": _tree_fingerprint(root),
        "mcp_launch": _mcp_launch_info(root),
    }


def _resolve_plugin_root(path: Path | None, *, plugin_name: str = PLUGIN_NAME) -> Path | None:
    if path is None:
        return None
    if (path / MANIFEST_RELATIVE).exists():
        return path
    marketplace_plugin = path / "plugins" / plugin_name
    if (marketplace_plugin / MANIFEST_RELATIVE).exists():
        return marketplace_plugin
    direct = path / plugin_name
    if (direct / MANIFEST_RELATIVE).exists():
        return direct
    candidates = sorted(
        candidate.parent.parent
        for candidate in path.glob(f"*/{MANIFEST_RELATIVE.as_posix()}")
        if (_load_manifest_object(candidate) or {}).get("name") == plugin_name
    )
    return candidates[-1] if candidates else path


def _cached_plugin_roots(
    codex_home_path: Path,
    *,
    plugin_name: str = PLUGIN_NAME,
    marketplace_name: str | None = None,
) -> list[Path]:
    cache_root = codex_home_path / "plugins" / "cache"
    if not cache_root.exists():
        return []
    roots: list[Path] = []
    marketplaces = (
        [cache_root / marketplace_name]
        if marketplace_name
        else sorted(item for item in cache_root.iterdir() if item.is_dir())
    )
    for marketplace in marketplaces:
        if not marketplace.is_dir():
            continue
        plugin_parent = marketplace / plugin_name
        if not plugin_parent.exists():
            continue
        for version_dir in sorted(item for item in plugin_parent.iterdir() if item.is_dir()):
            manifest = version_dir / MANIFEST_RELATIVE
            if manifest.exists() and (_load_manifest_object(manifest) or {}).get("name") == plugin_name:
                roots.append(version_dir)
    return roots


def installed_cache_auto_resolution(
    codex_home_path: Path,
    *,
    plugin_name: str = PLUGIN_NAME,
    marketplace_name: str | None = MARKETPLACE_NAME,
) -> dict[str, Any]:
    roots = _cached_plugin_roots(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=marketplace_name,
    )
    if len(roots) == 1:
        return {
            "status": "unique",
            "count": 1,
            "root_path": str(roots[0]),
        }
    if roots:
        return {
            "status": "multiple_candidates",
            "count": len(roots),
            "root_paths": [str(path) for path in roots],
        }
    return {"status": "none", "count": 0}


def installed_cache_version_resolution(
    codex_home_path: Path,
    *,
    expected_version: str,
    plugin_name: str = PLUGIN_NAME,
    marketplace_name: str | None = MARKETPLACE_NAME,
) -> dict[str, Any]:
    roots = _cached_plugin_roots(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=marketplace_name,
    )
    matches = [
        root
        for root in roots
        if str(_manifest_info(root).get("version") or "") == expected_version
    ]
    base = {
        "candidate_count": len(roots),
        "version": expected_version,
    }
    if len(matches) == 1:
        return {
            **base,
            "status": "unique_version_match",
            "count": 1,
            "root_path": str(matches[0]),
        }
    if matches:
        return {
            **base,
            "status": "multiple_version_matches",
            "count": len(matches),
            "root_paths": [str(path) for path in matches],
        }
    return {
        **base,
        "status": "no_version_match",
        "count": 0,
    }


def unique_installed_cache_root(
    codex_home_path: Path,
    *,
    plugin_name: str = PLUGIN_NAME,
    marketplace_name: str | None = MARKETPLACE_NAME,
) -> Path | None:
    resolution = installed_cache_auto_resolution(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=marketplace_name,
    )
    root = resolution.get("root_path") if resolution.get("status") == "unique" else None
    return Path(str(root)) if root else None


def _layer_status(
    *,
    root: Path | None,
    expected_version: str | None,
    expected_tree_hash: str | None,
    configured: bool,
) -> dict[str, Any]:
    info = _manifest_info(root)
    if root is None and not configured:
        info["status"] = "not_configured"
        info["current"] = False
        return info
    if info["status"] != "present":
        info["current"] = False
        return info
    if expected_version and info.get("version") != expected_version:
        info["status"] = "stale_version"
    elif expected_tree_hash and info.get("tree_hash") != expected_tree_hash:
        info["status"] = "stale_hash"
    else:
        info["status"] = "current"
    info["current"] = info["status"] == "current"
    return info


def build_plugin_cache_status(
    *,
    source_root: Path,
    package_root: Path,
    codex_home_path: Path,
    marketplace_dir: Path | None = None,
    installed_dir: Path | None = None,
    plugin_name: str = PLUGIN_NAME,
) -> dict[str, Any]:
    source = _manifest_info(source_root)
    package = _manifest_info(package_root)
    expected_version = str(source.get("version") or package.get("version") or "")
    expected_tree_hash = (
        str(package.get("tree_hash") or "") if package.get("tree_hash") else str(source.get("tree_hash") or "")
    )
    local_marketplace_root = _resolve_plugin_root(marketplace_dir, plugin_name=plugin_name)
    cached_roots = _cached_plugin_roots(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=MARKETPLACE_NAME,
    )
    all_cached_roots = _cached_plugin_roots(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=None,
    )
    ignored_cached_roots = [
        path
        for path in all_cached_roots
        if path not in set(cached_roots)
    ]
    auto_resolution = installed_cache_auto_resolution(
        codex_home_path,
        plugin_name=plugin_name,
        marketplace_name=MARKETPLACE_NAME,
    )
    installed_root = _resolve_plugin_root(installed_dir, plugin_name=plugin_name)
    if installed_root is None and cached_roots:
        installed_root = cached_roots[-1]
    local_marketplace = _layer_status(
        root=local_marketplace_root,
        expected_version=expected_version,
        expected_tree_hash=expected_tree_hash,
        configured=marketplace_dir is not None,
    )
    installed_cache = _layer_status(
        root=installed_root,
        expected_version=expected_version,
        expected_tree_hash=expected_tree_hash,
        configured=installed_dir is not None or bool(cached_roots),
    )
    recommended_actions: list[str] = []
    if local_marketplace.get("status") in {"missing", "missing_manifest", "stale_version", "stale_hash"}:
        recommended_actions.append(
            "run `aippocampus update apply --surface plugin --plugin-marketplace-dir <path>` to refresh the local marketplace copy"
        )
    if installed_cache.get("status") in {"missing", "missing_manifest", "stale_version", "stale_hash"}:
        if auto_resolution.get("status") == "unique":
            recommended_actions.append(
                "run `aippocampus update apply --surface plugin --plugin-installed-dir auto` to refresh the detected Codex plugin cache"
            )
        elif auto_resolution.get("status") == "multiple_candidates":
            recommended_actions.append(
                "run `aippocampus plugin install --codex --verify --compact-json` to refresh the Codex plugin cache without choosing a path manually"
            )
        else:
            recommended_actions.append(
                "run `aippocampus update apply --surface plugin --plugin-installed-dir <path>` or reinstall the Codex plugin cache"
            )
    if installed_cache.get("status") == "not_configured":
        recommended_actions.append(
            "pass --plugin-installed-dir, or reinstall the plugin in Codex after refreshing the local marketplace"
        )
    recommended_action_cards = [
        {
            "id": "plugin_cache_recovery",
            "status": "plugin_cache_needs_refresh",
            "why": "The plugin package can be current while the Codex installed cache or marketplace copy is stale.",
            **status_actions.executable_update_action_fields(
                item,
                fallback_command=status_actions.PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND,
                manual_instruction=(
                    "Use the ordinary Codex plugin refresh unless a custom marketplace/cache path "
                    "is intentionally being repaired."
                ),
            ),
        }
        for item in recommended_actions
    ]
    return {
        "source_plugin_version": source.get("version"),
        "source_plugin_tree_hash": source.get("tree_hash"),
        "package_plugin_version": package.get("version"),
        "package_plugin_tree_hash": package.get("tree_hash"),
        "local_marketplace": local_marketplace,
        "installed_cache": installed_cache,
        "auto_detected_installed_cache_count": len(cached_roots),
        # owner: plugin cache status; removal: after unconfigured old Codex
        # cache layouts are no longer detected; default/exposure: count only,
        # no local cache root paths.
        "ignored_legacy_cache_count": len(ignored_cached_roots),
        "installed_cache_auto_resolution": auto_resolution,
        "recommended_actions": recommended_actions,
        "recommended_action_cards": recommended_action_cards,
        "boundary": {
            "package_artifact_is_not_installed_cache": True,
            "local_marketplace_is_not_codex_installed_cache": True,
            "host_app_reload_may_still_be_required": True,
        },
    }


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _portable_mcp_config(path: Path) -> bool:
    data = _load_manifest_object(path)
    if data is None:
        return False
    server = ((data.get("mcpServers") or {}).get(PLUGIN_NAME) or {}) if isinstance(data, Mapping) else {}
    command = str(server.get("command") or "") if isinstance(server, Mapping) else ""
    if Path(command).name.casefold() in {"aippocampus", "aippocampus.exe"}:
        return False
    return _current_mcp_server_config(server if isinstance(server, Mapping) else None)


def _codex_home_from_installed_cache_path(installed_root: Path) -> Path | None:
    for parent in installed_root.resolve().parents:
        if parent.name == "plugins":
            return parent.parent
    return None


def _ensure_installed_mcp_host_launch(
    installed_root: Path,
    *,
    codex_home_path: Path | None,
) -> dict[str, Any]:
    mcp_path = installed_root / ".mcp.json"
    data = dict(_load_manifest_object(mcp_path) or {})
    servers = data.get("mcpServers")
    if not isinstance(servers, Mapping):
        servers = {}
    servers = dict(servers)
    server = servers.get(PLUGIN_NAME)
    server = dict(server) if isinstance(server, Mapping) else {}
    original_command = str(server.get("command") or "")
    original_args = [str(item) for item in server.get("args") or []]
    original_current = _current_mcp_server_config(server)
    original_console_script = Path(original_command).name.casefold() in {
        "aippocampus",
        "aippocampus.exe",
    }
    original_absolute_command = Path(original_command).is_absolute()
    command_updated = False
    if not original_current or original_console_script or not original_absolute_command:
        # The public plugin package stays portable (`aippocampus mcp`), but the
        # installed Codex cache is host-local. GUI MCP hosts do not always
        # inherit the shell PATH. Keep the installed layer deterministic by
        # using the exact interpreter that refreshed the cache and an explicit
        # module entrypoint. A current absolute Python command is the only shape
        # we preserve here.
        server["command"] = str(Path(sys.executable))
        server["args"] = ["-m", "aippocampus_runtime.cli.facade", "mcp"]
        command_updated = (server["command"] != original_command) or (
            server["args"] != original_args
        )
    env = server.get("env")
    env = dict(env) if isinstance(env, Mapping) else {}
    resolved_codex_home = codex_home_path or _codex_home_from_installed_cache_path(installed_root)
    env_keys_added: list[str] = []
    env_keys_updated: list[str] = []
    if resolved_codex_home is not None:
        codex_home_text = str(resolved_codex_home.resolve())
        registry_dir_text = str((resolved_codex_home.resolve() / "aippocampus-registry"))
        for key, value in {
            "CODEX_HOME": codex_home_text,
            "AIPPOCAMPUS_REGISTRY_DIR": registry_dir_text,
        }.items():
            previous = env.get(key)
            env[key] = value
            if previous is None:
                env_keys_added.append(key)
            elif str(previous) != value:
                env_keys_updated.append(key)
    if env:
        server["env"] = env
    servers[PLUGIN_NAME] = server
    data["mcpServers"] = servers
    mcp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "current",
        "command_updated": command_updated,
        "env_keys_added": env_keys_added,
        "env_keys_updated": env_keys_updated,
        "env_key_count": len(env),
        "codex_home_env_present": "CODEX_HOME" in env,
        "registry_dir_env_present": "AIPPOCAMPUS_REGISTRY_DIR" in env,
        "command_kind": _mcp_launch_info(installed_root).get("command_kind"),
        "claim_boundary": "installed-cache launch repair is local host setup, not source evidence",
    }


def _replace_plugin_tree(source: Path, target: Path, *, preserve_portable_mcp: bool) -> dict[str, Any]:
    source_resolved = source.resolve()
    target_resolved = target.resolve()
    if source_resolved == target_resolved or _path_is_under(source_resolved, target_resolved):
        raise ValueError("refusing unsafe plugin cache refresh path")
    if len(target_resolved.parts) <= 2:
        raise ValueError("refusing shallow plugin cache refresh path")
    preserved_mcp = None
    existing_mcp = target / ".mcp.json"
    if preserve_portable_mcp and existing_mcp.exists() and _portable_mcp_config(existing_mcp):
        preserved_mcp = existing_mcp.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    with prepared_directory_replace(target) as tmp:
        shutil.copytree(
            source,
            tmp,
            ignore=shutil.ignore_patterns(*IGNORED_DIR_NAMES, "*.egg-info", "*.pyc", "*.pyo"),
        )
        if preserved_mcp is not None:
            (tmp / ".mcp.json").write_text(preserved_mcp, encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
    return {
        # Cache-refresh receipts are surfaced to agents after `update apply`.
        # Keep the actual write path private: rollback/install commands own
        # machine-local paths, but this foreground receipt only needs to say
        # the configured cache layer was refreshed.
        "target_path": "<redacted:local-path>",
        "ok": True,
        "portable_mcp_config_preserved": preserved_mcp is not None,
        "version": _manifest_info(target).get("version"),
        "tree_hash": _tree_fingerprint(target),
    }


def refresh_plugin_cache_layers(
    *,
    package_root: Path,
    marketplace_dir: Path | None = None,
    installed_dir: Path | None = None,
    codex_home_path: Path | None = None,
    plugin_name: str = PLUGIN_NAME,
) -> dict[str, Any]:
    if not package_root.exists():
        raise FileNotFoundError("plugin package must be built before cache refresh")
    marketplace_root = _resolve_plugin_root(marketplace_dir, plugin_name=plugin_name)
    installed_root = _resolve_plugin_root(installed_dir, plugin_name=plugin_name)
    refreshed: dict[str, Any] = {}
    if marketplace_root is not None:
        refreshed["local_marketplace"] = _replace_plugin_tree(
            package_root,
            marketplace_root,
            preserve_portable_mcp=False,
        )
    if installed_root is not None:
        refreshed["installed_cache"] = _replace_plugin_tree(
            package_root,
            installed_root,
            preserve_portable_mcp=True,
        )
        refreshed["installed_cache"]["mcp_host_launch"] = _ensure_installed_mcp_host_launch(
            installed_root,
            codex_home_path=codex_home_path,
        )
    return {
        "ok": True,
        "requested": bool(refreshed),
        "refreshed": refreshed,
        "host_app_reload_likely_required": bool(refreshed),
    }


__all__ = [
    "PLUGIN_NAME",
    "build_plugin_cache_status",
    "installed_cache_auto_resolution",
    "installed_cache_version_resolution",
    "refresh_plugin_cache_layers",
    "unique_installed_cache_root",
]
