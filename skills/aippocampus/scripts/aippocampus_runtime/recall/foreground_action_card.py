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
    if not packet:
        return "continue_normally"
    if packet.get("claim_permission") == "blocked" or packet.get("output_mode") == "ignore_or_blocked":
        return "ignore_or_blocked"
    risks = _risk_codes(packet)
    if {"check_currentness", "conflict_requires_deepen"} & risks:
        return "deepen_before_claim"
    if request or packet.get("output_mode") in {"reopenable_route", "bounded_summary_as_route"}:
        return "use_route_first"
    return "continue_normally"


def _next_action(decision: str, request: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
    if decision in {"use_route_first", "deepen_before_claim"}:
        return "deepen" if request else str(packet.get("next_action") or "reopen_source")
    return "continue_normally"


def build_recall_foreground_action_card(
    *,
    status: Any,
    memory_packets: Any,
    deepen_requests: Any,
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
        "claim_boundary": CLAIM_BOUNDARY if decision != "continue_normally" else "no_route_claim",
    }
    if packet:
        card["route_label"] = _route_label(packet)
        card["route_family"] = _safe_text(
            packet.get("route_kind") or packet.get("output_mode") or "recall_route",
            limit=80,
        )
    if request and decision in {"use_route_first", "deepen_before_claim"}:
        card["callable_handle"] = str(request.get("handle") or request.get("callable_handle") or "")
    compact = {key: value for key, value in card.items() if value not in {"", None}}
    return schema_profiles.project_record_for_profile(compact, "foreground_action_card")


def redact_public_card(card: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(card)
    if "callable_handle" in projected:
        projected.pop("callable_handle", None)
        projected.pop("short_action_token", None)
        projected["callable_handle_redacted"] = True
        projected["public_safe_action"] = "aippocampus agent deepen <local-private-handle>"
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
