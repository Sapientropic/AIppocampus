#!/usr/bin/env python3
"""Key-provider contract and diagnostics for encrypted sync identities."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.source.io_kernel import load_json_dict
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.encrypted.crypto import issue

KEY_PROVIDER_CONFIG_NAME = "key-provider.json"
ENCRYPTED_STATE_DIR = Path(".sync-state") / "encrypted"
LOCAL_IDENTITY_NAME = "device-identity.txt"
KEY_PROVIDER_FILE = "file"
KEY_PROVIDER_MACOS_KEYCHAIN = "macos-keychain"
KEY_PROVIDER_WINDOWS_CREDENTIAL_MANAGER = "windows-credential-manager"
KEY_PROVIDER_LINUX_SECRET_SERVICE = "linux-secret-service"
SUPPORTED_KEY_PROVIDERS = (
    KEY_PROVIDER_FILE,
    KEY_PROVIDER_MACOS_KEYCHAIN,
    KEY_PROVIDER_WINDOWS_CREDENTIAL_MANAGER,
    KEY_PROVIDER_LINUX_SECRET_SERVICE,
)


def encrypted_state_dir(registry_dir: str | Path) -> Path:
    return Path(registry_dir).resolve() / ENCRYPTED_STATE_DIR


def key_provider_config_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / KEY_PROVIDER_CONFIG_NAME


def local_identity_path(registry_dir: str | Path) -> Path:
    return encrypted_state_dir(registry_dir) / LOCAL_IDENTITY_NAME


def failed_key_provider_result(
    registry_dir: str | Path,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "encrypted": True,
        "registry_dir": str(Path(registry_dir).resolve()),
        "issues": [issue(code, message, **extra)],
    }


def default_key_provider_config() -> dict[str, Any]:
    return {
        "kind": "aippocampus_encrypted_sync_key_provider",
        "schema_version": 1,
        "provider": KEY_PROVIDER_FILE,
        "fallback_to_file_identity": False,
        "configured_at": None,
    }


def normalize_key_provider(provider: str | None) -> tuple[str, dict[str, Any] | None]:
    value = str(provider or KEY_PROVIDER_FILE).strip().casefold()
    if value not in SUPPORTED_KEY_PROVIDERS:
        return "", issue(
            "unsupported_key_provider",
            "key provider must be file, macos-keychain, windows-credential-manager, or linux-secret-service",
            provider=provider,
            supported_key_providers=list(SUPPORTED_KEY_PROVIDERS),
        )
    return value, None


def load_key_provider_config(registry_dir: str | Path) -> dict[str, Any]:
    path = key_provider_config_path(registry_dir)
    data = load_json_dict(path).data
    if not data:
        return default_key_provider_config()
    merged = default_key_provider_config()
    merged.update(data)
    provider, provider_issue = normalize_key_provider(str(merged.get("provider") or ""))
    if provider_issue:
        merged["provider"] = ""
        merged["invalid_provider_issue"] = provider_issue
    else:
        merged["provider"] = provider
    merged["fallback_to_file_identity"] = False
    return merged


def save_key_provider_config(registry_dir: str | Path, data: dict[str, Any]) -> None:
    path = key_provider_config_path(registry_dir)
    sync_bundle.save_json(path, data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def key_provider_secret_boundary(provider: str) -> str:
    if provider == KEY_PROVIDER_FILE:
        return "local_file_never_synced"
    return "os_provider_secret_material_not_exported"


def configure_key_provider(
    registry_dir: str | Path,
    *,
    provider: str,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve()
    provider_value, provider_issue = normalize_key_provider(provider)
    if provider_issue:
        return failed_key_provider_result(
            registry_root,
            provider_issue["code"],
            provider_issue["message"],
            supported_key_providers=list(SUPPORTED_KEY_PROVIDERS),
        )
    config = default_key_provider_config()
    config.update(
        {
            "provider": provider_value,
            "configured_at": now_utc(),
        }
    )
    save_key_provider_config(registry_root, config)
    return {
        "ok": True,
        "encrypted": True,
        "active_key_provider": provider_value,
        "status": "configured",
        "supported_key_providers": list(SUPPORTED_KEY_PROVIDERS),
        "fallback_to_file_identity": False,
        "secret_material": key_provider_secret_boundary(provider_value),
    }


def key_provider_status(registry_dir: str | Path) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve()
    config = load_key_provider_config(registry_root)
    invalid_provider_issue = config.get("invalid_provider_issue")
    if invalid_provider_issue:
        return {
            "ok": False,
            "encrypted": True,
            "active_key_provider": "",
            "status": "invalid_config",
            "supported_key_providers": list(SUPPORTED_KEY_PROVIDERS),
            "identity_available": False,
            "fallback_to_file_identity": False,
            "fallback_attempted": False,
            "local_file_identity_present": local_identity_path(registry_root).is_file(),
            "issues": [invalid_provider_issue],
        }

    provider = str(config.get("provider") or KEY_PROVIDER_FILE)
    file_identity_present = local_identity_path(registry_root).is_file()
    base = {
        "encrypted": True,
        "active_key_provider": provider,
        "supported_key_providers": list(SUPPORTED_KEY_PROVIDERS),
        "fallback_to_file_identity": False,
        "fallback_attempted": False,
        "local_file_identity_present": file_identity_present,
        "secret_material": key_provider_secret_boundary(provider),
    }
    if provider == KEY_PROVIDER_FILE:
        if file_identity_present:
            return {
                **base,
                "ok": True,
                "status": "available",
                "identity_available": True,
                "identity_location": "local_registry_state",
                "os_credential_store": "not_configured",
            }
        return {
            **base,
            "ok": False,
            "status": "missing",
            "identity_available": False,
            "identity_location": "local_registry_state",
            "issues": [
                issue(
                    "identity_missing",
                    "file key provider requires a local encrypted sync identity",
                )
            ],
        }

    return {
        **base,
        "ok": False,
        "status": "unavailable",
        "identity_available": False,
        "identity_location": "os_credential_store",
        "os_credential_store": provider,
        "issues": [
            issue(
                "key_provider_unavailable",
                "configured key provider is unavailable; encrypted sync will not fall back to file identity",
                provider=provider,
                reason="provider_adapter_not_implemented",
            )
        ],
    }
