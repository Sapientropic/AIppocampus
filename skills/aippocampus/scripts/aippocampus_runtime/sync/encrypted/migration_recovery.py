"""Recovery diagnostics for plaintext-to-encrypted sync migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.sync.encrypted import bundle as encrypted_sync_bundle
from aippocampus_runtime.sync.encrypted.crypto import issue


def partial_migration_recovery(
    *,
    source_kind: str,
    source_label: str,
    target_label: str,
    partial_encrypted_artifact_count: int | None,
) -> dict[str, Any]:
    return {
        "status": "partial_migration_preserved",
        "source_kind": source_kind,
        "plaintext_source": source_label,
        "encrypted_target": target_label,
        "plaintext_source_preserved": True,
        "target_preserved_for_inspection": True,
        "cleanup_allowed": False,
        "manual_recovery_required": True,
        "partial_encrypted_artifact_count": partial_encrypted_artifact_count,
        "next_steps": [
            "keep the plaintext source until an encrypted repair or pull succeeds",
            "inspect or retry the encrypted target before any plaintext cleanup",
            "run plaintext cleanup only after explicit verified encrypted target acknowledgement",
        ],
        "cannot_claim": [
            "plaintext cleanup is safe now",
            "provider console cleanup has been checked",
            "metadata padding or traffic-analysis resistance is implemented",
        ],
    }


def partial_migration_issue(recovery: dict[str, Any]) -> dict[str, Any]:
    return issue(
        "partial_migration_preserved",
        "plaintext source and partial encrypted target were preserved; verify or inspect the encrypted target before cleanup",
        cleanup_allowed=False,
        manual_recovery_required=True,
        partial_encrypted_artifact_count=recovery.get("partial_encrypted_artifact_count"),
    )


def local_partial_encrypted_artifact_count(target_sync_dir: Path) -> int:
    encrypted_root = encrypted_sync_bundle.encrypted_root(target_sync_dir)
    if not encrypted_root.exists():
        return 0
    return sum(1 for path in encrypted_root.rglob("*") if path.is_file())


def with_partial_migration_recovery(
    result: dict[str, Any],
    *,
    source_kind: str,
    source_label: str,
    target_label: str,
    partial_encrypted_artifact_count: int | None,
) -> dict[str, Any]:
    recovery = partial_migration_recovery(
        source_kind=source_kind,
        source_label=source_label,
        target_label=target_label,
        partial_encrypted_artifact_count=partial_encrypted_artifact_count,
    )
    issues = list(result.get("issues") or [])
    issues.append(partial_migration_issue(recovery))
    updated = dict(result)
    updated.update(
        {
            "ok": False,
            "encrypted": True,
            "would_delete_plaintext": False,
            "migration_recovery": recovery,
            "issues": issues,
        }
    )
    return updated
