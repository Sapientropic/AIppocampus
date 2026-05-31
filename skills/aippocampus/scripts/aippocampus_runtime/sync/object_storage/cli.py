#!/usr/bin/env python3
"""HTTP object-storage adapter for AIppocampus sync bundles.

The adapter intentionally reuses the local bundle manifest contract instead of
inventing a second sync format. The object store is only the transport/storage
boundary: generated clean-source artifacts stay hash-addressed by manifest,
source-device locators stay portable, and raw rollouts remain opt-in.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
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
    client_for,
    client_for_provider,
    hash_bytes,
    normalize_object_prefix,
    object_key,
    object_storage_client_for,
    safe_endpoint_label,
)

__all__ = ["client_for", "client_for_provider"]


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


def token_from_env(env_name: str | None) -> str | None:
    if not env_name:
        return None
    return os.environ.get(env_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "push", "pull", "repair"])
    parser.add_argument(
        "--object-store-url", default=os.environ.get("AIPPOCAMPUS_OBJECT_STORE_URL")
    )
    parser.add_argument(
        "--object-prefix", default=os.environ.get("AIPPOCAMPUS_OBJECT_PREFIX", DEFAULT_PREFIX)
    )
    parser.add_argument(
        "--object-provider", default=os.environ.get("AIPPOCAMPUS_OBJECT_PROVIDER")
    )
    parser.add_argument("--object-bucket", default=os.environ.get("AIPPOCAMPUS_OBJECT_BUCKET"))
    parser.add_argument("--object-region", default=os.environ.get("AIPPOCAMPUS_OBJECT_REGION"))
    parser.add_argument(
        "--object-account-id", default=os.environ.get("AIPPOCAMPUS_OBJECT_ACCOUNT_ID")
    )
    parser.add_argument("--token-env", default="AIPPOCAMPUS_OBJECT_STORE_TOKEN")
    parser.add_argument("--access-key-env", default="AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID")
    parser.add_argument("--secret-key-env", default="AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY")
    parser.add_argument("--session-token-env", default="AIPPOCAMPUS_OBJECT_SESSION_TOKEN")
    parser.add_argument("--registry-dir", default=None)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--encrypt", action="store_true")
    parser.add_argument("--require-encrypted", action="store_true")
    parser.add_argument("--recipient", action="append", default=[])
    parser.add_argument("--recipient-file", action="append", default=[])
    parser.add_argument("--identity-file", action="append", default=[])
    parser.add_argument("--age-bin", default=None)
    parser.add_argument("--no-decrypt", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    if not args.object_store_url and not args.object_provider:
        parser.error(
            "--object-store-url/AIPPOCAMPUS_OBJECT_STORE_URL or "
            "--object-provider/AIPPOCAMPUS_OBJECT_PROVIDER is required"
        )

    token = token_from_env(args.token_env)
    provider_kwargs = {
        "provider": args.object_provider,
        "bucket": args.object_bucket,
        "region": args.object_region,
        "account_id": args.object_account_id,
        "access_key_id": token_from_env(args.access_key_env),
        "secret_access_key": token_from_env(args.secret_key_env),
        "session_token": token_from_env(args.session_token_env),
    }
    if args.command == "status":
        if args.require_encrypted:
            result = status_encrypted_object_storage_bundle(
                args.object_store_url,
                prefix=args.object_prefix,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
        else:
            result = status_object_storage_bundle(
                args.object_store_url,
                prefix=args.object_prefix,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
    elif args.command == "push":
        if args.encrypt:
            result = push_encrypted_object_storage_bundle(
                args.registry_dir,
                args.object_store_url,
                prefix=args.object_prefix,
                recipients=args.recipient,
                recipient_files=args.recipient_file,
                include_raw=args.include_raw,
                age_bin=args.age_bin,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
        else:
            result = push_object_storage_bundle(
                args.registry_dir,
                args.object_store_url,
                prefix=args.object_prefix,
                include_raw=args.include_raw,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
    elif args.command == "pull":
        if args.require_encrypted:
            result = pull_encrypted_object_storage_bundle(
                args.object_store_url,
                args.registry_dir,
                prefix=args.object_prefix,
                identity_files=args.identity_file,
                age_bin=args.age_bin,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
        else:
            result = pull_object_storage_bundle(
                args.object_store_url,
                args.registry_dir,
                prefix=args.object_prefix,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
    else:
        if args.require_encrypted:
            result = repair_encrypted_object_storage_bundle(
                args.object_store_url,
                prefix=args.object_prefix,
                identity_files=args.identity_file,
                age_bin=args.age_bin,
                no_decrypt=args.no_decrypt,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )
        else:
            result = repair_object_storage_bundle(
                args.object_store_url,
                prefix=args.object_prefix,
                token=token,
                timeout=args.timeout,
                **provider_kwargs,
            )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"object sync {args.command}: {'ok' if result.get('ok') else 'needs attention'}")
        if result.get("manifest_key"):
            print(f"manifest object: {result['manifest_key']}")
        for issue in result.get("issues") or []:
            print(f"- {issue.get('code')}: {issue.get('path') or issue.get('message')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
