#!/usr/bin/env python3
"""Foreground recovery cards for MCP memory_health.

The MCP server facade is intentionally thin. Keep this split-state logic here
so health diagnostics can evolve without making the tool dispatcher another
operator-diagnostic blob.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime import core


def payload_for_health_exception(arguments: dict[str, Any]) -> dict[str, Any]:
    recall_capability = _recall_probe(arguments)
    if recall_capability.get("clean_source_available") and recall_capability.get(
        "recall_tool_available"
    ):
        return _degraded_recall_payload(recall_capability)
    return _unavailable_recovery_payload()


def _cwd_arg(arguments: dict[str, Any]) -> Path:
    return core.canonical_path(str(arguments.get("cwd") or os.getcwd()))


def _registry_dir_arg(arguments: dict[str, Any]) -> Path | None:
    return Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None


def _clean_source_dir_for(arguments: dict[str, Any]) -> Path:
    cwd = _cwd_arg(arguments)
    explicit = arguments.get("clean_source_dir")
    if explicit:
        return core.resolve_artifact_path(str(explicit), cwd, core.default_thread_clean_source_dir(cwd))
    global_dir = core.default_thread_clean_source_dir(cwd)
    legacy_dir = cwd / ".aippocampus" / "clean-source"
    if (global_dir / "messages.jsonl").exists() or not (legacy_dir / "messages.jsonl").exists():
        return global_dir
    return legacy_dir


def _agent_continuity_module() -> Any:
    return importlib.import_module("aippocampus_runtime.recall.agent_continuity")


def _template_tool_action(
    tool_name: str,
    arguments_template: dict[str, Any],
    requires: list[str],
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "arguments_template": arguments_template,
        "requires": requires,
        "template_only": True,
    }


def _recall_probe(arguments: dict[str, Any]) -> dict[str, Any]:
    source_dir = _clean_source_dir_for(arguments)
    if not (source_dir / "messages.jsonl").exists():
        return {
            "clean_source_available": False,
            "recall_tool_available": True,
            "route_probe_status": "clean_source_missing",
            "route_count": 0,
            "deepen_tool_available": False,
        }

    cue = str(
        arguments.get("query")
        or arguments.get("intent")
        or arguments.get("cue")
        or arguments.get("task")
        or "source-backed continuity"
    ).strip()
    try:
        recall_payload = _agent_continuity_module().recall(
            cue,
            cwd=_cwd_arg(arguments),
            clean_source_dir=source_dir,
            registry_dir=_registry_dir_arg(arguments),
            project=str(arguments.get("project") or "AIppocampus"),
            max_routes=1,
        )
    except Exception:
        return {
            "clean_source_available": True,
            "recall_tool_available": False,
            "route_probe_status": "recall_probe_failed",
            "route_count": 0,
            "deepen_tool_available": False,
        }

    deepen_requests = [
        item for item in recall_payload.get("deepen_requests") or [] if isinstance(item, dict)
    ]
    memory_packets = [
        item for item in recall_payload.get("memory_packets") or [] if isinstance(item, dict)
    ]
    route_count = max(len(deepen_requests), len(memory_packets))
    return {
        "clean_source_available": True,
        "recall_tool_available": True,
        "route_probe_status": "routes_available" if route_count else "source_present_probe_no_routes",
        "route_count": route_count,
        "deepen_tool_available": bool(deepen_requests),
    }


def _unavailable_recovery_payload() -> dict[str, Any]:
    return {
        "kind": "aippocampus_memory_health_recovery",
        "ok": False,
        "status": "unavailable",
        "error": {
            "code": "health_unavailable",
            "message": "Memory health could not find usable local source artifacts for this scope.",
        },
        "agent_next_action": {
            "id": "recover_or_continue_without_memory",
            "label": (
                "Check provider/onboarding status, register/sync a thread if this is setup, "
                "or continue without memory."
            ),
            "command": "aippocampus onboard --provider auto --status --json",
            "mutation_risk": "read_only",
            "claim_boundary": "setup_status_not_memory_evidence",
        },
        "safe_next_actions": [
            {
                "id": "check_onboarding_status",
                "command": "aippocampus onboard --provider auto --status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "setup_status_not_memory_evidence",
            },
            {
                "id": "list_mcp_tools",
                "command": "aippocampus mcp list-tools --compact",
                "mutation_risk": "read_only",
                "claim_boundary": "tool_discovery_not_memory_evidence",
            },
            {
                "id": "search_exact_phrase",
                "command_template": 'aippocampus search "{exact_phrase}" --json',
                "requires": ["exact_phrase"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "source_reopen_required_before_quoting",
            },
            {
                "id": "continue_without_memory",
                "manual_instruction": "Continue without memory when no local source exists.",
                "mutation_risk": "read_only",
                "claim_boundary": "no_local_source_available",
            },
        ],
        "source_boundary": {
            "no_rollout_found_is_not_a_recall_quality_claim": True,
            "local_paths_serialized": False,
        },
    }


def _degraded_recall_payload(recall_capability: dict[str, Any]) -> dict[str, Any]:
    recall_action = {
        **_template_tool_action(
            "agent_recall",
            {"query": "{task_or_memory_cue}", "cwd": "{project_cwd}", "max": 3},
            ["task_or_memory_cue"],
        ),
        "id": "try_agent_recall_with_cue",
        "label": "Try source-backed recall with the current task cue",
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": "Health artifacts are missing; use recall/deepen before setup recovery.",
    }
    deepen_action = {
        **_template_tool_action(
            "agent_deepen",
            {"request_index": 1, "last_recall": True},
            ["agent_recall_foreground_action"],
        ),
        "id": "deepen_selected_recall_route",
        "label": "Deepen a selected recall route",
        "mutation_risk": "read_only",
        "claim_boundary": "source_reopen_required_before_claim",
    }
    return {
        "kind": "aippocampus_memory_health_recovery",
        "ok": False,
        "status": "degraded",
        "health_artifacts_missing": True,
        "recall_capability": recall_capability,
        "error": {
            "code": "health_artifacts_missing_recall_available",
            "message": (
                "Memory health artifacts are missing, but the foreground recall path can still be used."
            ),
        },
        "agent_next_action": recall_action,
        "foreground_action": recall_action,
        "safe_next_actions": [
            recall_action,
            deepen_action,
            {
                "id": "check_onboarding_status",
                "command": "aippocampus onboard --provider auto --status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "setup_status_not_memory_evidence",
                "when": "Use only if recall has no route or setup status is the actual task.",
            },
            {
                "id": "list_mcp_tools",
                "command": "aippocampus mcp list-tools --compact",
                "mutation_risk": "read_only",
                "claim_boundary": "tool_discovery_not_memory_evidence",
            },
        ],
        "source_boundary": {
            "health_card_is_not_memory_evidence": True,
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
            "raw_source_text_serialized": False,
        },
    }
