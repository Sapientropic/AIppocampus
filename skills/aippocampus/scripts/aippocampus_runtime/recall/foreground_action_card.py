"""Foreground action-card projection for agent-facing recall.

This module owns the small product-facing card budget. Rich recall JSON stays
available for audit, but foreground agents should first see one direct action
and one source boundary instead of compiling router diagnostics by hand.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core, schema_profiles
from aippocampus_runtime.contracts import shell_quote
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

CARD_FIELD_BUDGET = 8
CARD_BYTE_BUDGET = 900
CLAIM_BOUNDARY = "no_claim_before_reopen"
AUDIT_ONLY_KEYS = set(schema_profiles.FOREGROUND_ACTION_CARD_AUDIT_ONLY_KEYS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_text(value: Any, *, limit: int = 120) -> str:
    text = core.compact_text(str(value or "").strip(), limit)
    redacted = redact_sensitive_values(redact_private_paths(text))
    return str(redacted or "").strip()


def _first_mapping(values: Any) -> Mapping[str, Any]:
    if not isinstance(values, list | tuple):
        return {}
    for value in values:
        if isinstance(value, Mapping):
            return value
    return {}


def _request_for_route(requests: Any, route_id: str) -> Mapping[str, Any]:
    if not isinstance(requests, list | tuple):
        return {}
    fallback: Mapping[str, Any] = {}
    for value in requests:
        if not isinstance(value, Mapping):
            continue
        if not fallback:
            fallback = value
        if str(value.get("route_id") or "") == route_id:
            return value
    return fallback


def _risk_codes(packet: Mapping[str, Any]) -> set[str]:
    raw = packet.get("risk_flags") or packet.get("triage_rank_reason_codes") or []
    if not isinstance(raw, list | tuple):
        return set()
    return {str(item) for item in raw if str(item).strip()}


def _route_label(packet: Mapping[str, Any]) -> str:
    return (
        _safe_text(packet.get("route_topic"), limit=80)
        or _safe_text(packet.get("route_label"), limit=100)
        or _safe_text(packet.get("route_id"), limit=80)
        or "memory_route"
    )


def _why_for_decision(decision: str, packet: Mapping[str, Any]) -> str:
    if decision == "use_opened_context":
        return "This route was already reopened in the local last-recall session; reuse that opened context unless scope changed."
    if decision == "recover_no_route":
        return "No compact source-backed route surfaced; try exact source search or check source registration."
    if decision == "continue_normally":
        return "No compact source-backed route surfaced."
    if decision == "ignore_or_blocked":
        return "The top route is blocked, private, or not safe for foreground use."
    if decision == "deepen_before_claim":
        return "The route may matter, but currentness or conflict must be checked first."
    hint = _mapping(packet.get("selection_hint"))
    if hint.get("source"):
        return _safe_text(f"{hint.get('source')}: {hint.get('why') or 'selected'}", limit=140)
    display = _safe_text(packet.get("display_hint"), limit=140)
    if display:
        return display
    return "A source-backed continuity route is likely relevant; do not answer from the packet."


def _decision_for(status: Any, packet: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    if str(status or "") in {"cannot_verify", "blocked", "privacy_blocked"}:
        return "ignore_or_blocked"
    if str(status or "") == "no_routes" and not packet:
        return "recover_no_route"
    if not packet:
        return "continue_normally"
    if packet.get("already_opened"):
        return "use_opened_context"
    if packet.get("claim_permission") == "blocked" or packet.get("output_mode") == "ignore_or_blocked":
        return "ignore_or_blocked"
    risks = _risk_codes(packet)
    if {"check_currentness", "conflict_requires_deepen"} & risks:
        return "deepen_before_claim"
    if request or packet.get("output_mode") in {"reopenable_route", "bounded_summary_as_route"}:
        return "use_route_first"
    return "continue_normally"


def _next_action(decision: str, request: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
    if decision == "recover_no_route":
        return "search_memory"
    if decision == "use_opened_context":
        return "continue_with_opened_context"
    if decision in {"use_route_first", "deepen_before_claim"}:
        return "deepen" if request else str(packet.get("next_action") or "reopen_source")
    return "continue_normally"


def _search_recovery_action(query: Any) -> dict[str, Any]:
    cue = _safe_text(query, limit=160)
    base = {
        "action_id": "recover_recall_miss",
        "tool_name": "search_memory",
        "why": "Search clean source for exact wording before broadening the recall attempt.",
        "claim_boundary": "no_route_claim",
    }
    if cue:
        return base | {
            "arguments": {"query": cue, "max": 5},
            "cli_command": f"aippocampus search {shell_quote(cue)} --json",
        }
    return base | {
        "arguments_template": {"query": "{exact_phrase}", "max": 5},
        "requires": ["exact_phrase"],
        "template_only": True,
        "cli_command_template": 'aippocampus search "{exact_phrase}" --json',
    }


def _onboarding_register_action() -> dict[str, Any]:
    return {
        "action_id": "register_source_before_recall",
        "tool_name": "shell",
        "arguments": {"command": "aippocampus onboard --provider codex --cwd . --json"},
        "cli_command": "aippocampus onboard --provider codex --cwd . --json",
        "why": "No clean source is registered yet; register source before repeating recall/search.",
        "mutation_risk": "writes_local_clean_source",
        "claim_boundary": "registration_enables_source_reopen_not_source_evidence",
    }


def _onboarding_status_action() -> dict[str, Any]:
    return {
        "action_id": "check_onboarding_status",
        "tool_name": "shell",
        "arguments": {"command": "aippocampus onboard --provider auto --status --json"},
        "cli_command": "aippocampus onboard --provider auto --status --json",
        "why": "Use if recall/search miss suggests clean source is missing or unregistered.",
        "claim_boundary": "setup_status_not_memory_evidence",
    }


def _canonical_action(
    decision: str,
    request: Mapping[str, Any],
    query: Any,
    *,
    source_registered: bool | None,
) -> dict[str, Any]:
    if decision == "recover_no_route":
        if source_registered is False:
            return _onboarding_register_action()
        return _search_recovery_action(query)
    if decision == "use_opened_context":
        return {
            "action_id": "use_opened_route_context",
            "tool_name": None,
            "arguments": {},
            "why": "same route and handle were already reopened in this local session",
            "claim_boundary": "source_open_within_opened_context",
        }
    if decision not in {"use_route_first", "deepen_before_claim"} or not request:
        return {
            "action_id": "continue_normally",
            "tool_name": None,
            "arguments": {},
            "claim_boundary": "no_route_claim",
        }
    request_index = request.get("request_index") or 1
    try:
        request_index = int(request_index)
    except (TypeError, ValueError):
        request_index = 1
    return {
        "action_id": "agent_deepen_selected_route",
        "tool_name": "agent_deepen",
        "arguments": {
            "request_index": request_index,
        },
        "cli_command_template": (
            f"aippocampus agent deepen --request {request_index} "
            "--recall-selector {recall_selector} --json"
        ),
        "requires": ["recall_selector"],
        "template_only": True,
        "last_recall_fallback_command": (
            f"aippocampus agent deepen --request {request_index} --last-recall --json"
        ),
        "last_recall_fallback_boundary": (
            "--last-recall reads a mutable same-machine cache; use only when "
            "the recall_selector emitted by the same recall is unavailable."
        ),
        "why": "reopen before using this route",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def build_recall_foreground_action_card(
    *,
    status: Any,
    memory_packets: Any,
    deepen_requests: Any,
    query: Any = None,
    source_registered: bool | None = None,
) -> dict[str, Any]:
    """Build the tiny default card for agent recall / MCP foreground use."""

    packet = _first_mapping(memory_packets)
    route_id = str(packet.get("route_id") or "")
    request = _request_for_route(deepen_requests, route_id)
    decision = _decision_for(status, packet, request)
    card: dict[str, Any] = {
        "decision": decision,
        "why": _why_for_decision(decision, packet),
        "next_action": _next_action(decision, request, packet),
        "claim_boundary": (
            "no_route_claim"
            if decision in {"continue_normally", "recover_no_route"}
            else CLAIM_BOUNDARY
        ),
        "canonical_action": _canonical_action(
            decision,
            request,
            query,
            source_registered=source_registered,
        ),
    }
    if decision == "recover_no_route":
        search_action = _search_recovery_action(query)
        actions = [card["canonical_action"], _onboarding_status_action()]
        if card["canonical_action"].get("action_id") != search_action.get("action_id"):
            actions.append(search_action)
        card["safe_next_actions"] = actions
    if packet:
        card["route_label"] = _route_label(packet)
        card["route_family"] = _safe_text(
            packet.get("route_kind") or packet.get("output_mode") or "recall_route",
            limit=80,
        )
    if request and decision in {"use_route_first", "deepen_before_claim"}:
        card["callable_handle"] = str(request.get("handle") or request.get("callable_handle") or "")
    compact = {
        key: value
        for key, value in card.items()
        if value is not None and value != ""
    }
    return schema_profiles.project_record_for_profile(compact, "foreground_action_card")


def redact_public_card(card: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(card)
    if "callable_handle" in projected:
        projected.pop("callable_handle", None)
        projected.pop("short_action_token", None)
        projected["callable_handle_redacted"] = True
    return schema_profiles.project_record_for_profile(projected, "foreground_action_card")


def card_metrics(card: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(card, ensure_ascii=False, sort_keys=True)
    leaked_keys = sorted(AUDIT_ONLY_KEYS & set(card))
    profile_report = schema_profiles.validate_profile_record(card, "foreground_action_card")
    return {
        "foreground_action_card_field_count": len(card),
        "foreground_action_card_byte_count": len(encoded.encode("utf-8")),
        "foreground_action_card_over_field_budget": len(card) > CARD_FIELD_BUDGET,
        "foreground_action_card_over_byte_budget": len(encoded.encode("utf-8")) > CARD_BYTE_BUDGET,
        "foreground_action_card_audit_key_leak_count": len(leaked_keys),
        "foreground_action_card_profile_ok": bool(profile_report["ok"]),
    }


def build_action_card_replay_report() -> dict[str, Any]:
    """Public-safe replay showing why the card exists.

    This is a deterministic product-contract fixture, not causal live evidence.
    """

    cases: list[dict[str, Any]] = [
        {
            "case_id": "positive_route",
            "audit_style_manual_compile_steps": 3,
            "card_action_steps": 1,
            "decision": "use_route_first",
        },
        {
            "case_id": "stale_conflicted_route",
            "audit_style_manual_compile_steps": 4,
            "card_action_steps": 1,
            "decision": "deepen_before_claim",
        },
        {
            "case_id": "blocked_private_route",
            "audit_style_manual_compile_steps": 2,
            "card_action_steps": 1,
            "decision": "ignore_or_blocked",
        },
        {
            "case_id": "no_route",
            "audit_style_manual_compile_steps": 1,
            "card_action_steps": 1,
            "decision": "continue_normally",
        },
    ]
    reduction = sum(
        max(0, int(case["audit_style_manual_compile_steps"]) - int(case["card_action_steps"]))
        for case in cases
    )
    return {
        "schema_version": 1,
        "kind": "aippocampus_foreground_action_card_replay",
        "ok": True,
        "case_count": len(cases),
        "broad_manual_search_reduction_proxy": reduction,
        "audit_available": True,
        "foreground_card_field_budget": CARD_FIELD_BUDGET,
        "audit_only_keys_excluded": sorted(AUDIT_ONLY_KEYS),
        "cases": cases,
        "red_lines": {
            "raw_source_leak_count": 0,
            "raw_prompt_text_leak_count": 0,
            "local_path_leak_count": 0,
            "source_truth_overclaim_count": 0,
            "audit_key_in_card_count": 0,
        },
        "cannot_claim": [
            "causal_live_agent_behavior_lift",
            "source_truth_from_action_card",
            "default_hook_activation",
        ],
    }
