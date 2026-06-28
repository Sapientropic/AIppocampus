"""Shared compact foreground profile for MCP tool results.

Compact MCP output is a foreground control surface, not an operator console.
This module centralizes the deny-by-default boundary so new diagnostics do not
silently leak into recall/deepen/search/health compact cards whenever another
routing subsystem grows a useful but backstage field family.

aippocampus-stage-map: strip backstage fields first, then project compact
foreground cards; full/detail profiles remain the route for diagnostics.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp.contracts import MCPCompactResponseContract, build_mcp_compact_card

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
        "recall_capability",
        "route_probe_status",
        "route_choice_posture",
        "runtime_provenance",
        "safe_operator_commands",
        "semantic_gate_diagnostics",
        "source_anchor_gate",
        "source_reopen_success",
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
        "last_recall_fallback_command_template",
        "primary_route_relation",
        "requires",
        "route_index",
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
        "actionability",
        "action_priority",
        "primary_action_relation",
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

MCP_SEARCH_SOURCE_BOUNDARY_KEYS = frozenset(
    {
        "authority",
        "source_reopen_required_before_claim",
        "source_backed_claim_allowed",
        "claim_scope",
        "search_miss_is_not_absence_of_memory",
        "demoted_artifact_matches_are_diagnostic",
        "capped_snippets_are_bounded_receipts",
        "source_open_selector_emitted",
        "snippets_are_source_open",
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


def _compact_claim_boundary(boundary: Any) -> dict[str, Any] | str:
    if isinstance(boundary, str):
        return boundary.strip()
    if not isinstance(boundary, Mapping):
        return {}
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in boundary.items()
        if key in MCP_CLAIM_BOUNDARY_KEYS and value not in (None, "")
    }


def _compact_background_recovery_card(card: Any) -> dict[str, Any]:
    if not isinstance(card, Mapping):
        return {}
    best = card.get("best_finding")
    best_map = best if isinstance(best, Mapping) else {}
    best_summary = {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in best_map.items()
        if key
        in {
            "finding_id",
            "finding_title",
            "matched_terms",
            "match_strength",
            "source_ref_count",
            "source_finding_count",
        }
        and value not in (None, "", [], {})
    }
    result = {
        key: strip_compact_foreground_debug_fields(card[key])
        for key in ("kind", "status", "summary", "primary_action", "claim_boundary")
        if key in card and card[key] not in (None, "", [], {})
    }
    if best_summary:
        result["best_finding"] = best_summary
    return result


def _compact_background_safe_action(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions = [
        _compact_action(safe_action)
        for safe_action in payload.get("safe_next_actions") or []
        if isinstance(safe_action, Mapping)
    ]
    return [
        action
        for action in actions
        if action and action.get("id") == "reopen_background_finding_source_route"
    ][:1]


def _compact_error(error: Any) -> dict[str, Any]:
    if not isinstance(error, Mapping):
        return {}
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in error.items()
        if key in {"code", "message", "tool_name", "required_any", "retryable"}
        and value not in (None, "", [], {})
    }


def _compact_source_window_message(message: Any, *, text_key: str = "text_preview") -> dict[str, Any]:
    if not isinstance(message, Mapping):
        return {}
    raw_text = str(message.get("text") or message.get("text_preview") or "").strip()
    result = {
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "line": message.get("line") or message.get("source_line"),
        "role": message.get("role"),
        "phase": message.get("phase"),
        "turn_index": message.get("turn_index"),
        "is_final": message.get("is_final"),
        text_key: core.compact_text(raw_text, 420),
        "text_char_limit": 420,
    }
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in result.items()
        if value not in (None, "", [], {})
    }


def _primary_source_snippet(payload: Mapping[str, Any]) -> dict[str, Any]:
    window = [item for item in payload.get("source_window") or [] if isinstance(item, Mapping)]
    if not window:
        return {}
    target_message_id = str(core.dict_or_empty(payload.get("source_route")).get("message_id") or "")
    selected_index = 0
    if target_message_id:
        for index, message in enumerate(window):
            current_id = str(message.get("message_id") or message.get("id") or "")
            if current_id == target_message_id:
                selected_index = index
                break
    snippet = _compact_source_window_message(window[selected_index], text_key="text")
    if snippet:
        snippet["source_scope"] = "opened_window_primary_message"
        snippet["claim_boundary"] = "exact_wording_inside_this_snippet_only"
        snippet["max_chars"] = 420
    return snippet


def _source_window_preview(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    window = [item for item in payload.get("source_window") or [] if isinstance(item, Mapping)]
    return [
        preview
        for preview in (_compact_source_window_message(item) for item in window[:3])
        if preview
    ]


def _search_hit_label(match: Mapping[str, Any]) -> str:
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    label = str(thread_map.get("title") or match.get("source") or "source hit").strip()
    line = match.get("line") or match.get("source_line")
    role = str(match.get("role") or "").strip()
    suffix = " ".join(part for part in (f"line {line}" if line else "", role) if part)
    return core.compact_text(f"{label} {suffix}".strip(), 120)


def _compact_search_hit(match: Any, *, include_source_snippets: bool) -> dict[str, Any]:
    if not isinstance(match, Mapping):
        return {}
    index = match.get("hit_index") or match.get("match_index") or match.get("request_index")
    hit: dict[str, Any] = {
        key: value
        for key, value in {
            "index": index,
            "request_index": match.get("request_index"),
            "label": _search_hit_label(match),
            "source": match.get("source"),
            "role": match.get("role"),
            "phase": match.get("phase"),
            "snippet_omitted": True,
        }.items()
        if value not in (None, "", [], {})
    }
    duplicate_count = int(match.get("duplicate_count") or 0)
    source_count = int(match.get("source_count") or 0)
    if duplicate_count > 0:
        hit["duplicate_count"] = duplicate_count
    if source_count > 1:
        hit["source_count"] = source_count
    if include_source_snippets:
        snippet = str(match.get("snippet") or "").strip()
        if snippet and not match.get("search_noise"):
            hit["snippet_preview"] = core.compact_text(snippet, 180)
            hit["snippet_omitted"] = False
    return hit


def _compact_source_boundary(boundary: Any) -> dict[str, Any]:
    if not isinstance(boundary, Mapping):
        return {}
    return {
        key: strip_compact_foreground_debug_fields(value)
        for key, value in boundary.items()
        if key in MCP_SEARCH_SOURCE_BOUNDARY_KEYS and value not in (None, "")
    }


def compact_search_memory_payload(
    payload: dict[str, Any],
    *,
    include_source_snippets: bool = False,
) -> MCPCompactResponseContract:
    """Project MCP search results as an action card, not a source table.

    Search often has useful receipts, but MCP compact structuredContent is
    foreground context that agents ingest by default. Keep the full match list,
    snippets, duplicate refs, and diagnostic counters in `detail=full`; compact
    gets only the state, first open action, and a tiny hit sketch so it can act
    without spending a turn parsing a source-search dump.
    """

    if str(payload.get("kind") or "") in {
        "aippocampus_current_thread_source_window",
        "aippocampus_registry_source_window",
        "aippocampus_last_recall_source_window",
    }:
        source_boundary = _compact_source_boundary(payload.get("source_boundary"))
        metrics = payload.get("metrics")
        metrics_map = metrics if isinstance(metrics, Mapping) else {}
        source_open_card = {
            key: payload[key]
            for key in ("detail", "kind", "mcp_search_scope", "ok", "status", "surface")
            if key in payload and payload[key] not in (None, "")
        }
        source_open_card["summary"] = (
            "Source window opened; use the bounded snippet or preview only within scope."
            if payload.get("ok")
            else "Source window could not be opened; rerun search for a fresh source route."
        )
        if source_boundary:
            source_open_card["source_boundary"] = source_boundary
        window_count = metrics_map.get("window_message_count")
        if isinstance(window_count, int):
            source_open_card["source_window_summary"] = {"message_count": window_count}
        primary_snippet = _primary_source_snippet(payload)
        if primary_snippet:
            source_open_card["primary_source_snippet"] = primary_snippet
        preview = _source_window_preview(payload)
        if preview:
            source_open_card["source_window_preview"] = preview
        action = _compact_action(payload.get("foreground_action"))
        if action:
            source_open_card["foreground_action"] = action
        return build_mcp_compact_card(
            strip_compact_foreground_debug_fields(source_open_card),
            surface="mcp_search_memory_compact",
        )

    matches = [item for item in payload.get("matches") or [] if isinstance(item, Mapping)]
    match_count = payload.get("match_count")
    count = len(matches)
    if isinstance(match_count, (int, str)):
        try:
            count = int(match_count)
        except ValueError:
            count = len(matches)
    card: dict[str, Any] = {
        key: payload[key]
        for key in (
            "detail",
            "kind",
            "schema_version",
            "mcp_search_scope",
            "ok",
            "query_text",
            "search_scope",
            "status",
            "surface",
            "useful_target_hit",
        )
        if key in payload and payload[key] not in (None, "")
    }
    card["match_count"] = count
    if count:
        card["summary"] = f"{count} source hit{'s' if count != 1 else ''}; open source before claiming."
    else:
        card["summary"] = "No source hit; refine the cue or broaden scope."
    action = _compact_action(payload.get("foreground_action"))
    if action:
        card["foreground_action"] = action
    if not action:
        safe_next_actions = [
            _compact_action(action)
            for action in payload.get("safe_next_actions") or []
            if isinstance(action, Mapping)
        ]
        safe_next_actions = [action for action in safe_next_actions if action][:1]
        if safe_next_actions:
            card["safe_next_actions"] = safe_next_actions
    source_boundary = _compact_source_boundary(payload.get("source_boundary"))
    if source_boundary:
        card["source_boundary"] = source_boundary
    hits = [
        _compact_search_hit(match, include_source_snippets=include_source_snippets)
        for match in matches[:2]
    ]
    hits = [hit for hit in hits if hit]
    if hits:
        card["source_hits"] = hits
    return build_mcp_compact_card(
        strip_compact_foreground_debug_fields(card),
        surface="mcp_search_memory_compact",
    )


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
            "decision",
            "route_id",
            "route_reason",
            "source_open_posture",
            "source_scope",
            "evidence_level",
            "summary",
            "use_this_for",
            "reopen_more_if",
            "surface_class",
            "required_any",
        )
        if key in payload and payload[key] not in (None, "")
    }
    error = _compact_error(payload.get("error"))
    if error:
        card["error"] = error
    action = _compact_action(payload.get("foreground_action"))
    if action:
        card["foreground_action"] = action
    follow_up_action = _compact_action(payload.get("follow_up_action"))
    if follow_up_action and follow_up_action != action:
        card["follow_up_action"] = follow_up_action
    recovery_card = card.get("status") != "ok" or bool(error) or bool(card.get("surface_class"))
    if recovery_card:
        safe_next_actions = [
            _compact_action(safe_action)
            for safe_action in payload.get("safe_next_actions") or []
            if isinstance(safe_action, Mapping)
        ]
        safe_next_actions = [
            safe_action
            for safe_action in safe_next_actions
            if safe_action and safe_action != action and safe_action != follow_up_action
        ][:2]
        if safe_next_actions:
            card["safe_next_actions"] = safe_next_actions
    else:
        background_safe_actions = _compact_background_safe_action(payload)
        if background_safe_actions:
            card["safe_next_actions"] = background_safe_actions
    routes = [_compact_route(route) for route in payload.get("routes") or []]
    routes = [route for route in routes if route][:2]
    if routes:
        card["routes"] = routes
    background_recovery = _compact_background_recovery_card(payload.get("background_recovery_card"))
    if background_recovery:
        card["background_recovery_card"] = background_recovery
    snippet = payload.get("primary_source_snippet")
    if isinstance(snippet, Mapping):
        card["primary_source_snippet"] = strip_compact_foreground_debug_fields(dict(snippet))
    boundary = _compact_claim_boundary(payload.get("claim_boundary"))
    if boundary:
        card["claim_boundary"] = boundary
    if "foreground_action_contract" in payload:
        card["foreground_action_contract"] = payload["foreground_action_contract"]
    compact_card = build_mcp_compact_card(
        strip_compact_foreground_debug_fields(card),
        surface=surface or "mcp_compact",
    )
    if surface == "mcp_agent_recall_compact":
        foreground_card: dict[str, Any] = dict(compact_card)
        foreground_card.pop("surface", None)
        return foreground_card
    return compact_card


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
