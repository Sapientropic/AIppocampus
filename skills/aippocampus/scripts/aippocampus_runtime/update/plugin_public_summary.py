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
    return {
        "kind": "aippocampus_plugin_install_public_summary",
        "ok": bool(result.get("ok")),
        "plugin": {
            "id": plugin.get("id"),
            "version": plugin.get("version"),
            "action": plugin.get("action"),
            "installed": bool(plugin.get("installed")),
            "enabled": bool(plugin.get("enabled")),
        },
        "agent_callable_status": result.get("agent_callable_status"),
        "host_probe": {
            "validation_ok": bool(host_probe.get("validation_ok")),
            "tool_count": len(tool_names),
            "key_tools_present": key_tools,
            "warning_summary": _warning_summary_counts(warning_summary),
        },
        "rollback_command": result.get("rollback_command"),
        "next_status_command": "aippocampus update status --json",
        "claim_boundary": "host probe success proves host exposure, not recall quality or current-thread tool discovery",
    }
