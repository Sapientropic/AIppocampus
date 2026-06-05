#!/usr/bin/env python3
"""Operator CLI for encrypted sync device keys and plaintext migration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import aippocampus_registry_dir
from aippocampus_runtime.sync.encrypted import keys as encrypted_sync_keys
from aippocampus_runtime.sync.encrypted import migration as encrypted_sync_migration
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output")


def add_recipient_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--recipient", action="append", default=[])
    parser.add_argument("--recipient-file", action="append", default=[])
    parser.add_argument("--age-bin", default=None)


def add_object_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--object-store-url",
        default=os.environ.get("AIPPOCAMPUS_OBJECT_STORE_URL"),
    )
    parser.add_argument(
        "--object-prefix",
        default=os.environ.get("AIPPOCAMPUS_OBJECT_PREFIX", sync_object_storage.DEFAULT_PREFIX),
    )
    parser.add_argument(
        "--object-provider",
        default=os.environ.get("AIPPOCAMPUS_OBJECT_PROVIDER"),
    )
    parser.add_argument("--object-bucket", default=os.environ.get("AIPPOCAMPUS_OBJECT_BUCKET"))
    parser.add_argument("--object-region", default=os.environ.get("AIPPOCAMPUS_OBJECT_REGION"))
    parser.add_argument(
        "--object-account-id",
        default=os.environ.get("AIPPOCAMPUS_OBJECT_ACCOUNT_ID"),
    )
    parser.add_argument("--token-env", default="AIPPOCAMPUS_OBJECT_STORE_TOKEN")
    parser.add_argument("--access-key-env", default="AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID")
    parser.add_argument("--secret-key-env", default="AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY")
    parser.add_argument("--session-token-env", default="AIPPOCAMPUS_OBJECT_SESSION_TOKEN")
    parser.add_argument("--timeout", type=float, default=sync_object_storage.DEFAULT_TIMEOUT_SECONDS)


def token_from_env(env_name: str | None) -> str | None:
    if not env_name:
        return None
    return os.environ.get(env_name)


def provider_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "token": token_from_env(args.token_env),
        "timeout": args.timeout,
        "provider": args.object_provider,
        "bucket": args.object_bucket,
        "region": args.object_region,
        "account_id": args.object_account_id,
        "access_key_id": token_from_env(args.access_key_env),
        "secret_access_key": token_from_env(args.secret_key_env),
        "session_token": token_from_env(args.session_token_env),
    }


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_token(value: Any, *, fallback: str = "", max_length: int = 96) -> str:
    text = str(value or "").strip()
    safe = "".join(
        char for char in text[:max_length] if char.isalnum() or char in {"_", "-", ":", "."}
    )
    lowered = safe.casefold()
    if not safe or any(marker in lowered for marker in ("secret", "token", "private")):
        return fallback
    return safe


def public_recipient(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.casefold()
    if not lowered.startswith("age1") or "secret" in lowered:
        return ""
    return public_token(text, max_length=160)


def public_issue(issue: Any) -> dict[str, Any]:
    if not isinstance(issue, dict):
        return {"code": "unknown"}
    return {
        "code": public_token(issue.get("code"), fallback="unknown"),
        "has_message": bool(issue.get("message")),
        "has_path": bool(issue.get("path")),
    }


def public_admin_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return public CLI output for credential-adjacent encrypted sync admin.

    Admin helpers deal with identity files, local paths, object-store
    credentials, and public age recipients. Keep the command result useful while
    projecting it onto a small whitelist before any print sink.
    """

    public: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "encrypted": bool(result.get("encrypted")),
    }
    recipient = public_recipient(result.get("recipient"))
    if recipient:
        public["recipient"] = recipient
    for key in (
        "device_id",
        "device_name",
        "role",
        "recipient_hash",
        "recipient_match",
        "status",
        "reason",
        "active_key_provider",
        "identity_location",
        "os_credential_store",
        "secret_material",
    ):
        value = public_token(result.get(key), fallback="")
        if value:
            public[key] = value
    for key in (
        "trusted_recipient_count",
        "revoked_recipient_count",
        "remaining_trusted_recipient_count",
        "required_recipient_count",
        "key_epoch",
    ):
        if key in result:
            public[key] = public_count(result.get(key))
    for key in (
        "identity_available",
        "created",
        "dry_run",
        "requires_reencrypt",
        "recovery_configured",
        "identity_available",
        "fallback_to_file_identity",
        "fallback_attempted",
        "local_file_identity_present",
    ):
        if key in result:
            public[key] = bool(result.get(key))
    issues = [public_issue(item) for item in result.get("issues") or []]
    if issues:
        public["issues"] = issues
    recovery_state = result.get("recovery_state")
    if isinstance(recovery_state, dict):
        public["recovery_state"] = {
            "configured": bool(recovery_state.get("configured")),
            "recovery_recipient_count": public_count(
                recovery_state.get("recovery_recipient_count")
            ),
        }
    supported = result.get("supported_key_providers")
    if isinstance(supported, list):
        public["supported_key_providers"] = [
            public_token(item, fallback="") for item in supported if public_token(item, fallback="")
        ]
    public["output_boundary"] = "credential-adjacent details omitted from CLI output"
    return public


