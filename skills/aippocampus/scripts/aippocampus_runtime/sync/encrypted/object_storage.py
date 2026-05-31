#!/usr/bin/env python3
"""Encrypted HTTP object-storage sync adapter for AIppocampus bundles."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.encrypted import bundle as encrypted_sync_bundle
from aippocampus_runtime.sync.encrypted.crypto import EncryptedSyncError, issue, resolve_age_binary
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage


def encrypted_manifest_relative_path() -> Path:
    return (
        Path(encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME)
        / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME
    )


def object_result_base(object_store_url: str, prefix: str) -> dict[str, Any]:
    return {
        "encrypted": True,
        "backend": sync_object_storage.OBJECT_BACKEND,
        "object_store": sync_object_storage.safe_endpoint_label(object_store_url),
        "object_prefix": sync_object_storage.normalize_object_prefix(prefix),
    }


def failed_object_result(
    object_store_url: str,
    prefix: str,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    result = object_result_base(object_store_url, prefix)
    result.update({"ok": False, "issues": [issue(code, message, **extra)]})
    return result


def encrypted_bundle_files(sync_root: Path) -> list[Path]:
    root = encrypted_sync_bundle.encrypted_root(sync_root)
    if not root.is_dir():
        return []
    outer_manifest = encrypted_sync_bundle.encrypted_manifest_path(sync_root)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    return [path for path in files if path != outer_manifest] + [outer_manifest]


def relative_to_sync_root(sync_root: Path, path: Path) -> Path:
    try:
        return path.resolve().relative_to(sync_root.resolve())
    except ValueError as exc:
        raise ValueError(f"encrypted object escaped sync root: {path}") from exc


def write_object(sync_root: Path, relative_path: Path, data: bytes) -> None:
    destination = sync_bundle.ensure_within(sync_root, sync_root / relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def plaintext_manifest_exists(client: sync_object_storage.HttpObjectStoreClient) -> bool:
    try:
        client.get_object(sync_bundle.SYNC_MANIFEST_NAME)
    except FileNotFoundError:
        return False
    return True


def load_encrypted_outer_manifest_from_object_store(
    client: sync_object_storage.HttpObjectStoreClient,
    sync_root: Path,
) -> dict[str, Any]:
    relative_path = encrypted_manifest_relative_path()
    data = client.get_object(relative_path)
    write_object(sync_root, relative_path, data)
    return encrypted_sync_bundle.load_encrypted_outer_manifest(sync_root)


def download_encrypted_manifest_pair(
    client: sync_object_storage.HttpObjectStoreClient,
    sync_root: Path,
) -> dict[str, Any]:
    outer = load_encrypted_outer_manifest_from_object_store(client, sync_root)
    manifest_object = encrypted_sync_bundle.encrypted_manifest_object_path(sync_root, outer)
    relative_manifest_object = relative_to_sync_root(sync_root, manifest_object)
    data = client.get_object(relative_manifest_object)
    write_object(sync_root, relative_manifest_object, data)
    return {
        "outer_manifest": outer,
        "manifest_object": relative_manifest_object.as_posix(),
        "downloaded": 2,
    }


def decrypt_downloaded_inner_manifest(
    sync_root: Path,
    *,
    identity_files: Iterable[str | Path] | None,
    age_bin: str | Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    resolved_age, age_issue = resolve_age_binary(age_bin)
    if age_issue or not resolved_age:
        return None, age_issue
    with tempfile.TemporaryDirectory(prefix="aippocampus-object-sync-inner-") as tmp:
        try:
            _, inner = encrypted_sync_bundle.decrypt_inner_manifest(
                sync_root,
                identity_files=identity_files,
                age_bin=resolved_age,
                tmp_root=Path(tmp),
            )
        except EncryptedSyncError as exc:
            return None, issue(exc.code, exc.message)
    return inner, None


def download_encrypted_objects(
    client: sync_object_storage.HttpObjectStoreClient,
    sync_root: Path,
    inner_manifest: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    downloaded = 0
    for record in inner_manifest.get("objects") or []:
        try:
            object_path = sync_bundle.validate_relative_sync_path(
                str(record.get("object_path") or "")
            )
        except ValueError as exc:
            issues.append(issue("unsafe_path", str(exc)))
            continue
        try:
            data = client.get_object(object_path)
        except FileNotFoundError:
            issues.append(issue("missing_file", f"missing encrypted object: {object_path}"))
            continue
        write_object(sync_root, object_path, data)
        downloaded += 1
    return {"ok": not issues, "downloaded": downloaded, "issues": issues}


def download_encrypted_object_bundle(
    client: sync_object_storage.HttpObjectStoreClient,
    sync_root: Path,
    *,
    identity_files: Iterable[str | Path] | None,
    age_bin: str | Path | None,
    include_objects: bool,
) -> dict[str, Any]:
    manifest_pair = download_encrypted_manifest_pair(client, sync_root)
    if not include_objects:
        return {"ok": True, "downloaded": manifest_pair["downloaded"], "issues": []}

    inner, inner_issue = decrypt_downloaded_inner_manifest(
        sync_root,
        identity_files=identity_files,
        age_bin=age_bin,
    )
    if inner_issue or inner is None:
        return {
            "ok": False,
            "downloaded": manifest_pair["downloaded"],
            "issues": [inner_issue],
        }
    objects = download_encrypted_objects(client, sync_root, inner)
    return {
        "ok": bool(objects["ok"]),
        "downloaded": manifest_pair["downloaded"] + objects["downloaded"],
        "inner_manifest": inner,
        "issues": objects["issues"],
    }


def push_encrypted_object_storage_bundle(
    registry_dir: str | Path | None,
    object_store_url: str | None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
    include_raw: bool = False,
    age_bin: str | Path | None = None,
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
        has_plaintext_manifest = plaintext_manifest_exists(client)
    except RuntimeError as exc:
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "object_store_unreachable",
            str(exc),
        )
    if has_plaintext_manifest:
        return failed_object_result(
            client.endpoint_url,
            prefix,
            "mixed_object_prefix",
            "encrypted sync refuses to share an object prefix with plaintext sync data",
            path=sync_object_storage.object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
        )

    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-object-sync-push-") as tmp:
        sync_root = Path(tmp)
        local_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            registry_dir,
            sync_root,
            recipients=recipients,
            recipient_files=recipient_files,
            include_raw=include_raw,
            age_bin=age_bin,
        )
        if not local_push.get("ok"):
            result = object_result_base(client.endpoint_url, prefix)
            result.update(local_push)
            return result

        uploaded: list[dict[str, Any]] = []
        for source in encrypted_bundle_files(sync_root):
            relative_path = relative_to_sync_root(sync_root, source)
            uploaded.append(client.put_object(relative_path, source.read_bytes()))

    result = object_result_base(client.endpoint_url, prefix)
    result.update(
        {
            "ok": True,
            "manifest_key": sync_object_storage.object_key(
                prefix,
                encrypted_manifest_relative_path(),
            ),
            "object_count": len(uploaded),
            "file_count": local_push.get("file_count"),
            "raw_rollout_included": bool(local_push.get("raw_rollout_included")),
            "manifest_hash": local_push.get("manifest_hash"),
            "manifest_revision": local_push.get("manifest_revision"),
            "local_bundle_file_count": local_push.get("local_bundle_file_count"),
        }
    )
    return result


def repair_encrypted_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    no_decrypt: bool = False,
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
    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-object-sync-repair-") as tmp:
        sync_root = Path(tmp)
        try:
            downloaded = download_encrypted_object_bundle(
                client,
                sync_root,
                identity_files=identity_files,
                age_bin=age_bin,
                include_objects=not no_decrypt,
            )
        except FileNotFoundError as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "missing_manifest",
                f"missing encrypted sync object: {exc}",
                path=str(exc),
            )
        except (json.JSONDecodeError, UnicodeDecodeError, sync_bundle.SyncManifestError, ValueError) as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "invalid_manifest",
                str(exc),
            )
        except RuntimeError as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "object_store_unreachable",
                str(exc),
            )

        if not downloaded["ok"]:
            result = object_result_base(client.endpoint_url, prefix)
            result.update(
                {
                    "ok": False,
                    "downloaded": downloaded.get("downloaded", 0),
                    "issues": downloaded.get("issues", []),
                }
            )
            return result

        repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            sync_root,
            identity_files=identity_files,
            age_bin=age_bin,
            no_decrypt=no_decrypt,
        )
        result = object_result_base(client.endpoint_url, prefix)
        result.update(repair)
        result["downloaded"] = downloaded.get("downloaded", 0)
        return result


def status_encrypted_object_storage_bundle(
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
    repair = repair_encrypted_object_storage_bundle(
        object_store_url,
        prefix=prefix,
        no_decrypt=True,
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
    return {
        "ok": bool(repair.get("ok")),
        "encrypted": True,
        "backend": sync_object_storage.OBJECT_BACKEND,
        "object_store": repair.get("object_store"),
        "object_prefix": repair.get("object_prefix"),
        "manifest_exists": repair.get("manifest_exists", bool(repair.get("ok"))),
        "schema_version": repair.get("schema_version"),
        "recipient_match": repair.get("recipient_match", "unknown"),
        "raw_rollout_included": repair.get("raw_rollout_included", "unknown"),
        "issues": repair.get("issues", []),
    }


def pull_encrypted_object_storage_bundle(
    object_store_url: str | None,
    target_registry_dir: str | Path | None = None,
    *,
    prefix: str = sync_object_storage.DEFAULT_PREFIX,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
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
    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-object-sync-pull-") as tmp:
        sync_root = Path(tmp)
        try:
            downloaded = download_encrypted_object_bundle(
                client,
                sync_root,
                identity_files=identity_files,
                age_bin=age_bin,
                include_objects=True,
            )
        except FileNotFoundError as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "missing_manifest",
                f"missing encrypted sync object: {exc}",
                path=str(exc),
            )
        except (json.JSONDecodeError, UnicodeDecodeError, sync_bundle.SyncManifestError, ValueError) as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "invalid_manifest",
                str(exc),
            )
        except RuntimeError as exc:
            return failed_object_result(
                client.endpoint_url,
                prefix,
                "object_store_unreachable",
                str(exc),
            )

        if not downloaded["ok"]:
            result = object_result_base(client.endpoint_url, prefix)
            result.update(
                {
                    "ok": False,
                    "downloaded": downloaded.get("downloaded", 0),
                    "issues": downloaded.get("issues", []),
                }
            )
            return result

        pull = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            sync_root,
            target_registry_dir,
            identity_files=identity_files,
            age_bin=age_bin,
        )
        result = object_result_base(client.endpoint_url, prefix)
        result.update(pull)
        result["downloaded"] = downloaded.get("downloaded", 0)
        return result
