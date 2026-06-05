#!/usr/bin/env python3
"""Real-provider encrypted object-storage smoke for AIppocampus.

This smoke uses the production encrypted object-storage path against a
configured provider endpoint. It creates a temporary source registry, performs
push/status/repair/pull, then deletes the encrypted objects it uploaded.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import smoke_cross_device_sync

from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.encrypted import bundle as encrypted_sync_bundle
from aippocampus_runtime.sync.encrypted import object_storage as encrypted_sync_object_storage
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage
from aippocampus_runtime.sync.object_storage import client as object_storage_client

DEFAULT_SMOKE_PREFIX = "aippocampus/encrypted-sync-smoke"
PROVIDER_METADATA_SCHEMA_VERSION = 1
SIZE_BUCKETS: tuple[tuple[int, str], ...] = (
    (1024, "le_1KiB"),
    (4096, "le_4KiB"),
    (16384, "le_16KiB"),
    (65536, "le_64KiB"),
    (262144, "le_256KiB"),
    (1048576, "le_1MiB"),
)
OVER_1MIB_BUCKET = "gt_1MiB"
PATH_SHAPE_KEYS = (
    "encrypted_outer_manifest",
    "encrypted_inner_manifest",
    "encrypted_ciphertext_object",
    "unknown_encrypted_object",
)


def token_from_env(env: Mapping[str, str], env_name: str | None) -> str | None:
    if not env_name:
        return None
    return env.get(env_name)


def provider_args_from_env(
    env: Mapping[str, str] | None = None,
    *,
    access_key_env: str = "AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID",
    secret_key_env: str = "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY",
    session_token_env: str = "AIPPOCAMPUS_OBJECT_SESSION_TOKEN",
    token_env: str = "AIPPOCAMPUS_OBJECT_STORE_TOKEN",
) -> dict[str, Any]:
    env = env or os.environ
    return {
        "object_store_url": env.get("AIPPOCAMPUS_OBJECT_STORE_URL"),
        "provider": env.get("AIPPOCAMPUS_OBJECT_PROVIDER"),
        "bucket": env.get("AIPPOCAMPUS_OBJECT_BUCKET"),
        "region": env.get("AIPPOCAMPUS_OBJECT_REGION"),
        "account_id": env.get("AIPPOCAMPUS_OBJECT_ACCOUNT_ID"),
        "access_key_id": token_from_env(env, access_key_env),
        "secret_access_key": token_from_env(env, secret_key_env),
        "session_token": token_from_env(env, session_token_env),
        "token": token_from_env(env, token_env),
    }


def generated_age_identity(
    identity_path: Path,
    *,
    age_keygen_bin: str | Path | None = None,
) -> tuple[Path, str]:
    keygen_bin = str(age_keygen_bin or "age-keygen")
    proc = subprocess.run(
        [keygen_bin, "-o", str(identity_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for line in [*proc.stderr.splitlines(), *proc.stdout.splitlines()]:
        if "public key:" in line.lower():
            return identity_path, line.split(":", 1)[1].strip()
    raise RuntimeError("age-keygen did not emit a public key")


def encrypted_cleanup_relative_paths(inner_manifest: dict[str, Any]) -> list[Path]:
    paths = [encrypted_sync_object_storage.encrypted_manifest_relative_path()]
    outer = inner_manifest.get("outer_manifest") or {}
    manifest_object = (outer.get("encryption") or {}).get("manifest_object")
    if manifest_object:
        paths.append(sync_bundle.validate_relative_sync_path(str(manifest_object)))
    for record in inner_manifest.get("objects") or []:
        paths.append(sync_bundle.validate_relative_sync_path(str(record.get("object_path") or "")))
    return sorted({path.as_posix(): path for path in paths}.values(), key=lambda path: path.as_posix())


def cleanup_encrypted_objects(
    client: object_storage_client.HttpObjectStoreClient,
    relative_paths: Iterable[Path],
) -> dict[str, Any]:
    paths = sorted({path.as_posix(): path for path in relative_paths}.values(), reverse=True)
    errors: list[dict[str, str]] = []
    missing_before_delete: list[str] = []
    missing_after_delete: list[str] = []
    deleted = 0

    for path in paths:
        try:
            client.request("DELETE", path)
            deleted += 1
        except FileNotFoundError:
            missing_before_delete.append(path.as_posix())
        except RuntimeError as exc:
            errors.append({"path": path.as_posix(), "error": str(exc)})

    for path in paths:
        try:
            client.get_object(path)
        except FileNotFoundError:
            continue
        except RuntimeError as exc:
            errors.append({"path": path.as_posix(), "error": str(exc)})
            continue
        missing_after_delete.append(path.as_posix())

    return {
        "attempted": len(paths),
        "deleted": deleted,
        "missing_before_delete": missing_before_delete,
        "missing_after_delete": missing_after_delete,
        "errors": errors,
    }


def size_bucket_label(size: int) -> str:
    for ceiling, label in SIZE_BUCKETS:
        if size <= ceiling:
            return label
    return OVER_1MIB_BUCKET


def metadata_path_shape(path: Path, *, inner_manifest_object: str | None) -> str:
    normalized = path.as_posix()
    if normalized == encrypted_sync_object_storage.encrypted_manifest_relative_path().as_posix():
        return "encrypted_outer_manifest"
    if inner_manifest_object and normalized == inner_manifest_object:
        return "encrypted_inner_manifest"
    if (
        len(path.parts) == 3
        and path.parts[0] == encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
        and path.parts[1] == encrypted_sync_bundle.ENCRYPTED_OBJECTS_DIR_NAME
        and path.suffix == ".age"
    ):
        return "encrypted_ciphertext_object"
    return "unknown_encrypted_object"


def empty_provider_metadata() -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_METADATA_SCHEMA_VERSION,
        "source": "encrypted_object_storage_smoke",
        "object_count": 0,
        "total_ciphertext_bytes": 0,
        "min_ciphertext_bytes": 0,
        "max_ciphertext_bytes": 0,
        "size_bucket_counts": {label: 0 for _, label in SIZE_BUCKETS} | {OVER_1MIB_BUCKET: 0},
        "path_shape_counts": {key: 0 for key in PATH_SHAPE_KEYS},
        "claims": {
            "provider_can_observe_object_count": False,
            "provider_can_observe_ciphertext_object_sizes": False,
            "metadata_padding_evaluated": False,
            "traffic_analysis_resistance": False,
        },
        "cannot_claim": [
            "traffic_analysis_resistance",
            "metadata_padding_cost_benefit",
            "provider_console_cleanup",
            "broader_provider_matrix",
        ],
        "errors": [],
    }


def observe_provider_metadata(
    client: object_storage_client.HttpObjectStoreClient,
    relative_paths: Iterable[Path],
    inner_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Return public-safe provider-visible metadata evidence for a smoke run.

    The provider and its console can see object keys, counts, sizes, and upload
    cadence. The smoke keeps the published evidence deliberately aggregated:
    no object keys, credential material, endpoint URLs, or decrypted registry
    contents leave this helper.
    """

    metadata = empty_provider_metadata()
    paths = sorted({path.as_posix(): path for path in relative_paths}.values())
    inner_manifest_object = str(
        ((inner_manifest.get("outer_manifest") or {}).get("encryption") or {}).get(
            "manifest_object"
        )
        or ""
    )
    sizes: list[int] = []

    for index, path in enumerate(paths):
        shape = metadata_path_shape(path, inner_manifest_object=inner_manifest_object)
        metadata["path_shape_counts"][shape] = metadata["path_shape_counts"].get(shape, 0) + 1
        try:
            data = client.get_object(path)
        except FileNotFoundError:
            metadata["errors"].append(
                {
                    "index": index,
                    "path_shape": shape,
                    "code": "missing_file",
                    "message": "encrypted smoke object was missing during metadata observation",
                }
            )
            continue
        except RuntimeError as exc:
            metadata["errors"].append(
                {
                    "index": index,
                    "path_shape": shape,
                    "code": "request_failed",
                    "error_type": type(exc).__name__,
                    "message": "encrypted smoke object could not be read during metadata observation",
                }
            )
            continue
        size = len(data)
        sizes.append(size)
        bucket = size_bucket_label(size)
        metadata["size_bucket_counts"][bucket] += 1

    if sizes:
        metadata.update(
            {
                "object_count": len(sizes),
                "total_ciphertext_bytes": sum(sizes),
                "min_ciphertext_bytes": min(sizes),
                "max_ciphertext_bytes": max(sizes),
            }
        )
        metadata["claims"]["provider_can_observe_object_count"] = True
        metadata["claims"]["provider_can_observe_ciphertext_object_sizes"] = True
    return metadata


def issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update(extra)
    return payload


def summarize_step(result: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "ok",
        "encrypted",
        "backend",
        "object_prefix",
        "manifest_key",
        "manifest_exists",
        "schema_version",
        "recipient_match",
        "raw_rollout_included",
        "manifest_hash",
        "manifest_revision",
        "object_count",
        "file_count",
        "local_bundle_file_count",
        "downloaded",
        "checked",
        "issues",
    }
    return {key: value for key, value in result.items() if key in allowed_keys}


def provider_kwargs(
    *,
    provider: str | None,
    bucket: str | None,
    region: str | None,
    account_id: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
    session_token: str | None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "bucket": bucket,
        "region": region,
        "account_id": account_id,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "session_token": session_token,
    }


def run_real_provider_encrypted_sync_smoke(
    *,
    object_store_url: str | None = None,
    prefix: str = DEFAULT_SMOKE_PREFIX,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
    token: str | None = None,
    recipient: str | None = None,
    recipient_files: Iterable[str | Path] | None = None,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    age_keygen_bin: str | Path | None = None,
    run_id: str | None = None,
    timeout: float = sync_object_storage.DEFAULT_TIMEOUT_SECONDS,
    keep_objects: bool = False,
) -> dict[str, Any]:
    provider_values = provider_kwargs(
        provider=provider,
        bucket=bucket,
        region=region,
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
    )
    if not object_store_url and not provider:
        return {
            "ok": False,
            "issues": [
                issue(
                    "missing_object_store",
                    "AIPPOCAMPUS_OBJECT_STORE_URL or AIPPOCAMPUS_OBJECT_PROVIDER is required",
                )
            ],
        }

    run_id = run_id or f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    base_prefix = sync_object_storage.normalize_object_prefix(prefix or DEFAULT_SMOKE_PREFIX)
    smoke_prefix = sync_object_storage.object_key(base_prefix, f"real-provider-{run_id}")
    temp_root = Path(tempfile.mkdtemp(prefix="aippocampus-real-provider-smoke-"))
    failures: list[dict[str, Any]] = []
    steps: dict[str, Any] = {}
    cleanup: dict[str, Any] = {
        "attempted": 0,
        "deleted": 0,
        "missing_before_delete": [],
        "missing_after_delete": [],
        "errors": [],
        "kept_objects": keep_objects,
    }
    provider_metadata: dict[str, Any] = empty_provider_metadata()

    try:
        identity_paths: list[str | Path] = [Path(path) for path in identity_files or []]
        recipients = [recipient] if recipient else []
        if recipient_files:
            recipient_file_values: list[str | Path] = [Path(path) for path in recipient_files]
        else:
            recipient_file_values = []
        if not recipients and not recipient_file_values:
            generated_identity_path, generated_recipient = generated_age_identity(
                temp_root / "age-identity.txt",
                age_keygen_bin=age_keygen_bin,
            )
            identity_paths.append(generated_identity_path)
            recipients.append(generated_recipient)
        if not identity_paths:
            failures.append(
                issue(
                    "missing_identity",
                    "identity_files are required when using explicit recipients",
                )
            )

        device = smoke_cross_device_sync.create_device_registry(
            temp_root / "source-device",
            device_name="real-provider-source",
            workspace_locator="/tmp/aippocampus-real-provider-source",
            message_text="Real provider encrypted object-storage sync smoke.",
        )
        target_registry = temp_root / "target-device" / "registry"

        if not failures:
            steps["push"] = sync_object_storage.push_encrypted_object_storage_bundle(
                device["registry"],
                object_store_url,
                prefix=smoke_prefix,
                recipients=recipients,
                recipient_files=recipient_file_values,
                age_bin=age_bin,
                token=token,
                timeout=timeout,
                **provider_values,
            )
            steps["status"] = sync_object_storage.status_encrypted_object_storage_bundle(
                object_store_url,
                prefix=smoke_prefix,
                token=token,
                timeout=timeout,
                **provider_values,
            )
            steps["repair"] = sync_object_storage.repair_encrypted_object_storage_bundle(
                object_store_url,
                prefix=smoke_prefix,
                identity_files=identity_paths,
                age_bin=age_bin,
                token=token,
                timeout=timeout,
                **provider_values,
            )
            steps["pull"] = sync_object_storage.pull_encrypted_object_storage_bundle(
                object_store_url,
                target_registry,
                prefix=smoke_prefix,
                identity_files=identity_paths,
                age_bin=age_bin,
                token=token,
                timeout=timeout,
                **provider_values,
            )

        for name in ("push", "status", "repair", "pull"):
            if name in steps and not steps[name].get("ok"):
                failures.append(issue(f"{name}_failed", f"{name} failed", result=steps[name]))

        target_threads_exists = (target_registry / "threads.json").is_file()
        if "pull" in steps and steps["pull"].get("ok") and not target_threads_exists:
            failures.append(issue("missing_target_registry", "pull did not materialize threads.json"))
        raw_rollout_synced = (target_registry / "raw-rollouts").exists()
        if raw_rollout_synced:
            failures.append(
                issue("raw_rollout_synced_without_opt_in", "raw rollout was pulled unexpectedly")
            )

        if "repair" in steps and steps["repair"].get("inner_manifest"):
            try:
                cleanup_paths = encrypted_cleanup_relative_paths(steps["repair"]["inner_manifest"])
            except ValueError as exc:
                cleanup_paths = []
                failures.append(issue("cleanup_path_invalid", str(exc)))
            expected_count = steps.get("push", {}).get("object_count")
            if expected_count is not None and len(cleanup_paths) != expected_count:
                failures.append(
                    issue(
                        "cleanup_object_count_mismatch",
                        "cleanup path count did not match pushed encrypted object count",
                        expected=expected_count,
                        actual=len(cleanup_paths),
                    )
                )
            client = object_storage_client.object_storage_client_for(
                object_store_url,
                prefix=smoke_prefix,
                token=token,
                timeout=timeout,
                **provider_values,
            )
            provider_metadata = observe_provider_metadata(
                client,
                cleanup_paths,
                steps["repair"]["inner_manifest"],
            )
            if provider_metadata["errors"]:
                failures.append(
                    issue(
                        "provider_metadata_observation_failed",
                        "one or more encrypted smoke objects could not be sampled for metadata evidence",
                        errors=provider_metadata["errors"],
                    )
                )
            if keep_objects:
                cleanup.update({"attempted": len(cleanup_paths), "kept_objects": True})
            else:
                cleanup.update(cleanup_encrypted_objects(client, cleanup_paths))
                if cleanup["errors"] or cleanup["missing_after_delete"]:
                    failures.append(
                        issue(
                            "cleanup_failed",
                            "one or more encrypted smoke objects survived cleanup",
                            cleanup=cleanup,
                        )
                    )
        elif not keep_objects:
            failures.append(
                issue("cleanup_manifest_unavailable", "repair did not return an inner manifest")
            )

        provider_label = provider or ("generic-http" if object_store_url else "unknown")
        return {
            "ok": not failures,
            "provider": provider_label,
            "bucket": bucket,
            "prefix": smoke_prefix,
            "claims": {
                "encrypted_object_storage_protocol_executed": bool(steps),
                "real_provider_mode": bool(provider and provider != "generic-http"),
                "generated_ephemeral_age_identity": not bool(identity_files),
            },
            "steps": {name: summarize_step(step) for name, step in steps.items()},
            "provider_metadata": provider_metadata,
            "cleanup": cleanup,
            "observed": {
                "target_threads_exists": target_threads_exists,
                "raw_rollout_synced_without_opt_in": raw_rollout_synced,
                "recipient_match": steps.get("repair", {}).get("recipient_match"),
            },
            "issues": failures,
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--object-store-url", default=os.environ.get("AIPPOCAMPUS_OBJECT_STORE_URL")
    )
    parser.add_argument(
        "--object-prefix",
        default=os.environ.get("AIPPOCAMPUS_OBJECT_PREFIX", DEFAULT_SMOKE_PREFIX),
    )
    parser.add_argument("--object-provider", default=os.environ.get("AIPPOCAMPUS_OBJECT_PROVIDER"))
    parser.add_argument("--object-bucket", default=os.environ.get("AIPPOCAMPUS_OBJECT_BUCKET"))
    parser.add_argument("--object-region", default=os.environ.get("AIPPOCAMPUS_OBJECT_REGION"))
    parser.add_argument(
        "--object-account-id", default=os.environ.get("AIPPOCAMPUS_OBJECT_ACCOUNT_ID")
    )
    parser.add_argument("--token-env", default="AIPPOCAMPUS_OBJECT_STORE_TOKEN")
    parser.add_argument("--access-key-env", default="AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID")
    parser.add_argument("--secret-key-env", default="AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY")
    parser.add_argument("--session-token-env", default="AIPPOCAMPUS_OBJECT_SESSION_TOKEN")
    parser.add_argument("--recipient")
    parser.add_argument("--recipient-file", action="append", default=[])
    parser.add_argument("--identity-file", action="append", default=[])
    parser.add_argument("--age-bin", default=None)
    parser.add_argument("--age-keygen-bin", default=None)
    parser.add_argument("--run-id")
    parser.add_argument("--timeout", type=float, default=sync_object_storage.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-objects", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    env_provider_args = provider_args_from_env(
        access_key_env=args.access_key_env,
        secret_key_env=args.secret_key_env,
        session_token_env=args.session_token_env,
        token_env=args.token_env,
    )
    result = run_real_provider_encrypted_sync_smoke(
        object_store_url=args.object_store_url,
        prefix=args.object_prefix,
        provider=args.object_provider,
        bucket=args.object_bucket,
        region=args.object_region,
        account_id=args.object_account_id,
        access_key_id=env_provider_args["access_key_id"],
        secret_access_key=env_provider_args["secret_access_key"],
        session_token=env_provider_args["session_token"],
        token=env_provider_args["token"],
        recipient=args.recipient,
        recipient_files=args.recipient_file,
        identity_files=args.identity_file,
        age_bin=args.age_bin,
        age_keygen_bin=args.age_keygen_bin,
        run_id=args.run_id,
        timeout=args.timeout,
        keep_objects=args.keep_objects,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"real-provider encrypted sync smoke: {'ok' if result.get('ok') else 'failed'}")
        print(f"provider: {result.get('provider')}")
        print(f"prefix: {result.get('prefix')}")
        for failure in result.get("issues") or []:
            print(f"- {failure.get('code')}: {failure.get('message')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
