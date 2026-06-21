"""Foreground recovery payloads for local-folder sync bundle failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields, write_boundary
from aippocampus_runtime.sync.cli_support import sync_dir_required_actions
from aippocampus_runtime.sync.contract import SYNC_MANIFEST_NAME


def missing_manifest_recovery_payload() -> dict[str, Any]:
    actions = sync_dir_required_actions()
    return {
        "ok": False,
        "status": "missing_manifest",
        "sync_dir_label": "<local-sync-dir-redacted>",
        "manifest_exists": False,
        "schema_version": None,
        "file_count": 0,
        "raw_rollout_included": False,
        "privacy_boundary": {"local_paths_included": False},
        "issues": [
            {
                "code": "missing_manifest",
                "path_redacted": True,
            }
        ],
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
    }


def sync_recovery_action(
    action_id: str,
    command: str,
    *,
    mutation_risk: str = "read_only",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "command": command,
        "mutation_risk": mutation_risk,
        "claim_boundary": "local_sync_recovery_not_source_truth",
    }


def sync_manifest_recovery_payload(
    sync_root: Path,
    *,
    status: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    repair = sync_recovery_action(
        "repair_sync_manifest",
        "aippocampus sync repair --sync-dir <sync-dir> --json",
    )
    rebuild = sync_recovery_action(
        "rebuild_sync_bundle",
        "aippocampus sync push --sync-dir <sync-dir> --json",
        mutation_risk="writes_sync_dir",
    )
    actions = [rebuild, repair] if code == "unsupported_sync_manifest_schema" else [repair, rebuild]
    return {
        "ok": False,
        "status": status,
        "sync_dir": str(sync_root),
        "manifest_exists": True,
        "schema_version": None,
        "file_count": 0,
        "raw_rollout_included": False,
        "issues": [{"code": code, "path": str(sync_root / SYNC_MANIFEST_NAME), "message": message}],
        "recovery_actions": actions,
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "write_boundary": write_boundary(written=False, explicit_write_required=True),
    }


def managed_sync_dir_collision_payload(sync_root: Path, names: list[str]) -> dict[str, Any]:
    action = sync_recovery_action(
        "repair_sync_manifest",
        "aippocampus sync repair --sync-dir <sync-dir> --json",
    )
    return {
        "ok": False,
        "status": "managed_sync_dir_collision",
        "sync_dir": str(sync_root),
        "issues": [
            {
                "code": "managed_sync_dir_without_valid_manifest",
                "managed_dirs": names,
                "message": (
                    "AIppocampus-owned sync dirs are present but no trusted manifest "
                    "allows clearing them."
                ),
            }
        ],
        "recovery_actions": [action],
        "write_boundary": write_boundary(written=False, explicit_write_required=True),
    }
