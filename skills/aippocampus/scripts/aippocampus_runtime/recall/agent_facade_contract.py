"""Agent-native recall/deepen/explain facade contract.

This module is a small contract fixture for agent hosts. It projects existing
route packets into the smallest useful foreground shape, then keeps source
handles and diagnostics behind explicit deepen/explain calls. It does not
replace MCP, source reopen, or the attention-router internals.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.navigation import attention_router_contract
from aippocampus_runtime.recall import authority
from aippocampus_runtime.source.io_kernel import safe_float as kernel_safe_float

SCHEMA_VERSION = "agent-native-recall-facade-v0"
# #1125 owns the stricter foreground UX budget. This facade fixture keeps only
# the smoke-level ceiling needed to prove packets are not provenance dumps.
FOREGROUND_PACKET_BYTE_BUDGET = 560
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
_TRIAGE_TEXT_FORBIDDEN_MARKERS = (
    "source_id",
    "message_id",
    "turn_id",
    "source_ref",
    "source_handle",
    "head_vote",
    "mask_applied",
    "raw_text",
    "private_",
    "secret",
    "password",
    "credential",
    "api_key",
    "token=",
    "c:\\",
    "\\users\\",
    "/users/",
    "://",
)
_PROFILE_LIKE_MARKERS = (
    "adhd",
    "anxiety",
    "identity",
    "personality",
    "profile",
    "private impression",
    "dislikes",
    "hates",
)
_CODE_RE = re.compile(r"[^a-z0-9_]+")
_ROUTE_LABEL_FALLBACKS = {
    "bounded_summary_as_route": "bounded_summary_route",
    "reopenable_route": "source_reopen_route",
    "bounded_evidence": "bounded_source_route",
    "direction_only": "direction_only_route",
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


def _safe_preview_text(value: Any, *, max_chars: int = 140) -> str:
    text = _truncate_for_budget(_as_text(value), max_chars=max_chars)
    folded = text.casefold()
    if not text:
        return ""
    if any(marker in folded for marker in _TRIAGE_TEXT_FORBIDDEN_MARKERS):
        return ""
    if any(marker in folded for marker in _PROFILE_LIKE_MARKERS):
        return ""
    return text


def _safe_code(value: Any, *, max_chars: int = 64) -> str:
    text = _as_text(value).casefold().replace("-", "_").replace(" ", "_")
    text = _CODE_RE.sub("_", text).strip("_")
    if not text:
        return ""
    if any(marker.strip("_") and marker.strip("_") in text for marker in _PROFILE_LIKE_MARKERS):
        return ""
    if any(marker.strip("_") and marker.strip("_") in text for marker in ("secret", "password", "credential", "api_key")):
        return ""
    return text[:max_chars].strip("_")


def _safe_code_list(values: Any, *, limit: int = 4) -> list[str]:
    if isinstance(values, str):
        raw_values: list[Any] = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    else:
        raw_values = []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        code = _safe_code(value)
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(code)
        if len(result) >= limit:
            break
    return result


def _confidence_float(value: Any) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return round(max(0.0, min(1.0, kernel_safe_float(value))), 3)


def _router_reason_codes(packet: Mapping[str, Any]) -> list[str]:
    diagnostics = packet.get("router_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return []
    return _safe_code_list(diagnostics.get("reason_codes"), limit=6)


def _route_label(packet: Mapping[str, Any], output_mode: str) -> str:
    explicit = _safe_preview_text(packet.get("route_label"), max_chars=72)
    if explicit:
        return explicit
    route_kind = _safe_code(packet.get("route_kind"))
    if route_kind and route_kind != "aippocampus_attention_route_packet":
        return route_kind
    return _ROUTE_LABEL_FALLBACKS.get(output_mode, "memory_route")


def _risk_flags(packet: Mapping[str, Any], output_mode: str) -> list[str]:
    flags = _safe_code_list(packet.get("risk_flags"), limit=6)
    reasons = set(_router_reason_codes(packet))
    currentness = _safe_code(packet.get("currentness"))
    conflict = _safe_code(packet.get("conflict"))
    if currentness in {"stale", "needs_reopen", "superseded"} or "stale_or_conflicted_source_reopen" in reasons:
        flags.append("check_currentness")
    if conflict and conflict not in {"none", "unknown"}:
        flags.append("conflict_requires_deepen")
    result: list[str] = []
    seen: set[str] = set()
    for flag in flags:
        clean = _safe_code(flag)
        if clean in {"source_reopen_required", "summary_is_not_evidence"}:
            continue
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
        if len(result) >= 4:
            break
    return result


def _rank_reason_codes(packet: Mapping[str, Any], risk_flags: list[str]) -> list[str]:
    explicit = _safe_code_list(packet.get("triage_rank_reason_codes"), limit=4)
    if explicit:
        return explicit
    reasons = _router_reason_codes(packet)
    if reasons:
        return reasons[:4]
    return risk_flags[:3]


def _why_may_matter(
    packet: Mapping[str, Any],
    output_mode: str,
    *,
    risk_flags: list[str],
) -> str:
    explicit = _safe_preview_text(packet.get("why_may_matter"), max_chars=132)
    if explicit:
        return explicit
    if output_mode == "bounded_summary_as_route":
        return "Scoped summary can orient the next step; reopen source before claims."
    if output_mode == "reopenable_route" and (
        "check_currentness" in risk_flags or "conflict_requires_deepen" in risk_flags
    ):
        return "Route may be stale or conflicted; reopen and check currentness before use."
    if output_mode == "reopenable_route":
        return "Source-backed route matched the cue; reopen before using details."
    if output_mode == "bounded_evidence":
        return "Source is already open only within the declared bounded scope."
    return "Navigation hint only; do not turn it into a factual claim."


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


def _default_display_hint(
    packet: Mapping[str, Any],
    output_mode: str,
    *,
    route_label: str = "",
    why_may_matter: str = "",
) -> str:
    if output_mode == "ignore_or_blocked":
        return "Recall route blocked; stay silent unless the user asks to inspect the boundary."
    if output_mode == "bounded_summary_as_route":
        return "Use scoped route; reopen before claims."
    if output_mode == "reopenable_route":
        if "check_currentness" in _risk_flags(packet, output_mode):
            return f"{route_label or 'route'}: reopen/check currentness."
        if packet.get("route_topic"):
            return "Reopen before use; route is not evidence."
        if route_label:
            return f"{route_label}: reopen before use."
        return "A source route may matter; reopen it before using the detail."
    if output_mode == "bounded_evidence":
        return "Source is already open within scope; use only that bounded evidence."
    return "This is a direction-only memory hint; do not turn it into a claim."


def _fit_memory_packet_budget(result: dict[str, Any]) -> dict[str, Any]:
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    if "why_may_matter" in result:
        result["why_may_matter"] = _truncate_for_budget(
            str(result["why_may_matter"]),
            max_chars=92,
        )
    if "display_hint" in result:
        result["display_hint"] = _truncate_for_budget(str(result["display_hint"]), max_chars=132)
    if "triage_rank_reason_codes" in result:
        result["triage_rank_reason_codes"] = list(result["triage_rank_reason_codes"])[:2]
    if "risk_flags" in result:
        result["risk_flags"] = list(result["risk_flags"])[:3]
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("route_label_specificity_score", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("triage_rank_reason_codes", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("label_granularity", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("scope_bucket", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("preview_permission", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("risk_flags", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("route_topic", None)
    if _json_bytes(result) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return result
    result.pop("why_may_matter", None)
    result["display_hint"] = _truncate_for_budget(str(result.get("display_hint") or ""), max_chars=96)
    return result


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
    route_label = _route_label(packet, output_mode)
    risk_flags = _risk_flags(packet, output_mode)
    why_may_matter = _why_may_matter(packet, output_mode, risk_flags=risk_flags)
    triage_rank_reason_codes = _rank_reason_codes(packet, risk_flags)
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
            display_hint
            or _default_display_hint(
                packet,
                output_mode,
                route_label=route_label,
                why_may_matter=why_may_matter,
            )
        ),
        "claim_permission": claim_permission,
        "next_action": _default_next_action(output_mode),
        "deepen_route_id": f"deepen:{route_id}",
    }
    if output_mode != "ignore_or_blocked":
        result["route_label"] = route_label
        route_topic = _safe_code(packet.get("route_topic"))
        scope_bucket = _safe_code(packet.get("scope_bucket"))
        label_granularity = _safe_code(packet.get("label_granularity"))
        specificity = _confidence_float(packet.get("route_label_specificity_score"))
        if route_topic:
            result["route_topic"] = route_topic
        if scope_bucket:
            result["scope_bucket"] = scope_bucket
        if label_granularity:
            result["label_granularity"] = label_granularity
        if specificity is not None:
            result["route_label_specificity_score"] = specificity
        declared_authority = _as_text(
            packet.get("authority_level") or packet.get("output_authority")
        )
        if (
            declared_authority == authority.AUTHORITY_NAVIGATION_ONLY
            or output_mode in {"direction_only", "bounded_summary_as_route"}
        ):
            result["authority_level"] = authority.AUTHORITY_NAVIGATION_ONLY
        if risk_flags:
            result["risk_flags"] = risk_flags
        if triage_rank_reason_codes and _json_bytes(result) < FOREGROUND_PACKET_BYTE_BUDGET - 96:
            result["triage_rank_reason_codes"] = triage_rank_reason_codes[:2]
    return _fit_memory_packet_budget(result)


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
