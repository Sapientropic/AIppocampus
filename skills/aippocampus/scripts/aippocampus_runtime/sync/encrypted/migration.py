#!/usr/bin/env python3
"""Plaintext-to-encrypted sync migration helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.encrypted import bundle as encrypted_sync_bundle
from aippocampus_runtime.sync.encrypted import keys as encrypted_sync_keys
from aippocampus_runtime.sync.encrypted import object_storage as encrypted_sync_object_storage
from aippocampus_runtime.sync.encrypted.crypto import (
    issue,
    recipients_from_files,
    validate_recipients,
)
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage


def failed_local_result(sync_root: Path, code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "encrypted": True,
        "sync_dir": str(sync_root.resolve()),
        "issues": [issue(code, message, **extra)],
    }


def failed_object_result(
    object_store_url: str,
    prefix: str,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "encrypted": True,
        "backend": sync_object_storage.OBJECT_BACKEND,
        "object_store": sync_object_storage.safe_endpoint_label(object_store_url),
        "object_prefix": sync_object_storage.normalize_object_prefix(prefix),
        "issues": [issue(code, message, **extra)],
    }


def plaintext_sync_file_paths(sync_root: Path, manifest: dict[str, Any]) -> tuple[list[Path], list[dict[str, Any]]]:
    paths = [sync_root / sync_bundle.SYNC_MANIFEST_NAME]
    issues: list[dict[str, Any]] = []
    for item in manifest.get("files") or []:
        try:
            relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        except ValueError as exc:
            issues.append(issue("unsafe_path", str(exc), path=str(item.get("path") or "")))
            continue
        paths.append(sync_bundle.ensure_within(sync_root, sync_root / relative_path))
    unique_paths = sorted({path.resolve() for path in paths}, key=lambda path: str(path))
    return unique_paths, issues


def inventory_plaintext_sync_dir(
    sync_dir: str | Path,
    *,
    target_sync_dir: str | Path | None = None,
) -> dict[str, Any]:
    sync_root = Path(sync_dir).resolve()
    manifest_path = sync_root / sync_bundle.SYNC_MANIFEST_NAME
    encrypted_root = encrypted_sync_bundle.encrypted_root(sync_root)
    if encrypted_root.exists() and manifest_path.exists():
        return failed_local_result(
            sync_root,
            "mixed_sync_dir",
            "plaintext and encrypted sync data coexist in the source sync directory",
            paths=[str(manifest_path), str(encrypted_root)],
        )
    try:
        manifest = sync_bundle.load_sync_manifest(manifest_path)
    except FileNotFoundError:
        return failed_local_result(
            sync_root,
            "missing_manifest",
            f"missing plaintext sync manifest: {manifest_path}",
        )
    except sync_bundle.SyncManifestError as exc:
        return failed_local_result(sync_root, "invalid_manifest", str(exc))
    if (
        manifest.get("kind") != sync_bundle.SYNC_BUNDLE_KIND
        or manifest.get("schema_version") != sync_bundle.SYNC_SCHEMA_VERSION
    ):
        return failed_local_result(sync_root, "invalid_manifest", f"unrecognized plaintext sync manifest: {manifest_path}")

    paths, path_issues = plaintext_sync_file_paths(sync_root, manifest)
    existing = [path for path in paths if path.exists()]
    missing = [path for path in paths if not path.exists()]
    issues = list(path_issues)
    issues.extend(
        issue("missing_file", f"missing plaintext sync file: {path}", path=str(path))
        for path in missing
    )
    return {
        "ok": not issues,
        "encrypted": True,
        "source_kind": "local_folder",
        "sync_dir": str(sync_root),
        "target_sync_dir": str(Path(target_sync_dir).resolve()) if target_sync_dir else None,
        "plaintext_exposure": True,
        "plaintext_manifest": str(manifest_path),
        "plaintext_object_count": len(existing),
        "plaintext_objects": [str(path) for path in existing],
        "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
        "file_count": int(manifest.get("file_count") or max(len(existing) - 1, 0)),
        "issues": issues,
    }


def target_sync_dir_fresh(source_sync_dir: Path, target_sync_dir: Path) -> dict[str, Any] | None:
    source_root = source_sync_dir.resolve()
    target_root = target_sync_dir.resolve()
    if source_root == target_root:
        return issue(
            "target_not_fresh",
            "encrypted migration target must be a fresh directory distinct from the plaintext source",
            path=str(target_root),
        )
    if target_root.exists() and any(target_root.iterdir()):
        return issue(
            "target_not_fresh",
            "encrypted migration target is not empty",
            path=str(target_root),
        )
    return None


def collect_recipients_for_registry(
    registry_dir: str | Path,
    *,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    explicit, explicit_issue = validate_recipients(recipients or [])
    if explicit_issue and recipients:
        return [], explicit_issue
    file_recipients, file_issue = recipients_from_files(recipient_files)
    if file_issue and recipient_files:
        return [], file_issue
    trusted = (
        encrypted_sync_keys.trusted_recipients_for_registry(registry_dir)
        if not explicit and not file_recipients
        else []
    )
    collected = explicit + file_recipients + trusted
    return validate_recipients(collected)


def migrate_plaintext_sync_dir_to_encrypted(
    source_sync_dir: str | Path,
    target_sync_dir: str | Path,
    *,
    registry_dir: str | Path | None = None,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    source_root = Path(source_sync_dir).resolve()
    target_root = Path(target_sync_dir).resolve()
    inventory = inventory_plaintext_sync_dir(source_root, target_sync_dir=target_root)
    if not inventory.get("ok"):
        return inventory
    fresh_issue = target_sync_dir_fresh(source_root, target_root)
    if fresh_issue:
        return failed_local_result(source_root, fresh_issue["code"], fresh_issue["message"], path=fresh_issue.get("path"))

    recipient_root = Path(registry_dir).resolve() if registry_dir else source_root
    resolved_recipients, recipient_issue = collect_recipients_for_registry(
        recipient_root,
        recipients=recipients,
        recipient_files=recipient_files,
    )
    if recipient_issue:
        return failed_local_result(source_root, recipient_issue["code"], recipient_issue["message"])

    base = {
        "ok": True,
        "encrypted": True,
        "source_kind": "local_folder",
        "dry_run": dry_run,
        "source_sync_dir": str(source_root),
        "target_sync_dir": str(target_root),
        "plaintext_exposure": True,
        "plaintext_object_count": inventory.get("plaintext_object_count", 0),
        "raw_rollout_included": bool(inventory.get("raw_rollout_included")),
        "required_recipient_count": len(resolved_recipients),
        "would_delete_plaintext": False,
    }
    if dry_run:
        base.update({"would_upload_encrypted": False, "issues": []})
        return base

    with tempfile.TemporaryDirectory(prefix="aippocampus-plaintext-migration-") as tmp:
        temp_registry = Path(tmp) / "registry"
        pull = sync_bundle.pull_sync_bundle(source_root, temp_registry)
        if not pull.get("ok"):
            return failed_local_result(
                source_root,
                "migration_plaintext_pull_failed",
                "failed to materialize plaintext source before encryption",
            )
        push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            temp_registry,
            target_root,
            recipients=resolved_recipients,
            age_bin=age_bin,
        )
    result = dict(base)
    result.update(push)
    result["source_sync_dir"] = str(source_root)
    result["target_sync_dir"] = str(target_root)
    result["would_delete_plaintext"] = False
    return result


def cleanup_plaintext_sync_dir(
    sync_dir: str | Path,
    *,
    dry_run: bool = True,
    confirm: bool = False,
    verified_encrypted_target: bool = False,
) -> dict[str, Any]:
    sync_root = Path(sync_dir).resolve()
    inventory = inventory_plaintext_sync_dir(sync_root)
    if not inventory.get("ok"):
        return inventory
    objects = [Path(path) for path in inventory.get("plaintext_objects") or []]
    manifest_path = sync_root / sync_bundle.SYNC_MANIFEST_NAME
    delete_order = [path for path in objects if path != manifest_path]
    delete_order.append(manifest_path)
    base = {
        "ok": True,
        "encrypted": True,
        "source_kind": "local_folder",
        "sync_dir": str(sync_root),
        "dry_run": dry_run,
        "would_delete_count": len(delete_order),
        "would_delete": [str(path) for path in delete_order],
    }
    if dry_run:
        base["issues"] = []
        return base
    if not confirm:
        return failed_local_result(
            sync_root,
            "cleanup_confirmation_required",
            "plaintext cleanup requires confirm=True after inspecting the dry-run delete list",
        )
    if not verified_encrypted_target:
        return failed_local_result(
            sync_root,
            "encrypted_target_verification_required",
            "plaintext cleanup requires an explicit verified encrypted target acknowledgement",
        )
    deleted: list[str] = []
    for path in delete_order:
        if path.exists():
            path.unlink()
            deleted.append(str(path))
    base.update({"deleted_count": len(deleted), "deleted": deleted, "issues": []})
    return base


def object_exists(client: sync_object_storage.HttpObjectStoreClient, relative_path: str | Path) -> bool:
    try:
        client.get_object(relative_path)
    except FileNotFoundError:
        return False
    return True


def plaintext_object_records(manifest: dict[str, Any], prefix: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = [
        {
            "relative_path": sync_bundle.SYNC_MANIFEST_NAME,
            "object_key": sync_object_storage.object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
        }
    ]
    issues: list[dict[str, Any]] = []
    for item in manifest.get("files") or []:
        try:
            relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        except ValueError as exc:
            issues.append(issue("unsafe_path", str(exc), path=str(item.get("path") or "")))
            continue
        records.append(
            {
                "relative_path": relative_path.as_posix(),
                "object_key": sync_object_storage.object_key(prefix, relative_path),
                "size": item.get("size"),
                "sha256": item.get("sha256"),
            }
        )
    return records, issues


def inventory_plaintext_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = sync_object_storage.DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    client = sync_object_storage.object_storage_client_for(
        object_store_url,
        prefix=prefix,
        token=token,
        timeout=timeout,
        provider=provider,
        bucket=bucket,
        region=region,
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
    )
    try:
        manifest = sync_object_storage.load_object_manifest(client)
    except FileNotFoundError:
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "missing_manifest",
            f"missing plaintext sync manifest: {sync_object_storage.object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME)}",
        )
    except RuntimeError as exc:
        return failed_object_result(client.endpoint_url, prefix, "object_store_unreachable", str(exc))
    except (ValueError, UnicodeDecodeError) as exc:
        return failed_object_result(client.endpoint_url, prefix, "invalid_manifest", str(exc))

    encrypted_manifest = encrypted_sync_object_storage.encrypted_manifest_relative_path()
    if object_exists(client, encrypted_manifest):
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "mixed_object_prefix",
            "plaintext and encrypted sync data coexist in the source object prefix",
            path=sync_object_storage.object_key(prefix, encrypted_manifest),
        )
    if (
        manifest.get("kind") != sync_bundle.SYNC_BUNDLE_KIND
        or manifest.get("schema_version") != sync_bundle.SYNC_SCHEMA_VERSION
    ):
        return failed_object_result(client.endpoint_url, prefix, "invalid_manifest", "unrecognized plaintext object-storage sync manifest")
    records, path_issues = plaintext_object_records(manifest, prefix)
    return {
        "ok": not path_issues,
        "encrypted": True,
        "source_kind": "http_object_store",
        "backend": sync_object_storage.OBJECT_BACKEND,
        "object_store": sync_object_storage.safe_endpoint_label(client.endpoint_url),
        "object_prefix": sync_object_storage.normalize_object_prefix(prefix),
        "plaintext_exposure": True,
        "plaintext_object_count": len(records),
        "plaintext_objects": records,
        "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
        "file_count": int(manifest.get("file_count") or max(len(records) - 1, 0)),
        "issues": path_issues,
    }


def target_object_prefix_fresh(
    object_store_url: str | None,
    *,
    source_prefix: str,
    target_prefix: str,
    token: str | None = None,
    timeout: float = sync_object_storage.DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any] | None:
    if sync_object_storage.normalize_object_prefix(source_prefix) == sync_object_storage.normalize_object_prefix(target_prefix):
        return issue("target_not_fresh", "encrypted migration target prefix must differ from plaintext source prefix")
    client = sync_object_storage.object_storage_client_for(
        object_store_url,
        prefix=target_prefix,
        token=token,
        timeout=timeout,
        provider=provider,
        bucket=bucket,
        region=region,
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
    )
    checked: list[str | Path] = [
        sync_bundle.SYNC_MANIFEST_NAME,
        encrypted_sync_object_storage.encrypted_manifest_relative_path(),
    ]
    for relative_path in checked:
        if object_exists(client, relative_path):
            return issue(
                "target_not_fresh",
                "encrypted migration target prefix already contains sync data",
                path=sync_object_storage.object_key(target_prefix, relative_path),
            )
    return None


def migrate_plaintext_object_storage_to_encrypted(
    registry_dir: str | Path | None,
    object_store_url: str | None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    target_prefix: str,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    dry_run: bool = False,
    token: str | None = None,
    timeout: float = sync_object_storage.DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    provider_kwargs: dict[str, Any] = {
        "token": token,
        "timeout": timeout,
        "provider": provider,
        "bucket": bucket,
        "region": region,
        "account_id": account_id,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "session_token": session_token,
    }
    source_inventory = inventory_plaintext_object_storage_bundle(
        object_store_url,
        prefix=prefix,
        **provider_kwargs,
    )
    if not source_inventory.get("ok"):
        return source_inventory
    fresh_issue = target_object_prefix_fresh(
        object_store_url,
        source_prefix=prefix,
        target_prefix=target_prefix,
        **provider_kwargs,
    )
    client_label = str(object_store_url or "")
    if fresh_issue:
        return failed_object_result(
            client_label,
            target_prefix,
            fresh_issue["code"],
            fresh_issue["message"],
            path=fresh_issue.get("path"),
        )
    recipient_root = Path(registry_dir).resolve() if registry_dir else Path.cwd()
    resolved_recipients, recipient_issue = collect_recipients_for_registry(
        recipient_root,
        recipients=recipients,
        recipient_files=recipient_files,
    )
    if recipient_issue:
        return failed_object_result(client_label, prefix, recipient_issue["code"], recipient_issue["message"])
    base = {
        "ok": True,
        "encrypted": True,
        "source_kind": "http_object_store",
        "dry_run": dry_run,
        "object_prefix": sync_object_storage.normalize_object_prefix(prefix),
        "target_object_prefix": sync_object_storage.normalize_object_prefix(target_prefix),
        "plaintext_exposure": True,
        "plaintext_object_count": source_inventory.get("plaintext_object_count", 0),
        "raw_rollout_included": bool(source_inventory.get("raw_rollout_included")),
        "required_recipient_count": len(resolved_recipients),
        "would_delete_plaintext": False,
    }
    if dry_run:
        base.update({"would_upload_encrypted": False, "issues": []})
        return base

    with tempfile.TemporaryDirectory(prefix="aippocampus-object-plaintext-migration-") as tmp:
        temp_registry = Path(tmp) / "registry"
        pull = sync_object_storage.pull_object_storage_bundle(
            object_store_url,
            temp_registry,
            prefix=prefix,
            **provider_kwargs,
        )
        if not pull.get("ok"):
            return failed_object_result(
                client_label,
                prefix,
                "migration_plaintext_pull_failed",
                "failed to materialize plaintext source before encryption",
            )
        push = sync_object_storage.push_encrypted_object_storage_bundle(
            temp_registry,
            object_store_url,
            prefix=target_prefix,
            recipients=resolved_recipients,
            age_bin=age_bin,
            **provider_kwargs,
        )
    result = dict(base)
    result.update(push)
    result["target_object_prefix"] = sync_object_storage.normalize_object_prefix(target_prefix)
    result["would_delete_plaintext"] = False
    return result


def cleanup_plaintext_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    dry_run: bool = True,
    confirm: bool = False,
    verified_encrypted_target: bool = False,
    token: str | None = None,
    timeout: float = sync_object_storage.DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    provider_kwargs: dict[str, Any] = {
        "token": token,
        "timeout": timeout,
        "provider": provider,
        "bucket": bucket,
        "region": region,
        "account_id": account_id,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "session_token": session_token,
    }
    inventory = inventory_plaintext_object_storage_bundle(
        object_store_url,
        prefix=prefix,
        **provider_kwargs,
    )
    if not inventory.get("ok"):
        return inventory
    client = sync_object_storage.object_storage_client_for(
        object_store_url,
        prefix=prefix,
        **provider_kwargs,
    )
    records = list(inventory.get("plaintext_objects") or [])
    manifest_record = records[0] if records else None
    data_records = records[1:]
    delete_order = data_records + ([manifest_record] if manifest_record else [])
    base = {
        "ok": True,
        "encrypted": True,
        "source_kind": "http_object_store",
        "backend": sync_object_storage.OBJECT_BACKEND,
        "object_store": sync_object_storage.safe_endpoint_label(client.endpoint_url),
        "object_prefix": sync_object_storage.normalize_object_prefix(prefix),
        "dry_run": dry_run,
        "would_delete_count": len(delete_order),
        "would_delete": [record["object_key"] for record in delete_order],
    }
    if dry_run:
        base["issues"] = []
        return base
    if not confirm:
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "cleanup_confirmation_required",
            "plaintext cleanup requires confirm=True after inspecting the dry-run delete list",
        )
    if not verified_encrypted_target:
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "encrypted_target_verification_required",
            "plaintext cleanup requires an explicit verified encrypted target acknowledgement",
        )
    deleted: list[str] = []
    errors: list[dict[str, Any]] = []
    for record in delete_order:
        relative_path = record["relative_path"]
        try:
            client.delete_object(relative_path)
            deleted.append(record["object_key"])
        except FileNotFoundError:
            errors.append(issue("missing_file", f"missing plaintext object during cleanup: {record['object_key']}", path=record["object_key"]))
        except RuntimeError as exc:
            errors.append(issue("object_delete_failed", str(exc), path=record["object_key"]))
    base.update({"ok": not errors, "deleted_count": len(deleted), "deleted": deleted, "issues": errors})
    return base
