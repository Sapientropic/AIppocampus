"""First-run capability labels projected from update status surfaces."""

from __future__ import annotations

from typing import Any

READY_SURFACE_STATUSES = {"current", "ready", "installed_package"}


def _surface_ready(item: dict[str, Any]) -> bool:
    if item.get("surface") == "llm":
        return bool(item.get("ready"))
    return item.get("status") in READY_SURFACE_STATUSES


def _status_or_unknown(item: dict[str, Any]) -> str:
    return str(item.get("status") or "unknown")


def _ready_or_status(item: dict[str, Any]) -> str:
    return "ready" if _surface_ready(item) else _status_or_unknown(item)


def build_capability_ladder(
    surfaces: dict[str, dict[str, Any]], *, core_ready: bool
) -> list[dict[str, Any]]:
    hooks = surfaces.get("hooks") or {}
    llm = surfaces.get("llm") or {}
    mcp = surfaces.get("mcp") or {}
    llm_ready = _surface_ready(llm)
    child_visible = llm.get("visible_in_child_process")
    if not llm_ready:
        hook_provider_status = _status_or_unknown(llm)
        hook_provider_next = "aippocampus doctor provider --json"
    elif child_visible is True:
        hook_provider_status = "restart_codex_to_confirm"
        hook_provider_next = "restart Codex, then rerun aippocampus doctor provider --json"
    elif child_visible is False:
        hook_provider_status = "not_visible_to_child_process"
        hook_provider_next = "set the provider key in the environment that launches Codex"
    else:
        hook_provider_status = "child_process_not_checked"
        hook_provider_next = "rerun aippocampus doctor provider --json without --no-child-check"

    return [
        {
            "id": "source_search_ready",
            "ready": core_ready,
            "status": "ready" if core_ready else "blocked",
            "what_works": "onboarding plus clean-source search after user consent",
            "next_command": "aippocampus onboard --provider codex --all",
        },
        {
            "id": "active_recall_ready",
            "ready": _surface_ready(mcp),
            "status": _ready_or_status(mcp),
            "what_works": "MCP/progressive recall routes for agent source reopen",
            "next_command": "aippocampus mcp list-tools",
        },
        {
            "id": "ambient_hooks_ready",
            "ready": _surface_ready(hooks),
            "status": _ready_or_status(hooks),
            "what_works": "prompt-time recall scent and lifecycle refresh hooks",
            "next_command": "aippocampus update apply --surface hooks",
        },
        {
            "id": "semantic_provider_ready",
            "ready": llm_ready,
            "status": _ready_or_status(llm),
            "what_works": "semantic lift, warm scouts, and provider-backed jobs",
            "next_command": "aippocampus doctor provider --json",
        },
        {
            "id": "hook_provider_ready",
            "ready": False,
            "status": hook_provider_status,
            "what_works": "provider key visibility for future hook processes",
            "next_command": hook_provider_next,
        },
        {
            "id": "dream_or_subconscious_ready",
            "ready": llm_ready,
            "status": "provider_ready" if llm_ready else "needs_semantic_provider",
            "what_works": "background semantic, subconscious, and Dream-style work",
            "next_command": "aippocampus doctor provider --json",
        },
        {
            "id": "agent_fallback_ready",
            "ready": False,
            "status": "planned_issue_752",
            "what_works": "future agent-backed fallback without external LLM keys",
            "next_command": "track GitHub issue #752",
        },
    ]
