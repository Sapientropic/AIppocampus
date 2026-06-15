"""Public-safe projection for Codex plugin install results."""

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
            "warning_summary": warning_counts,
        },
        "rollback_command": result.get("rollback_command"),
        "rollback_preview_command": result.get("rollback_preview_command")
        or "aippocampus plugin uninstall --codex --dry-run --json",
        "next_status_command": "aippocampus update status --json",
        "claim_boundary": "host probe success proves host exposure, not recall quality or current-thread tool discovery",
    }
