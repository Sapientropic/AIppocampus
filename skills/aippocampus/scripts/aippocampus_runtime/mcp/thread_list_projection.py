"""Foreground actions for MCP thread listing."""

from __future__ import annotations

from typing import Any


def mcp_template_action(
    *,
    action_id: str,
    tool_name: str,
    arguments_template: dict[str, Any],
    requires: list[str],
    label: str,
    why: str,
    mutation_risk: str = "read_only",
    claim_boundary: str = "no_claim_before_reopen",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "tool_name": tool_name,
        "arguments_template": arguments_template,
        "requires": list(requires),
        "template_only": True,
        "label": label,
        "why": why,
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
    }


def list_threads_missing_registry_actions() -> list[dict[str, Any]]:
    register = mcp_template_action(
        action_id="register_thread_before_listing",
        tool_name="register_thread",
        arguments_template={
            "cwd": "{project_cwd}",
            "provider": "{provider}",
            "confirm_write": True,
        },
        requires=["cwd", "provider", "confirm_write"],
        label="Register a thread before listing routes",
        why="The registry does not exist yet; choose an explicit provider and confirm the local write before listing.",
        mutation_risk="explicit_local_registry_write",
        claim_boundary="registry_write_not_source_claim",
    )
    status = mcp_template_action(
        action_id="inspect_thread_registration_status",
        tool_name="memory_health",
        arguments_template={"cwd": "{project_cwd}", "detail": "compact"},
        requires=["cwd"],
        label="Inspect thread registration health",
        why="Use a read-only health check if registration status is unclear.",
        claim_boundary="health_status_not_source_evidence",
    )
    return [register, status]


def list_threads_ok_actions() -> list[dict[str, Any]]:
    agent_recall = mcp_template_action(
        action_id="agent_recall_from_thread_list",
        tool_name="agent_recall",
        arguments_template={"query": "{task_or_memory_cue}"},
        requires=["query"],
        label="Recall from a task-specific cue",
        why="Thread lists orient the registry; use agent_recall with a concrete cue before relying on source.",
    )
    full_detail = mcp_template_action(
        action_id="inspect_list_threads_full_detail",
        tool_name="list_threads",
        arguments_template={"detail": "full"},
        requires=["operator_diagnostic_need"],
        label="Inspect full registry detail only for diagnostics",
        why="Full detail may expose private identifiers; keep it behind an explicit diagnostic need.",
        claim_boundary="operator_detail_not_source_evidence",
    )
    return [agent_recall, full_detail]
