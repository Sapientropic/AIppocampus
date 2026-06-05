#!/usr/bin/env python3
"""Recovery-kit and vault-id diagnostics for encrypted sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.sync.encrypted.crypto import issue

ENCRYPTED_STATE_DIR = Path(".sync-state") / "encrypted"
RECIPIENT_ROLE_RECOVERY = "recovery"
VAULT_ID_NAME = "vault-id"
VAULT_ID_BACKUP_NAME = "vault-id.backup"


def encrypted_state_dir(registry_dir: str | Path) -> Path:
    return Path(registry_dir).resolve() / ENCRYPTED_STATE_DIR


def vault_id_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / VAULT_ID_NAME


def vault_id_backup_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / VAULT_ID_BACKUP_NAME


def recovery_state_for(trusted: list[dict[str, Any]]) -> dict[str, Any]:
    recovery_count = sum(1 for item in trusted if item.get("role") == RECIPIENT_ROLE_RECOVERY)
    if recovery_count:
        warning = issue(
            "recovery_identity_offline_backup_required",
            "recovery recipient is configured; keep the matching private recovery identity offline and backed up",
        )
        status = "configured"
        backup_status = "operator_required"
    else:
        warning = issue(
            "recovery_kit_not_configured",
            "no offline recovery recipient is configured; losing all trusted identities makes encrypted sync unrecoverable",
        )
        status = "missing"
        backup_status = "missing"
    return {
        "status": status,
        "mode": "offline_recovery_recipient" if recovery_count else "none",
        "configured": recovery_count > 0,
        "recovery_recipient_count": recovery_count,
        "identity_available": False,
        "identity_location": "offline_operator_controlled" if recovery_count else "none",
        "backup_status": backup_status,
        "backup_required": True,
        "warning": None
        if recovery_count
        else "losing all trusted device identities means encrypted sync data is unrecoverable",
        "warnings": [warning],
    }


def read_vault_id_value(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def vault_id_state_for(registry_dir: str | Path) -> dict[str, Any]:
    """Return public-safe vault-id continuity diagnostics without the vault id.

    The vault id is a stable correlation handle. Diagnostics intentionally report
    only presence, validity, and backup freshness so a future operator can tell
    whether to restore/re-enroll without leaking the id into CLI output.
    """

    vault_value = read_vault_id_value(vault_id_path(registry_dir))
    backup_value = read_vault_id_value(vault_id_backup_path(registry_dir))
    backup_exists = backup_value is not None
    warnings: list[dict[str, Any]] = []

    if vault_value is None:
        if backup_exists and backup_value:
            backup_status = "available_for_restore"
        elif backup_exists:
            backup_status = "invalid"
        else:
            backup_status = "missing"
        warnings.append(
            issue(
                "vault_id_missing",
                "vault-id continuity anchor is missing; restore a backup or explicitly enroll a new vault",
            )
        )
        return {
            "status": "missing",
            "vault_id_available": False,
            "backup_status": backup_status,
            "backup_recommended": True,
            "restore_required": True,
            "warnings": warnings,
        }

    if not vault_value:
        warnings.append(
            issue(
                "vault_id_invalid",
                "vault-id continuity anchor is empty or corrupt; restore a backup or explicitly re-enroll",
            )
        )
        return {
            "status": "invalid",
            "vault_id_available": False,
            "backup_status": "available_for_restore"
            if backup_exists and backup_value
            else "missing",
            "backup_recommended": True,
            "restore_required": True,
            "warnings": warnings,
        }

    if not backup_exists:
        backup_status = "missing"
        warnings.append(
            issue(
                "vault_id_backup_missing",
                "vault-id exists but no local backup marker was found",
            )
        )
    elif not backup_value:
        backup_status = "invalid"
        warnings.append(
            issue(
                "vault_id_backup_invalid",
                "vault-id backup marker is empty or corrupt",
            )
        )
    elif backup_value == vault_value:
        backup_status = "current"
    else:
        backup_status = "mismatch"
        warnings.append(
            issue(
                "vault_id_backup_mismatch",
                "vault-id backup does not match the current local continuity anchor",
            )
        )

    return {
        "status": "present",
        "vault_id_available": True,
        "backup_status": backup_status,
        "backup_recommended": True,
        "restore_required": False,
        "warnings": warnings,
    }
