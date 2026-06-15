#!/usr/bin/env python3
"""Public-safe MCP payload projections."""

from __future__ import annotations

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


def compact_thread(item: dict[str, Any]) -> dict[str, Any]:
    paths = item.get("paths") if isinstance(item.get("paths"), dict) else {}
    pairs = {
        "thread_key": item.get("thread_key"),
        "title": core.compact_text(
            str(item.get("title") or item.get("workspace_name") or item.get("thread_key") or ""),
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
    result = {
        "status": status,
        "thread_handle": entry.get("thread_key") or payload.get("thread_key"),
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
