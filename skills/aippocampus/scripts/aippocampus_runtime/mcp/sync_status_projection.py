"""Public MCP projection for sync status when no backend is selected."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def backend_selection_payload(cwd: Path, *, diagnostic: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cwd": str(cwd),
        "status": "available_requires_sync_dir",
        "backend": "local_folder",
        "backends": ["local_folder", "http_object_store"],
        "commands": ["status", "push", "pull", "repair"],
        "command": "aippocampus sync status --sync-dir <folder> --json",
        "object_storage_command": "aippocampus sync status --object-store-url <url> --json",
        "diagnostic_commands": [],
        "agent_next_action": (
            "Pick a backend explicitly: pass sync_dir for local folder sync or "
            "object_store_url for HTTP object storage status."
        ),
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
