"""Opt-in provider-key bridge support for live MCP semantic diagnostics."""

from __future__ import annotations

import os
from typing import Any


def maybe_apply_provider_key_bridge_for_semantic_diagnostic(
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    """Expose provider-key bridge env to a live semantic diagnostic call.

    The bridge manifest is an explicit user/operator install artifact. Reading
    it here is deliberately scoped to `recall_diagnostic` with a requested live
    semantic gate, because agents otherwise see missing-auth diagnostics even
    after hooks or CLI were configured. Secret values are copied only into this
    MCP process env; the returned report is value/path-free.
    """

    if not arguments.get("run_semantic_gate"):
        return None
    semantic_gate_mode = str(arguments.get("semantic_gate_mode") or "off").strip().casefold()
    if semantic_gate_mode == "off":
        return None
    try:
        from aippocampus_runtime.hooks import (
            provider_bridge as hook_provider_bridge,  # noqa: PLC0415
        )
        from aippocampus_runtime.ops import provider_key_bridge  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - defensive for partial plugin copies.
        return {
            "status": "bridge_adapter_unavailable",
            "reason": type(exc).__name__,
            "secret_values_printed": False,
            "local_paths_printed": False,
            "agent_next_action": "Restart the MCP/plugin host after refreshing the AIppocampus plugin if semantic auth still fails.",
        }

    manifest_path = provider_key_bridge.bridge_manifest_path()
    if not manifest_path.exists():
        return {
            "status": "not_installed",
            "secret_values_printed": False,
            "local_paths_printed": False,
            "agent_next_action": "Run doctor provider or install the provider-key bridge, then restart the MCP/plugin host if live semantic diagnostics still report missing auth.",
        }
    updates = hook_provider_bridge.environment_update_from_manifest(manifest_path)
    if not updates:
        return {
            "status": "manifest_present_but_value_unavailable",
            "provider_env_vars": [],
            "secret_values_printed": False,
            "local_paths_printed": False,
            "agent_next_action": "Recheck the bridge source, then restart the MCP/plugin host after the provider-key bridge can resolve a value.",
        }
    applied: list[str] = []
    already_visible: list[str] = []
    for key, value in updates.items():
        if os.environ.get(key):
            already_visible.append(key)
            continue
        os.environ[key] = value
        applied.append(key)
    return {
        "status": (
            "applied_to_current_mcp_process"
            if applied
            else "already_visible_in_current_mcp_process"
        ),
        "provider_env_vars": sorted({*applied, *already_visible}),
        "secret_values_printed": False,
        "local_paths_printed": False,
        "agent_next_action": "Run recall_diagnostic again only if the current semantic gate result still reports missing auth.",
    }
