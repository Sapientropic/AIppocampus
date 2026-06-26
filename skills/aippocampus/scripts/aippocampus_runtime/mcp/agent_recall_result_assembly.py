"""Final compact result assembly for agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    command_value_needs_input,
    shell_quote,
)
from aippocampus_runtime.mcp import agent_recall_result_projection as result_projection
from aippocampus_runtime.mcp import agent_recall_route_projection as route_projection
from aippocampus_runtime.mcp.compact_profile import strip_compact_foreground_debug_fields

_RECALL_DETAIL_COMMAND_TEMPLATE = 'aippocampus agent recall "{cue}" --json --detail full'


def assemble_compact_recall_payload(
    payload: Mapping[str, Any],
    context: Any,
    *,
    route_projection_result: route_projection.RouteReceiptProjection,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    miss_recovery_card: dict[str, Any] | None,
    weak_route_recovery_card: dict[str, Any] | None,
    apw_recovery: dict[str, Any] | None,
    repo_familiarity_fallback: dict[str, Any] | None,
    discussion_atlas_pointer: Any,
    exact_wording_source_search_primary: bool,
) -> dict[str, Any]:
    route_receipts = route_projection_result.route_receipts
    duplicate_omission_rows = result_projection.sorted_duplicate_label_omissions(
        route_projection_result.duplicate_label_omissions
    )
    hidden_route_count_fields = result_projection.hidden_route_count_fields(
        route_receipts=route_receipts,
        memory_packets=context.memory_packets,
        labels_low_specificity=context.labels_low_specificity,
    )
    if context.labels_low_specificity and context.memory_packets:
        weak_route_recovery_card = result_projection.low_specificity_weak_route_recovery_card(
            weak_route_recovery_card=weak_route_recovery_card,
            safe_next_actions=safe_next_actions,
            foreground_action=foreground_action,
            memory_packets=context.memory_packets,
            displayed_route_count=int(hidden_route_count_fields.get("displayed_route_count") or 0),
        )
    detail_fields = _recall_detail_command_fields(context.recovery_cue)
    detail_command = str(detail_fields.get("operator_detail_command") or "")
    detail_command_template = str(detail_fields.get("operator_detail_command_template") or "")
    can_use_for = ["next_action_choice"]
    if not context.labels_low_specificity and not exact_wording_source_search_primary:
        can_use_for.append("route_selection")
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "mode": payload.get("mode"),
        "surface": "mcp_agent_recall_compact",
        "status": context.status,
        "apw_recovery_state": apw_recovery.get("state") if isinstance(apw_recovery, dict) else None,
        "last_recall_cache_available": context.cache_available,
        "recall_selector_available": bool(context.recall_selector),
        "recall_selector_id": context.recall_selector or None,
        "foreground_action": foreground_action,
        "miss_recovery_card": miss_recovery_card,
        "weak_route_recovery_card": weak_route_recovery_card,
        "routes": route_receipts,
        "route_count": len(context.memory_packets),
        **hidden_route_count_fields,
        "hidden_low_confidence_route_count": (
            route_projection_result.suppressed_low_confidence_route_count or None
        ),
        "omitted_duplicate_route_label_count": sum(
            int(row["omitted_count"]) for row in duplicate_omission_rows
        )
        or None,
        "route_label_omissions": {"duplicate_label_count": len(duplicate_omission_rows)}
        if duplicate_omission_rows
        else None,
        "repo_familiarity_fallback": repo_familiarity_fallback,
        "discussion_atlas_pointer": discussion_atlas_pointer,
        "claim_boundary": _compact_claim_boundary(
            can_use_for=can_use_for,
            must_reopen_for=["source_backed_claims", "exact_wording", "sensitive_or_stale_facts"],
            detail_command=detail_command or None,
            detail_command_template=detail_command_template or None,
        ),
    }
    result.update(
        canonical_foreground_action_fields(
            foreground_action,
            safe_next_actions=safe_next_actions,
        )
    )
    return strip_compact_foreground_debug_fields(core.strip_empty(result))


def _compact_claim_boundary(
    *,
    can_use_for: list[str],
    must_reopen_for: list[str],
    detail_command: str | None = None,
    detail_command_template: str | None = None,
) -> dict[str, Any]:
    boundary: dict[str, Any] = {
        "can_use_for": can_use_for,
        "must_reopen_for": must_reopen_for,
    }
    if detail_command:
        boundary["detail_available"] = True
        boundary["detail_mode"] = "full"
    elif detail_command_template:
        boundary["detail_available"] = True
        boundary["detail_mode"] = "full"
        boundary["detail_requires"] = ["cue"]
    return boundary


def _recall_detail_command_fields(cue: str) -> dict[str, Any]:
    if cue and not command_value_needs_input(cue):
        return {
            "operator_detail_command": (
                f"aippocampus agent recall {shell_quote(cue)} --json --detail full"
            )
        }
    return {
        "operator_detail_command_template": _RECALL_DETAIL_COMMAND_TEMPLATE,
        "operator_detail_requires": ["cue"],
        "operator_detail_template_only": True,
    }
