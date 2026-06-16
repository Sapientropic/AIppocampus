"""Public-safe projection for Codex plugin install/uninstall results."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.update.host_probe_warnings import (
    BUCKETS as WARNING_BUCKETS,
)
from aippocampus_runtime.update.host_probe_warnings import (
    SUMMARY_KIND as WARNING_SUMMARY_KIND,
)


def _warning_summary_counts(summary: dict[str, Any] | None) -> dict[str, Any]:
    payload = summary if isinstance(summary, dict) else {}
    buckets = {bucket: len(payload.get(bucket) or []) for bucket in WARNING_BUCKETS}
    return {
        "kind": WARNING_SUMMARY_KIND,
        "status": payload.get("status") or "not_available",
        "validation_ok": bool(payload.get("validation_ok")),
        "warning_count": int(payload.get("warning_count") or 0),
        "nonfatal_warning_count": int(payload.get("nonfatal_warning_count") or 0),
        "bucket_counts": buckets,
    }


def _aippocampus_action_required(warning_counts: dict[str, Any], *, ok: bool) -> bool:
    buckets = warning_counts.get("bucket_counts") or {}
    return (not ok) or bool(
        buckets.get("fatal_failures")
        or buckets.get("aippocampus_actionable_warnings")
    )


def _next_action(
    *,
    ok: bool,
    action_required: bool,
    agent_callable_status: Any,
) -> str:
    if not ok:
        return "review plugin install error details with --operator-json"
    if action_required:
        return "review aippocampus host warnings with --operator-json"
    if agent_callable_status == "host_live_probe_ok":
        return "reload host app if tools are not visible"
    return "run aippocampus update status --json"


def public_install_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Return the user-reportable install/probe summary without local paths."""

    plugin = result.get("plugin") if isinstance(result.get("plugin"), dict) else {}
    host_probe = result.get("host_probe") if isinstance(result.get("host_probe"), dict) else {}
    warning_summary = host_probe.get("warning_summary") if isinstance(host_probe, dict) else {}
    tool_names = [
        str(item)
        for item in ((host_probe.get("mcp_status") or {}).get("tool_names") or [])
    ]
    key_tools = [
        name
        for name in ("agent_recall", "agent_aippo", "agent_deepen", "agent_explain")
        if name in tool_names
    ]
    key_tool_smokes = [
        item for item in host_probe.get("key_tool_smokes") or [] if isinstance(item, dict)
    ]
    key_tool_failures = [item for item in key_tool_smokes if not item.get("ok")]
    ok = bool(result.get("ok"))
    agent_callable_status = result.get("agent_callable_status")
    warning_counts = _warning_summary_counts(warning_summary)
    action_required = _aippocampus_action_required(warning_counts, ok=ok)
    return {
        "kind": "aippocampus_plugin_install_public_summary",
        "ok": ok,
        "agent_callable_status": agent_callable_status,
        "tool_count": len(tool_names),
        "nonfatal_host_warning_count": warning_counts["nonfatal_warning_count"],
        "aippocampus_action_required": action_required,
        "next_action": _next_action(
            ok=ok,
            action_required=action_required,
            agent_callable_status=agent_callable_status,
        ),
        "plugin": {
            "id": plugin.get("id"),
            "version": plugin.get("version"),
            "action": plugin.get("action"),
            "installed": bool(plugin.get("installed")),
            "enabled": bool(plugin.get("enabled")),
        },
        "host_probe": {
            "validation_ok": bool(host_probe.get("validation_ok")),
            "tool_count": len(tool_names),
            "key_tools_present": key_tools,
            "key_tools_callable": None
            if not key_tool_smokes
            else not bool(key_tool_failures),
            "key_tool_failure_count": len(key_tool_failures),
            "warning_summary": warning_counts,
        },
        "rollback_command": result.get("rollback_command"),
        "rollback_preview_command": result.get("rollback_preview_command")
        or "aippocampus plugin uninstall --codex --dry-run --json",
        "next_status_command": "aippocampus update status --json",
        "claim_boundary": "host probe success proves host exposure and key-tool callability when checked, not recall quality or current-thread tool discovery",
    }


def public_uninstall_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Project plugin uninstall results without local host paths.

    Rollback previews are meant to be agent-readable. The raw Codex home,
    marketplace root, and installed-cache root are operator coordinates; expose
    only booleans/countable decisions unless --operator-json is requested.
    """

    if result.get("kind") == "aippocampus_plugin_uninstall_preview":
        will_remove = []
        if result.get("would_remove_installed_cache"):
            will_remove.append("installed_plugin_cache")
        if result.get("would_remove_marketplace_root"):
            will_remove.append("owned_marketplace_copy")
        return {
            "kind": "aippocampus_plugin_uninstall_preview_public_summary",
            "ok": bool(result.get("ok")),
            "dry_run": True,
            "will_remove": will_remove,
            "would_remove_installed_cache": bool(result.get("would_remove_installed_cache")),
            "would_remove_marketplace_root": bool(result.get("would_remove_marketplace_root")),
            "marketplace_owned_by_aippocampus": bool(
                result.get("marketplace_owned_by_aippocampus")
            ),
            "keep_marketplace": bool(result.get("keep_marketplace")),
            "codex_plugin_manager_can_see_plugin": result.get(
                "codex_plugin_manager_can_see_plugin"
            ),
            "codex_plugin_manager_check_error": result.get(
                "codex_plugin_manager_check_error"
            ),
            "execute_command": result.get("execute_command"),
            "agent_next_action": (
                "Review the dry-run booleans, then run the execute_command to remove the "
                "plugin; reinstall with `aippocampus plugin install --codex --verify`."
            ),
            "operator_json_available": True,
            "local_private_fields": result.get("local_private_fields")
            or ["codex_home", "marketplace_root", "installed_cache_root"],
            "privacy_boundary": {
                "local_paths_serialized": False,
                "operator_json_required_for_raw_paths": True,
            },
        }
    return {
        "kind": "aippocampus_plugin_uninstall_public_summary",
        "ok": bool(result.get("ok")),
        "removed_installed_cache": bool(result.get("removed_installed_cache")),
        "removed_marketplace_root": bool(result.get("removed_marketplace_root")),
        "agent_next_action": "Plugin removed. Reinstall with `aippocampus plugin install --codex --verify` if needed.",
        "operator_json_available": True,
        "local_private_fields": ["codex_home", "marketplace_root"],
        "privacy_boundary": {
            "local_paths_serialized": False,
            "operator_json_required_for_raw_paths": True,
        },
    }
