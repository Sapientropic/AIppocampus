#!/usr/bin/env python3
"""MCP tool catalog schema for AIppocampus."""

from __future__ import annotations

from typing import Any

from conversation_sources import PROVIDER_CHOICES

PARAMETER_TIER_KEYS = ("required", "common", "advanced", "operator_internal")

OPERATOR_INTERNAL_PARAMETER_POLICY = {
    "owner": "mcp_detail_and_compat_surface",
    "removal_criteria": (
        "Keep for detail/full diagnostics, legacy clients, and explicit operator "
        "routing only; remove or demote when supported MCP/CLI hosts no longer "
        "need that compatibility surface."
    ),
}

LEGACY_RECALL_TOOL_POLICY = {
    "owner": "mcp_detail_and_compat_surface",
    "replacement": "agent_recall -> agent_deepen",
    "default_exposure": "full_schema_and_explicit_legacy_tool_calls_only",
    "removal_or_wrapper_condition": (
        "Keep callable for existing recall_context/recall_deepen clients; do not "
        "surface in compact/default foreground guidance. Remove or wrap once "
        "supported MCP hosts consume agent_recall selectors directly."
    ),
}


def tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
    required_any: list[str] | None = None,
    parameter_tiers: dict[str, list[str]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
    if required_any:
        # `required_any` is an AIppocampus readability extension. Mirror it into
        # standard JSON Schema so strict MCP clients do not treat all alternates
        # as optional and discover the error only after a tool call.
        input_schema["anyOf"] = [{"required": [name]} for name in required_any]
        input_schema["required_any"] = required_any
    tool: dict[str, Any] = {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    }
    aippocampus_metadata: dict[str, Any] = dict(metadata or {})
    if parameter_tiers is not None:
        tiers = _normalize_parameter_tiers(name, properties, parameter_tiers)
        input_schema["x-aippocampus-parameter-tiers"] = tiers
        aippocampus_metadata["parameter_tiers"] = tiers
        if tiers["operator_internal"]:
            # Internal/path parameters remain callable for explicit detail/full
            # and compatibility flows, but foreground guidance must not present
            # them as ordinary knobs for a recall agent to fill.
            aippocampus_metadata["operator_internal_parameter_policy"] = (
                OPERATOR_INTERNAL_PARAMETER_POLICY
            )
    if aippocampus_metadata:
        tool["metadata"] = {"aippocampus": aippocampus_metadata}
    return tool


def _normalize_parameter_tiers(
    tool_name: str,
    properties: dict[str, Any],
    parameter_tiers: dict[str, list[str]],
) -> dict[str, list[str]]:
    tiers = {key: list(parameter_tiers.get(key, [])) for key in PARAMETER_TIER_KEYS}
    classified: list[str] = [name for values in tiers.values() for name in values]
    duplicate = sorted({name for name in classified if classified.count(name) > 1})
    if duplicate:
        raise ValueError(f"{tool_name} parameter tier duplicates: {duplicate}")
    missing = sorted(set(properties) - set(classified))
    extra = sorted(set(classified) - set(properties))
    if missing or extra:
        raise ValueError(
            f"{tool_name} parameter tier mismatch: missing={missing} extra={extra}"
        )
    return tiers


TOOLS: list[dict[str, Any]] = [
    tool_schema(
        "agent_recall",
        "Find source-backed continuity routes for the current task. When: prefer over recall_context for semantic, attention-router, macro-aware, or agent-native follow-up recall; use search_memory for exact wording. After: call agent_deepen on the selected route before claims.",
        {
            "cue": {"type": "string"},
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
            "include_associative_fallback": {"type": "boolean"},
            "apw_fallback": {"type": "boolean"},
            "apw_sidecar_dir": {"type": "string"},
            "apw_semantic_bridge_path": {"type": "string"},
            "apw_navigation_path": {"type": "string"},
            "apw_active_lock_path": {"type": "string"},
            "apw_feedback_path": {"type": "string"},
            "last_recall_path": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["query", "intent", "cue"],
        parameter_tiers={
            "required": ["query", "intent", "cue"],
            "common": ["cwd", "max", "detail"],
            "advanced": [
                "project",
                "attention_router",
                "attention_router_mode",
                "semantic",
                "run_semantic_gate",
                "semantic_gate_mode",
                "semantic_timeout",
                "include_associative_fallback",
            ],
            "operator_internal": [
                "clean_source_dir",
                "registry_dir",
                "macro_state_jsonl",
                "apw_fallback",
                "apw_sidecar_dir",
                "apw_semantic_bridge_path",
                "apw_navigation_path",
                "apw_active_lock_path",
                "apw_feedback_path",
                "last_recall_path",
                "include_private_paths",
            ],
        },
        metadata={
            "workflow": "recall_then_deepen",
            "posture": "navigation_only",
            "claim_boundary": "no_claim_before_reopen",
            "requires_prior": [],
            "enables_next": ["agent_deepen"],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "agent_aippo",
        "Get low-risk working guidance for a task before editing or broad search. When: use for quick orientation when you do not yet need route receipts. After: run agent_recall or search_memory if the guidance says prior source matters.",
        {
            "task": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "agent_background",
        "Surface reviewed background findings for a task cue; does not start background jobs or make findings source truth. When: use for previously reviewed async findings, not live recall. After: reopen source with agent_recall and agent_deepen before claims.",
        {
            "cue": {"type": "string"},
            "query": {"type": "string"},
            "task": {"type": "string"},
            "registry_dir": {"type": "string"},
            "working_memory_path": {"type": "string"},
            "project": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 12},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["cue", "query", "task"],
    ),
    tool_schema(
        "agent_deepen",
        "Open the selected recall route from agent_recall before quoting or relying on it. When: use after agent_recall request_index or last-recall handles; use recall_deepen for recall_context handles. After: use returned source scope for bounded claims.",
        {
            "handle": {"type": ["string", "object"]},
            "request_index": {"type": "integer", "minimum": 1, "maximum": 25},
            "last_recall": {"type": "boolean"},
            "recall_selector": {"type": "string"},
            "last_recall_path": {"type": "string"},
            "cwd": {"type": "string"},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "macro_state_jsonl": {"type": "string"},
            "project": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["handle", "request_index"],
        parameter_tiers={
            "required": ["handle", "request_index"],
            "common": ["recall_selector", "cwd", "max", "detail"],
            "advanced": ["last_recall", "project"],
            "operator_internal": [
                "last_recall_path",
                "clean_source_dir",
                "registry_dir",
                "macro_state_jsonl",
                "include_private_paths",
            ],
        },
        metadata={
            "workflow": "open_selected_recall_route",
            "posture": "opens_source",
            "claim_boundary": "bounded_evidence_after_source_open",
            "requires_prior": ["agent_recall"],
            "enables_next": ["get_turn_context"],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "agent_explain",
        "Explain why a recall or AIppo route surfaced, without treating it as source evidence. When: use after agent_recall or agent_aippo selection; use recall_diagnostic for no-route, silence, or degradation. After: call agent_deepen if you will rely on the route.",
        {
            "handle": {"type": ["string", "object"]},
            "request_index": {"type": "integer", "minimum": 1, "maximum": 25},
            "last_recall": {"type": "boolean"},
            "recall_selector": {"type": "string"},
            "last_recall_path": {"type": "string"},
            "macro_state_jsonl": {"type": "string"},
            "project": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["handle", "request_index"],
        metadata={
            "workflow": "explain_selected_route_then_deepen_if_needed",
            "posture": "diagnostic_only",
            "claim_boundary": "diagnostic_not_source_evidence",
            "requires_prior": ["agent_recall", "agent_aippo"],
            "enables_next": ["agent_deepen"],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "search_memory",
        "Search clean source for source-backed receipts. When: use exact or distinctive wording; use agent_recall for fuzzy continuity. After: reopen with get_turn_context or deepen an agent_recall route before exact claims.",
        {
            "query": {"type": "string"},
            "scope": {
                "type": "string",
                "enum": ["current", "all_registered_sources", "last_recall_candidates"],
            },
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "search_budget": {"type": "string", "enum": ["default", "deep"]},
            "max_elapsed_ms": {"type": "integer", "minimum": 0, "maximum": 120000},
            "thread_key": {"type": "string"},
            "hit_index": {"type": "integer", "minimum": 1, "maximum": 25},
            "source_ref_index": {"type": "integer", "minimum": 1, "maximum": 100},
            "request_index": {"type": "integer", "minimum": 1, "maximum": 25},
            "recall_selector": {"type": "string"},
            "last_recall_path": {"type": "string"},
            "last_search": {"type": "boolean"},
            "open_source": {"type": "boolean"},
            "message_id": {"type": "string"},
            "line": {"type": "integer"},
            "context_lines": {"type": "integer", "minimum": 0, "maximum": 8},
            "metadata_only": {"type": "boolean"},
            "include_source_snippets": {"type": "boolean"},
            "include_snippets": {"type": "boolean"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        ["query"],
        parameter_tiers={
            "required": ["query"],
            "common": ["scope", "cwd", "max", "detail"],
            "advanced": [
                "search_budget",
                "max_elapsed_ms",
                "thread_key",
                "hit_index",
                "source_ref_index",
                "request_index",
                "recall_selector",
                "last_search",
                "open_source",
                "message_id",
                "line",
                "context_lines",
                "metadata_only",
                "include_source_snippets",
                "include_snippets",
            ],
            "operator_internal": [
                "clean_source_dir",
                "registry_dir",
                "last_recall_path",
                "include_private_paths",
            ],
        },
        metadata={
            "workflow": "exact_search_then_open",
            "posture": "source_locator",
            "claim_boundary": "no_exact_claim_before_source_open",
            "requires_prior": [],
            "enables_next": ["get_turn_context", "agent_deepen"],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "recall_context",
        "Legacy/detail route-handle tool for recall_deepen clients. When: prefer agent_recall for ordinary foreground continuity; use recall_context only when an existing workflow needs recall_deepen handles. After: call recall_deepen on a selected full-detail route, or rerun with agent_recall.",
        {
            "intent": {"type": "string"},
            "query": {"type": "string"},
            "cue": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "registry_dir": {"type": "string"},
            "continuity_domains_snapshot": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["intent", "query", "cue"],
        metadata={
            "workflow": "legacy_recall_context_then_recall_deepen",
            "posture": "legacy_detail_compat",
            "claim_boundary": "legacy_route_requires_recall_deepen_before_claim",
            "requires_prior": [],
            "enables_next": ["recall_deepen"],
            "legacy": True,
            "owner": LEGACY_RECALL_TOOL_POLICY["owner"],
            "default_exposure": LEGACY_RECALL_TOOL_POLICY["default_exposure"],
            "removal_condition": LEGACY_RECALL_TOOL_POLICY["removal_or_wrapper_condition"],
            "deprecation": LEGACY_RECALL_TOOL_POLICY,
            "foreground_recommended": False,
        },
    ),
    tool_schema(
        "recall_deepen",
        "Reopen clean source for a route from recall_context or an ambient navigation card. When: use for recall_context handles; use agent_deepen for agent_recall last-recall or request_index routes. After: read the returned source window before claiming.",
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
        metadata={
            "workflow": "legacy_open_recall_context_route",
            "posture": "legacy_detail_compat",
            "claim_boundary": "bounded_evidence_after_source_open",
            "requires_prior": ["recall_context"],
            "enables_next": ["get_turn_context"],
            "legacy": True,
            "owner": LEGACY_RECALL_TOOL_POLICY["owner"],
            "default_exposure": LEGACY_RECALL_TOOL_POLICY["default_exposure"],
            "removal_condition": LEGACY_RECALL_TOOL_POLICY["removal_or_wrapper_condition"],
            "deprecation": LEGACY_RECALL_TOOL_POLICY,
            "foreground_recommended": False,
        },
    ),
    tool_schema(
        "recall_diagnostic",
        "Explain why recall surfaced, stayed silent, degraded, or needs source reopen. When: use for recall_context or route/no-route diagnostics instead of agent_explain, which explains a selected agent route. After: run the suggested recall, deepen, or repair action.",
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
            "include_associative_path_diagnostics": {"type": "boolean"},
            "apw_sidecar_dir": {"type": "string"},
            "apw_semantic_bridge_path": {"type": "string"},
            "apw_navigation_path": {"type": "string"},
            "apw_active_lock_path": {"type": "string"},
            "apw_feedback_path": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        metadata={
            "workflow": "diagnose_recall_surface_then_choose_next_action",
            "posture": "diagnostic_only",
            "claim_boundary": "diagnostic_not_source_evidence",
            "requires_prior": [],
            "enables_next": ["agent_recall", "recall_context"],
            "foreground_recommended": False,
        },
    ),
    tool_schema(
        "latest_reply",
        "Find the latest assistant closeout for continuing work; prefer clean source when supplied. When: use to resume thread closeout context, not arbitrary memory search. After: run agent_recall or source reopen on any claim-bearing cue.",
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
        "Open one clean-source turn by turn_id, message_id, or turn_index from a route. When: use after search_memory, recall_deepen, or a route gives a selector. After: quote only within the returned source scope.",
        {
            "cwd": {"type": "string"},
            "turn_id": {"type": "string"},
            "message_id": {"type": "string"},
            "turn_index": {"type": "integer"},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        required_any=["turn_id", "message_id", "turn_index"],
        metadata={
            "workflow": "open_clean_source_turn",
            "posture": "opens_source",
            "claim_boundary": "bounded_evidence_after_source_open",
            "requires_prior": ["search_memory"],
            "enables_next": [],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "list_threads",
        "List registered local memory threads as route handles, not source evidence. When: use for inventory or debugging before recall, not for answering from memory. After: pass a useful cue to agent_recall or search_memory.",
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
        "Register the current thread after explicit consent so future agents can find it. When: use only for an approved local registry write, not read-only recall. After: run memory_health or agent_recall to verify discoverability.",
        {
            "cwd": {"type": "string"},
            "registry_dir": {"type": "string"},
            "build_index": {"type": "boolean"},
            "provider": {"type": "string", "enum": list(PROVIDER_CHOICES)},
            "confirm_write": {"type": "boolean"},
            "write": {"type": "boolean"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        ["cwd", "provider", "confirm_write"],
    ),
    tool_schema(
        "sync_status",
        "Check local sync readiness without pushing, pulling, or exposing private paths. When: use before sync push, pull, repair, or object-store setup. After: choose an explicit sync command only if the user wants writes.",
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
        "Check whether recall is usable now and get one stable next action. When: use when source or index readiness is uncertain, not as a recall substitute. After: follow foreground_action or run agent_recall when ready.",
        {
            "cwd": {"type": "string"},
            "detail": {"type": "string", "enum": ["compact", "full"]},
            "include_private_paths": {"type": "boolean"},
        },
        parameter_tiers={
            "required": [],
            "common": ["cwd", "detail"],
            "advanced": [],
            "operator_internal": ["include_private_paths"],
        },
        metadata={
            "workflow": "readiness_then_choose_recall_or_repair",
            "posture": "readiness_diagnostic",
            "claim_boundary": "tool_readiness_not_memory_evidence",
            "requires_prior": [],
            "enables_next": ["agent_recall"],
            "foreground_recommended": True,
        },
    ),
    tool_schema(
        "list_telepathy_handoffs",
        "List opt-in Telepathy handoff cards without writing coordination state. When: use when the user asks for saved handoff or coordination cards. After: call deepen_telepathy_handoff for the selected card.",
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
        "Return one Telepathy handoff card with sanitized source selectors for reopen. When: use after list_telepathy_handoffs. After: reopen cited source via get_turn_context or agent_recall before claims.",
        {
            "card_id": {"type": "string"},
            "cwd": {"type": "string"},
            "store_path": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["card_id"],
    ),
]
