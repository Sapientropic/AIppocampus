#!/usr/bin/env python3
"""HTTP object-storage adapter for AIppocampus sync bundles.

The adapter intentionally reuses the local bundle manifest contract instead of
inventing a second sync format. The object store is only the transport/storage
boundary: generated clean-source artifacts stay hash-addressed by manifest,
source-device locators stay portable, and raw rollouts remain opt-in.
"""

from __future__ import annotations

import argparse
import json
import os

from aippocampus_runtime.sync.object_storage.cli_support import (
    explicit_object_prefix_arg,
    explicit_object_store_url_arg,
    object_provider_kwargs,
    object_sync_backend_chooser,
    object_sync_direction,
    object_sync_direction_plan,
    object_sync_help_card,
    parser_command,
    print_object_sync_human_result,
    public_object_sync_status,
)
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
from aippocampus_runtime.sync.object_storage.operations import (
    download_object_bundle,
    iter_manifest_paths,
    load_object_manifest,
    local_manifest_for_object_storage,
    pull_encrypted_object_storage_bundle,
    pull_object_storage_bundle,
    push_encrypted_object_storage_bundle,
    push_object_storage_bundle,
    repair_encrypted_object_storage_bundle,
    repair_object_storage_bundle,
    status_encrypted_object_storage_bundle,
    status_object_storage_bundle,
    verify_manifest_objects,
)

__all__ = [
    "client_for",
    "client_for_provider",
    "DEFAULT_PREFIX",
    "DEFAULT_TIMEOUT_SECONDS",
    "download_object_bundle",
    "hash_bytes",
    "HttpObjectStoreClient",
    "iter_manifest_paths",
    "load_object_manifest",
    "local_manifest_for_object_storage",
    "normalize_object_prefix",
    "OBJECT_BACKEND",
    "object_key",
    "object_storage_client_for",
    "pull_encrypted_object_storage_bundle",
    "pull_object_storage_bundle",
    "push_encrypted_object_storage_bundle",
    "push_object_storage_bundle",
    "repair_encrypted_object_storage_bundle",
    "repair_object_storage_bundle",
    "status_encrypted_object_storage_bundle",
    "status_object_storage_bundle",
    "safe_endpoint_label",
    "verify_manifest_objects",
]


def token_from_env(env_name: str | None) -> str | None:
    if not env_name:
        return None
    return os.environ.get(env_name)


def main(argv: list[str] | None = None) -> int:
    prog, parse_argv, command_override = parser_command(argv, "aippocampus object-sync")
    command_label = command_override or "COMMAND"
    description = (
        object_sync_direction(command_label)["description"]
        if command_override
        else "Object-storage sync status/push/pull/repair for AIppocampus."
    )
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=f"{prog} [options]"
        if command_override
        else "aippocampus object-sync {status,push,pull,repair} [options]",
        description=f"{description}\n\n{object_sync_help_card(command_override)}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    if command_override is None:
        parser.add_argument("command", choices=["status", "push", "pull", "repair"])
    explicit_object_store_url = explicit_object_store_url_arg(parse_argv)
    explicit_object_prefix = explicit_object_prefix_arg(parse_argv)
    action_group = parser.add_argument_group("action options")
    raw_group = parser.add_argument_group("raw and encryption options")
    operator_group = parser.add_argument_group("operator object-store configuration")
    output_group = parser.add_argument_group("output and diagnostics")
    operator_group.add_argument(
        "--object-store-url", default=os.environ.get("AIPPOCAMPUS_OBJECT_STORE_URL")
    )
    operator_group.add_argument(
        "--object-prefix", default=os.environ.get("AIPPOCAMPUS_OBJECT_PREFIX", DEFAULT_PREFIX)
    )
    for flag, default in (
        ("--object-provider", None),
        ("--object-bucket", None),
        ("--object-region", None),
        ("--object-account-id", None),
        ("--token-env", "AIPPOCAMPUS_OBJECT_STORE_TOKEN"),
        ("--access-key-env", "AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID"),
        ("--secret-key-env", "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY"),
        ("--session-token-env", "AIPPOCAMPUS_OBJECT_SESSION_TOKEN"),
    ):
        operator_group.add_argument(flag, default=default)
    action_group.add_argument("--registry-dir", default=None)
    raw_group.add_argument(
        "--include-raw",
        action="store_true",
        help=(
            "explicitly include raw rollout audit files; this requires an encrypted sync "
            "decision and is not ordinary clean-source sync"
        ),
    )
    raw_group.add_argument(
        "--encrypt",
        action="store_true",
        help="encrypt a push using the encrypted object-sync adapter before writing object storage",
    )
    raw_group.add_argument(
        "--require-encrypted",
        action="store_true",
        help="refuse plaintext pull/status/repair and read only the encrypted object-sync adapter",
    )
    for flag in ("--recipient", "--recipient-file", "--identity-file"):
        raw_group.add_argument(flag, action="append", default=[])
    raw_group.add_argument("--age-bin", default=None)
    raw_group.add_argument("--no-decrypt", action="store_true")
    operator_group.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    action_group.add_argument("--plan", "--dry-run", action="store_true", dest="plan")
    output_group.add_argument("--json", action="store_true", dest="json_output")
    output_group.add_argument(
        "--operator-json",
        action="store_true",
        help="With status, emit full local endpoint/prefix diagnostics.",
    )
    args = parser.parse_args(parse_argv)
    if command_override is not None:
        args.command = command_override

    provider_kwargs = object_provider_kwargs(
        args,
        explicit_object_store_url=explicit_object_store_url,
        read_env=token_from_env,
    )

    if not args.object_store_url and not provider_kwargs["provider"]:
        message = (
            "--object-store-url/AIPPOCAMPUS_OBJECT_STORE_URL or "
            "--object-provider/AIPPOCAMPUS_OBJECT_PROVIDER is required"
        )
        if args.json_output:
            print(
                json.dumps(
                    object_sync_backend_chooser(requested_command=str(args.command)),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        parser.error(message)

    token = token_from_env(args.token_env)
    if args.plan:
        result = object_sync_direction_plan(args)
    elif args.command == "status":
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

    if args.command == "status":
        result = {
            **result,
            "object_config_source": (
                "explicit_object_store_url"
                if explicit_object_store_url
                else "provider_or_environment_configuration"
            ),
            "object_prefix_source": (
                "explicit_object_prefix"
                if explicit_object_prefix
                else "environment_or_default_prefix"
            ),
        }

    if args.json_output or args.operator_json:
        output = (
            public_object_sync_status(result)
            if args.command == "status" and not args.operator_json
            else result
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_object_sync_human_result(str(args.command), result)
    if args.command == "status" and args.json_output and not args.operator_json and not result.get("error"):
        return 0
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
