"""Final compact result assembly for agent recall projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    normalize_foreground_action,
)
from aippocampus_runtime.mcp import agent_recall_result_projection as result_projection
from aippocampus_runtime.mcp import agent_recall_route_projection as route_projection
from aippocampus_runtime.mcp.compact_profile import strip_compact_foreground_debug_fields
from aippocampus_runtime.mcp.contracts import (
    MCPCompactResponseContract,
    build_mcp_compact_card,
    without_internal_surface,
)

# Recall compact is an action card, not a foreground protocol dump. Keep only
# fields an agent can execute or use to choose the next route; full/detail owns
# selectors inventories, source-proof cards, and operator diagnostics.
_RECALL_COMPACT_ACTION_KEYS = frozenset(
    {
        "id",
        "label",
        "tool_name",
        "arguments",
        "command",
        "command_template",
        "requires",
        "template_only",
        "mutation_risk",
        "claim_boundary",
        "why",
        "continue_without_command",
    }
)


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
    background_recovery: dict[str, Any] | None,
    exact_wording_source_search_primary: bool,
) -> MCPCompactResponseContract:
    route_receipts = route_projection_result.route_receipts
    if context.labels_low_specificity and context.memory_packets:
        weak_route_recovery_card = result_projection.low_specificity_route_guidance_card(
            base_card=weak_route_recovery_card,
            action_options=safe_next_actions,
            foreground_action=foreground_action,
        )
    can_use_for = ["next_action_choice"]
    if not context.labels_low_specificity and not exact_wording_source_search_primary:
        can_use_for.append("route_selection")
    apw_primary = _action_id(foreground_action) == "deepen_associative_path_fallback"
    if apw_primary:
        miss_recovery_card = None
    action_fields = _compact_recall_action_fields(
        foreground_action,
        safe_next_actions=[] if apw_primary else safe_next_actions,
    )
    result = {
        "detail": "compact",
        "status": "ok" if apw_primary and context.status == "no_routes" else context.status,
        "foreground_action": foreground_action,
        "miss_recovery_card": miss_recovery_card,
        "background_recovery_card": background_recovery,
        "routes": route_receipts,
        "repo_familiarity_fallback": repo_familiarity_fallback,
        "claim_boundary": _compact_claim_boundary(can_use_for=can_use_for),
    }
    result.update(action_fields)
    compact_card = build_mcp_compact_card(
        strip_compact_foreground_debug_fields(core.strip_empty(result)),
        surface="mcp_agent_recall_compact",
    )
    # `surface` is an internal routing hint. Recall compact is the flagship
    # foreground card and is consumed directly by CLI, MCP, and public JSON
    # callers; exposing the protocol label makes agents reconcile meta shape
    # instead of simply following recall -> deepen. Recovery/error cards may
    # still carry a public `surface_class`, but recall cards stay action sized.
    return without_internal_surface(compact_card)


def _action_id(action: Mapping[str, Any]) -> str:
    return str(action.get("id") or action.get("action_id") or "")


def _compact_recall_action_fields(
    foreground_action: Mapping[str, object],
    *,
    safe_next_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    action_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=safe_next_actions,
    )
    raw_primary = action_fields.get("foreground_action")
    primary_map = raw_primary if isinstance(raw_primary, Mapping) else {}
    nested_secondary = primary_map.get("secondary_action")
    raw_safe_actions = []
    if isinstance(nested_secondary, Mapping):
        raw_safe_actions.append(nested_secondary)
    safe_action_rows = action_fields.get("safe_next_actions")
    if isinstance(safe_action_rows, list):
        raw_safe_actions.extend(item for item in safe_action_rows if isinstance(item, Mapping))
    primary = _compact_recall_action(raw_primary)
    safe_actions = [
        action
        for action in (
            _compact_recall_action(item)
            for item in raw_safe_actions
        )
        if action and action != primary
    ]
    result: dict[str, Any] = {"foreground_action": primary}
    if safe_actions:
        result["safe_next_actions"] = safe_actions
    return result


def _compact_recall_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        return {}
    normalized = normalize_foreground_action(action)
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in normalized.items()
        if key in _RECALL_COMPACT_ACTION_KEYS and value not in (None, "", [], {})
    }


def _compact_claim_boundary(*, can_use_for: list[str]) -> str:
    if "route_selection" in can_use_for:
        return "route_selection_ok_after_source_reopen"
    return "next_action_only_reopen_before_claims"
