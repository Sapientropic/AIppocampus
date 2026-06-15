#!/usr/bin/env python3
"""Public-safe MCP payload projections."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def public_payload(arguments: dict[str, Any], payload: Any) -> Any:
    if arguments.get("include_private_paths"):
        return payload
    return redact_sensitive_values(redact_private_paths(payload))


def detail_arg(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("detail") or "").strip().casefold()
    if value in {"full", "diagnostic", "debug"} or arguments.get("diagnostic"):
        return "full"
    return "compact"


def compact_message(item: dict[str, Any]) -> dict[str, Any]:
    preview = core.compact_text(str(item.get("text") or ""), 360)
    pairs = {
        "message_id": item.get("message_id") or item.get("id"),
        "turn_id": item.get("turn_id"),
        "turn_index": item.get("turn_index"),
        "role": item.get("role"),
        "phase": item.get("phase"),
        "is_final": item.get("is_final"),
        "timestamp": item.get("timestamp"),
        "text_preview": preview,
    }
    return {key: value for key, value in pairs.items() if value not in (None, "")}


def compact_thread(
    item: dict[str, Any],
    *,
    include_private_identifiers: bool = False,
) -> dict[str, Any]:
    paths = item.get("paths") if isinstance(item.get("paths"), dict) else {}
    raw_thread_key = str(item.get("thread_key") or "").strip()
    thread_handle = (
        raw_thread_key
        if include_private_identifiers
        else core.stable_text_fingerprint(
            raw_thread_key or str(item.get("title") or item.get("workspace_name") or "unknown"),
            namespace="mcp-thread-handle",
            length=12,
            prefix="thread",
        )
    )
    pairs = {
        "thread_handle": thread_handle,
        "title": core.compact_text(
            str(
                item.get("title")
                or item.get("workspace_name")
                or ("private thread" if raw_thread_key else "")
            ),
            120,
        ),
        "project_label": item.get("project_label"),
        "workspace_name": item.get("workspace_name"),
        "updated_at": item.get("updated_at"),
        "message_count": item.get("message_count"),
        "anchor_count": item.get("anchor_count"),
        "scope_labels": item.get("scope_labels") if isinstance(item.get("scope_labels"), list) else None,
        "has_clean_source": bool(paths.get("clean_source_messages_jsonl")),
    }
    if include_private_identifiers and raw_thread_key:
        pairs["thread_key"] = raw_thread_key
    elif raw_thread_key:
        pairs["thread_key_redacted"] = True
    return {key: value for key, value in pairs.items() if value not in (None, "", [])}


def compact_action(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        pairs = {
            "id": item.get("id") or item.get("name") or item.get("action"),
            "severity": item.get("severity") or item.get("level"),
            "reason": core.compact_text(str(item.get("reason") or item.get("message") or ""), 220),
            "command": item.get("command"),
            "scope": item.get("scope"),
            "retryable": item.get("retryable"),
        }
        return {key: value for key, value in pairs.items() if value not in (None, "", [])}
    text = core.compact_text(str(item or ""), 220)
    return {"id": "recommended_action", "reason": text} if text else {}


def compact_health_payload(payload: dict[str, Any]) -> dict[str, Any]:
    recommended = [
        action
        for item in payload.get("recommended_actions") or []
        if (action := compact_action(item))
    ][:3]
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    return {
        "detail": "compact",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status") or ("ok" if payload.get("ok") else "attention_needed"),
        "cwd": payload.get("cwd"),
        "recommended_actions": recommended,
        "check_count": len(checks),
        "agent_next_action": (
            recommended[0]
            if recommended
            else {
                "id": "no_action",
                "reason": "Run memory_health with detail=full only when diagnosing setup.",
            }
        ),
    }


def compact_register_thread_payload(payload: dict[str, Any]) -> dict[str, Any]:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    paths = entry.get("paths") if isinstance(entry.get("paths"), dict) else {}
    status = payload.get("status") or "registered"
    raw_thread_key = str(entry.get("thread_key") or payload.get("thread_key") or "").strip()
    thread_handle = core.stable_text_fingerprint(
        raw_thread_key or str(entry.get("title") or entry.get("workspace_name") or "unknown"),
        namespace="mcp-thread-handle",
        length=12,
        prefix="thread",
    )
    result = {
        "detail": "compact",
        "status": status,
        "thread_handle": thread_handle,
        "thread_key_redacted": bool(raw_thread_key),
        "title": core.compact_text(
            str(entry.get("title") or entry.get("workspace_name") or entry.get("thread_key") or ""),
            160,
        ),
        "project_label": entry.get("project_label"),
        "message_count": entry.get("message_count"),
        "has_clean_source": bool(paths.get("clean_source_messages_jsonl") or paths.get("clean_source_dir")),
        "index_built": bool(payload.get("index_report") or payload.get("index_built")),
        "agent_next_action": (
            "Use recall_context or search_memory for task-specific routes; request diagnostic output only for local audit."
        ),
    }
    if not entry and "status" in payload:
        result["status"] = payload["status"]
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _without_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _without_empty(item)) not in (None, "", [])
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _without_empty(item)) not in (None, "", [])]
    return value


def _handle_digest(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _canonical_agent_action(card: Any) -> dict[str, Any]:
    card_map = card if isinstance(card, dict) else {}
    action = card_map.get("canonical_action") if isinstance(card_map.get("canonical_action"), dict) else {}
    if action:
        return _without_empty(action)
    return {
        "action_id": "continue_normally",
        "arguments": {},
        "claim_boundary": "no_route_claim",
    }


def compact_agent_recall_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project agent_recall into one foreground action plus compact route receipts."""

    memory_packets = [
        packet for packet in payload.get("memory_packets") or [] if isinstance(packet, dict)
    ]
    route_receipts: list[dict[str, Any]] = []
    for index, packet in enumerate(memory_packets[:3], start=1):
        route_receipts.append(
            _without_empty(
                {
                    "route_index": index,
                    "route_id": packet.get("route_id"),
                    "route_label": core.compact_text(
                        str(
                            packet.get("route_topic")
                            or packet.get("route_label")
                            or packet.get("display_hint")
                            or "memory route"
                        ),
                        120,
                    ),
                    "route_family": packet.get("route_kind") or packet.get("output_mode"),
                    "claim_permission": packet.get("claim_permission"),
                    "next_action_boundary": "reopen_required_before_claim",
                }
            )
        )
    semantic = payload.get("semantic_gate_diagnostics")
    semantic_compact = None
    if isinstance(semantic, dict):
        semantic_compact = _without_empty(
            {
                "requested": semantic.get("requested"),
                "mode": semantic.get("mode"),
                "overall_recall_diagnostic": semantic.get("overall_recall_diagnostic"),
                "semantic_sidecar": semantic.get("semantic_sidecar"),
                "agent_next_action": semantic.get("agent_next_action"),
                "boundary": semantic.get("boundary"),
            }
        )
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "mode": payload.get("mode"),
        "surface": "mcp_agent_recall_compact",
        "status": payload.get("status"),
        "opt_in_required": payload.get("opt_in_required"),
        "foreground_action": _canonical_agent_action(payload.get("foreground_action_card")),
        "routes": route_receipts,
        "route_count": len(memory_packets),
        "metrics": _without_empty(
            {
                "requested_max_routes": (payload.get("metrics") or {}).get("requested_max_routes"),
                "effective_max_routes": (payload.get("metrics") or {}).get("effective_max_routes"),
                "memory_packet_count": (payload.get("metrics") or {}).get("memory_packet_count"),
                "deepen_request_count": (payload.get("metrics") or {}).get("deepen_request_count"),
            }
        ),
        "audit_available": bool(payload.get("audit_available")),
        "semantic_gate_diagnostics": semantic_compact,
        "provider_key_bridge": payload.get("provider_key_bridge"),
        "policy_boundary": payload.get("policy_boundary"),
        "output_boundary": "compact_foreground_no_local_private_handles",
        "agent_next_action": "Use foreground_action first; request detail=full only for local diagnostics.",
    }
    return _without_empty(result)


