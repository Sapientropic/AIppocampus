"""Source-backed attention-router contract helpers.

This module is deliberately a contract surface, not the router implementation.
Hard masks run before score interpretation, and emitted values are route
handles/source handles only. Later attention heads should consume this shape
instead of inventing a parallel evidence or memory-fact layer.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Literal

ACTION_GRAMMARS = {
    "direction_only",
    "reopenable_route",
    "bounded_evidence",
    "ignore_or_blocked",
}
CLAIM_PERMISSIONS = {
    "no_claim_before_reopen",
    "bounded_claim_allowed",
    "blocked",
}
HARD_MASKS = {
    "privacy_domain",
    "source_visibility",
    "transfer_allowed",
    "deleted_source",
    "no_recall",
    "no_cross_domain",
    "stale_handle_invalid",
    "high_risk_no_source",
}

OutputMode = Literal[
    "silence",
    "direction_only",
    "bounded_summary_as_route",
    "reopenable_route",
    "bounded_evidence",
]
ClaimPermission = Literal["no_claim_before_reopen", "bounded_claim_allowed", "blocked"]


def _stable_id(*parts: Any, prefix: str = "rt") -> str:
    payload = "|".join(str(part) for part in parts if part is not None)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _compact_source_handle(handle: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_id": str(handle.get("source_id") or ""),
        "segment_id": str(handle.get("segment_id") or ""),
        "reopen_required": bool(handle.get("reopen_required", True)),
    }
    turn_range = handle.get("turn_range")
    if isinstance(turn_range, (list, tuple)) and len(turn_range) == 2:
        result["turn_range"] = [int(turn_range[0]), int(turn_range[1])]
    for range_key in ("line_range", "char_range"):
        span_range = handle.get(range_key)
        if isinstance(span_range, (list, tuple)) and len(span_range) == 2:
            result[range_key] = [int(span_range[0]), int(span_range[1])]
    return result


def _head_vote(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "head": str(row.get("head") or "unknown_head"),
        "score": float(row.get("score") or 0.0),
        "reason_code": str(row.get("reason_code") or "unspecified"),
    }


def _hard_masks(candidate: Mapping[str, Any]) -> list[str]:
    masks = []
    for mask in candidate.get("hard_masks") or []:
        name = str(mask)
        if name in HARD_MASKS:
            masks.append(name)
    return sorted(set(masks))


def _strings(values: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    result = []
    for value in values:
        text = str(value or "").strip()
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _optional_text(candidate: Mapping[str, Any], key: str) -> str:
    return str(candidate.get(key) or "").strip()


def _copy_triage_preview_fields(packet: dict[str, Any], candidate: Mapping[str, Any]) -> None:
    """Keep safe route-selection hints with the route packet, never evidence.

    These fields are small labels/reason codes for the agent facade to clean and
    budget. They deliberately exclude source refs, handles, raw snippets, head
    votes, and scoring internals.
    """

    for key in ("route_label", "why_may_matter", "preview_permission", "route_kind", "currentness", "conflict"):
        value = _optional_text(candidate, key)
        if value:
            packet[key] = value
    for key in ("risk_flags", "triage_rank_reason_codes"):
        values = _strings(candidate.get(key), limit=6)
        if values:
            packet[key] = values


def _summary_fallback_reason_codes(summary: Mapping[str, Any] | None) -> list[str]:
    if summary is None:
        return []
    reasons = []
    if not str(summary.get("scope") or "").strip():
        reasons.append("summary_scope_missing")
    if not _strings(summary.get("source_coverage")):
        reasons.append("summary_coverage_missing")
    if not str(summary.get("freshness") or "").strip():
        reasons.append("summary_freshness_missing")
    if not str(summary.get("reopen_path") or "").strip():
        reasons.append("summary_reopen_path_missing")
    if summary.get("stale") or str(summary.get("freshness") or "").strip().lower() == "stale":
        reasons.append("summary_stale")
    if summary.get("coverage_weak"):
        reasons.append("summary_coverage_weak")
    if summary.get("conflicted"):
        reasons.append("summary_conflicted")
    if summary.get("high_risk"):
        reasons.append("summary_high_risk")
    return sorted(set(reasons))


def _compact_bounded_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scope": str(summary.get("scope") or "").strip(),
        "source_coverage": _strings(summary.get("source_coverage")),
        "freshness": str(summary.get("freshness") or "").strip(),
        "claim_permission": "no_claim_before_reopen",
        "reopen_path": str(summary.get("reopen_path") or "").strip(),
    }


def build_route_packet(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Project a candidate into the #1107 route-packet contract.

    Relevance scores never override hard masks. Bounded evidence is available
    only when the caller marks source as already open and bounded to a declared
    scope; otherwise source-backed candidates remain reopenable routes.
    """

    route_id = str(candidate.get("route_id") or "") or _stable_id(
        candidate.get("case_id"),
        candidate.get("source_handles"),
    )
    masks = _hard_masks(candidate)
    head_votes = [_head_vote(row) for row in candidate.get("head_votes") or []]
    source_handles = [
        _compact_source_handle(handle)
        for handle in candidate.get("source_handles") or []
        if isinstance(handle, Mapping)
    ]
    summary_input = candidate.get("bounded_summary")
    bounded_summary = (
        _compact_bounded_summary(summary_input) if isinstance(summary_input, Mapping) else None
    )
    summary_fallback_reason_codes = _summary_fallback_reason_codes(
        summary_input if isinstance(summary_input, Mapping) else None
    )

    if masks:
        output_mode: OutputMode = "silence"
        claim_permission: ClaimPermission = "blocked"
        emitted = False
        action_grammar = "ignore_or_blocked"
    elif candidate.get("source_open") and candidate.get("bounded_scope"):
        output_mode = "bounded_evidence"
        claim_permission = "bounded_claim_allowed"
        emitted = True
        action_grammar = "bounded_evidence"
    elif bounded_summary and not summary_fallback_reason_codes:
        output_mode = "bounded_summary_as_route"
        claim_permission = "no_claim_before_reopen"
        emitted = True
        action_grammar = "direction_only"
    elif source_handles:
        output_mode = "reopenable_route"
        claim_permission = "no_claim_before_reopen"
        emitted = True
        action_grammar = "reopenable_route"
    else:
        output_mode = "direction_only"
        claim_permission = "no_claim_before_reopen"
        emitted = True
        action_grammar = "direction_only"

    packet: dict[str, Any] = {
        "kind": "aippocampus_attention_route_packet",
        "schema_version": "attention-router-contract-v0",
        "route_id": route_id,
        "output_mode": output_mode,
        "action_grammar": action_grammar,
        "claim_permission": claim_permission,
        "emitted": emitted,
        "source_handles": [] if masks else source_handles,
        "head_votes": head_votes,
        "masks_applied": masks,
        "contract": {
            "hard_masks_are_gates": True,
            "attention_score_is_not_evidence": True,
            "route_value_is_not_memory_fact": True,
            "bounded_summary_is_route_not_evidence": True,
            "source_reopen_required_before_claim": claim_permission == "no_claim_before_reopen",
        },
    }
    if output_mode == "bounded_summary_as_route" and bounded_summary is not None:
        packet["bounded_summary"] = bounded_summary
    if summary_fallback_reason_codes:
        packet["summary_fallback_reason_codes"] = summary_fallback_reason_codes
    _copy_triage_preview_fields(packet, candidate)
    return packet


