#!/usr/bin/env python3
"""Encrypted local-folder sync bundle for AIppocampus memory artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.core import aippocampus_registry_dir, file_sha256, now_utc, safe_path_name
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.encrypted import keys as encrypted_sync_keys
from aippocampus_runtime.sync.encrypted.crypto import (
    EncryptedSyncError,
    decrypt_with_age,
    encrypt_with_age,
    issue,
    recipients_from_files,
    resolve_age_binary,
    validate_recipients,
)

ENCRYPTED_SYNC_SCHEMA_VERSION = 1
ENCRYPTED_SYNC_DIR_NAME = "encrypted-sync"
ENCRYPTED_SYNC_MANIFEST_NAME = "aippocampus-encrypted-sync-manifest.json"
ENCRYPTED_OBJECTS_DIR_NAME = "objects"
ENCRYPTED_STATE_DIR = ".sync-state/encrypted"


def failed_result(sync_root: Path, code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "encrypted": True,
        "sync_dir": str(sync_root),
        "issues": [issue(code, message, **extra)],
    }


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_json(data: Any) -> str:
    return sha256_bytes(canonical_json_bytes(data))


def inner_manifest_hash_payload(inner_manifest: dict[str, Any]) -> dict[str, Any]:
    payload = dict(inner_manifest)
    payload.pop("manifest_hash", None)
    objects = []
    for record in payload.get("objects") or []:
        item = dict(record)
        item.pop("manifest_hash", None)
        objects.append(item)
    payload["objects"] = objects
    return payload


def encrypted_root(sync_root: Path) -> Path:
    return sync_root / ENCRYPTED_SYNC_DIR_NAME


def encrypted_manifest_path(sync_root: Path) -> Path:
    return encrypted_root(sync_root) / ENCRYPTED_SYNC_MANIFEST_NAME


def encrypted_state_file(registry_dir: Path, vault_id_hash: str) -> Path:
    return registry_dir / ENCRYPTED_STATE_DIR / f"{safe_path_name(vault_id_hash, 'vault')}.json"


def load_encrypted_state(registry_dir: Path, vault_id_hash: str) -> dict[str, Any]:
    return sync_bundle.load_json(encrypted_state_file(registry_dir, vault_id_hash))


def save_encrypted_state(registry_dir: Path, inner_manifest: dict[str, Any]) -> None:
    state = {
        "vault_id_hash": inner_manifest.get("vault_id_hash"),
        "manifest_hash": inner_manifest.get("manifest_hash"),
        "manifest_revision": inner_manifest.get("manifest_revision"),
        "key_epoch": inner_manifest.get("key_epoch"),
        "parent_manifest_hash": inner_manifest.get("parent_manifest_hash"),
        "updated_at": now_utc(),
    }
    sync_bundle.save_json(
        encrypted_state_file(registry_dir, str(inner_manifest.get("vault_id_hash"))), state
    )


def vault_id_hash_for_registry(registry_dir: Path) -> str:
    state_dir = registry_dir / ENCRYPTED_STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    vault_file = state_dir / "vault-id"
    if vault_file.is_file():
        vault_id = vault_file.read_text(encoding="utf-8").strip()
    else:
        vault_id = uuid.uuid4().hex
        vault_file.write_text(vault_id + "\n", encoding="utf-8")
        try:
            os.chmod(vault_file, 0o600)
        except OSError:
            pass
    return sha256_bytes(vault_id.encode("utf-8"))


def plaintext_sync_markers(sync_root: Path) -> list[Path]:
    markers = [sync_root / sync_bundle.SYNC_MANIFEST_NAME]
    markers.extend(sync_root / name for name in sync_bundle.MANAGED_SYNC_DIRS)
    return [path for path in markers if path.exists()]


def ensure_encrypted_sync_root_safe(sync_root: Path) -> dict[str, Any] | None:
    markers = plaintext_sync_markers(sync_root)
    if not markers:
        return None
    return issue(
        "mixed_sync_dir",
        "encrypted sync refuses to share a sync directory with plaintext sync data",
        paths=[str(path) for path in markers],
    )


def encrypted_outer_manifest(manifest_object: Path) -> dict[str, Any]:
    return {
        "kind": "aippocampus_encrypted_sync_bundle",
        "schema_version": ENCRYPTED_SYNC_SCHEMA_VERSION,
        "encryption": {
            "format": "age",
            "manifest_object": manifest_object.as_posix(),
        },
    }


def load_encrypted_outer_manifest(sync_root: Path) -> dict[str, Any]:
    manifest = sync_bundle.load_sync_manifest(encrypted_manifest_path(sync_root))
    if (
        manifest.get("kind") != "aippocampus_encrypted_sync_bundle"
        or manifest.get("schema_version") != ENCRYPTED_SYNC_SCHEMA_VERSION
        or (manifest.get("encryption") or {}).get("format") != "age"
    ):
        raise sync_bundle.SyncManifestError(
            f"unrecognized encrypted sync manifest: {encrypted_manifest_path(sync_root)}"
        )
    manifest_object = (manifest.get("encryption") or {}).get("manifest_object")
    sync_bundle.validate_relative_sync_path(str(manifest_object or ""))
    return manifest


def encrypted_manifest_object_path(sync_root: Path, outer: dict[str, Any]) -> Path:
    manifest_object = str((outer.get("encryption") or {}).get("manifest_object") or "")
    relative = sync_bundle.validate_relative_sync_path(manifest_object)
    return sync_bundle.ensure_within(sync_root, sync_root / relative)


def build_encrypted_inner_manifest(
    *,
    plain_root: Path,
    encrypted_root_path: Path,
    plain_manifest: dict[str, Any],
    outer_manifest_object: Path,
    recipients: list[str],
    registry_root: Path,
    age_bin: str,
) -> tuple[dict[str, Any], int]:
    vault_id_hash = vault_id_hash_for_registry(registry_root)
    previous_state = load_encrypted_state(registry_root, vault_id_hash)
    revision = int(previous_state.get("manifest_revision") or 0) + 1
    parent_hash = previous_state.get("manifest_hash")
    recipient_set_hash = sha256_bytes("\n".join(sorted(recipients)).encode("utf-8"))
    device_metadata = encrypted_sync_keys.device_sync_metadata(registry_root, recipients)
    objects: list[dict[str, Any]] = []

    for item in plain_manifest.get("files") or []:
        relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        source = sync_bundle.ensure_within(plain_root, plain_root / relative_path)
        object_id = uuid.uuid4().hex
        object_path = Path(ENCRYPTED_SYNC_DIR_NAME) / ENCRYPTED_OBJECTS_DIR_NAME / f"{object_id}.age"
        encrypted_destination = encrypted_root_path / ENCRYPTED_OBJECTS_DIR_NAME / f"{object_id}.age"
        encrypt_with_age(source, encrypted_destination, recipients=recipients, age_bin=age_bin)
        objects.append(
            {
                "object_id": object_id,
                "object_path": object_path.as_posix(),
                "logical_path": relative_path.as_posix(),
                "object_type": relative_path.as_posix().replace("/", "_"),
                "manifest_revision": revision,
                "ciphertext_sha256": file_sha256(encrypted_destination),
                "ciphertext_size": encrypted_destination.stat().st_size,
                "plaintext_sha256": file_sha256(source),
                "plaintext_size": source.stat().st_size,
            }
        )

    outer = encrypted_outer_manifest(outer_manifest_object)
    inner_without_hash: dict[str, Any] = {
        "kind": "aippocampus_encrypted_sync_inner_manifest",
        "schema_version": ENCRYPTED_SYNC_SCHEMA_VERSION,
        "encrypted_schema_version": ENCRYPTED_SYNC_SCHEMA_VERSION,
        "vault_id_hash": vault_id_hash,
        "source_device_id": device_metadata["source_device_id"],
        "source_device_name": device_metadata.get("source_device_name"),
        "manifest_revision": revision,
        "key_epoch": device_metadata["key_epoch"],
        "recipient_set_hash": recipient_set_hash,
        "recipient_count": device_metadata["recipient_count"],
        "encrypted_manifest_object_id": outer_manifest_object.name,
        "outer_manifest": outer,
        "parent_manifest_hash": parent_hash,
        "plaintext_sync_schema_version": plain_manifest.get("schema_version"),
        "sync_manifest": plain_manifest,
        "objects": objects,
        "raw_rollout_included": bool(plain_manifest.get("raw_rollout_included")),
    }
    manifest_hash = hash_json(inner_manifest_hash_payload(inner_without_hash))
    for record in objects:
        record["manifest_hash"] = manifest_hash
    inner_manifest = dict(inner_without_hash)
    inner_manifest["objects"] = objects
    inner_manifest["manifest_hash"] = manifest_hash
    return inner_manifest, len(objects)


def push_encrypted_sync_bundle(
    registry_dir: str | Path | None,
    sync_dir: str | Path,
    *,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
    include_raw: bool = False,
    age_bin: str | Path | None = None,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve() if registry_dir else aippocampus_registry_dir().resolve()
    sync_root = Path(sync_dir).resolve()
    sync_root.mkdir(parents=True, exist_ok=True)

    mixed_issue = ensure_encrypted_sync_root_safe(sync_root)
    if mixed_issue:
        return failed_result(sync_root, mixed_issue["code"], mixed_issue["message"])

    explicit_recipients: list[str] = []
    if recipients:
        explicit_recipients, recipient_issue = validate_recipients(recipients)
    else:
        recipient_issue = None
    if recipient_issue:
        return failed_result(sync_root, recipient_issue["code"], recipient_issue["message"])

    file_recipients, file_issue = recipients_from_files(recipient_files)
    if file_issue and recipient_files:
        return failed_result(sync_root, file_issue["code"], file_issue["message"])
    trusted_recipients = (
        encrypted_sync_keys.trusted_recipients_for_registry(registry_root)
        if not explicit_recipients and not file_recipients
        else []
    )
    all_recipients = explicit_recipients + file_recipients + trusted_recipients
    all_recipients, recipient_issue = validate_recipients(all_recipients)
    if recipient_issue:
        return failed_result(sync_root, recipient_issue["code"], recipient_issue["message"])
    revoked_issue = encrypted_sync_keys.revoked_recipient_issue_for_registry(
        registry_root, all_recipients
    )
    if revoked_issue:
        extra = {key: value for key, value in revoked_issue.items() if key not in {"code", "message"}}
        return failed_result(
            sync_root,
            revoked_issue["code"],
            revoked_issue["message"],
            **extra,
        )

    resolved_age, age_issue = resolve_age_binary(age_bin)
    if age_issue or not resolved_age:
        return failed_result(sync_root, age_issue["code"], age_issue["message"])  # type: ignore[index]

    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-sync-push-") as tmp:
        tmp_root = Path(tmp)
        plain_root = tmp_root / "plain"
        encrypted_tmp_root = tmp_root / ENCRYPTED_SYNC_DIR_NAME
        local_push = sync_bundle.push_sync_bundle(
            registry_root,
            plain_root,
            include_raw=include_raw,
            allow_plaintext_raw=True,
        )
        plain_manifest = sync_bundle.load_sync_manifest(plain_root / sync_bundle.SYNC_MANIFEST_NAME)
        manifest_object_id = uuid.uuid4().hex
        manifest_object = (
            Path(ENCRYPTED_SYNC_DIR_NAME)
            / ENCRYPTED_OBJECTS_DIR_NAME
            / f"{manifest_object_id}.age"
        )
        inner_manifest, object_count = build_encrypted_inner_manifest(
            plain_root=plain_root,
            encrypted_root_path=encrypted_tmp_root,
            plain_manifest=plain_manifest,
            outer_manifest_object=manifest_object,
            recipients=all_recipients,
            registry_root=registry_root,
            age_bin=resolved_age,
        )
        inner_plain = tmp_root / "inner-manifest.json"
        inner_plain.write_text(
            json.dumps(inner_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        encrypt_with_age(
            inner_plain,
            encrypted_tmp_root / ENCRYPTED_OBJECTS_DIR_NAME / f"{manifest_object_id}.age",
            recipients=all_recipients,
            age_bin=resolved_age,
        )
        sync_bundle.save_json(encrypted_tmp_root / ENCRYPTED_SYNC_MANIFEST_NAME, inner_manifest["outer_manifest"])

        target_root = encrypted_root(sync_root)
        if target_root.exists():
            shutil.rmtree(target_root)
        shutil.copytree(encrypted_tmp_root, target_root)
        save_encrypted_state(registry_root, inner_manifest)
        reencryption = encrypted_sync_keys.mark_reencrypted_after_push(
            registry_root, inner_manifest, recipients=all_recipients
        )

    return {
        "ok": True,
        "encrypted": True,
        "sync_dir": str(sync_root),
        "manifest": str(encrypted_manifest_path(sync_root)),
        "file_count": plain_manifest.get("file_count", object_count),
        "object_count": object_count,
        "raw_rollout_included": bool(plain_manifest.get("raw_rollout_included")),
        "manifest_hash": inner_manifest.get("manifest_hash"),
        "manifest_revision": inner_manifest.get("manifest_revision"),
        "reencryption": reencryption,
        "local_bundle_file_count": local_push.get("file_count"),
    }


def decrypt_inner_manifest(
    sync_root: Path,
    *,
    identity_files: Iterable[str | Path] | None,
    age_bin: str,
    tmp_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outer = load_encrypted_outer_manifest(sync_root)
    encrypted_manifest = encrypted_manifest_object_path(sync_root, outer)
    if not encrypted_manifest.is_file():
        raise EncryptedSyncError("missing_file", f"missing encrypted inner manifest: {encrypted_manifest}")
    inner_plain = tmp_root / "inner-manifest.json"
    decrypt_with_age(encrypted_manifest, inner_plain, identity_files=identity_files, age_bin=age_bin)
    try:
        inner = json.loads(inner_plain.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EncryptedSyncError("invalid_manifest", f"invalid encrypted inner manifest: {exc}")
    if not isinstance(inner, dict):
        raise EncryptedSyncError("invalid_manifest", "encrypted inner manifest must be an object")
    if inner.get("outer_manifest") != outer:
        raise EncryptedSyncError("outer_manifest_mismatch", "outer manifest does not match inner")
    expected_hash = inner.get("manifest_hash")
    if hash_json(inner_manifest_hash_payload(inner)) != expected_hash:
        raise EncryptedSyncError("inner_manifest_hash_mismatch", "inner manifest hash mismatch")
    return outer, inner


def materialize_encrypted_sync_bundle(
    sync_root: Path,
    plain_root: Path,
    *,
    identity_files: Iterable[str | Path] | None,
    age_bin: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-sync-manifest-") as tmp:
        _, inner = decrypt_inner_manifest(
            sync_root,
            identity_files=identity_files,
            age_bin=age_bin,
            tmp_root=Path(tmp),
        )

    issues: list[dict[str, Any]] = []
    checked = 0
    for record in inner.get("objects") or []:
        try:
            object_path = sync_bundle.validate_relative_sync_path(str(record.get("object_path") or ""))
            logical_path = sync_bundle.validate_relative_sync_path(str(record.get("logical_path") or ""))
        except ValueError as exc:
            issues.append(issue("unsafe_path", str(exc)))
            continue
        if record.get("manifest_hash") != inner.get("manifest_hash"):
            issues.append(
                issue(
                    "inner_manifest_hash_mismatch",
                    "object record is not bound to the encrypted inner manifest",
                    path=object_path.as_posix(),
                )
            )
            continue
        source = sync_bundle.ensure_within(sync_root, sync_root / object_path)
        if not source.is_file():
            issues.append(
                issue(
                    "missing_file",
                    f"missing encrypted object: {object_path}",
                    path=object_path.as_posix(),
                )
            )
            continue
        actual_ciphertext = file_sha256(source)
        if actual_ciphertext != record.get("ciphertext_sha256"):
            issues.append(
                issue(
                    "hash_mismatch",
                    "encrypted object hash mismatch",
                    path=object_path.as_posix(),
                    expected=record.get("ciphertext_sha256"),
                    actual=actual_ciphertext,
                )
            )
            continue
        destination = sync_bundle.ensure_within(plain_root, plain_root / logical_path)
        try:
            decrypt_with_age(source, destination, identity_files=identity_files, age_bin=age_bin)
        except EncryptedSyncError as exc:
            issues.append(issue(exc.code, exc.message, path=object_path.as_posix()))
            continue
        actual_plaintext = file_sha256(destination)
        if actual_plaintext != record.get("plaintext_sha256"):
            issues.append(
                issue(
                    "plaintext_hash_mismatch",
                    "decrypted object hash mismatch",
                    path=logical_path.as_posix(),
                    expected=record.get("plaintext_sha256"),
                    actual=actual_plaintext,
                )
            )
            continue
        checked += 1

    if issues:
        return {"ok": False, "inner_manifest": inner, "checked": checked, "issues": issues}

    sync_bundle.save_json(plain_root / sync_bundle.SYNC_MANIFEST_NAME, inner.get("sync_manifest") or {})
    return {"ok": True, "inner_manifest": inner, "checked": checked, "issues": []}


def repair_encrypted_sync_bundle(
    sync_dir: str | Path,
    *,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    no_decrypt: bool = False,
) -> dict[str, Any]:
    sync_root = Path(sync_dir).resolve()
    try:
        outer = load_encrypted_outer_manifest(sync_root)
        manifest_object = encrypted_manifest_object_path(sync_root, outer)
    except FileNotFoundError:
        return failed_result(
            sync_root,
            "missing_manifest",
            f"missing encrypted sync manifest: {encrypted_manifest_path(sync_root)}",
        )
    except (sync_bundle.SyncManifestError, ValueError) as exc:
        return failed_result(sync_root, "invalid_manifest", str(exc))

    if not manifest_object.is_file():
        return failed_result(
            sync_root,
            "missing_file",
            f"missing encrypted inner manifest: {manifest_object}",
            path=str(manifest_object),
        )
    if no_decrypt:
        return {
            "ok": True,
            "encrypted": True,
            "sync_dir": str(sync_root),
            "manifest_exists": True,
            "schema_version": ENCRYPTED_SYNC_SCHEMA_VERSION,
            "recipient_match": "unknown",
            "raw_rollout_included": "unknown",
            "checked": 1,
            "issues": [],
        }

    resolved_age, age_issue = resolve_age_binary(age_bin)
    if age_issue or not resolved_age:
        return failed_result(sync_root, age_issue["code"], age_issue["message"])  # type: ignore[index]

    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-sync-repair-") as tmp:
        plain_root = Path(tmp) / "plain"
        try:
            materialized = materialize_encrypted_sync_bundle(
                sync_root,
                plain_root,
                identity_files=identity_files,
                age_bin=resolved_age,
            )
        except EncryptedSyncError as exc:
            return failed_result(sync_root, exc.code, exc.message)
        if not materialized["ok"]:
            return {
                "ok": False,
                "encrypted": True,
                "sync_dir": str(sync_root),
                "inner_manifest": materialized.get("inner_manifest"),
                "checked": materialized.get("checked", 0),
                "issues": materialized["issues"],
            }
        plain_repair = sync_bundle.repair_sync_bundle(plain_root)
        return {
            "ok": bool(plain_repair.get("ok")),
            "encrypted": True,
            "sync_dir": str(sync_root),
            "manifest_exists": True,
            "schema_version": ENCRYPTED_SYNC_SCHEMA_VERSION,
            "recipient_match": "yes",
            "raw_rollout_included": bool(materialized["inner_manifest"].get("raw_rollout_included")),
            "manifest_hash": materialized["inner_manifest"].get("manifest_hash"),
            "manifest_revision": materialized["inner_manifest"].get("manifest_revision"),
            "inner_manifest": materialized["inner_manifest"],
            "checked": materialized.get("checked", 0),
            "issues": plain_repair.get("issues", []),
        }


def status_encrypted_sync_bundle(
    sync_dir: str | Path,
    *,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
    decrypt: bool = False,
) -> dict[str, Any]:
    sync_root = Path(sync_dir).resolve()
    if not decrypt and not identity_files:
        return repair_encrypted_sync_bundle(sync_root, no_decrypt=True)
    repair = repair_encrypted_sync_bundle(
        sync_root,
        identity_files=identity_files,
        age_bin=age_bin,
        no_decrypt=not decrypt and not identity_files,
    )
    return {
        "ok": bool(repair.get("ok")),
        "encrypted": True,
        "sync_dir": str(sync_root),
        "manifest_exists": repair.get("manifest_exists", bool(repair.get("inner_manifest"))),
        "schema_version": repair.get("schema_version"),
        "recipient_match": repair.get("recipient_match", "no" if repair.get("issues") else "unknown"),
        "raw_rollout_included": repair.get("raw_rollout_included", "unknown"),
        "manifest_hash": repair.get("manifest_hash"),
        "manifest_revision": repair.get("manifest_revision"),
        "issues": repair.get("issues", []),
    }


def replay_issue_for(target_registry: Path, inner_manifest: dict[str, Any]) -> dict[str, Any] | None:
    vault_id_hash = str(inner_manifest.get("vault_id_hash") or "")
    current = load_encrypted_state(target_registry, vault_id_hash)
    if not current:
        return None
    incoming_hash = inner_manifest.get("manifest_hash")
    current_hash = current.get("manifest_hash")
    if incoming_hash == current_hash:
        return None
    incoming_revision = int(inner_manifest.get("manifest_revision") or 0)
    current_revision = int(current.get("manifest_revision") or 0)
    if incoming_revision <= current_revision:
        return issue(
            "stale_manifest",
            "incoming encrypted sync manifest is older than the accepted local head",
            incoming_revision=incoming_revision,
            current_revision=current_revision,
        )
    if inner_manifest.get("parent_manifest_hash") != current_hash:
        return issue(
            "divergent_head",
            "incoming encrypted sync manifest does not descend from the accepted local head",
            incoming_revision=incoming_revision,
            current_revision=current_revision,
        )
    return None


def pull_encrypted_sync_bundle(
    sync_dir: str | Path,
    target_registry_dir: str | Path | None = None,
    *,
    identity_files: Iterable[str | Path] | None = None,
    age_bin: str | Path | None = None,
) -> dict[str, Any]:
    sync_root = Path(sync_dir).resolve()
    target_registry = (
        Path(target_registry_dir).resolve()
        if target_registry_dir
        else aippocampus_registry_dir().resolve()
    )
    resolved_age, age_issue = resolve_age_binary(age_bin)
    if age_issue or not resolved_age:
        return failed_result(sync_root, age_issue["code"], age_issue["message"])  # type: ignore[index]

    with tempfile.TemporaryDirectory(prefix="aippocampus-encrypted-sync-pull-") as tmp:
        plain_root = Path(tmp) / "plain"
        try:
            materialized = materialize_encrypted_sync_bundle(
                sync_root,
                plain_root,
                identity_files=identity_files,
                age_bin=resolved_age,
            )
        except EncryptedSyncError as exc:
            return failed_result(sync_root, exc.code, exc.message)
        if not materialized["ok"]:
            return {
                "ok": False,
                "encrypted": True,
                "sync_dir": str(sync_root),
                "target_registry_dir": str(target_registry),
                "issues": materialized["issues"],
            }
        replay_issue = replay_issue_for(target_registry, materialized["inner_manifest"])
        if replay_issue:
            return {
                "ok": False,
                "encrypted": True,
                "sync_dir": str(sync_root),
                "target_registry_dir": str(target_registry),
                "issues": [replay_issue],
            }
        pull = sync_bundle.pull_sync_bundle(plain_root, target_registry)
        if pull.get("ok"):
            save_encrypted_state(target_registry, materialized["inner_manifest"])
        return {
            "ok": bool(pull.get("ok")),
            "encrypted": True,
            "sync_dir": str(sync_root),
            "target_registry_dir": str(target_registry),
            "manifest_hash": materialized["inner_manifest"].get("manifest_hash"),
            "manifest_revision": materialized["inner_manifest"].get("manifest_revision"),
            "raw_rollout_included": bool(materialized["inner_manifest"].get("raw_rollout_included")),
            "pull": pull,
            "issues": pull.get("path_repair", {}).get("issues", []) if not pull.get("ok") else [],
        }
