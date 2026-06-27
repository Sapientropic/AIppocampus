"""Public-safe projection for Codex plugin install/uninstall results.

aippocampus-instruction-surface: plugin install public summary owner; text is runtime output boundary, not hidden agent policy.
"""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
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


def _mcp_preflight_action_required(mcp_preflight: dict[str, Any]) -> bool:
    return bool(mcp_preflight and not mcp_preflight.get("resolves"))


def _next_action(
    *,
    ok: bool,
    action_required: bool,
    agent_callable_status: Any,
    mcp_preflight: dict[str, Any] | None = None,
) -> str:
    if not ok:
        return "review plugin install error details with --operator-json"
    if _mcp_preflight_action_required(mcp_preflight or {}):
        repair = str((mcp_preflight or {}).get("primary_repair_command") or "").strip()
        return repair or "repair the aippocampus MCP command path, then rerun plugin install --verify"
    if action_required:
        return "review aippocampus host warnings with --operator-json"
    if agent_callable_status == "host_live_probe_ok":
        return (
            "host probe passed for a fresh MCP launch; reload already-open Codex "
            "threads if foreground MCP still fails, then use CLI recall as fallback"
        )
    return "run aippocampus update status --json"


def _trusted_codex_next_actions(*, ok: bool, action_required: bool) -> list[dict[str, Any]]:
    if not ok or action_required:
        return []
    return [
        {
            "id": "check_current_thread_mcp_boundary",
            "command": "aippocampus update status --foreground-tools-visible --agent-json",
            "mutation_risk": "read_only",
            "why": (
                "Host verification launches a fresh MCP process; an already-open "
                "Codex thread may still need reload or CLI fallback."
            ),
        },
        {
            "id": "check_action_time_hints",
            "command": "aippocampus hooks action status --json",
            "mutation_risk": "read_only",
            "why": "Trusted Codex sessions should review action-time hints before relying on hook nudges.",
        },
        {
            "id": "install_action_time_hints_after_review",
            "command": "aippocampus hooks action install --json",
            "mutation_risk": "explicit_config_write",
            "why": "Install only after reviewing status/guidance and choosing to enable local hook wiring.",
        },
    ]


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
        for name in (
            "agent_recall",
            "agent_aippo",
            "agent_background",
            "agent_deepen",
            "agent_explain",
        )
        if name in tool_names
    ]
    key_tool_smokes = [
        item for item in host_probe.get("key_tool_smokes") or [] if isinstance(item, dict)
    ]
    key_tool_failures = [item for item in key_tool_smokes if not item.get("ok")]
    ok = bool(result.get("ok"))
    agent_callable_status = result.get("agent_callable_status")
    warning_counts = _warning_summary_counts(warning_summary)
    mcp_preflight = (
        result.get("mcp_command_preflight")
        if isinstance(result.get("mcp_command_preflight"), dict)
        else {}
    )
    action_required = _aippocampus_action_required(warning_counts, ok=ok) or _mcp_preflight_action_required(
        mcp_preflight
    )
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
            mcp_preflight=mcp_preflight,
        ),
        "trusted_codex_next_actions": _trusted_codex_next_actions(
            ok=ok,
            action_required=action_required,
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
        "mcp_command_preflight": {
            "status": mcp_preflight.get("status"),
            "command": mcp_preflight.get("command"),
            "resolves": bool(mcp_preflight.get("resolves")),
            "primary_repair_command": mcp_preflight.get("primary_repair_command"),
            "repair_options": list(mcp_preflight.get("repair_options") or [])[:3],
            "resolved_path_emitted": False,
        },
        "current_thread_mcp_boundary": {
            "host_probe_refreshes_existing_thread": False,
            "already_open_thread_may_need_reload": True,
            "reload_instruction": (
                "Reload Codex Desktop or restart the MCP transport before trusting "
                "MCP-first recall in a thread that was open before install."
            ),
            "cli_fallback_command_template": 'aippocampus agent recall "{cue}" --json',
            "status_command": "aippocampus update status --foreground-tools-visible --agent-json",
        },
        "rollback_command": result.get("rollback_command"),
        "rollback_preview_command": result.get("rollback_preview_command")
        or "aippocampus plugin uninstall --codex --dry-run --json",
        "next_status_command": "aippocampus update status --json",
        "claim_boundary": (
            "host probe success proves a fresh host launch can expose/call key tools; "
            "it does not prove recall quality or refresh an already-open foreground MCP process"
        ),
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
        preview_action = {
            "id": "review_plugin_uninstall_preview",
            "label": "Review plugin uninstall preview",
            "message": "Review dry-run booleans before choosing whether to remove the Codex plugin.",
            "why": "Dry-run output is a decision card; no uninstall has happened yet.",
            "mutation_risk": "read_only_preview_of_delete",
            "claim_boundary": "host_setup_not_memory_evidence",
            "continue_without_command": True,
        }
        execute_action = {
            "id": "uninstall_codex_plugin_after_consent",
            "label": "Uninstall Codex plugin after consent",
            "command": str(result.get("execute_command") or "aippocampus plugin uninstall --codex"),
            "why": "Run only after the dry-run removal set is acceptable to the user.",
            "mutation_risk": "explicit_local_plugin_delete",
            "requires_user_consent": True,
            "claim_boundary": "host_setup_not_memory_evidence",
        }
        return {
            "kind": "aippocampus_plugin_uninstall_preview_public_summary",
            "ok": bool(result.get("ok")),
            "dry_run": True,
            **canonical_foreground_action_fields(
                preview_action,
                safe_next_actions=[preview_action, execute_action],
            ),
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
            "agent_guidance": (
                "Review the dry-run booleans; run the uninstall action only after explicit consent."
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
        "foreground_guidance": "Plugin removed. Reinstall with `aippocampus plugin install --codex --verify` if needed.",
        "operator_json_available": True,
        "local_private_fields": ["codex_home", "marketplace_root"],
        "privacy_boundary": {
            "local_paths_serialized": False,
            "operator_json_required_for_raw_paths": True,
        },
    }


def with_operator_stdout_boundary(result: dict[str, Any]) -> dict[str, Any]:
    """Mark an operator JSON request while keeping plugin stdout path-safe."""

    payload = dict(result)
    privacy = payload.get("privacy_boundary")
    privacy_payload = dict(privacy) if isinstance(privacy, dict) else {}
    privacy_payload.update(
        {
            "operator_json_requested": True,
            "local_paths_serialized": False,
            "raw_exception_serialized": False,
        }
    )
    payload["privacy_boundary"] = privacy_payload
    payload["operator_diagnostics"] = {
        "raw_stdout_disabled": True,
        "reason": "plugin install stdout stays public-safe even for operator JSON",
        "next_status_command": "aippocampus plugin status --operator-json",
    }
    return payload