def fixture_candidates() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "privacy_mask_beats_high_relevance",
            "hard_masks": ["privacy_domain"],
            "source_handles": [
                {
                    "source_id": "src_private_masked",
                    "segment_id": "seg_masked",
                    "turn_range": [12, 14],
                    "reopen_required": True,
                    "source_text": "PRIVATE_ROUTER_TEXT_SENTINEL",
                }
            ],
            "head_votes": [
                {"head": "lexical_head", "score": 0.99, "reason_code": "exact_issue_id_match"},
                {"head": "semantic_head", "score": 0.98, "reason_code": "semantic_bridge"},
            ],
        },
        {
            "case_id": "source_backed_reopenable_route",
            "source_handles": [
                {
                    "source_id": "src_public_route",
                    "segment_id": "seg_reopen",
                    "turn_range": [4, 6],
                    "reopen_required": True,
                }
            ],
            "head_votes": [
                {"head": "lexical_head", "score": 0.86, "reason_code": "path_match"},
            ],
        },
        {
            "case_id": "source_open_bounded_evidence",
            "source_open": True,
            "bounded_scope": True,
            "source_handles": [
                {
                    "source_id": "src_open",
                    "segment_id": "seg_bounded",
                    "turn_range": [20, 21],
                    "reopen_required": False,
                }
            ],
            "head_votes": [
                {"head": "evidence_packaging_head", "score": 0.91, "reason_code": "source_open_span"},
            ],
        },
        {
            "case_id": "source_thin_direction_only",
            "source_handles": [],
            "head_votes": [
                {"head": "abstention_head", "score": 0.55, "reason_code": "weak_route_scent"},
            ],
        },
        {
            "case_id": "bounded_summary_as_route",
            "bounded_summary": {
                "scope": "project:AIppocampus",
                "source_coverage": ["discussion:#1106", "issue:#1107"],
                "freshness": "regenerated_at:2026-06-10T18:49:00+08:00",
                "reopen_path": "summarize -> re-summarize by selected source spans",
                "summary_text": "PRIVATE_SUMMARY_TEXT_SENTINEL",
            },
            "head_votes": [
                {"head": "summary_head", "score": 0.82, "reason_code": "bounded_low_risk_summary"},
            ],
        },
        {
            "case_id": "stale_summary_falls_back_to_direction_only",
            "bounded_summary": {
                "scope": "project:AIppocampus",
                "source_coverage": ["issue:#250"],
                "freshness": "stale",
                "reopen_path": "refresh familiarity source refs before use",
                "coverage_weak": True,
                "stale": True,
                "summary_text": "PRIVATE_SUMMARY_TEXT_SENTINEL",
            },
            "head_votes": [
                {"head": "summary_head", "score": 0.48, "reason_code": "stale_weak_summary"},
            ],
        },
    ]


