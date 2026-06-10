"""Agent-native recall/deepen/explain facade contract.

This module is a small contract fixture for agent hosts. It projects existing
route packets into the smallest useful foreground shape, then keeps source
handles and diagnostics behind explicit deepen/explain calls. It does not
replace MCP, source reopen, or the attention-router internals.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.navigation import attention_router_contract

SCHEMA_VERSION = "agent-native-recall-facade-v0"
# #1125 owns the stricter foreground UX budget. This facade fixture keeps only
# the smoke-level ceiling needed to prove packets are not provenance dumps.
FOREGROUND_PACKET_BYTE_BUDGET = 480
FACADE_OUTPUT_MODES = {
    "direction_only",
    "bounded_summary_as_route",
    "reopenable_route",
    "bounded_evidence",
    "ignore_or_blocked",
}

_FOREGROUND_FORBIDDEN_KEYS = {
    "source_handles",
    "source_id",
    "segment_id",
    "turn_range",
    "line_range",
    "char_range",
    "head_votes",
    "masks_applied",
    "bounded_summary",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _truncate_for_budget(text: str, *, max_chars: int = 180) -> str:
    normalized = " ".join(text.strip().split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _source_handles(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    handles: list[dict[str, Any]] = []
    for handle in packet.get("source_handles") or []:
        if isinstance(handle, Mapping):
            handles.append(dict(handle))
    return handles


def _facade_mode(packet: Mapping[str, Any]) -> str:
    output_mode = _as_text(packet.get("output_mode"))
    action_grammar = _as_text(packet.get("action_grammar"))
    claim_permission = _as_text(packet.get("claim_permission"))
    if output_mode == "silence" or action_grammar == "ignore_or_blocked" or claim_permission == "blocked":
        return "ignore_or_blocked"
    if output_mode in FACADE_OUTPUT_MODES:
        return output_mode
    return "direction_only"


def _default_next_action(output_mode: str) -> str:
    if output_mode == "ignore_or_blocked":
        return "stay_silent"
    if output_mode == "reopenable_route":
        return "reopen_source"
    return "use_hint"


def _default_display_hint(packet: Mapping[str, Any], output_mode: str) -> str:
    if output_mode == "ignore_or_blocked":
        return "Recall route blocked; stay silent unless the user asks to inspect the boundary."
    if output_mode == "bounded_summary_as_route":
        summary = packet.get("bounded_summary")
        scope = _as_text(summary.get("scope")) if isinstance(summary, Mapping) else "this source trail"
        return f"Use the bounded route for {scope}; reopen source before claims."
    if output_mode == "reopenable_route":
        return "A source route may matter; reopen it before using the detail."
    if output_mode == "bounded_evidence":
        return "Source is already open within scope; use only that bounded evidence."
    return "This is a direction-only memory hint; do not turn it into a claim."


def memory_packet_from_route_packet(
    packet: Mapping[str, Any],
    *,
    display_hint: str | None = None,
) -> dict[str, Any]:
    """Return the compact packet an agent sees from ``recall``.

    Foreground packets intentionally omit source handles, head votes, masks, and
    raw route internals. An agent that needs those details should call
    ``deepen_route_packet`` or ``explain_route_packet`` with the route id.
    """

    route_id = _as_text(packet.get("route_id")) or "route:unknown"
    output_mode = _facade_mode(packet)
    claim_permission = (
        "blocked" if output_mode == "ignore_or_blocked" else _as_text(packet.get("claim_permission"))
    )
    if not claim_permission:
        claim_permission = "no_claim_before_reopen"

    result: dict[str, Any] = {
        "kind": "aippocampus_memory_packet",
        "schema_version": SCHEMA_VERSION,
        "route_id": route_id,
        "output_mode": output_mode,
        "display_hint": _truncate_for_budget(
            display_hint or _default_display_hint(packet, output_mode)
        ),
        "claim_permission": claim_permission,
        "next_action": _default_next_action(output_mode),
        "deepen_route_id": f"deepen:{route_id}",
    }
    return result


def deepen_route_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return source-route detail, bounded evidence, blocked, or cannot-verify."""

    route_id = _as_text(packet.get("route_id")) or "route:unknown"
    output_mode = _facade_mode(packet)
    handles = _source_handles(packet)
    if output_mode == "ignore_or_blocked":
        return {
            "kind": "aippocampus_deepen_result",
            "schema_version": SCHEMA_VERSION,
            "route_id": route_id,
            "status": "blocked",
            "claim_permission": "blocked",
            "blocked_reason_codes": list(packet.get("masks_applied") or ["blocked"]),
            "source_handles": [],
            "cannot_claim": ["blocked_route_as_source_truth"],
        }
    if not handles:
        return {
            "kind": "aippocampus_deepen_result",
            "schema_version": SCHEMA_VERSION,
            "route_id": route_id,
            "status": "cannot_verify",
            "claim_permission": "no_claim_before_reopen",
            "reason_codes": ["no_reopenable_source_handle"],
            "source_handles": [],
            "cannot_claim": ["source_backed_claim"],
        }

    status = "source_route"
    claim_permission = "no_claim_before_reopen"
    if output_mode == "bounded_evidence" and packet.get("claim_permission") == "bounded_claim_allowed":
        status = "source_backed_evidence"
        claim_permission = "bounded_claim_allowed"

    result: dict[str, Any] = {
        "kind": "aippocampus_deepen_result",
        "schema_version": SCHEMA_VERSION,
        "route_id": route_id,
        "status": status,
        "claim_permission": claim_permission,
        "source_handles": handles,
        "source_handle_count": len(handles),
        "claim_boundary": (
            "reopen_source_before_claim"
            if status == "source_route"
            else "bounded_to_already_open_scope"
        ),
    }
    summary = packet.get("bounded_summary")
    if isinstance(summary, Mapping):
        result["bounded_summary"] = dict(summary)
    return result