def write_stdout_line(text: str) -> None:
    os.write(1, f"{text}\n".encode("utf-8"))


def emit_result(result: dict[str, Any], *, json_output: bool, plain_field: str | None = None) -> int:
    public_result = public_admin_result(result)
    if json_output:
        json.dump(public_result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif plain_field == "recipient" and public_result.get("recipient"):
        write_stdout_line(str(public_result["recipient"]))
    else:
        write_stdout_line(
            "encrypted sync: ok"
            if public_result.get("ok")
            else "encrypted sync: needs attention"
        )
        for item in public_result.get("issues") or []:
            write_stdout_line(f"- {item.get('code')}")
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    key = subcommands.add_parser("key")
    key_subcommands = key.add_subparsers(dest="key_command", required=True)

    key_init = key_subcommands.add_parser("init")
    key_init.add_argument("--registry-dir", default=None)
    key_init.add_argument("--device-name", default=None)
    key_init.add_argument("--identity-file", default=None)
    key_init.add_argument("--age-keygen-bin", default=None)
    key_init.add_argument("--overwrite", action="store_true")
    add_json_flag(key_init)

    key_recipient = key_subcommands.add_parser("recipient")
    key_recipient.add_argument("--registry-dir", default=None)
    key_recipient.add_argument("--age-keygen-bin", default=None)
    add_json_flag(key_recipient)

    key_list = key_subcommands.add_parser("list")
    key_list.add_argument("--registry-dir", default=None)
    add_json_flag(key_list)

    key_trust = key_subcommands.add_parser("trust")
    key_trust.add_argument("--registry-dir", default=None)
    key_trust.add_argument("--recipient", required=True)
    key_trust.add_argument("--device-name", default=None)
    key_trust.add_argument(
        "--recovery",
        action="store_true",
        help="Trust this public recipient as an offline recovery identity.",
    )
    add_json_flag(key_trust)

    key_revoke = key_subcommands.add_parser("revoke")
    key_revoke.add_argument("--registry-dir", default=None)
    key_revoke.add_argument("--recipient", required=True)
    key_revoke.add_argument("--dry-run", action="store_true")
    key_revoke.add_argument("--confirm", action="store_true")
    add_json_flag(key_revoke)

    key_provider_configure = key_subcommands.add_parser("provider-configure")
    key_provider_configure.add_argument("--registry-dir", default=None)
    key_provider_configure.add_argument("--provider", required=True)
    add_json_flag(key_provider_configure)

    key_provider_status = key_subcommands.add_parser("provider-status")
    key_provider_status.add_argument("--registry-dir", default=None)
    add_json_flag(key_provider_status)

    migrate = subcommands.add_parser("migrate-to-encrypted")
    migrate.add_argument("--sync-dir", required=True)
    migrate.add_argument("--target-sync-dir", required=True)
    migrate.add_argument("--registry-dir", default=None)
    migrate.add_argument("--dry-run", action="store_true")
    add_recipient_flags(migrate)
    add_json_flag(migrate)

    cleanup = subcommands.add_parser("cleanup-plaintext")
    cleanup.add_argument("--sync-dir", required=True)
    cleanup.add_argument("--dry-run", action="store_true")
    cleanup.add_argument("--confirm", action="store_true")
    cleanup.add_argument("--verified-encrypted-target", action="store_true")
    add_json_flag(cleanup)

    object_migrate = subcommands.add_parser("migrate-object-to-encrypted")
    object_migrate.add_argument("--registry-dir", default=None)
    object_migrate.add_argument("--target-object-prefix", required=True)
    object_migrate.add_argument("--dry-run", action="store_true")
    add_object_flags(object_migrate)
    add_recipient_flags(object_migrate)
    add_json_flag(object_migrate)

    object_cleanup = subcommands.add_parser("cleanup-object-plaintext")
    object_cleanup.add_argument("--dry-run", action="store_true")
    object_cleanup.add_argument("--confirm", action="store_true")
    object_cleanup.add_argument("--verified-encrypted-target", action="store_true")
    add_object_flags(object_cleanup)
    add_json_flag(object_cleanup)

    return parser


def registry_arg(value: str | None) -> Path:
    return Path(value).resolve() if value else aippocampus_registry_dir().resolve()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "key":
            registry_dir = registry_arg(args.registry_dir)
            if args.key_command == "init":
                result = encrypted_sync_keys.init_device_key(
                    registry_dir,
                    device_name=args.device_name,
                    identity_file=args.identity_file,
                    age_keygen_bin=args.age_keygen_bin,
                    overwrite=args.overwrite,
                )
                return emit_result(result, json_output=args.json_output)
            if args.key_command == "recipient":
                result = encrypted_sync_keys.recipient_for_device_key(
                    registry_dir,
                    age_keygen_bin=args.age_keygen_bin,
                )
                return emit_result(
                    result,
                    json_output=args.json_output,
                    plain_field="recipient",
                )
            if args.key_command == "list":
                result = encrypted_sync_keys.list_device_keys(registry_dir)
                return emit_result(result, json_output=args.json_output)
            if args.key_command == "trust":
                result = encrypted_sync_keys.trust_recipient(
                    registry_dir,
                    recipient=args.recipient,
                    device_name=args.device_name,
                    role="recovery" if args.recovery else "device",
                )
                return emit_result(result, json_output=args.json_output)
            if args.key_command == "provider-configure":
                result = encrypted_sync_keys.configure_key_provider(
                    registry_dir,
                    provider=args.provider,
                )
                return emit_result(result, json_output=args.json_output)
            if args.key_command == "provider-status":
                result = encrypted_sync_keys.key_provider_status(registry_dir)
                return emit_result(result, json_output=args.json_output)
            result = encrypted_sync_keys.revoke_recipient(
                registry_dir,
                args.recipient,
                dry_run=args.dry_run,
                confirm=args.confirm,
            )
            return emit_result(result, json_output=args.json_output)

        if args.command == "migrate-to-encrypted":
            result = encrypted_sync_migration.migrate_plaintext_sync_dir_to_encrypted(
                args.sync_dir,
                args.target_sync_dir,
                registry_dir=args.registry_dir,
                recipients=args.recipient,
                recipient_files=args.recipient_file,
                age_bin=args.age_bin,
                dry_run=args.dry_run,
            )
            return emit_result(result, json_output=args.json_output)

        if args.command == "cleanup-plaintext":
            result = encrypted_sync_migration.cleanup_plaintext_sync_dir(
                args.sync_dir,
                dry_run=args.dry_run,
                confirm=args.confirm,
                verified_encrypted_target=args.verified_encrypted_target,
            )
            return emit_result(result, json_output=args.json_output)

        if args.command == "migrate-object-to-encrypted":
            result = encrypted_sync_migration.migrate_plaintext_object_storage_to_encrypted(
                registry_arg(args.registry_dir) if args.registry_dir else None,
                args.object_store_url,
                prefix=args.object_prefix,
                target_prefix=args.target_object_prefix,
                recipients=args.recipient,
                recipient_files=args.recipient_file,
                age_bin=args.age_bin,
                dry_run=args.dry_run,
                **provider_kwargs(args),
            )
            return emit_result(result, json_output=args.json_output)

        result = encrypted_sync_migration.cleanup_plaintext_object_storage_bundle(
            args.object_store_url,
            prefix=args.object_prefix,
            dry_run=args.dry_run,
            confirm=args.confirm,
            verified_encrypted_target=args.verified_encrypted_target,
            **provider_kwargs(args),
        )
        return emit_result(result, json_output=args.json_output)
    except ValueError as exc:
        result = {"ok": False, "issues": [{"code": str(exc).split(":", 1)[0], "message": str(exc)}]}
        return emit_result(result, json_output=getattr(args, "json_output", False))


if __name__ == "__main__":
    raise SystemExit(main())
