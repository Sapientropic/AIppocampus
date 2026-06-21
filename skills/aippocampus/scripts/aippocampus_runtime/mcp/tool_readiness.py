"""Compact MCP tool-readiness projections for public CLI checks."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.mcp.tool_catalog import TOOLS

KEY_AGENT_NATIVE_TOOLS = (
    "agent_recall",
    "agent_aippo",
    "agent_background",
    "agent_deepen",
    "agent_explain",
)


def visible_tool_names() -> list[str]:
    return sorted(str(tool.get("name") or "") for tool in TOOLS if tool.get("name"))


def tool_names_summary() -> dict[str, Any]:
    names = visible_tool_names()
    return {"ok": True, "tool_count": len(names), "tool_names": names}


def _tool_use_guide() -> dict[str, Any]:
    return {
        "primary_consumer_field": "foreground_action",
        "when_to_use": {
            "agent_recall": "Use first when the agent has a task cue, old correction, issue title, or handoff phrase.",
            "agent_deepen": "Use after recall surfaces a numbered route that may support a claim or decision.",
            "route_feedback": "Use the CLI feedback fallback only after judging a route as helpful, wrong, stale, noisy, or quiet-worthy.",
        },
        "fallbacks": {
            "current_thread_visibility_missing": (
                "Run recall with a concrete cue or exact search; tool discovery is routing metadata, not source evidence."
            ),
            "route_selector_missing": "Run agent_recall again or request detail=full only for local diagnostics.",
            "route_feedback_cli": (
                "MCP does not expose an agent_feedback tool; use `aippocampus agent feedback ... --json` only when explicitly recording local route feedback."
            ),
        },
        "boundary": "tool_discovery_routes_attention_source_claims_require_recall_or_deepen",
    }


def tool_readiness_summary() -> dict[str, Any]:
    names = visible_tool_names()
    key_present = [name for name in KEY_AGENT_NATIVE_TOOLS if name in names]
    missing = [name for name in KEY_AGENT_NATIVE_TOOLS if name not in names]
    payload: dict[str, Any] = {
        "kind": "aippocampus_mcp_tool_readiness",
        "ok": not missing,
        "tool_count": len(names),
        "agent_native_tools_present": not missing,
        "key_tools_present": key_present,
        "missing_key_tools": missing,
        "schema_available": True,
        "full_schema_command": "aippocampus mcp list-tools --json",
    }
    if missing:
        primary = foreground_shell_action(
            action_id="repair_mcp_tool_catalog",
            command="aippocampus plugin install --codex --verify --json",
            label="Repair Codex plugin MCP wiring",
            why="Key agent-native MCP tools are missing; reinstall or verify the local Codex plugin wiring.",
            mutation_risk="writes_local_plugin_cache",
            claim_boundary="install_status_not_memory_evidence",
        )
        status = foreground_shell_action(
            action_id="inspect_mcp_status_after_repair",
            command="aippocampus mcp status",
            label="Recheck MCP tool readiness",
            why="Use after repair to confirm key agent-native tools are visible.",
            mutation_risk="read_only",
            claim_boundary="tool_visibility_not_memory_evidence",
        )
        payload.update(canonical_foreground_action_fields(primary, safe_next_actions=[primary, status]))
    else:
        primary = foreground_shell_action(
            action_id="inspect_current_thread_tool_discovery",
            command="aippocampus update status --json",
            label="Inspect current-thread continuity tools",
            why=(
                "MCP tools are visible; inspect current-thread status before choosing "
                "recall, deepen, or feedback."
            ),
            mutation_risk="read_only",
            claim_boundary="tool_discovery_not_memory_evidence",
        )
        recall = foreground_template_action(
            action_id="try_agent_recall",
            command_template='aippocampus agent recall "{cue}" --json',
            requires=["cue"],
            label="Try source-backed recall",
            why="Key agent-native MCP tools are visible; use recall with a concrete task or memory cue.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
        deepen = foreground_template_action(
            action_id="deepen_recall_selector_route",
            command_template=(
                "aippocampus agent deepen --request {request_index} "
                "--recall-selector {recall_selector} --json"
            ),
            requires=["request_index", "recall_selector"],
            label="Open a selected recall route",
            why=(
                "Use only after recall returns a numbered request and recall_selector; "
                "--last-recall is a mutable-cache compatibility fallback."
            ),
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
        feedback = foreground_template_action(
            action_id="record_route_feedback_cli_fallback",
            command_template=(
                "aippocampus agent feedback {route_id} --outcome {feedback_outcome} --json"
            ),
            requires=["route_id", "feedback_outcome"],
            label="Record route feedback",
            why="Use after a route helped, misled, went stale, or should stay quiet.",
            mutation_risk="durable_low_authority_feedback_write",
            claim_boundary="feedback_is_not_source_truth",
        )
        payload["tool_use_guide"] = _tool_use_guide()
        payload.update(
            canonical_foreground_action_fields(
                primary,
                safe_next_actions=[primary, recall, deepen],
            )
        )
        payload["cli_fallback_actions"] = [feedback]
    return payload