def explain_route_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe why-recall / why-not-recall explanation."""

    route_id = _as_text(packet.get("route_id")) or "route:unknown"
    output_mode = _facade_mode(packet)
    head_votes = [dict(vote) for vote in packet.get("head_votes") or [] if isinstance(vote, Mapping)]
    masks = list(packet.get("masks_applied") or [])
    if output_mode == "ignore_or_blocked":
        decision = "why_not_recall"
        next_safe_action = "stay_silent"
        reason_codes = ["blocked_by_hard_mask", *[f"mask:{mask}" for mask in masks]]
    elif output_mode == "reopenable_route":
        decision = "why_recall"
        next_safe_action = "reopen_source"
        reason_codes = ["reopenable_route_available"]
    elif output_mode == "bounded_summary_as_route":
        decision = "why_recall"
        next_safe_action = "use_hint"
        reason_codes = ["bounded_summary_route_available", "summary_is_not_evidence"]
    elif output_mode == "bounded_evidence":
        decision = "why_recall"
        next_safe_action = "use_hint"
        reason_codes = ["source_open_bounded_scope"]
    else:
        decision = "why_recall"
        next_safe_action = "use_hint"
        reason_codes = ["direction_only_navigation"]

    return {
        "kind": "aippocampus_route_explanation",
        "schema_version": SCHEMA_VERSION,
        "route_id": route_id,
        "decision": decision,
        "output_mode": output_mode,
        "claim_permission": (
            "blocked" if output_mode == "ignore_or_blocked" else _as_text(packet.get("claim_permission"))
        ),
        "next_safe_action": next_safe_action,
        "reason_codes": reason_codes,
        "source_handle_count": len(_source_handles(packet)),
        "head_vote_count": len(head_votes),
        "cannot_claim": [
            "source_truth_without_deepen",
            "foreground_packet_as_full_provenance",
        ],
    }


def _fixture_route_packets() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [
        {
            "case_id": "tiny_bounded_summary_hint",
            "route_id": "route_project_workflow_summary",
            "source_handles": [
                {
                    "source_id": "src_project_policy",
                    "segment_id": "seg_contract",
                    "turn_range": [3, 5],
                    "reopen_required": True,
                }
            ],
            "bounded_summary": {
                "scope": "project:AIppocampus/workflow",
                "source_coverage": ["issue:#1129", "doc:source-backed-attention-router"],
                "freshness": "current",
                "reopen_path": "recall_deepen:route_project_workflow_summary",
                "summary_text": "PRIVATE_SUMMARY_SENTINEL",
            },
            "head_votes": [
                {"head": "scope_head", "score": 0.92, "reason_code": "project_workflow_scope"},
            ],
        },
        {
            "case_id": "reopenable_source_route",
            "route_id": "route_old_decision_reopen",
            "source_handles": [
                {
                    "source_id": "src_old_decision",
                    "segment_id": "seg_reopen",
                    "line_range": [10, 16],
                    "reopen_required": True,
                }
            ],
            "head_votes": [
                {"head": "lexical_head", "score": 0.81, "reason_code": "issue_id_match"},
            ],
        },
        {
            "case_id": "blocked_private_route",
            "route_id": "route_private_blocked",
            "hard_masks": ["privacy_domain"],
            "source_handles": [
                {
                    "source_id": "src_private",
                    "segment_id": "seg_private",
                    "reopen_required": True,
                    "source_text": "PRIVATE_SOURCE_SENTINEL",
                }
            ],
            "head_votes": [
                {"head": "semantic_head", "score": 0.97, "reason_code": "semantic_match"},
            ],
        },
        {
            "case_id": "direction_only_cannot_verify",
            "route_id": "route_direction_only",
            "head_votes": [
                {"head": "semantic_head", "score": 0.44, "reason_code": "weak_scent"},
            ],
        },
        {
            "case_id": "source_open_bounded_evidence",
            "route_id": "route_source_open_bounded",
            "source_open": True,
            "bounded_scope": True,
            "source_handles": [
                {
                    "source_id": "src_open",
                    "segment_id": "seg_open",
                    "line_range": [20, 22],
                    "reopen_required": False,
                }
            ],
            "head_votes": [
                {"head": "evidence_packaging_head", "score": 0.93, "reason_code": "source_open"},
            ],
        },
    ]
    return [attention_router_contract.build_route_packet(candidate) for candidate in candidates]


def build_facade_fixture_report() -> dict[str, Any]:
    """Build the public-safe #1129 facade fixture report."""

    records = []
    for packet in _fixture_route_packets():
        memory_packet = memory_packet_from_route_packet(packet)
        records.append(
            {
                "route_id": packet["route_id"],
                "route_packet": packet,
                "memory_packet": memory_packet,
                "deepen": deepen_route_packet(packet),
                "explain": explain_route_packet(packet),
                "foreground_packet_bytes": _json_bytes(memory_packet),
            }
        )

    memory_packets = [record["memory_packet"] for record in records]
    encoded_foreground = json.dumps(memory_packets, ensure_ascii=False, sort_keys=True)
    forbidden_in_foreground = sum(
        1 for key in _FOREGROUND_FORBIDDEN_KEYS if f'"{key}"' in encoded_foreground
    )
    source_backed_claim_without_reopen = sum(
        1
        for record in records
        if record["memory_packet"]["claim_permission"] == "bounded_claim_allowed"
        and record["route_packet"]["output_mode"] != "bounded_evidence"
    )
    metrics = {
        "foreground_packet_count": len(memory_packets),
        "foreground_packet_max_bytes": max(record["foreground_packet_bytes"] for record in records),
        "foreground_forbidden_key_count": forbidden_in_foreground,
        "bounded_summary_as_route_count": sum(
            1 for packet in memory_packets if packet["output_mode"] == "bounded_summary_as_route"
        ),
        "reopenable_route_count": sum(
            1 for packet in memory_packets if packet["output_mode"] == "reopenable_route"
        ),
        "ignore_or_blocked_count": sum(
            1 for packet in memory_packets if packet["output_mode"] == "ignore_or_blocked"
        ),
        "blocked_deepen_count": sum(
            1 for record in records if record["deepen"]["status"] == "blocked"
        ),
        "cannot_verify_count": sum(
            1 for record in records if record["deepen"]["status"] == "cannot_verify"
        ),
        "source_route_deepen_count": sum(
            1 for record in records if record["deepen"]["status"] == "source_route"
        ),
        "source_backed_evidence_deepen_count": sum(
            1 for record in records if record["deepen"]["status"] == "source_backed_evidence"
        ),
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
    }
    red_lines = {
        "foreground_forbidden_key_count": forbidden_in_foreground,
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
        "foreground_packet_budget_violation_count": sum(
            1
            for record in records
            if record["foreground_packet_bytes"] > FOREGROUND_PACKET_BYTE_BUDGET
        ),
    }
    return {
        "kind": "aippocampus_agent_native_recall_facade_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()),
        "api_shape": {
            "recall": "recall(query, context) -> MemoryPacket[]",
            "deepen": "deepen(route_id, options?) -> SourceRoute | SourceBackedEvidence | Blocked | CannotVerify",
            "explain": "explain(route_id) -> WhyRecall | WhyNotRecall",
        },
        "foreground_packet_budget_bytes": FOREGROUND_PACKET_BYTE_BUDGET,
        "records": records,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "foreground_packets_include_source_handles": False,
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
        },
        "cannot_claim": [
            "public_sdk_stability",
            "hosted_service_readiness",
            "network_api_contract",
            "profile_memory_equivalence",
            "source_truth_without_deepen",
            "default_agent_adoption",
        ],
    }
