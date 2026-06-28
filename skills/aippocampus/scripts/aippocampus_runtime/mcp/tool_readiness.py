"""Compact MCP tool-readiness projections for public CLI checks."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.foreground_compact_language import strip_compact_policy_vocabulary
from aippocampus_runtime.mcp.tool_catalog import TOOLS

KEY_AGENT_NATIVE_TOOLS = (
    "agent_recall",
    "agent_aippo",
    "agent_background",
    "agent_deepen",
    "agent_explain",
)

FOREGROUND_PARAMETER_TOOLS = (
    "agent_recall",
    "agent_deepen",
    "search_memory",
    "memory_health",
)

WORKFLOW_GUIDE_TOOLS = (
    "agent_recall",
    "agent_deepen",
    "search_memory",
    "get_turn_context",
    "agent_explain",
    "recall_diagnostic",
    "memory_health",
)


def visible_tool_names() -> list[str]:
    return sorted(str(tool.get("name") or "") for tool in TOOLS if tool.get("name"))


def tool_names_summary() -> dict[str, Any]:
    names = visible_tool_names()
    return {"ok": True, "tool_count": len(names), "tool_names": names}


def _tools_by_name() -> dict[str, dict[str, Any]]:
    return {str(tool.get("name") or ""): tool for tool in TOOLS if tool.get("name")}


def _aippocampus_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    metadata = tool.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    aippocampus = metadata.get("aippocampus")
    return aippocampus if isinstance(aippocampus, dict) else {}


def _foreground_parameter_guide(tools_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    guide: dict[str, Any] = {}
    for tool_name in FOREGROUND_PARAMETER_TOOLS:
        metadata = _aippocampus_metadata(tools_by_name.get(tool_name, {}))
        tiers = metadata.get("parameter_tiers")
        if not isinstance(tiers, dict):
            continue
        guide[tool_name] = {
            "required": list(tiers.get("required") or []),
            "common": list(tiers.get("common") or []),
        }
    return guide


def _workflow_guide(
    tools_by_name: dict[str, dict[str, Any]],
    *,
    tool_names: tuple[str, ...] = WORKFLOW_GUIDE_TOOLS,
    include_legacy_edges: bool = False,
) -> dict[str, Any]:
    guide: dict[str, Any] = {}
    for tool_name in tool_names:
        metadata = _aippocampus_metadata(tools_by_name.get(tool_name, {}))
        if not metadata:
            continue
        requires_prior = list(metadata.get("requires_prior") or [])
        enables_next = list(metadata.get("enables_next") or [])
        if not include_legacy_edges:
            requires_prior = [
                name for name in requires_prior if name not in {"recall_context", "recall_deepen"}
            ]
            enables_next = [
                name for name in enables_next if name not in {"recall_context", "recall_deepen"}
            ]
        row = {
            "workflow": metadata.get("workflow"),
            "requires_prior": requires_prior,
            "enables_next": enables_next,
        }
        if include_legacy_edges:
            row["posture"] = metadata.get("posture")
            row["claim_boundary"] = metadata.get("claim_boundary")
        guide[tool_name] = row
        if metadata.get("legacy"):
            guide[tool_name]["legacy"] = True
        if metadata.get("foreground_recommended") is not None:
            guide[tool_name]["foreground_recommended"] = bool(
                metadata.get("foreground_recommended")
            )
    return guide


def _tool_use_guide(*, detail: str = "compact") -> dict[str, Any]:
    tools_by_name = _tools_by_name()
    guide = {
        "primary_consumer_field": "foreground_action",
        "foreground_parameters": _foreground_parameter_guide(tools_by_name),
        "workflow": _workflow_guide(tools_by_name),
        "when_to_use": {
            "agent_recall": "Use first when the agent has a task cue, old correction, issue title, or handoff phrase.",
            "agent_deepen": "Use after recall surfaces a numbered route that may support a claim or decision.",
        },
        "fallbacks": {
            "current_thread_visibility_missing": (
                "Run recall with a concrete cue or exact search; tool discovery is routing metadata, not source evidence."
            ),
            "route_selector_missing": "Run agent_recall again or request detail=full only for local diagnostics.",
        },
        "status_note": "Tool discovery guides recall/deepen choice; open source before relying on a memory claim.",
    }
    if detail == "full":
        guide["legacy_workflow"] = _workflow_guide(
            {
                name: tools_by_name[name]
                for name in ("recall_context", "recall_deepen")
                if name in tools_by_name
            },
            tool_names=("recall_context", "recall_deepen"),
            include_legacy_edges=True,
        )
        guide["operator_write_lanes"] = {
            "route_feedback_cli": (
                "MCP does not expose an agent_feedback tool; use `aippocampus agent feedback ... --json` "
                "only when explicitly recording local route feedback."
            )
        }
    return guide


def _feedback_operator_action() -> dict[str, Any]:
    return foreground_template_action(
        action_id="record_route_feedback_cli_fallback",
        command_template=(
            "aippocampus agent feedback {route_id} --outcome {feedback_outcome} --json"
        ),
        requires=["route_id", "feedback_outcome"],
        label="Record route feedback",
        why="Use only when explicitly recording whether a route helped, misled, went stale, or should stay quiet.",
        mutation_risk="durable_low_authority_feedback_write",
        claim_boundary="feedback_is_not_source_truth",
    )


def tool_readiness_summary(*, detail: str = "compact") -> dict[str, Any]:
    detail = "full" if str(detail or "").strip().casefold() == "full" else "compact"
    names = visible_tool_names()
    key_present = [name for name in KEY_AGENT_NATIVE_TOOLS if name in names]
    missing = [name for name in KEY_AGENT_NATIVE_TOOLS if name not in names]
    payload: dict[str, Any] = {
        "kind": "aippocampus_mcp_tool_readiness",
        "ok": not missing,
        "tool_count": len(names),
        "detail": detail,
        "agent_native_tools_present": not missing,
        "key_tools_present": key_present,
        "missing_key_tools": missing,
        "schema_available": True,
        "full_schema_command": "aippocampus mcp list-tools --json",
    }
    if missing:
        primary = foreground_shell_action(
            action_id="inspect_mcp_plugin_status",
            command="aippocampus plugin status --json",
            label="Inspect Codex plugin MCP wiring",
            why="Key agent-native MCP tools are missing; inspect local plugin status before choosing an explicit repair write.",
            mutation_risk="read_only",
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
        if detail == "full":
            payload["operator_write_actions"] = [
                foreground_shell_action(
                    action_id="repair_mcp_tool_catalog",
                    command="aippocampus plugin install --codex --verify --json",
                    label="Repair Codex plugin MCP wiring",
                    why="Run only after deciding to refresh local plugin/cache wiring.",
                    mutation_risk="writes_local_plugin_cache",
                    claim_boundary="install_status_not_memory_evidence",
                )
            ]
    else:
        primary = foreground_shell_action(
            action_id="inspect_current_thread_tool_discovery",
            command="aippocampus update status --json",
            label="Inspect current-thread continuity tools",
            why=(
                "MCP tools are visible; inspect current-thread status before choosing "
                "recall or deepen."
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
        payload["tool_use_guide"] = _tool_use_guide(detail=detail)
        payload.update(
            canonical_foreground_action_fields(
                primary,
                safe_next_actions=[primary, recall, deepen],
            )
        )
        if detail == "full":
            payload["operator_write_actions"] = [_feedback_operator_action()]
    if detail == "compact":
        return strip_compact_policy_vocabulary(payload)
    return payload
