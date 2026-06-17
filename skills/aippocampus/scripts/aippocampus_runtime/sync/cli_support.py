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


def sync_help_card(command: str | None = None) -> str:
    """Return a task-first local-folder sync card before path/crypto flags."""

    if not command:
        return (
            "Action card:\n"
            "  status        Check local-folder sync readiness; never writes.\n"
            "  push --plan   Preview local registry -> sync folder.\n"
            "  pull --plan   Preview sync folder -> local registry.\n"
            "  repair --plan Preview sync manifest repair.\n"
            "  push/pull/repair without --plan can write; choose the side intentionally.\n\n"
            "Local-folder sync is for portable registry artifacts. Raw rollout audit files "
            "are explicit and should use encrypted sync; clean-source sync remains the ordinary path."
        )
    direction = sync_direction(command)
    source = direction["source_side"]
    destination = direction["destination_side"]
    mutates = ", ".join(direction["mutates"]) or "nothing"
    if command == "status":
        return (
            "Action card:\n"
            "  Read side: sync folder configuration.\n"
            "  Write side: none; status never mutates.\n"
            "  Use: aippocampus sync status --sync-dir <folder> --json\n\n"
            "Use --sync-dir to choose the folder; local paths stay local."
        )
    return (
        "Action card:\n"
        f"  Read side: {source}.\n"
        f"  Write side: {destination}.\n"
        f"  Plan boundary: aippocampus sync {command} --sync-dir <folder> --plan --json previews without writing.\n"
        f"  Apply boundary: aippocampus sync {command} --sync-dir <folder> --json may mutate {mutates}.\n\n"
        "Raw rollout sync is explicit and should be encrypted; clean-source sync remains the ordinary path."
    )


HUGE_PLAN_FILE_COUNT = 1000


def _included_count(file_count_breakdown: list[dict[str, Any]]) -> int:
    return sum(int(item.get("count") or 0) for item in file_count_breakdown if item.get("included"))


def _plan_count_interpretation(
    *, command: str, estimated_file_count: int | None, file_count_breakdown: list[dict[str, Any]]
) -> str:
    if estimated_file_count is None:
        return "not_available_without_manifest_or_registry_scan"
    if estimated_file_count >= HUGE_PLAN_FILE_COUNT:
        return "large_plan_review_categories_before_apply"
    if command == "push" and file_count_breakdown:
        return "category_breakdown_available"
    return "small_or_manifest_reported_plan"


def sync_direction_plan(
    args: Namespace,
    *,
    estimated_file_count: int | None,
    file_count_breakdown: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    command = str(args.command)
    command_preview = f"aippocampus sync {command} --sync-dir {{sync_dir}}"
    if command == "status":
        command_preview = "aippocampus sync status --sync-dir {sync_dir} --json"
    breakdown = file_count_breakdown or []
    next_safe_action = command_preview
    if estimated_file_count is not None and estimated_file_count >= HUGE_PLAN_FILE_COUNT:
        next_safe_action = (
            "Review estimated_file_breakdown first; if the count is surprising, choose an "
            "explicit sync dir or narrow what you sync before applying."
        )
    return {
        "ok": True,
        "kind": "aippocampus_sync_direction_plan",
        "command": command,
        "dry_run": True,
        **sync_direction(command),
        "sync_dir": "<local-path-redacted>" if args.sync_dir else None,
        "registry_dir": "<local-path-redacted>" if args.registry_dir else None,
        "estimated_file_count": estimated_file_count,
        "estimated_file_breakdown": breakdown,
        "estimated_included_file_count": _included_count(breakdown) if breakdown else estimated_file_count,
        "count_interpretation": _plan_count_interpretation(
            command=command,
            estimated_file_count=estimated_file_count,
            file_count_breakdown=breakdown,
        ),
        "raw_rollout_included": bool(args.include_raw),
        "raw_rollout_boundary": (
            "included_only_because_include_raw_was_requested"
            if args.include_raw
            else "excluded_unless_include_raw_and_encrypted_sync_are_explicitly_requested"
        ),
        "encryption_requested": bool(args.encrypt or args.require_encrypted),
        "conflict_boundary": (
            "plan mode performs no writes; apply-time safety checks prevent unmanaged overwrite "
            "of existing managed sync dirs"
        ),
        "next_command_template": command_preview,
        "requires": ["sync_dir"],
        "next_safe_action": next_safe_action,
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
        print(f"estimated files: {result.get('estimated_file_count')}")
        for item in result.get("estimated_file_breakdown") or []:
            included = "included" if item.get("included") else "excluded"
            print(f"- {item.get('category')}: {item.get('count')} ({included})")
        print(f"raw rollout: {result.get('raw_rollout_boundary')}")
        print(f"boundary: {result.get('conflict_boundary')}")
        if result.get("next_safe_action") != result.get("next_command_template"):
            print(f"next safe action: {result.get('next_safe_action')}")
        print(f"template: {result.get('next_command_template')}")
    elif result.get("status") == "available_requires_sync_dir":
        print("sync status: capability available; no sync folder selected")
        print(f"template: {result.get('next_command_template')}")
        print(f"boundary: {result.get('claim_boundary')}")
    else:
        print(f"sync {command}: {'ok' if result.get('ok') else 'needs attention'}")
    if result.get("manifest"):
        print(f"manifest: {result['manifest']}")
    if result.get("issues"):
        for issue in result["issues"]:
            print(f"- {issue.get('code')}: {issue.get('path')}")