def _recall_context_foreground_action(route: dict[str, Any], index: int) -> dict[str, Any]:
    reopen = route.get("source_reopen_path") if isinstance(route.get("source_reopen_path"), dict) else {}
    arguments = reopen.get("arguments") if isinstance(reopen.get("arguments"), dict) else {}
    if arguments:
        return {
            "action_id": "recall_deepen_selected_route",
            "tool_name": "recall_deepen",
            "arguments": dict(arguments),
            "claim_boundary": "source_reopen_required_before_strong_claim",
        }
    return {
        "action_id": "recall_deepen_requires_full_detail",
        "tool_name": "recall_deepen",
        "arguments": {"request_index": index, "detail": "full"},
        "claim_boundary": "source_reopen_required_before_strong_claim",
    }


def compact_recall_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    routes = [route for route in payload.get("routes") or [] if isinstance(route, dict)]
    compact_routes: list[dict[str, Any]] = []
    for index, route in enumerate(routes[:5], start=1):
        compact_routes.append(
            _without_empty(
                {
                    "route_index": index,
                    "route_id": route.get("route_id"),
                    "kind": route.get("kind"),
                    "route_label": core.compact_text(
                        str(route.get("route_label") or route.get("title") or "memory route"),
                        120,
                    ),
                    "summary": core.compact_text(str(route.get("summary") or ""), 180),
                    "evidence_level": route.get("evidence_level"),
                    "support_level": route.get("support_level"),
                    "source_ref_count": len(
                        [ref for ref in route.get("source_refs") or [] if isinstance(ref, dict)]
                    ),
                    "handle_sha256_12": _handle_digest(route.get("handle")),
                    "foreground_action": _recall_context_foreground_action(route, index),
                }
            )
        )
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "support_level": payload.get("support_level"),
        "status": payload.get("status"),
        "routes": compact_routes,
        "route_count": len(routes),
        "suggested_next": "follow_route_foreground_action" if routes else payload.get("suggested_next"),
        "continuity_route_status": payload.get("continuity_route_status"),
        "source_boundary": payload.get("source_boundary"),
        "metrics": {
            "funnel_stage": (payload.get("metrics") or {}).get("funnel_stage"),
            "route_count": len(routes),
        },
        "output_boundary": "compact_foreground_no_local_private_handles",
        "agent_next_action": (
            "Use routes[].foreground_action; request detail=full only for opaque handle diagnostics."
        ),
        "warnings": payload.get("warnings"),
    }
    return _without_empty(result)