def build_contract_fixture_report(
    candidates: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates if candidates is not None else fixture_candidates():
        packet = build_route_packet(candidate)
        rows.append(
            {
                "case_id": str(candidate.get("case_id") or packet["route_id"]),
                "packet": packet,
            }
        )

    masked_source_resurrection_count = 0
    source_backed_claim_without_reopen = 0
    summary_claim_ready_without_reopen_count = 0
    bounded_summary_fallback_count = 0
    for row in rows:
        packet = row["packet"]
        if packet["masks_applied"] and packet["emitted"]:
            masked_source_resurrection_count += 1
        if packet["claim_permission"] == "bounded_claim_allowed" and not any(
            bool(handle.get("reopen_required") is False)
            for handle in packet.get("source_handles") or []
        ):
            source_backed_claim_without_reopen += 1
        if (
            packet["output_mode"] == "bounded_summary_as_route"
            and packet["claim_permission"] != "no_claim_before_reopen"
        ):
            summary_claim_ready_without_reopen_count += 1
        if packet.get("summary_fallback_reason_codes"):
            bounded_summary_fallback_count += 1

    return {
        "kind": "aippocampus_attention_router_contract_fixture",
        "schema_version": "attention-router-contract-v0",
        "ok": (
            masked_source_resurrection_count == 0
            and source_backed_claim_without_reopen == 0
            and summary_claim_ready_without_reopen_count == 0
        ),
        "cases": rows,
        "metrics": {
            "case_count": len(rows),
            "masked_source_resurrection_count": masked_source_resurrection_count,
            "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
            "summary_claim_ready_without_reopen_count": summary_claim_ready_without_reopen_count,
            "bounded_summary_fallback_count": bounded_summary_fallback_count,
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "private_text_emitted": False,
            "route_packets_are_handles_only": True,
        },
        "cannot_claim": [
            "broad_attention_router_quality",
            "private_history_behavior_quality",
            "model_training_or_learned_attention",
            "route_packet_as_source_truth",
            "default_foreground_router_adoption",
        ],
    }
