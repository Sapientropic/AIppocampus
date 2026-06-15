"""Small CLI projections for local-folder sync."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

SYNC_COMMANDS = {"status", "push", "pull", "repair"}


def parser_command(
    argv: list[str] | None, base_prog: str
) -> tuple[str, list[str] | None, str | None]:
    if argv and argv[0] in SYNC_COMMANDS and any(arg in {"-h", "--help"} for arg in argv[1:]):
        return f"{base_prog} {argv[0]}", list(argv[1:]), argv[0]
    return base_prog, argv, None


def sync_direction(command: str) -> dict[str, Any]:
    if command == "push":
        return {
            "source_side": "local_registry",
            "destination_side": "sync_dir",
            "mutates": ["sync_dir"],
            "description": "copy local AIppocampus registry artifacts into the sync folder",
        }
    if command == "pull":
        return {
            "source_side": "sync_dir",
            "destination_side": "local_registry",
            "mutates": ["local_registry"],
            "description": "copy sync folder artifacts into the local AIppocampus registry",
        }
    if command == "repair":
        return {
            "source_side": "sync_dir",
            "destination_side": "sync_dir_manifest",
            "mutates": ["sync_dir_manifest"],
            "description": "verify sync files and repair the sync manifest",
        }
    return {
        "source_side": "sync_dir",
        "destination_side": "none",
        "mutates": [],
        "description": "inspect sync readiness without writing",
    }


def sync_direction_plan(args: Namespace, *, estimated_file_count: int | None) -> dict[str, Any]:
    command = str(args.command)
    command_preview = f"aippocampus sync {command} --sync-dir <folder>"
    if command == "status":
        command_preview = "aippocampus sync status --sync-dir <folder> --json"
    return {
        "ok": True,
        "kind": "aippocampus_sync_direction_plan",
        "command": command,
        "dry_run": True,
        **sync_direction(command),
        "sync_dir": "<local-path-redacted>" if args.sync_dir else None,
        "registry_dir": "<local-path-redacted>" if args.registry_dir else None,
        "estimated_file_count": estimated_file_count,
        "raw_rollout_included": bool(args.include_raw),
        "encryption_requested": bool(args.encrypt or args.require_encrypted),
        "next_command": command_preview,
        "privacy_boundary": {
            "local_paths_included": False,
            "raw_rollout_included_only_if_requested": True,
            "writes_performed": False,
        },
    }


def print_sync_human_result(command: str, result: dict[str, Any]) -> None:
    if result.get("kind") == "aippocampus_sync_direction_plan":
        print(f"sync {command}: plan only")
        print(f"read: {result.get('source_side')}")
        print(f"write: {', '.join(result.get('mutates') or []) or 'none'}")
        print(f"next: {result.get('next_command')}")
    elif result.get("status") == "available_requires_sync_dir":
        print("sync status: capability available; no sync folder selected")
        print(f"next: {result.get('next_command')}")
        print(f"boundary: {result.get('claim_boundary')}")
    else:
        print(f"sync {command}: {'ok' if result.get('ok') else 'needs attention'}")
    if result.get("manifest"):
        print(f"manifest: {result['manifest']}")
    if result.get("issues"):
        for issue in result["issues"]:
            print(f"- {issue.get('code')}: {issue.get('path')}")
