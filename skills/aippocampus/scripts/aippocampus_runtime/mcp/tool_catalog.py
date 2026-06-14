#!/usr/bin/env python3
"""MCP tool catalog schema for AIppocampus."""

from __future__ import annotations

from typing import Any

from conversation_sources import PROVIDER_CHOICES


def tool_schema(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


TOOLS: list[dict[str, Any]] = [
    tool_schema(
        "search_memory",
        "Search clean-source AIppocampus memory for the current or supplied workspace.",
        {
            "query": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["query"],
    ),
    tool_schema(
        "recall_context",
        "Return a compact progressive-recall navigation packet for a fuzzy cue.",
        {
            "intent": {"type": "string"},
            "query": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "continuity_domains_snapshot": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "recall_deepen",
        "Deepen a recall_context handle or ambient navigation seed by reopening clean source.",
        {
            "handle": {"type": ["string", "object"]},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "lock_path": {"type": "string"},
            "continuity_domains_snapshot": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["handle"],
    ),
    tool_schema(
        "recall_diagnostic",
        "Explain why a recall route surfaced, stayed silent, degraded, or needs source reopen.",
        {
            "cue": {"type": "string"},
            "intent": {"type": "string"},
            "query": {"type": "string"},
            "mode": {"type": "string", "enum": ["why-recall", "why-not-recall"]},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "handle": {"type": ["string", "object"]},
            "thread_id": {"type": "string"},
            "topic_epoch": {"type": "string"},
            "lock_id": {"type": "string"},
            "lock_path": {"type": "string"},
            "cache_path": {"type": "string"},
            "run_semantic_gate": {"type": "boolean"},
            "semantic_gate_mode": {"type": "string", "enum": ["off", "auto", "on"]},
            "semantic_timeout": {"type": "integer", "minimum": 1, "maximum": 60},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "latest_reply",
        "Return the latest assistant final answer for a workspace rollout.",
        {
            "cwd": {"type": "string"},
            "rollout": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "get_turn_context",
        "Return clean-source messages for a turn, message id, or turn index.",
        {
            "cwd": {"type": "string"},
            "turn_id": {"type": "string"},
            "message_id": {"type": "string"},
            "turn_index": {"type": "integer"},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "list_threads",
        "List machine-wide registered AIppocampus threads.",
        {
            "registry_dir": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 100},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "register_thread",
        "Explicitly register the current workspace thread in the machine-wide registry.",
        {
            "cwd": {"type": "string"},
            "registry_dir": {"type": "string"},
            "build_index": {"type": "boolean"},
            "provider": {"type": "string", "enum": list(PROVIDER_CHOICES)},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "sync_status",
        "Report current local bundle/sync capability without pushing or pulling data.",
        {
            "cwd": {"type": "string"},
            "sync_dir": {"type": "string"},
            "object_store_url": {"type": "string"},
            "object_prefix": {"type": "string"},
            "token_env": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "memory_health",
        "Run the local AIppocampus health check for a workspace.",
        {
            "cwd": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "list_telepathy_handoffs",
        "List opt-in local Telepathy handoff cards without writing coordination state.",
        {
            "cwd": {"type": "string"},
            "store_path": {"type": "string"},
            "scope": {"type": "string"},
            "status": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 100},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "deepen_telepathy_handoff",
        "Return one Telepathy handoff card with sanitized source selectors for reopen.",
        {
            "card_id": {"type": "string"},
            "cwd": {"type": "string"},
            "store_path": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["card_id"],
    ),
]
