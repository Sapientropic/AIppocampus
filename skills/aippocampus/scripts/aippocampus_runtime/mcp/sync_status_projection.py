"""Public MCP projection for sync status when no backend is selected."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.sync.cli_support import sync_dir_required_actions


def backend_selection_payload(cwd: Path, *, diagnostic: bool = False) -> dict[str, Any]:
    local_sync_actions = sync_dir_required_actions()
    payload: dict[str, Any] = {
        "cwd": str(cwd),
        "status": "available_requires_sync_dir",
        "surface_class": "foreground_status_card",
        "foreground_action_contract": "foreground-action-v1",
        "backend": "local_folder",
        "backends": ["local_folder", "http_object_store"],
        "commands": ["status", "push", "pull", "repair"],
        "command_template": "aippocampus sync status --sync-dir {sync_dir} --json",
        "object_storage_command_template": (
            "aippocampus sync status --object-store-url {object_store_url} --json"
        ),
        "requires": ["sync_dir_or_object_store_url"],
        "diagnostic_commands": [],
        "agent_next_action": local_sync_actions[0],
        "foreground_action": local_sync_actions[0],
        "safe_next_actions": [
            *local_sync_actions,
            {
                "id": "check_object_sync_status",
                "label": "Check object sync status",
                "command_template": "aippocampus sync status --object-store-url {object_store_url} --json",
                "requires": ["object_store_url"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "sync_status_not_source_evidence",
                "why": "Choose an object-store URL only when using the HTTP object backend.",
            },
        ],
        "sync_flows": {
            "status": "implemented",
            "push": "implemented",
            "pull": "implemented",
            "repair": "implemented",
        },
        "object_storage": {
            "backend": "http_object_store",
            "status": "implemented_requires_object_store_url",
            "transport": "HTTP PUT/GET object keys",
        },
        "raw_rollout_sync": "explicit_only",
    }
    if diagnostic:
        payload["diagnostic_commands"] = [
            "python -m aippocampus_runtime.sync.bundle",
            "python -m aippocampus_runtime.sync.object_storage.cli",
        ]
    return payload
