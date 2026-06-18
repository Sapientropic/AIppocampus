"""Small CLI projections for object-storage sync."""

from __future__ import annotations

import os
import sys
from argparse import Namespace
from collections.abc import Callable
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.sync.object_storage.client import OBJECT_BACKEND, safe_endpoint_label

OBJECT_SYNC_COMMANDS = {"status", "push", "pull", "repair"}


def parser_command(
    argv: list[str] | None, base_prog: str
) -> tuple[str, list[str] | None, str | None]:
    if argv and argv[0] in OBJECT_SYNC_COMMANDS and any(
        arg in {"-h", "--help"} for arg in argv[1:]
    ):
        return f"{base_prog} {argv[0]}", list(argv[1:]), argv[0]
    return base_prog, argv, None


def explicit_object_store_url_arg(parse_argv: list[str] | None) -> bool:
    effective_parse_argv = parse_argv if parse_argv is not None else sys.argv[1:]
    return any(
        arg == "--object-store-url" or arg.startswith("--object-store-url=")
        for arg in effective_parse_argv
    )


def explicit_object_prefix_arg(parse_argv: list[str] | None) -> bool:
    effective_parse_argv = parse_argv if parse_argv is not None else sys.argv[1:]
    return any(
        arg == "--object-prefix" or arg.startswith("--object-prefix=")
        for arg in effective_parse_argv
    )


def object_sync_direction(command: str) -> dict[str, Any]:
    if command == "push":
        return {
            "source_side": "local_registry",
            "destination_side": "object_store_prefix",
            "mutates": ["object_store_prefix"],
            "description": "upload a local AIppocampus sync bundle into object storage",
        }
    if command == "pull":
        return {
            "source_side": "object_store_prefix",
            "destination_side": "local_registry",
            "mutates": ["local_registry"],
            "description": "download an object-storage sync bundle into the local registry",
        }
    if command == "repair":
        return {
            "source_side": "object_store_prefix",
            "destination_side": "object_store_manifest",
            "mutates": ["object_store_manifest"],
            "description": "verify object-storage sync files and repair the manifest",
        }
    return {
        "source_side": "object_store_prefix",
        "destination_side": "none",
        "mutates": [],
        "description": "inspect object-storage sync readiness without writing",
    }


def object_sync_help_card(command: str | None = None) -> str:
    """Return a task-first help card without exposing object-store plumbing first."""

    if not command:
        return (
            "Action card:\n"
            "  status        Check configured object sync readiness; never writes.\n"
            "  push --plan   Preview local registry -> object prefix.\n"
            "  pull --plan   Preview object prefix -> local registry.\n"
            "  repair --plan Preview object manifest repair.\n"
            "  push/pull/repair without --plan can write; choose the side intentionally.\n\n"
            "Operator configuration lives in flags/env below. Raw rollout sync is explicit "
            "and should be encrypted; clean-source sync remains the ordinary path."
        )
    direction = object_sync_direction(command)
    source = direction["source_side"]
    destination = direction["destination_side"]
    mutates = ", ".join(direction["mutates"]) or "nothing"
    if command == "status":
        return (
            "Action card:\n"
            "  Read side: object-store configuration.\n"
            "  Write side: none; status never mutates.\n"
            "  Use: aippocampus object-sync status --json\n\n"
            "Operator configuration lives in flags/env below."
        )
    return (
        "Action card:\n"
        f"  Read side: {source}.\n"
        f"  Write side: {destination}.\n"
        f"  Plan boundary: aippocampus object-sync {command} --plan --json previews without writing.\n"
        f"  Apply boundary: aippocampus object-sync {command} --json may mutate {mutates}.\n\n"
        "Operator configuration lives in flags/env below. Raw rollout sync is explicit "
        "and should be encrypted; clean-source sync remains the ordinary path."
    )


