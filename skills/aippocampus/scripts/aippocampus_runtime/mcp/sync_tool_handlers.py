"""MCP sync-status handler.

Keep sync-specific backend selection out of the main tool handler facade so the
hot MCP dispatch file stays small enough to review before adding another route.
"""

from __future__ import annotations

import os
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp.result_profile import render_profiled_result
from aippocampus_runtime.mcp.sync_status_projection import backend_selection_payload
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage


def _cwd_arg(arguments: dict[str, Any]):
    return core.canonical_path(str(arguments.get("cwd") or os.getcwd()))


def call_sync_status(arguments: dict[str, Any]) -> dict[str, Any]:
    cwd = _cwd_arg(arguments)
    if arguments.get("object_store_url"):
        token_env = str(arguments.get("token_env") or "AIPPOCAMPUS_OBJECT_STORE_TOKEN")
        return render_profiled_result(
            arguments,
            sync_object_storage.status_object_storage_bundle(
                str(arguments["object_store_url"]),
                prefix=str(arguments.get("object_prefix") or sync_object_storage.DEFAULT_PREFIX),
                token=os.environ.get(token_env),
            ),
        )
    if arguments.get("sync_dir"):
        return render_profiled_result(
            arguments,
            sync_bundle.status_sync_bundle(str(arguments["sync_dir"])),
        )

    return render_profiled_result(
        arguments,
        backend_selection_payload(cwd, diagnostic=bool(arguments.get("diagnostic"))),
    )
