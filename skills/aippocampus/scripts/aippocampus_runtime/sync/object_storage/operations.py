#!/usr/bin/env python3
"""Bundle orchestration for the object-storage sync transport."""

from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync import contract as sync_contract
from aippocampus_runtime.sync.object_storage.client import (
    DEFAULT_PREFIX,
    DEFAULT_TIMEOUT_SECONDS,
    OBJECT_BACKEND,
    HttpObjectStoreClient,
    hash_bytes,
    normalize_object_prefix,
    object_key,
    object_storage_client_for,
    safe_endpoint_label,
)


def load_object_manifest(client: HttpObjectStoreClient) -> dict[str, Any]:
    data = client.get_object(sync_bundle.SYNC_MANIFEST_NAME)
    manifest = json.loads(data.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("object store manifest must be a JSON object")
    return manifest


def local_manifest_for_object_storage(manifest_path: Path, *, prefix: str) -> dict[str, Any]:
    manifest = sync_bundle.load_json(manifest_path)
    if not manifest:
        raise FileNotFoundError(f"missing local sync manifest: {manifest_path}")
    rewritten = dict(manifest)
    rewritten["backend"] = OBJECT_BACKEND
    rewritten["bundle_format"] = sync_contract.SYNC_BUNDLE_KIND
    rewritten["object_prefix"] = normalize_object_prefix(prefix)
    rewritten["privacy_boundary"] = sync_contract.sync_privacy_boundary(
        include_raw=bool(manifest.get("raw_rollout_included"))
    )
    rewritten["transport"] = sync_contract.sync_transport_metadata(
        kind=OBJECT_BACKEND,
        manifest_object=object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
    )
    return rewritten


def iter_manifest_paths(manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for item in manifest.get("files") or []:
        paths.append(sync_bundle.validate_relative_sync_path(str(item.get("path") or "")))
    return paths


def verify_manifest_objects(
    client: HttpObjectStoreClient, manifest: dict[str, Any]
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checked = 0
    for item in manifest.get("files") or []:
        try:
            relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        except ValueError as exc:
            issues.append(
                {"code": "unsafe_path", "path": str(item.get("path") or ""), "message": str(exc)}
            )
            continue
        try:
            data = client.get_object(relative_path)
        except FileNotFoundError:
            issues.append({"code": "missing_file", "path": relative_path.as_posix()})
            continue
        checked += 1
        actual_hash = hash_bytes(data)
        if actual_hash != item.get("sha256"):
            issues.append(
                {
                    "code": "hash_mismatch",
                    "path": relative_path.as_posix(),
                    "expected": item.get("sha256"),
                    "actual": actual_hash,
                    "expected_size": item.get("size"),
                    "actual_size": len(data),
                }
            )
    return {"ok": not issues, "checked": checked, "issues": issues}


def push_object_storage_bundle(
    registry_dir: str | Path | None,
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    include_raw: bool = False,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    client = object_storage_client_for(
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
    with tempfile.TemporaryDirectory(prefix="aippocampus-object-sync-push-") as tmp:
        sync_root = Path(tmp)
        try:
            local_push = sync_bundle.push_sync_bundle(
                registry_dir,
                sync_root,
                include_raw=include_raw,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "backend": OBJECT_BACKEND,
                "object_store": safe_endpoint_label(client.endpoint_url),
                "object_prefix": normalize_object_prefix(prefix),
                "issues": [{"code": str(exc).split(":", 1)[0], "message": str(exc)}],
            }
        manifest = local_manifest_for_object_storage(
            sync_root / sync_bundle.SYNC_MANIFEST_NAME, prefix=prefix
        )
        uploaded: list[dict[str, Any]] = []
        for relative_path in iter_manifest_paths(manifest):
            source = sync_bundle.ensure_within(sync_root, sync_root / relative_path)
            uploaded.append(client.put_object(relative_path, source.read_bytes()))

        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        manifest_upload = client.put_object(sync_bundle.SYNC_MANIFEST_NAME, manifest_bytes)
        return {
            "ok": True,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(client.endpoint_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_key": manifest_upload["key"],
            "file_count": manifest.get("file_count", len(uploaded)),
            "object_count": len(uploaded) + 1,
            "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
            "local_bundle_file_count": local_push.get("file_count"),
        }


def repair_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    client = object_storage_client_for(
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
        manifest = load_object_manifest(client)
    except FileNotFoundError:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(client.endpoint_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": False,
            "issues": [
                {
                    "code": "missing_manifest",
                    "path": object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
                }
            ],
        }
    except RuntimeError as exc:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(client.endpoint_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": None,
            "issues": [{"code": "object_store_unreachable", "message": str(exc)}],
        }
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(client.endpoint_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": True,
            "issues": [{"code": "invalid_manifest", "message": str(exc)}],
        }
    verification = verify_manifest_objects(client, manifest)
    return {
        "ok": verification["ok"],
        "backend": OBJECT_BACKEND,
        "object_store": safe_endpoint_label(client.endpoint_url),
        "object_prefix": normalize_object_prefix(prefix),
        "manifest_exists": True,
        "schema_version": manifest.get("schema_version"),
        "file_count": manifest.get("file_count", 0),
        "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
        "checked": verification["checked"],
        "issues": verification["issues"],
    }


def status_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    repair = repair_object_storage_bundle(
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
    return {
        "ok": bool(repair.get("ok")),
        "backend": OBJECT_BACKEND,
        "object_store": repair.get("object_store"),
        "object_prefix": repair.get("object_prefix"),
        "manifest_exists": repair.get("manifest_exists"),
        "schema_version": repair.get("schema_version"),
        "file_count": repair.get("file_count", 0),
        "raw_rollout_included": repair.get("raw_rollout_included", False),
        "issues": repair.get("issues", []),
    }


def download_object_bundle(client: HttpObjectStoreClient, sync_root: Path) -> dict[str, Any]:
    manifest = load_object_manifest(client)
    manifest_path = sync_root / sync_bundle.SYNC_MANIFEST_NAME
    sync_bundle.save_json(manifest_path, manifest)
    issues: list[dict[str, Any]] = []
    downloaded = 0
    for item in manifest.get("files") or []:
        relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        try:
            data = client.get_object(relative_path)
        except FileNotFoundError:
            issues.append({"code": "missing_file", "path": relative_path.as_posix()})
            continue
        actual_hash = hash_bytes(data)
        if actual_hash != item.get("sha256"):
            issues.append(
                {
                    "code": "hash_mismatch",
                    "path": relative_path.as_posix(),
                    "expected": item.get("sha256"),
                    "actual": actual_hash,
                    "expected_size": item.get("size"),
                    "actual_size": len(data),
                }
            )
            continue
        destination = sync_bundle.ensure_within(sync_root, sync_root / relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        downloaded += 1
    return {"ok": not issues, "manifest": manifest, "downloaded": downloaded, "issues": issues}


def pull_object_storage_bundle(
    object_store_url: str | None,
    target_registry_dir: str | Path | None = None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    client = object_storage_client_for(
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
    with tempfile.TemporaryDirectory(prefix="aippocampus-object-sync-pull-") as tmp:
        sync_root = Path(tmp)
        downloaded = download_object_bundle(client, sync_root)
        if not downloaded["ok"]:
            return {
                "ok": False,
                "backend": OBJECT_BACKEND,
                "object_store": safe_endpoint_label(client.endpoint_url),
                "object_prefix": normalize_object_prefix(prefix),
                "downloaded": downloaded["downloaded"],
                "issues": downloaded["issues"],
            }
        pull = sync_bundle.pull_sync_bundle(sync_root, target_registry_dir)
        return {
            "ok": bool(pull.get("ok")),
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(client.endpoint_url),
            "object_prefix": normalize_object_prefix(prefix),
            "downloaded": downloaded["downloaded"],
            "file_count": downloaded["manifest"].get("file_count", 0),
            "raw_rollout_included": bool(downloaded["manifest"].get("raw_rollout_included")),
            "pull": pull,
        }


def push_encrypted_object_storage_bundle(
    registry_dir: str | Path | None,
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    recipients: list[str] | None = None,
    recipient_files: list[str | Path] | None = None,
    include_raw: bool = False,
    age_bin: str | Path | None = None,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    encrypted_sync_object_storage = importlib.import_module(
        "aippocampus_runtime.sync.encrypted.object_storage"
    )

    return encrypted_sync_object_storage.push_encrypted_object_storage_bundle(
        registry_dir,
        object_store_url,
        prefix=prefix,
        recipients=recipients,
        recipient_files=recipient_files,
        include_raw=include_raw,
        age_bin=age_bin,
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


def repair_encrypted_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    identity_files: list[str | Path] | None = None,
    age_bin: str | Path | None = None,
    no_decrypt: bool = False,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    encrypted_sync_object_storage = importlib.import_module(
        "aippocampus_runtime.sync.encrypted.object_storage"
    )

    return encrypted_sync_object_storage.repair_encrypted_object_storage_bundle(
        object_store_url,
        prefix=prefix,
        identity_files=identity_files,
        age_bin=age_bin,
        no_decrypt=no_decrypt,
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


def status_encrypted_object_storage_bundle(
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    encrypted_sync_object_storage = importlib.import_module(
        "aippocampus_runtime.sync.encrypted.object_storage"
    )

    return encrypted_sync_object_storage.status_encrypted_object_storage_bundle(
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


def pull_encrypted_object_storage_bundle(
    object_store_url: str | None,
    target_registry_dir: str | Path | None = None,
    *,
    prefix: str = DEFAULT_PREFIX,
    identity_files: list[str | Path] | None = None,
    age_bin: str | Path | None = None,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    encrypted_sync_object_storage = importlib.import_module(
        "aippocampus_runtime.sync.encrypted.object_storage"
    )

    return encrypted_sync_object_storage.pull_encrypted_object_storage_bundle(
        object_store_url,
        target_registry_dir,
        prefix=prefix,
        identity_files=identity_files,
        age_bin=age_bin,
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
