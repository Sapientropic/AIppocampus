#!/usr/bin/env python3
"""Device-key UX helpers for AIppocampus encrypted sync."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import sync_bundle
from aippocampuslib import now_utc, safe_path_name
from encrypted_sync_crypto import issue, validate_recipients

DEVICE_KEYS_NAME = "device-keys.json"
DEVICE_ID_PREFIX = "device"
ENCRYPTED_STATE_DIR = Path(".sync-state") / "encrypted"
LOCAL_IDENTITY_NAME = "device-identity.txt"
RECIPIENT_ROLE_DEVICE = "device"
RECIPIENT_ROLE_RECOVERY = "recovery"
RECIPIENT_ROLES = {RECIPIENT_ROLE_DEVICE, RECIPIENT_ROLE_RECOVERY}


def encrypted_state_dir(registry_dir: str | Path) -> Path:
    return Path(registry_dir).resolve() / ENCRYPTED_STATE_DIR


def device_keys_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / DEVICE_KEYS_NAME


def local_identity_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / LOCAL_IDENTITY_NAME


def recipient_hash(recipient: str) -> str:
    return hashlib.sha256(recipient.encode("utf-8")).hexdigest()


def device_id_for_recipient(recipient: str) -> str:
    return f"{DEVICE_ID_PREFIX}-{recipient_hash(recipient)[:16]}"


def default_device_keys() -> dict[str, Any]:
    return {
        "kind": "aippocampus_encrypted_sync_device_keys",
        "schema_version": 1,
        "key_epoch": 1,
        "local_device": None,
        "trusted_recipients": [],
        "revoked_recipients": [],
        "reencryption_required": None,
    }


def load_device_keys(registry_dir: str | Path) -> dict[str, Any]:
    path = device_keys_path(registry_dir)
    data = sync_bundle.load_json(path)
    if not data:
        return default_device_keys()
    merged = default_device_keys()
    merged.update(data)
    merged["trusted_recipients"] = [
        item for item in merged.get("trusted_recipients") or [] if isinstance(item, dict)
    ]
    merged["revoked_recipients"] = [
        item for item in merged.get("revoked_recipients") or [] if isinstance(item, dict)
    ]
    return merged


def save_device_keys(registry_dir: str | Path, data: dict[str, Any]) -> None:
    path = device_keys_path(registry_dir)
    sync_bundle.save_json(path, data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def public_identity_storage() -> dict[str, Any]:
    return {
        "mode": "local_registry_file",
        "identity_location": "local_registry_state",
        "os_credential_store": "not_configured",
        "secret_material": "local_only_never_synced",
        "permission_model": "owner_only_best_effort",
    }


def normalize_recipient_role(role: str | None) -> tuple[str, dict[str, Any] | None]:
    value = str(role or RECIPIENT_ROLE_DEVICE).strip().casefold()
    if value not in RECIPIENT_ROLES:
        return "", issue(
            "invalid_recipient_role",
            "recipient role must be device or recovery",
            role=role,
        )
    return value, None


def resolve_age_keygen_binary(age_keygen_bin: str | Path | None = None) -> tuple[str | None, dict[str, Any] | None]:
    candidate = str(age_keygen_bin or os.environ.get("AIPPOCAMPUS_AGE_KEYGEN_BIN") or "")
    if candidate:
        resolved = shutil.which(candidate) if not Path(candidate).exists() else candidate
    else:
        resolved = shutil.which("age-keygen")
    if not resolved:
        return None, issue(
            "age_keygen_missing",
            "age-keygen binary was not found; install age or set AIPPOCAMPUS_AGE_KEYGEN_BIN",
        )
    return str(resolved), None


def failed_key_result(registry_dir: str | Path, code: str, message: str, **extra: Any) -> dict[str, Any]:
    result = {
        "ok": False,
        "encrypted": True,
        "registry_dir": str(Path(registry_dir).resolve()),
        "issues": [issue(code, message, **extra)],
    }
    return result


def run_keygen(args: list[str]) -> tuple[str, dict[str, Any] | None]:
    try:
        proc = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return "", issue("age_keygen_failed", f"failed to run age-keygen: {exc}")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "age-keygen failed").strip()
        return "", issue("age_keygen_failed", detail)
    return proc.stdout.strip(), None


def public_recipient_from_identity(
    identity_file: str | Path,
    *,
    age_keygen_bin: str | Path | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    identity = Path(identity_file).resolve()
    if not identity.is_file():
        return None, issue("identity_missing", f"identity file not found: {identity}")
    resolved_keygen, keygen_issue = resolve_age_keygen_binary(age_keygen_bin)
    if keygen_issue or not resolved_keygen:
        return None, keygen_issue
    output, run_issue = run_keygen([resolved_keygen, "-y", str(identity)])
    if run_issue:
        return None, run_issue
    recipient = output.splitlines()[-1].strip() if output else ""
    recipients, recipient_issue = validate_recipients([recipient])
    if recipient_issue:
        return None, recipient_issue
    return recipients[0], None


def trusted_record(
    *,
    recipient: str,
    device_name: str,
    source: str,
    role: str = RECIPIENT_ROLE_DEVICE,
    trusted_at: str | None = None,
) -> dict[str, Any]:
    return {
        "recipient": recipient,
        "recipient_hash": recipient_hash(recipient),
        "device_id": device_id_for_recipient(recipient),
        "device_name": device_name,
        "role": role,
        "status": "trusted",
        "source": source,
        "trusted_at": trusted_at or now_utc(),
    }


def normalize_device_name(device_name: str | None, fallback: str) -> str:
    text = str(device_name or "").strip()
    return text or fallback


def revoked_record_for(data: dict[str, Any], recipient: str) -> dict[str, Any] | None:
    fingerprint = recipient_hash(recipient)
    for record in data.get("revoked_recipients") or []:
        if record.get("recipient_hash") == fingerprint or record.get("recipient") == recipient:
            return record
    return None


def trusted_record_for(data: dict[str, Any], recipient: str) -> dict[str, Any] | None:
    fingerprint = recipient_hash(recipient)
    for record in data.get("trusted_recipients") or []:
        if record.get("recipient_hash") == fingerprint or record.get("recipient") == recipient:
            return record
    return None


def upsert_trusted_recipient(data: dict[str, Any], record: dict[str, Any]) -> None:
    fingerprint = record["recipient_hash"]
    trusted = [
        item
        for item in data.get("trusted_recipients") or []
        if item.get("recipient_hash") != fingerprint
    ]
    trusted.append(record)
    trusted.sort(key=lambda item: (str(item.get("device_name") or ""), str(item.get("recipient") or "")))
    data["trusted_recipients"] = trusted


def public_local_device(local_device: dict[str, Any] | None) -> dict[str, Any] | None:
    if not local_device:
        return None
    return {
        "device_id": local_device.get("device_id"),
        "device_name": local_device.get("device_name"),
        "recipient": local_device.get("recipient"),
        "identity_available": bool(local_device.get("identity_available")),
        "identity_location": "local_registry_state",
        "identity_storage": public_identity_storage(),
        "updated_at": local_device.get("updated_at"),
    }


def recovery_state_for(trusted: list[dict[str, Any]]) -> dict[str, Any]:
    recovery_count = sum(1 for item in trusted if item.get("role") == RECIPIENT_ROLE_RECOVERY)
    return {
        "mode": "offline_recovery_recipient" if recovery_count else "none",
        "configured": recovery_count > 0,
        "recovery_recipient_count": recovery_count,
        "warning": None
        if recovery_count
        else "losing all trusted device identities means encrypted sync data is unrecoverable",
    }


def re_encryption_plan_for(record: dict[str, Any], remaining: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "required_after_revoke",
        "reason": "recipient_revoked",
        "revoked_recipient_hash": record.get("recipient_hash"),
        "revoked_device_id": record.get("device_id"),
        "revoked_device_name": record.get("device_name"),
        "revoked_role": record.get("role") or RECIPIENT_ROLE_DEVICE,
        "old_ciphertexts_remain_decryptable": True,
        "remaining_trusted_recipient_count": len(remaining),
        "remaining_recovery_recipient_count": sum(
            1 for item in remaining if item.get("role") == RECIPIENT_ROLE_RECOVERY
        ),
        "required_steps": [
            "push a fresh encrypted bundle for the remaining trusted recipients",
            "repair or pull the fresh encrypted bundle with a remaining identity",
            "treat older encrypted bundles as still decryptable by the revoked identity",
        ],
    }


def init_device_key(
    registry_dir: str | Path,
    *,
    device_name: str | None = None,
    identity_file: str | Path | None = None,
    age_keygen_bin: str | Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve()
    state_dir = encrypted_state_dir(registry_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        pass

    local_identity = local_identity_path(registry_root)
    generated = identity_file is None
    imported = identity_file is not None
    if generated and (overwrite or not local_identity.exists()):
        resolved_keygen, keygen_issue = resolve_age_keygen_binary(age_keygen_bin)
        if keygen_issue or not resolved_keygen:
            return failed_key_result(registry_root, keygen_issue["code"], keygen_issue["message"])  # type: ignore[index]
        _, run_issue = run_keygen([resolved_keygen, "-o", str(local_identity)])
        if run_issue:
            return failed_key_result(registry_root, run_issue["code"], run_issue["message"])
        try:
            os.chmod(local_identity, 0o600)
        except OSError:
            pass
    elif imported:
        source_identity = Path(str(identity_file)).resolve()
        if not source_identity.is_file():
            return failed_key_result(
                registry_root,
                "identity_missing",
                f"identity file not found: {source_identity}",
            )
        if local_identity.exists() and not overwrite:
            return failed_key_result(
                registry_root,
                "identity_exists",
                "local encrypted sync identity already exists; pass overwrite=True to replace it",
            )
        shutil.copy2(source_identity, local_identity)
        try:
            os.chmod(local_identity, 0o600)
        except OSError:
            pass
    elif not local_identity.is_file():
        return failed_key_result(registry_root, "identity_missing", f"identity file not found: {local_identity}")

    recipient, recipient_issue = public_recipient_from_identity(
        local_identity,
        age_keygen_bin=age_keygen_bin,
    )
    if recipient_issue or not recipient:
        return failed_key_result(registry_root, recipient_issue["code"], recipient_issue["message"])  # type: ignore[index]

    data = load_device_keys(registry_root)
    name = normalize_device_name(device_name, safe_path_name(os.environ.get("COMPUTERNAME") or "local-device", "device"))
    local_device = {
        "device_id": device_id_for_recipient(recipient),
        "device_name": name,
        "recipient": recipient,
        "identity_available": True,
        "identity_location": "local_registry_state",
        "updated_at": now_utc(),
    }
    data["local_device"] = local_device
    upsert_trusted_recipient(
        data,
        trusted_record(recipient=recipient, device_name=name, source="key_init"),
    )
    save_device_keys(registry_root, data)
    return {
        "ok": True,
        "encrypted": True,
        "registry_dir": str(registry_root),
        "device_id": local_device["device_id"],
        "device_name": name,
        "recipient": recipient,
        "identity_available": True,
        "identity_location": "local_registry_state",
        "identity_storage": public_identity_storage(),
        "trusted_recipient_count": len(data["trusted_recipients"]),
        "created": generated,
    }


def recipient_for_device_key(
    registry_dir: str | Path,
    *,
    age_keygen_bin: str | Path | None = None,
) -> dict[str, Any]:
    identity_file = str(local_identity_path(registry_dir))
    recipient, recipient_issue = public_recipient_from_identity(
        identity_file,
        age_keygen_bin=age_keygen_bin,
    )
    if recipient_issue or not recipient:
        return failed_key_result(registry_dir, recipient_issue["code"], recipient_issue["message"])  # type: ignore[index]
    return {
        "ok": True,
        "encrypted": True,
        "registry_dir": str(Path(registry_dir).resolve()),
        "device_id": device_id_for_recipient(recipient),
        "recipient": recipient,
    }


def list_device_keys(registry_dir: str | Path) -> dict[str, Any]:
    data = load_device_keys(registry_dir)
    local = data.get("local_device") or None
    trusted = list(data.get("trusted_recipients") or [])
    revoked = list(data.get("revoked_recipients") or [])
    identity_file = Path(str((local or {}).get("identity_file") or local_identity_path(registry_dir)))
    recovery_state = recovery_state_for(trusted)
    return {
        "ok": True,
        "encrypted": True,
        "registry_dir": str(Path(registry_dir).resolve()),
        "identity_available": identity_file.is_file(),
        "local_device": public_local_device(local),
        "trusted_recipients": trusted,
        "trusted_recipient_count": len(trusted),
        "revoked_recipients": revoked,
        "revoked_recipient_count": len(revoked),
        "recovery_state": recovery_state,
        "recovery_configured": recovery_state["configured"],
        "reencryption_required": data.get("reencryption_required") or None,
        "key_epoch": int(data.get("key_epoch") or 1),
    }


def trust_recipient(
    registry_dir: str | Path,
    *,
    recipient: str,
    device_name: str | None = None,
    role: str = RECIPIENT_ROLE_DEVICE,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve()
    recipients, recipient_issue = validate_recipients([recipient])
    if recipient_issue:
        return failed_key_result(registry_root, recipient_issue["code"], recipient_issue["message"])
    role_value, role_issue = normalize_recipient_role(role)
    if role_issue:
        return failed_key_result(registry_root, role_issue["code"], role_issue["message"], role=role)
    public_recipient = recipients[0]
    data = load_device_keys(registry_root)
    revoked = revoked_record_for(data, public_recipient)
    if revoked:
        return failed_key_result(
            registry_root,
            "revoked_recipient",
            "recipient was previously revoked; re-enroll with a new device identity",
            recipient_hash=recipient_hash(public_recipient),
            device_name=revoked.get("device_name"),
        )
    name = normalize_device_name(device_name, device_id_for_recipient(public_recipient))
    upsert_trusted_recipient(
        data,
        trusted_record(
            recipient=public_recipient,
            device_name=name,
            role=role_value,
            source="recovery_trust" if role_value == RECIPIENT_ROLE_RECOVERY else "key_trust",
        ),
    )
    save_device_keys(registry_root, data)
    return {
        "ok": True,
        "encrypted": True,
        "registry_dir": str(registry_root),
        "recipient": public_recipient,
        "device_id": device_id_for_recipient(public_recipient),
        "device_name": name,
        "role": role_value,
        "trusted_recipient_count": len(data["trusted_recipients"]),
        "recovery_state": recovery_state_for(data["trusted_recipients"]),
    }


def revoke_recipient(
    registry_dir: str | Path,
    recipient: str,
    *,
    dry_run: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve()
    recipients, recipient_issue = validate_recipients([recipient])
    if recipient_issue:
        return failed_key_result(registry_root, recipient_issue["code"], recipient_issue["message"])
    public_recipient = recipients[0]
    data = load_device_keys(registry_root)
    record = trusted_record_for(data, public_recipient)
    if not record:
        return failed_key_result(
            registry_root,
            "recipient_not_trusted",
            "recipient is not in the trusted device list",
            recipient_hash=recipient_hash(public_recipient),
        )
    remaining = [
        item
        for item in data.get("trusted_recipients") or []
        if item.get("recipient_hash") != record.get("recipient_hash")
    ]
    reencrypt_plan = re_encryption_plan_for(record, remaining)
    plan = {
        "ok": True,
        "encrypted": True,
        "registry_dir": str(registry_root),
        "dry_run": dry_run,
        "recipient_hash": record.get("recipient_hash"),
        "device_id": record.get("device_id"),
        "device_name": record.get("device_name"),
        "requires_reencrypt": True,
        "remaining_trusted_recipient_count": len(remaining),
        "re_encryption_plan": reencrypt_plan,
        "next_step": "push a fresh encrypted bundle for the remaining trusted recipients",
    }
    if dry_run:
        return plan
    if not confirm:
        return failed_key_result(
            registry_root,
            "revoke_confirmation_required",
            "recipient revoke requires confirm=True; run dry-run first to inspect the re-encryption plan",
            recipient_hash=record.get("recipient_hash"),
        )
    data["trusted_recipients"] = remaining
    revoked = list(data.get("revoked_recipients") or [])
    revoked = [
        item for item in revoked if item.get("recipient_hash") != record.get("recipient_hash")
    ]
    revoked.append(
        {
            "recipient": public_recipient,
            "recipient_hash": record.get("recipient_hash"),
            "device_id": record.get("device_id"),
            "device_name": record.get("device_name"),
            "revoked_at": now_utc(),
        }
    )
    data["revoked_recipients"] = revoked
    data["key_epoch"] = int(data.get("key_epoch") or 1) + 1
    pending_reencrypt = dict(reencrypt_plan)
    pending_reencrypt.update(
        {
            "status": "pending_after_revoke",
            "key_epoch": data["key_epoch"],
            "recorded_at": now_utc(),
        }
    )
    data["reencryption_required"] = pending_reencrypt
    save_device_keys(registry_root, data)
    plan.update(
        {
            "dry_run": False,
            "revoked": True,
            "key_epoch": data["key_epoch"],
            "reencryption_required": data["reencryption_required"],
        }
    )
    return plan


def revoked_recipient_issue_for_registry(
    registry_dir: str | Path, recipients: list[str]
) -> dict[str, Any] | None:
    data = load_device_keys(registry_dir)
    for recipient in recipients:
        revoked = revoked_record_for(data, recipient)
        if revoked:
            return issue(
                "revoked_recipient",
                "recipient was revoked; push a fresh bundle for the remaining trusted recipients",
                recipient_hash=recipient_hash(recipient),
                device_name=revoked.get("device_name"),
            )
    return None


def mark_reencrypted_after_push(
    registry_dir: str | Path,
    inner_manifest: dict[str, Any],
    *,
    recipients: list[str] | None = None,
) -> dict[str, Any]:
    data = load_device_keys(registry_dir)
    pending = data.get("reencryption_required") or None
    if not pending:
        return {"cleared": False, "reason": "no_pending_reencryption"}
    key_epoch = int(inner_manifest.get("key_epoch") or 0)
    pending_epoch = int(pending.get("key_epoch") or 0)
    if key_epoch < pending_epoch:
        return {"cleared": False, "reason": "manifest_epoch_before_pending_revoke"}
    trusted = trusted_recipients_for_registry(registry_dir)
    if recipients is not None and set(trusted) - set(recipients):
        return {"cleared": False, "reason": "remaining_trusted_recipients_missing"}
    data["reencryption_required"] = None
    save_device_keys(registry_dir, data)
    return {
        "cleared": True,
        "key_epoch": key_epoch,
        "manifest_hash": inner_manifest.get("manifest_hash"),
    }


def trusted_recipients_for_registry(registry_dir: str | Path) -> list[str]:
    data = load_device_keys(registry_dir)
    recipients = [
        str(record.get("recipient") or "").strip()
        for record in data.get("trusted_recipients") or []
        if record.get("status") == "trusted"
    ]
    recipients = [recipient for recipient in recipients if recipient]
    if not recipients:
        return []
    valid, validation_issue = validate_recipients(recipients)
    return [] if validation_issue else valid


def device_sync_metadata(registry_dir: str | Path, recipients: list[str]) -> dict[str, Any]:
    data = load_device_keys(registry_dir)
    local = data.get("local_device") or {}
    return {
        "source_device_id": local.get("device_id") or "local-device",
        "source_device_name": local.get("device_name"),
        "key_epoch": int(data.get("key_epoch") or 1),
        "recipient_count": len(recipients),
    }
