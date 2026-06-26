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
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_readiness_card,
)
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir


def payload_for_health_exception(arguments: dict[str, Any]) -> dict[str, Any]:
    recall_capability = _recall_probe(arguments)
    if _recall_routes_available(recall_capability):
        return _degraded_recall_payload(recall_capability)
    return _unavailable_recovery_payload()


def recall_first_health_payload(
    arguments: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Keep foreground health from hiding a usable recall/deepen path.

    Health artifacts can be stale or missing while the agent-native recall
    facade can still return reopenable routes through registry/navigation
    state. In that split state the primary agent action should remain recall;
    setup or maintenance stays visible as a follow-up, not the first step.
    """

    if not _payload_blocks_first_recall(payload):
        return payload
    recall_capability = _recall_probe(arguments)
    if not _recall_routes_available(recall_capability):
        return payload

    recall_action = _recall_action()
    deepen_action = _deepen_action()
    maintenance_action = payload.get("foreground_action")
    safe_next_actions = [recall_action, deepen_action]
    if isinstance(maintenance_action, dict):
        maintenance_copy = dict(maintenance_action)
        maintenance_copy.setdefault("when", "Use after recall when maintenance is the actual task.")
        safe_next_actions.append(maintenance_copy)

    source_boundary = payload.get("source_boundary")
    merged_source_boundary = dict(source_boundary) if isinstance(source_boundary, dict) else {}
    updated = dict(payload)
    updated.update(
        {
            "ok": False,
            "status": "degraded",
            "ordinary_first_recall_usable": True,
            "blocks_first_recall": False,
            "health_artifacts_missing": _health_artifacts_missing(payload),
            "recall_capability": recall_capability,
            "readiness_card": foreground_readiness_card(
                subject="memory_health",
                scope="current_workspace",
                state="degraded_recall_available",
                usable_now=True,
                blocks_first_recall=False,
                blocks_exact_latest=True,
                recommended=["refresh_health_artifacts_after_recall"],
                next_actions=[recall_action, deepen_action],
                claim_boundary="health_readiness_not_source_evidence",
            ),
            **canonical_foreground_action_fields(
                recall_action,
                safe_next_actions=safe_next_actions,
            ),
            "source_boundary": {
                **merged_source_boundary,
                "health_card_is_not_memory_evidence": True,
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
                "local_paths_serialized": False,
                "raw_source_text_serialized": False,
            },
        }
    )
    if isinstance(maintenance_action, dict):
        updated["maintenance_next_action"] = maintenance_action
    return updated


def _cwd_arg(arguments: dict[str, Any]) -> Path:
    return core.canonical_path(str(arguments.get("cwd") or os.getcwd()))


def _registry_dir_arg(arguments: dict[str, Any]) -> Path | None:
    if arguments.get("registry_dir"):
        return Path(str(arguments["registry_dir"])).resolve()
    return core.aippocampus_registry_dir().resolve()


def _clean_source_dir_for(arguments: dict[str, Any]) -> Path:
    return resolve_clean_source_dir(_cwd_arg(arguments), arguments.get("clean_source_dir"))


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
    clean_source_available = (source_dir / "messages.jsonl").exists()

    cue = str(
        arguments.get("query")
        or arguments.get("intent")
        or arguments.get("cue")
        or arguments.get("task")
        or "source-backed continuity"
    ).strip()
    try:
        agent = _agent_continuity_module()
        recall_payload = agent.recall(
            cue,
            cwd=_cwd_arg(arguments),
            clean_source_dir=source_dir,
            registry_dir=_registry_dir_arg(arguments),
            project=str(arguments.get("project") or "AIppocampus"),
            max_routes=1,
        )
    except Exception:
        return {
            "clean_source_available": clean_source_available,
            "recall_tool_available": False,
            "route_probe_status": "recall_probe_failed",
            "route_count": 0,
            "deepen_tool_available": False,
            "source_reopen_success": False,
        }

    deepen_requests = [
        item for item in recall_payload.get("deepen_requests") or [] if isinstance(item, dict)
    ]
    memory_packets = [
        item for item in recall_payload.get("memory_packets") or [] if isinstance(item, dict)
    ]
    route_count = max(len(deepen_requests), len(memory_packets))
    source_reopen_success = _probe_deepen_success(
        agent=agent,
        deepen_requests=deepen_requests,
        arguments=arguments,
        source_dir=source_dir,
    )
    return {
        "clean_source_available": clean_source_available,
        "recall_tool_available": True,
        "route_probe_status": _route_probe_status(
            clean_source_available=clean_source_available,
            route_count=route_count,
        ),
        "route_count": route_count,
        "deepen_tool_available": bool(deepen_requests),
        "source_reopen_success": source_reopen_success,
    }


def _probe_deepen_success(
    *,
    agent: Any,
    deepen_requests: list[dict[str, Any]],
    arguments: dict[str, Any],
    source_dir: Path,
) -> bool:
    if not deepen_requests:
        return False
    handle = deepen_requests[0].get("handle") or deepen_requests[0].get("callable_handle")
    if not handle:
        return False
    try:
        payload = agent.deepen(
            handle,
            cwd=_cwd_arg(arguments),
            clean_source_dir=source_dir,
            registry_dir=_registry_dir_arg(arguments),
            project=str(arguments.get("project") or "AIppocampus"),
            max_matches=1,
        )
    # aippocampus-debt-ok: broad-exception-boundary
    # This is an MCP readiness probe boundary: deepen failures degrade the
    # probe to source_reopen_success=false while the surrounding report still
    # exposes route/deepen availability instead of blocking compact recall.
    except Exception:
        return False
    result = payload.get("result") if isinstance(payload, dict) else None
    metrics = result.get("metrics") if isinstance(result, dict) else None
    if isinstance(metrics, dict) and metrics.get("source_reopen_success") is True:
        return True
    return bool(
        isinstance(result, dict)
        and result.get("evidence_level") == "source_backed"
        and payload.get("status") == "ok"
    )


def _route_probe_status(*, clean_source_available: bool, route_count: int) -> str:
    if route_count:
        return "routes_available"
    if clean_source_available:
        return "source_present_probe_no_routes"
    return "clean_source_missing_probe_no_routes"


def _recall_routes_available(recall_capability: dict[str, Any]) -> bool:
    return bool(
        recall_capability.get("recall_tool_available")
        and recall_capability.get("deepen_tool_available")
        and recall_capability.get("source_reopen_success")
    )


def _payload_blocks_first_recall(payload: dict[str, Any]) -> bool:
    if payload.get("blocks_first_recall") is True:
        return True
    readiness = payload.get("product_readiness")
    if isinstance(readiness, dict) and readiness.get("ordinary_first_recall_usable") is False:
        return True
    return payload.get("ok") is False and payload.get("ordinary_first_recall_usable") is False


def _health_artifacts_missing(payload: dict[str, Any]) -> bool:
    artifact_actions = {"build_clean_source", "build_index", "build_segments"}
    action_ids = {
        str(item.get("id") or "")
        for item in payload.get("recommended_actions") or []
        if isinstance(item, dict)
    }
    maintenance_summary = payload.get("maintenance_summary")
    if isinstance(maintenance_summary, dict):
        action_ids.update(
            str(item)
            for item in maintenance_summary.get("recommended_action_ids") or []
            if str(item)
        )
    foreground = payload.get("foreground_action")
    if isinstance(foreground, dict):
        action_ids.add(str(foreground.get("id") or ""))
    return bool(action_ids & artifact_actions)


def _recall_action() -> dict[str, Any]:
    return {
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


def _deepen_action() -> dict[str, Any]:
    return {
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


def _unavailable_recovery_payload() -> dict[str, Any]:
    recovery_action = {
        "id": "recover_or_continue_without_memory",
        "label": (
            "Check provider/onboarding status, register/sync a thread if this is setup, "
            "or continue without memory."
        ),
        "command": "aippocampus onboard --provider auto --status --json",
        "mutation_risk": "read_only",
        "claim_boundary": "setup_status_not_memory_evidence",
    }
    return {
        "kind": "aippocampus_memory_health_recovery",
        "ok": False,
        "status": "unavailable",
        "error": {
            "code": "health_unavailable",
            "message": "Memory health could not find usable local source artifacts for this scope.",
        },
        **canonical_foreground_action_fields(
            recovery_action,
            safe_next_actions=[
                recovery_action,
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
        ),
        "source_boundary": {
            "no_rollout_found_is_not_a_recall_quality_claim": True,
            "local_paths_serialized": False,
        },
    }


def _degraded_recall_payload(recall_capability: dict[str, Any]) -> dict[str, Any]:
    recall_action = _recall_action()
    deepen_action = _deepen_action()
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
        **canonical_foreground_action_fields(
            recall_action,
            safe_next_actions=[
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
        ),
        "source_boundary": {
            "health_card_is_not_memory_evidence": True,
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
            "raw_source_text_serialized": False,
        },
    }
