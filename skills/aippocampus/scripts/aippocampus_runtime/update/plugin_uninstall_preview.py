"""Non-mutating rollback preview for the Codex plugin installer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.update.codex_plugin_cli import (
    CommandRunner,
)
from aippocampus_runtime.update.codex_plugin_cli import (
    codex_base as _codex_base,
)
from aippocampus_runtime.update.plugin_marketplace import (
    MARKETPLACE_NAME,
    PLUGIN_NAME,
    default_marketplace_root,
    owned_marketplace_manifest,
)


def uninstall_codex_plugin_preview(
    *,
    codex_home_path: Path | str | None = None,
    marketplace_root: Path | str | None = None,
    marketplace_name: str = MARKETPLACE_NAME,
    codex_command: str | list[str] | None = None,
    keep_marketplace: bool = False,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    codex_home_resolved = (
        Path(codex_home_path).expanduser().resolve() if codex_home_path else codex_home()
    )
    marketplace = (
        Path(marketplace_root).expanduser().resolve()
        if marketplace_root
        else default_marketplace_root(codex_home_resolved)
    )
    installed_cache_root = (
        codex_home_resolved / "plugins" / "cache" / marketplace_name / PLUGIN_NAME
    )
    manager_visible: bool | None = None
    manager_error: str | None = None
    if runner is not None:
        try:
            proc = runner([*_codex_base(codex_command), "plugin", "list"])
            text = f"{proc.stdout or ''}\n{proc.stderr or ''}"
            manager_visible = PLUGIN_NAME in text or f"{PLUGIN_NAME}@{marketplace_name}" in text
            if proc.returncode != 0:
                manager_error = f"plugin list exited {proc.returncode}"
        except Exception as exc:  # pragma: no cover - depends on host CLI shape
            manager_error = f"{type(exc).__name__}: {exc}"
    execute = "aippocampus plugin uninstall --codex"
    if keep_marketplace:
        execute += " --keep-marketplace"
    return {
        "kind": "aippocampus_plugin_uninstall_preview",
        "ok": True,
        "dry_run": True,
        "would_remove_installed_cache": installed_cache_root.exists(),
        "would_remove_marketplace_root": marketplace.exists()
        and not keep_marketplace
        and owned_marketplace_manifest(marketplace, marketplace_name=marketplace_name),
        "marketplace_owned_by_aippocampus": owned_marketplace_manifest(
            marketplace, marketplace_name=marketplace_name
        ),
        "keep_marketplace": keep_marketplace,
        "codex_plugin_manager_can_see_plugin": manager_visible,
        "codex_plugin_manager_check_error": manager_error,
        "execute_command": execute,
        "local_private_fields": ["codex_home", "marketplace_root", "installed_cache_root"],
        "codex_home": str(codex_home_resolved),
        "marketplace_root": str(marketplace),
        "installed_cache_root": str(installed_cache_root),
    }
