"""Registry-entry reachability helpers for registry-wide source search."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text

SEARCHABLE_SOURCE_PATH_KEYS = ("clean_source_messages_jsonl", "sqlite")
SOURCE_REPAIR_PATH_KEYS = (
    "rollout",
    "index",
    "index_dir",
    "clean_source_dir",
    "clean_source_manifest",
)


def registry_entry_ref(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "thread_key": entry.get("thread_key"),
            "title": compact_text(str(entry.get("title") or ""), 90),
            "workspace_name": compact_text(str(entry.get("workspace_name") or ""), 90),
            "source_provider": entry.get("source_provider"),
        }.items()
        if value not in (None, "", [])
    }


def _path_text(paths: Mapping[str, Any], key: str) -> str:
    return str(paths.get(key) or "").strip()


def _path_exists(path_text: str) -> bool:
    if not path_text:
        return False
    try:
        return Path(path_text).exists()
    except (OSError, ValueError):
        return False


def registry_entry_search_skip(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_paths = entry.get("paths")
    paths: Mapping[str, Any] = raw_paths if isinstance(raw_paths, Mapping) else {}
    searchable = {
        key: _path_text(paths, key)
        for key in SEARCHABLE_SOURCE_PATH_KEYS
        if _path_text(paths, key)
    }
    if any(_path_exists(path) for path in searchable.values()):
        return None
    repairable = {
        key: _path_text(paths, key)
        for key in SOURCE_REPAIR_PATH_KEYS
        if _path_text(paths, key)
    }
    if searchable:
        reason = "configured_search_sources_missing"
        message = (
            "This registry entry names searchable source paths, but none are reachable "
            "on this machine."
        )
    elif repairable:
        reason = "source_route_not_indexed_for_registry_search"
        message = (
            "This registry entry has a source route, but no reachable clean-source "
            "or SQLite search artifact for registry-wide search."
        )
    else:
        reason = "not_searchable_workspace_entry"
        message = (
            "This registry entry only has workspace metadata and is not a source-search target."
        )
    item = {
        "thread": registry_entry_ref(entry),
        "reason": reason,
        "message": message,
    }
    if reason != "not_searchable_workspace_entry":
        item["maintenance_action"] = {
            "label": "Audit registry source reachability",
            "command": "aippocampus registry audit --json",
            "why": (
                "Registry search can only search reachable clean-source or index artifacts; "
                "audit the registry before treating a miss as meaningful."
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "registry_reachability_audit_not_memory_evidence",
        }
    return item


def skipped_maintenance_actions(skipped_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions_by_key = {
        json.dumps(item.get("maintenance_action"), ensure_ascii=False, sort_keys=True): item.get(
            "maintenance_action"
        )
        for item in skipped_entries
        if isinstance(item.get("maintenance_action"), Mapping)
    }
    return [dict(action) for action in actions_by_key.values() if isinstance(action, Mapping)]
