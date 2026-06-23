"""Shared compact foreground profile for MCP tool results.

Compact MCP output is a foreground control surface, not an operator console.
This module centralizes the deny-by-default boundary so new diagnostics do not
silently leak into recall/deepen/search/health compact cards whenever another
routing subsystem grows a useful but backstage field family.
"""

from __future__ import annotations

import json
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
    compact_payload = strip_compact_foreground_debug_fields(payload)
    return {
        "content": [{"type": "text", "text": compact_foreground_summary(compact_payload)}],
        "structuredContent": compact_payload,
        "isError": is_error,
    }
