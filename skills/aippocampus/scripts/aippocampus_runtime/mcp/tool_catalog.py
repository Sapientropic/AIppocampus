#!/usr/bin/env python3
"""MCP tool catalog schema for AIppocampus."""

from __future__ import annotations

from typing import Any

from conversation_sources import PROVIDER_CHOICES


def tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
    required_any: list[str] | None = None,
) -> dict[str, Any]:
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
    if required_any:
        input_schema["required_any"] = required_any
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    }


TOOLS: list[dict[str, Any]] = [
    tool_schema(
        "agent_recall",
        "Find source-backed continuity routes for the current task; deepen before making claims.",
        {
            "query": {"type": "string"},
            "intent": {"type": "string"},
            "cwd": {"type": "string"},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "macro_state_jsonl": {"type": "string"},
            "project": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "attention_router": {"type": "boolean"},
            "attention_router_mode": {"type": "string", "enum": ["off", "on", "auto"]},
            "semantic": {"type": "string", "enum": ["off", "auto", "on"]},
            "run_semantic_gate": {"type": "boolean"},
            "semantic_gate_mode": {"type": "string", "enum": ["off", "auto", "on"]},
            "semantic_timeout": {"type": "integer", "minimum": 1, "maximum": 60},
            "detail": {"type": "string", "enum": ["compact", "full", "diagnostic", "debug"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["query", "intent"],
    ),
    tool_schema(
        "agent_aippo",
        "Get low-risk working guidance for a task before editing or broad search.",
        {
            "task": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "agent_deepen",
        "Open the selected recall route from agent_recall before quoting or relying on it.",
        {
            "handle": {"type": ["string", "object"]},
            "request_index": {"type": "integer", "minimum": 1, "maximum": 25},
            "last_recall": {"type": "boolean"},
            "last_recall_path": {"type": "string"},
            "cwd": {"type": "string"},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "macro_state_jsonl": {"type": "string"},
            "project": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["handle", "request_index"],
    ),
    tool_schema(
        "agent_explain",
        "Explain why a recall or AIppo route surfaced, without treating it as source evidence.",
        {
            "handle": {"type": ["string", "object"]},
            "macro_state_jsonl": {"type": "string"},
            "project": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["handle"],
    ),
    tool_schema(
        "search_memory",
        "Search clean source for source-backed receipts; reopen/deepen before exact claims.",
        {
            "query": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "metadata_only": {"type": "boolean"},
            "include_source_snippets": {"type": "boolean"},
            "include_snippets": {"type": "boolean"},
            "include_private_paths": {"type": "boolean"},
        },
        ["query"],
    ),
    tool_schema(
        "recall_context",
        "Get a compact route card for a fuzzy continuity cue, then deepen the useful route.",
        {
            "intent": {"type": "string"},
            "query": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "continuity_domains_snapshot": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full", "diagnostic", "debug"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["intent", "query"],
    ),
    tool_schema(
        "recall_deepen",
        "Reopen clean source for a route from recall_context or an ambient navigation card.",
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
        "Explain why recall surfaced, stayed silent, degraded, or needs source reopen.",
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
        "Find the latest assistant closeout for continuing work; prefer clean source when supplied.",
        {
            "cwd": {"type": "string"},
            "rollout": {"type": "string"},
            "clean_source_dir": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "get_turn_context",
        "Open one clean-source turn by turn_id, message_id, or turn_index from a route.",
        {
            "cwd": {"type": "string"},
            "turn_id": {"type": "string"},
            "message_id": {"type": "string"},
            "turn_index": {"type": "integer"},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["turn_id", "message_id", "turn_index"],
    ),
    tool_schema(
        "list_threads",
        "List registered local memory threads as route handles, not source evidence.",
        {
            "registry_dir": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 100},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_identifiers": {"type": "boolean"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "register_thread",
        "Register the current thread after explicit consent so future agents can find it.",
        {
            "cwd": {"type": "string"},
            "registry_dir": {"type": "string"},
            "build_index": {"type": "boolean"},
            "provider": {"type": "string", "enum": list(PROVIDER_CHOICES)},
            "confirm_write": {"type": "boolean"},
            "write": {"type": "boolean"},
            "detail": {"type": "string", "enum": ["compact", "full", "diagnostic", "debug"]},
            "include_private_paths": {"type": "boolean"},
        },
        ["cwd", "provider", "confirm_write"],
    ),
    tool_schema(
        "sync_status",
        "Check local sync readiness without pushing, pulling, or exposing private paths.",
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
        "Check whether recall is usable now and get one stable next action.",
        {
            "cwd": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "list_telepathy_handoffs",
        "List opt-in Telepathy handoff cards without writing coordination state.",
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
