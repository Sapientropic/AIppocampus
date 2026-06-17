"""Fast partial update status for foreground agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.update.agent_callable import (
    default_host_probe_report_path,
    load_json_file,
    status_agent_callable,
)
from aippocampus_runtime.update.capability_ladder import build_capability_ladder
from aippocampus_runtime.update.host_conformance import build_host_conformance_status

DETAIL_COMMAND = "aippocampus update status --operator-json"


def _deferred_surface(surface: str, *, component: str, reason: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "status": "deferred",
        "ready": False,
        "deferred_component": component,
        "operator_detail_available": True,
        "operator_detail_command": DETAIL_COMMAND,
        "reason": reason,
    }


def build_partial_status(
    args: Any, *, mode: str, cli_helpers: dict[str, Any]
) -> dict[str, Any]:
    """Return a foreground-sized partial card without importing the full CLI back."""

    repo_root = cli_helpers["find_repo_root"](
        Path(args.repo_root).resolve() if args.repo_root else None
    )
    codex_home_path = Path(args.codex_home).resolve() if args.codex_home else codex_home()
    surfaces = {
        "cli": cli_helpers["status_cli"](repo_root),
        "skill": _deferred_surface(
            "skill",
            component="skill_tree_fingerprint",
            reason="skill package tree comparison deferred from foreground status",
        ),
        "mcp": cli_helpers["status_mcp"](
            repo_root, Path(args.mcp_config).resolve() if args.mcp_config else None
        ),
        "plugin": _deferred_surface(
            "plugin",
            component="plugin_cache_fingerprint",
            reason="plugin package/cache tree comparison deferred from foreground status",
        ),
        "hooks": _deferred_surface(
            "hooks",
            component="hooks_status",
            reason="hook and action-hint cache inspection deferred from foreground status",
        ),
        "llm": _deferred_surface(
            "llm",
            component="llm_child_process",
            reason="provider and child-process key inheritance checks deferred",
        ),
    }
    host_probe_path = (
        Path(args.host_probe_report).resolve()
        if args.host_probe_report
        else default_host_probe_report_path(codex_home_path)
    )
    surfaces["agent_callable"] = status_agent_callable(
        codex_home_path,
        surfaces,
        host_probe=load_json_file(host_probe_path),
        foreground_tools_visible_asserted=bool(args.foreground_tools_visible),
        foreground_key_tools_callable_asserted=bool(args.foreground_key_tools_callable),
        foreground_key_tool_failure=args.foreground_key_tool_failure,
    )
    surfaces["host_conformance"] = build_host_conformance_status(surfaces)
    deferred = [
        str(item.get("deferred_component") or name)
        for name, item in surfaces.items()
        if item.get("operator_detail_available")
    ]
    capability_ladder = build_capability_ladder(surfaces, core_ready=False)
    return {
        "schema_version": cli_helpers["SCHEMA_VERSION"],
        "kind": f"aippocampus_update_{mode}",
        "mode": mode,
        "ok": True,
        "repo_root": str(repo_root),
        "codex_home": str(codex_home_path),
        "summary": {
            "core_ready": False,
            "core_blockers": [],
            "magic_ready": False,
            "magic_blockers": [],
            "optional_surfaces": [],
            "operator_surfaces": ["mcp", "agent_callable"],
            "operator_blockers": [],
            "agent_callable_ready": surfaces["agent_callable"]["ready"],
            "agent_callable_status": surfaces["agent_callable"]["status"],
            "agent_callable_host_ready": (
                (surfaces["agent_callable"].get("host_live_probe") or {}).get("ok")
                is True
            ),
            "agent_callable_current_thread_visible": (
                surfaces["agent_callable"].get("foreground_tools_visible") is True
            ),
            "agent_callable_current_thread_callable": surfaces["agent_callable"]["ready"],
            "agent_callable_foreground_probe_requested": bool(
                surfaces["agent_callable"].get("foreground_probe_requested")
            ),
            "agent_callable_foreground_probe_state": surfaces["agent_callable"].get(
                "foreground_probe_state"
            ),
            "host_conformance_label": surfaces["host_conformance"]["label"],
            "capability_ladder": capability_ladder,
            "needs_action": [],
            "stale_or_missing_surfaces": [],
            "nested_action_surfaces": [],
            "plugin_cache_needs_action": False,
            "plugin_cache_recommended_actions": [],
            "dirty_worktree_guards": {},
            "plan_surface_filter": [],
            "plan_scope": "foreground_partial",
            "partial_readiness": True,
            "deferred_components": deferred,
        },
        "surfaces": surfaces,
        "safety_notes": [
            "status is a read-only foreground partial card",
            "slow freshness, hook, plugin-cache, and provider checks are deferred",
            "rerun operator detail before release-grade or exact/latest readiness claims",
        ],
    }
