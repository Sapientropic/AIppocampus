"""Shared compact foreground profile for MCP tool results.

Compact MCP output is a foreground control surface, not an operator console.
This module centralizes the deny-by-default boundary so new diagnostics do not
silently leak into recall/deepen/search/health compact cards whenever another
routing subsystem grows a useful but backstage field family.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime import core

COMPACT_DEBUG_FIELD_DENYLIST = frozenset(
    {
        "apw_route_identity",
        "associative_path_fallback",
        "associative_path_policy",
        "callable_selector",
        "carry_next_actions",
        "claim_permission",
        "confidence",
        "diagnostic_detail_command",
        "diagnostic_fields_omitted",
        "feedback_actions",
        "feedback_boundary",
        "feedback_id",
        "operator_detail_command",
        "operator_detail_command_template",
        "operator_detail_requires",
        "operator_detail_template_only",
        "output_boundary",
        "policy_boundary",
        "private_handle_boundary",
        "provider_key_bridge",
        "recall_gate_context",
        "route_choice_posture",
        "runtime_provenance",
        "safe_operator_commands",
        "semantic_gate_diagnostics",
        "source_anchor_gate",
        "target_source_matched",
    }
)

MCP_COMPACT_CARD_SURFACES = frozenset(
    {
        "mcp_agent_recall_compact",
        "mcp_agent_deepen_compact",
        "mcp_agent_explain_compact",
    }
)

MCP_ACTION_KEYS = frozenset(
    {
        "id",
        "tool_name",
        "arguments",
        "arguments_template",
        "mutation_risk",
        "claim_boundary",
        "label",
        "why",
        "command",
        "command_template",
        "followup_arguments_template",
        "requires",
        "template_only",
        "continue_without_command",
    }
)

MCP_ROUTE_KEYS = frozenset(
    {
        "index",
        "label",
        "why_this_route",
        "source_boundary",
        "claim_boundary",
        "action",
    }
)

MCP_CLAIM_BOUNDARY_KEYS = frozenset(
    {
        "can_use_for",
        "must_reopen_for",
        "detail_available",
        "detail_mode",
        "source_summary_is_not_quote",
    }
)


def strip_compact_foreground_debug_fields(value: Any) -> Any:
    """Remove backstage field families from compact foreground payloads."""

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key in COMPACT_DEBUG_FIELD_DENYLIST:
                continue
            projected = strip_compact_foreground_debug_fields(item)
            if projected in (None, ""):
                continue
            cleaned[key] = projected
        return cleaned
    if isinstance(value, list):
        return [strip_compact_foreground_debug_fields(item) for item in value]
    return value


def is_compact_foreground_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    detail = str(payload.get("detail") or "").strip().casefold()
    if detail == "full":
        return False
    surface = str(payload.get("surface") or "").strip().casefold()
    kind = str(payload.get("kind") or "").strip()
    return (
        detail == "compact"
        or surface.endswith("_compact")
        or "_compact" in surface
        or (
            kind
            in {
                "aippocampus_search_result",
                "aippocampus_memory_health_recovery",
                "aippocampus_health_card",
                "aippocampus_foreground_recovery",
            }
            and isinstance(payload.get("foreground_action"), dict)
        )
    )


def compact_foreground_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return core.compact_text(json.dumps(payload, ensure_ascii=False), 280)
    action = payload.get("foreground_action")
    action = action if isinstance(action, dict) else {}
    label = str(action.get("label") or action.get("id") or action.get("action_id") or "").strip()
    why = str(action.get("why") or payload.get("summary") or payload.get("status") or "").strip()
    posture = str(payload.get("source_open_posture") or payload.get("status") or "").strip()
    parts = [part for part in [posture, label, why] if part]
    if not parts:
        parts = [str(payload.get("kind") or payload.get("surface") or "AIppocampus compact result")]
    return core.compact_text(" | ".join(parts), 360)


def _compact_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        return {}
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in action.items()
        if key in MCP_ACTION_KEYS and value not in (None, "")
    }


def _compact_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, value in route.items():
        if key not in MCP_ROUTE_KEYS or value in (None, ""):
            continue
        result[key] = _compact_action(value) if key == "action" else strip_compact_foreground_debug_fields(value)
    return result


def _compact_claim_boundary(boundary: Any) -> dict[str, Any]:
    if not isinstance(boundary, Mapping):
        return {}
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in boundary.items()
        if key in MCP_CLAIM_BOUNDARY_KEYS and value not in (None, "")
    }


def compact_mcp_structured_content(payload: Any) -> Any:
    """Shrink MCP compact structuredContent to the foreground card.

    The CLI compact JSON can remain a richer operator/test artifact. MCP compact
    is different: models ingest structuredContent by default, so keeping route
    counts, cache state, policy matrices, or acceptance breadcrumbs there turns
    the foreground tool into a token-heavy debug console. Full/detail output is
    the escape hatch for that audit material.
    """

    if not isinstance(payload, dict):
        return payload
    surface = str(payload.get("surface") or "").strip()
    if surface not in MCP_COMPACT_CARD_SURFACES:
        return payload
    card: dict[str, Any] = {
        key: payload[key]
        for key in (
            "detail",
            "kind",
            "schema_version",
            "mode",
            "surface",
            "status",
            "ok",
            "source_open_posture",
            "evidence_level",
            "summary",
        )
        if key in payload and payload[key] not in (None, "")
    }
    action = _compact_action(payload.get("foreground_action"))
    if action:
        card["foreground_action"] = action
    follow_up_action = _compact_action(payload.get("follow_up_action"))
    if follow_up_action and follow_up_action != action:
        card["follow_up_action"] = follow_up_action
    routes = [_compact_route(route) for route in payload.get("routes") or []]
    routes = [route for route in routes if route][:2]
    if routes:
        card["routes"] = routes
    snippet = payload.get("primary_source_snippet")
    if isinstance(snippet, Mapping):
        card["primary_source_snippet"] = strip_compact_foreground_debug_fields(dict(snippet))
    boundary = _compact_claim_boundary(payload.get("claim_boundary"))
    if boundary:
        card["claim_boundary"] = boundary
    if "foreground_action_contract" in payload:
        card["foreground_action_contract"] = payload["foreground_action_contract"]
    return strip_compact_foreground_debug_fields(card)


def compact_mcp_tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    """Return an MCP result shape agents can read without parsing a JSON wall."""

    if not is_compact_foreground_payload(payload):
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, indent=2),
                }
            ],
            "isError": is_error,
        }
    compact_payload = compact_mcp_structured_content(
        strip_compact_foreground_debug_fields(payload)
    )
    return {
        "content": [{"type": "text", "text": compact_foreground_summary(compact_payload)}],
        "structuredContent": compact_payload,
        "isError": is_error,
    }


def mcp_tool_result_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """Read a tool result without forcing compact foreground text to be JSON.

    MCP compact text is the user/agent-facing card. Tests and diagnostic
    harnesses that need the machine payload should consume structuredContent
    first, otherwise they pressure compact UX back into becoming a JSON dump.
    """

    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content") or []
    if not isinstance(content, Sequence):
        return {}
    first = content[0] if content else {}
    if not isinstance(first, Mapping):
        return {}
    try:
        payload = json.loads(str(first.get("text") or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
