#!/usr/bin/env python3
"""Inventory and purge AIppocampus-owned local artifacts.

Uninstall has two different risk classes: host integration artifacts
(marketplace/cache/staged skill/hook entries) and user data (registry, indexes,
clean source, logs). Keep them in one inventory so users can see the full
footprint, but require an explicit user-data confirmation before deleting the
registry tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.hooks import claude_code


def _exists(path: Path) -> bool:
    return path.exists()


def _artifact(
    artifact_id: str,
    category: str,
    path: Path,
    *,
    user_data: bool = False,
    purge_supported: bool = True,
    purge_mode: str = "delete_artifact",
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "category": category,
        "exists": _exists(path),
        "path_label": artifact_id,
        "path_redacted": True,
        "user_data": user_data,
        "purge_supported": purge_supported,
        "purge_mode": purge_mode if purge_supported else "inspect_only",
    }


def build_inventory(
    *,
    codex_home_path: str | Path | None = None,
    registry_dir: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    codex = Path(codex_home_path).expanduser() if codex_home_path else core.codex_home()
    registry = Path(registry_dir).expanduser() if registry_dir else core.aippocampus_registry_dir()
    workspace = Path(cwd).resolve() if cwd else Path.cwd()
    artifacts = [
        _artifact(
            "codex_marketplace",
            "host_integration",
            codex / "aippocampus-marketplace",
        ),
        _artifact(
            "codex_installed_plugin_cache",
            "host_integration",
            codex / "plugins" / "cache" / "aippocampus-local",
        ),
        _artifact(
            "staged_skill",
            "host_integration",
            codex / "skills" / "aippocampus",
        ),
        _artifact(
            "codex_hooks_json",
            "host_integration",
            codex / "hooks.json",
            purge_supported=False,
        ),
        _artifact(
            "claude_home_settings",
            "host_integration",
            claude_code.default_settings_path(),
            purge_supported=True,
            purge_mode="remove_aippocampus_entries",
        ),
        _artifact(
            "claude_project_settings",
            "host_integration",
            workspace / ".claude" / "settings.json",
            purge_supported=True,
            purge_mode="remove_aippocampus_entries",
        ),
        _artifact("registry_root", "user_data", registry, user_data=True),
        _artifact("registry_logs", "user_data", registry / "logs", user_data=True),
        _artifact("registry_threads", "user_data", registry / "threads", user_data=True),
        _artifact("registry_indexes", "user_data", registry / "indexes", user_data=True),
    ]
    existing = [item for item in artifacts if item["exists"]]
    primary = foreground_shell_action(
        action_id="review_uninstall_inventory",
        command="aippocampus uninstall --dry-run --json",
        label="Review uninstall inventory",
        why="Inspect what exists before choosing any explicit deletion path.",
        mutation_risk="read_only",
        claim_boundary="uninstall_inventory_not_memory_evidence",
    )
    purge_host = foreground_shell_action(
        action_id="purge_host_artifacts_after_review",
        command="aippocampus uninstall --purge --confirm-host-integration --json",
        label="Purge host integration artifacts",
        why="Deletes host integration artifacts only after explicit host confirmation.",
        mutation_risk="explicit_host_artifact_delete",
        claim_boundary="uninstall_inventory_not_memory_evidence",
    )
    purge_user_data = foreground_shell_action(
        action_id="purge_user_data_after_separate_confirmation",
        command="aippocampus uninstall --purge --confirm-host-integration --confirm-user-data --json",
        label="Purge host integration and user data",
        why="Deletes registry/index data only after separate user-data confirmation.",
        mutation_risk="explicit_user_data_delete",
        claim_boundary="uninstall_inventory_not_memory_evidence",
    )
    return {
        "kind": "aippocampus_uninstall_inventory",
        "ok": True,
        "dry_run": True,
        "artifact_count": len(artifacts),
        "existing_artifact_count": len(existing),
        "artifacts": artifacts,
        **canonical_foreground_action_fields(
            primary,
            safe_next_actions=[primary, purge_host, purge_user_data],
        ),
        "privacy": {
            "local_paths_emitted": False,
            "raw_private_memory_emitted": False,
        },
        "purge_command": "aippocampus uninstall --purge --confirm-host-integration --json",
        "purge_user_data_command": "aippocampus uninstall --purge --confirm-host-integration --confirm-user-data --json",
        "claim_boundary": "inventory reports filesystem presence only; it does not inspect private memory contents",
    }


def _safe_remove(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def purge(
    *,
    codex_home_path: str | Path | None = None,
    registry_dir: str | Path | None = None,
    cwd: str | Path | None = None,
    confirm_host_integration: bool = False,
    confirm_user_data: bool = False,
) -> dict[str, Any]:
    inventory = build_inventory(codex_home_path=codex_home_path, registry_dir=registry_dir, cwd=cwd)
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    codex = Path(codex_home_path).expanduser() if codex_home_path else core.codex_home()
    registry = Path(registry_dir).expanduser() if registry_dir else core.aippocampus_registry_dir()
    workspace = Path(cwd).resolve() if cwd else Path.cwd()
    path_by_id = {
        "codex_marketplace": codex / "aippocampus-marketplace",
        "codex_installed_plugin_cache": codex / "plugins" / "cache" / "aippocampus-local",
        "staged_skill": codex / "skills" / "aippocampus",
        "claude_home_settings": claude_code.default_settings_path(),
        "claude_project_settings": workspace / ".claude" / "settings.json",
        "registry_root": registry,
        "registry_logs": registry / "logs",
        "registry_threads": registry / "threads",
        "registry_indexes": registry / "indexes",
    }
    for artifact in inventory["artifacts"]:
        artifact_id = str(artifact["id"])
        if not artifact.get("exists") or not artifact.get("purge_supported"):
            continue
        if artifact.get("category") == "host_integration" and not confirm_host_integration:
            skipped.append({"id": artifact_id, "reason": "requires_confirm_host_integration"})
            continue
        if artifact.get("user_data") and not confirm_user_data:
            skipped.append({"id": artifact_id, "reason": "requires_confirm_user_data"})
            continue
        path = path_by_id.get(artifact_id)
        if path is None:
            skipped.append({"id": artifact_id, "reason": "no_purge_handler"})
            continue
        if artifact.get("purge_mode") == "remove_aippocampus_entries":
            result = claude_code.uninstall_hooks(settings_path=path)
            removed.append(
                {
                    "id": artifact_id,
                    "removed": bool(result.get("changed")),
                    "handler": "claude_code_uninstall_hooks",
                    "ok": bool(result.get("ok")),
                }
            )
            continue
        removed.append({"id": artifact_id, "removed": _safe_remove(path)})
    primary = foreground_shell_action(
        action_id="check_post_uninstall_status",
        command="aippocampus uninstall --dry-run --json",
        label="Recheck uninstall inventory",
        why="Confirm no AIppocampus-owned artifacts remain after purge.",
        mutation_risk="read_only",
        claim_boundary="uninstall_inventory_not_memory_evidence",
    )
    return {
        "kind": "aippocampus_uninstall_purge",
        "ok": True,
        "dry_run": False,
        "confirm_host_integration": bool(confirm_host_integration),
        "confirm_user_data": bool(confirm_user_data),
        "removed": removed,
        "skipped": skipped,
        "workspace_label": "current_workspace",
        "path_redacted": True,
        **canonical_foreground_action_fields(primary),
        "privacy": {
            "local_paths_emitted": False,
            "raw_private_memory_emitted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus uninstall",
        description="Inventory or purge AIppocampus local host artifacts.",
    )
    parser.add_argument("--dry-run", "--preview", action="store_true", dest="dry_run")
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--confirm-host-integration", action="store_true")
    parser.add_argument("--confirm-user-data", action="store_true")
    parser.add_argument("--codex-home")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cwd")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    if args.purge:
        payload = purge(
            codex_home_path=args.codex_home,
            registry_dir=args.registry_dir,
            cwd=args.cwd,
            confirm_host_integration=args.confirm_host_integration,
            confirm_user_data=args.confirm_user_data,
        )
    else:
        payload = build_inventory(
            codex_home_path=args.codex_home,
            registry_dir=args.registry_dir,
            cwd=args.cwd,
        )
    if args.json_output or args.dry_run or args.purge:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("AIppocampus uninstall inventory")
        print(f"- Existing artifacts: {payload['existing_artifact_count']}")
        print("- Next: aippocampus uninstall --dry-run --json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