def object_sync_direction_plan(args: Namespace) -> dict[str, Any]:
    command = str(args.command)
    command_preview = f"aippocampus object-sync {command} --object-store-url {{object_store_url}} --json"
    if command == "status":
        command_preview = "aippocampus object-sync status --object-store-url {object_store_url} --json"
    safe_store = (
        safe_endpoint_label(args.object_store_url)
        if args.object_store_url
        else "<provider-object-store>"
    )
    return {
        "ok": True,
        "kind": "aippocampus_object_sync_direction_plan",
        "command": command,
        "dry_run": True,
        **object_sync_direction(command),
        "object_store": safe_store,
        "object_prefix": "<object-prefix-redacted>",
        "registry_dir": "<local-path-redacted>" if args.registry_dir else None,
        "raw_rollout_included": bool(args.include_raw),
        "encryption_requested": bool(args.encrypt or args.require_encrypted),
        "next_command_template": command_preview,
        "requires": ["object_store_url"],
        "privacy_boundary": {
            "local_paths_included": False,
            "endpoint_included": False,
            "object_prefix_included": False,
            "writes_performed": False,
        },
    }


def object_sync_backend_chooser(*, requested_command: str) -> dict[str, Any]:
    actions = [
        {
            "id": "check_object_sync_status",
            "label": "Check object-sync status after choosing backend",
            "command_template": "aippocampus object-sync status --object-store-url {object_store_url} --json",
            "requires": ["object_store_url"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_status_not_source_evidence",
            "why": "Choose an object backend before status or plan touches any object-store route.",
        },
        {
            "id": "check_object_sync_provider_status",
            "label": "Check provider-backed object-sync status",
            "command_template": (
                "aippocampus object-sync status --object-provider {object_provider} "
                "--object-bucket {object_bucket} --json"
            ),
            "requires": ["object_provider", "object_bucket"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_status_not_source_evidence",
            "why": "Use provider fields when no direct object-store URL is available.",
        },
        {
            "id": "preview_object_sync_after_backend",
            "label": "Preview object sync after backend selection",
            "command_template": (
                "aippocampus object-sync {requested_command} --plan "
                "--object-store-url {object_store_url} --json"
            ),
            "requires": ["requested_command", "object_store_url"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_plan_not_source_evidence",
            "why": "Preview remains read-only after a backend has been selected.",
        },
    ]
    primary = actions[0]
    return {
        "kind": "aippocampus_object_sync_backend_chooser",
        "ok": True,
        "status": "needs_object_backend_before_plan",
        "requested_command": requested_command,
        "route_value": "object_sync_backend_must_be_selected_before_planning",
        "current_uncertainty": "no_object_store_url_or_provider_selected",
        **canonical_foreground_action_fields(primary, safe_next_actions=actions),
        "privacy_boundary": {
            "endpoint_included": False,
            "object_prefix_included": False,
            "bucket_or_account_included": False,
            "writes_performed": False,
        },
    }


def _object_sync_status_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "preview_object_sync_push",
            "label": "Preview object sync push",
            "command": "aippocampus object-sync push --plan --json",
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_plan_not_source_evidence",
            "why": "Use when the object-store manifest is missing and local registry upload may be intended.",
        },
        {
            "id": "preview_object_sync_pull",
            "label": "Preview object sync pull",
            "command": "aippocampus object-sync pull --plan --json",
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_plan_not_source_evidence",
            "why": "Use when an object-store bundle may already exist but needs explicit selection.",
        },
        {
            "id": "preview_object_sync_repair",
            "label": "Preview object sync repair",
            "command": "aippocampus object-sync repair --plan --json",
            "mutation_risk": "read_only",
            "claim_boundary": "object_sync_plan_not_source_evidence",
            "why": "Use only after status indicates manifest or object-store metadata needs repair.",
        },
        {
            "id": "inspect_object_sync_operator_detail",
            "label": "Inspect object-sync operator detail",
            "command": "aippocampus object-sync status --operator-json",
            "mutation_risk": "read_only_operator_diagnostic",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
            "why": "Use locally when endpoint/prefix diagnostics are needed; default JSON keeps them redacted.",
        },
    ]


def object_provider_kwargs(
    args: Namespace,
    *,
    explicit_object_store_url: bool,
    read_env: Callable[[str | None], str | None],
) -> dict[str, str | None]:
    use_provider_env = not explicit_object_store_url
    return {
        "provider": args.object_provider
        or (os.environ.get("AIPPOCAMPUS_OBJECT_PROVIDER") if use_provider_env else None),
        "bucket": args.object_bucket
        or (os.environ.get("AIPPOCAMPUS_OBJECT_BUCKET") if use_provider_env else None),
        "region": args.object_region
        or (os.environ.get("AIPPOCAMPUS_OBJECT_REGION") if use_provider_env else None),
        "account_id": args.object_account_id
        or (os.environ.get("AIPPOCAMPUS_OBJECT_ACCOUNT_ID") if use_provider_env else None),
        "access_key_id": read_env(args.access_key_env),
        "secret_access_key": read_env(args.secret_key_env),
        "session_token": read_env(args.session_token_env),
    }


def _public_object_sync_issue(issue: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {"code": issue.get("code")}
    if issue.get("message"):
        public["message"] = issue.get("message")
    if issue.get("path"):
        public["path"] = "<object-path-redacted>"
    return public


def public_object_sync_status(result: dict[str, Any]) -> dict[str, Any]:
    actions = _object_sync_status_actions()
    return {
        "kind": "aippocampus_object_sync_status",
        "ok": bool(result.get("ok")),
        "backend": result.get("backend", OBJECT_BACKEND),
        "status": "ready" if result.get("ok") else "needs_attention",
        "surface_class": "foreground_status_card",
        "foreground_action_contract": "foreground-action-v1",
        "object_store": "<object-store-redacted>" if result.get("object_store") else None,
        "object_prefix": "<object-prefix-redacted>" if result.get("object_prefix") else None,
        "object_config_source": result.get("object_config_source"),
        "object_prefix_source": result.get("object_prefix_source"),
        "manifest_exists": result.get("manifest_exists"),
        "schema_version": result.get("schema_version"),
        "file_count": result.get("file_count", 0),
        "raw_rollout_included": result.get("raw_rollout_included", False),
        "issues": [
            _public_object_sync_issue(issue)
            for issue in result.get("issues", [])
            if isinstance(issue, dict)
        ],
        "operator_json_flag": "--operator-json",
        "privacy_boundary": {
            "endpoint_included": False,
            "object_prefix_included": False,
            "bucket_or_account_included": False,
            "writes_performed": False,
        },
        "agent_next_action": actions[0],
        "foreground_action": actions[0],
        "safe_next_actions": actions,
    }


def print_object_sync_human_result(command: str, result: dict[str, Any]) -> None:
    if result.get("kind") == "aippocampus_object_sync_direction_plan":
        print(f"object sync {command}: plan only")
        print(f"read: {result.get('source_side')}")
        print(f"write: {', '.join(result.get('mutates') or []) or 'none'}")
        print(f"next: {result.get('next_command') or result.get('next_command_template')}")
    elif command == "status":
        public = public_object_sync_status(result)
        print(f"object sync status: {public.get('status')}")
        print("object store: <object-store-redacted>")
        print("object prefix: <object-prefix-redacted>")
        if public.get("object_config_source"):
            print(f"config source: {public.get('object_config_source')}")
        if public.get("object_prefix_source"):
            print(f"prefix source: {public.get('object_prefix_source')}")
        print(f"manifest: {'present' if public.get('manifest_exists') else 'missing'}")
        print(f"raw rollout: {str(public.get('raw_rollout_included')).lower()}")
        for issue in public.get("issues") or []:
            print(f"- {issue.get('code')}: {issue.get('path') or issue.get('message')}")
        action_raw = public.get("agent_next_action")
        action = action_raw if isinstance(action_raw, dict) else {}
        print(f"next: {action.get('command') or action.get('label') or 'aippocampus object-sync push --plan --json'}")
        print(
            "boundary: endpoint/prefix/path hidden by default; preview push/pull/repair with --plan first; "
            "rerun status with --operator-json only for local endpoint diagnostics."
        )
    else:
        print(f"object sync {command}: {'ok' if result.get('ok') else 'needs attention'}")
    if command != "status" and result.get("manifest_key"):
        print(f"manifest object: {result['manifest_key']}")
    if command != "status":
        for issue in result.get("issues") or []:
            print(f"- {issue.get('code')}: {issue.get('path') or issue.get('message')}")
