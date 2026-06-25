"""Source-window to source-span evidence packaging diagnostics.

The packager tightens a reopenable source window into compact span handles, but
it keeps first-stage retrieval separate and never treats a packaging score as
source truth. Claim-ready packets require already-open, bounded, current, and
unconflicted source input.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_text_non_null_join_id
from aippocampus_runtime.navigation import attention_router_contract


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _range(value: Any) -> list[int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    return None


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value or [] if isinstance(row, Mapping)]


def _safe_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _baseline_window(window: Mapping[str, Any]) -> dict[str, Any]:
    handle = {
        "source_id": _text(window.get("source_id"), "unknown_source"),
        "segment_id": _text(window.get("segment_id") or window.get("window_id"), "unknown_window"),
        "reopen_required": not bool(window.get("source_open")),
    }
    for key in ("turn_range", "line_range"):
        span_range = _range(window.get(key))
        if span_range:
            handle[key] = span_range
    return {
        "window_id": _text(window.get("window_id"))
        or stable_text_non_null_join_id("epkg", window.get("source_id")),
        "source_id": handle["source_id"],
        "segment_id": handle["segment_id"],
        "retrieval_rank": int(window.get("retrieval_rank") or 0),
        "retrieval_score": round(_safe_score(window.get("retrieval_score")), 3),
        "source_window_radius": int(window.get("source_window_radius") or 0),
        "first_stage_retrieval_preserved": True,
        "source_handle": handle,
    }


def _span_rank(span: Mapping[str, Any]) -> int:
    return int(span.get("candidate_rank") or span.get("span_rank") or 9999)


def _span_handle(span: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    source_id = _text(span.get("source_id"), _text(window.get("source_id"), "unknown_source"))
    segment_id = _text(
        span.get("segment_id") or window.get("segment_id") or window.get("window_id"),
        "unknown_segment",
    )
    handle: dict[str, Any] = {
        "source_id": source_id,
        "segment_id": segment_id,
        "reopen_required": not bool(span.get("source_open") or window.get("source_open")),
    }
    for key in ("turn_range", "line_range", "char_range"):
        span_range = _range(span.get(key) or window.get(key))
        if span_range:
            handle[key] = span_range
    return handle


def _metadata(window: Mapping[str, Any], span: Mapping[str, Any]) -> dict[str, str]:
    metadata = {}
    route_metadata = window.get("route_metadata")
    span_metadata = span.get("route_metadata")
    for key in ("currentness", "conflict", "privacy"):
        value = ""
        if isinstance(route_metadata, Mapping):
            value = _text(route_metadata.get(key))
        if isinstance(span_metadata, Mapping) and span_metadata.get(key):
            value = _text(span_metadata.get(key))
        if span.get(key):
            value = _text(span.get(key))
        metadata[key] = value or "unknown"
    return metadata


def _reject_reason(window: Mapping[str, Any], span: Mapping[str, Any]) -> str | None:
    expected_source = _text(window.get("expected_source_id") or window.get("source_id"))
    span_source = _text(span.get("source_id"), expected_source)
    if expected_source and span_source != expected_source:
        return "wrong_source_span"
    if span.get("hard_masks"):
        return "hard_masked_span"
    return None


def _counter_evidence_handles(window: Mapping[str, Any], span: Mapping[str, Any]) -> list[dict[str, Any]]:
    handles = []
    for handle in [*_mappings(window.get("counter_evidence_handles")), *_mappings(span.get("counter_evidence_handles"))]:
        compact = {
            "source_id": _text(handle.get("source_id"), _text(window.get("source_id"), "unknown_source")),
            "segment_id": _text(handle.get("segment_id"), "counter-evidence"),
            "reopen_required": True,
        }
        line_range = _range(handle.get("line_range"))
        if line_range:
            compact["line_range"] = line_range
        handles.append(compact)
    return handles[:4]


def package_source_windows(windows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    cases = [_package_window(window) for window in windows]
    bounded_evidence_packet_count = sum(
        1 for case in cases if case["packet"]["output_mode"] == "bounded_evidence"
    )
    wrong_source_span_promoted_count = sum(
        1
        for case in cases
        if case["packaging"].get("selected_span_reject_reason") == "wrong_source_span"
    )
    stale_or_conflicted_claim_ready_count = sum(
        1
        for case in cases
        if case["packet"]["claim_permission"] == "bounded_claim_allowed"
        and (
            case["packaging"]["include_currentness_check"]
            or case["packaging"]["include_counter_evidence"]
        )
    )
    return {
        "kind": "aippocampus_attention_evidence_packaging_fixture",
        "schema_version": "attention-evidence-packager-v0",
        "ok": wrong_source_span_promoted_count == 0 and stale_or_conflicted_claim_ready_count == 0,
        "cases": cases,
        "metrics": {
            "baseline_window_preserved_count": len(cases),
            "context_visible_packaged_count": sum(
                1 for case in cases if case["packaging"]["selected_span_rank"] > 0
            ),
            "bounded_evidence_packet_count": bounded_evidence_packet_count,
            "wrong_source_span_promoted_count": wrong_source_span_promoted_count,
            "stale_or_conflicted_claim_ready_count": stale_or_conflicted_claim_ready_count,
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "raw_span_text_emitted": False,
            "gold_labels_or_answers_emitted": False,
        },
        "cannot_claim": [
            "exact_line_quality_or_sota",
            "longmemeval_qa_score",
            "reranker_output_as_source_truth",
            "private_history_packaging_quality",
            "default_foreground_router_adoption",
        ],
    }


def _package_window(window: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _baseline_window(window)
    rejected = []
    selected: Mapping[str, Any] | None = None
    for span in sorted(_mappings(window.get("span_candidates")), key=_span_rank):
        reason = _reject_reason(window, span)
        if reason:
            rejected.append(
                {
                    "span_id": _text(span.get("span_id"), "unknown_span"),
                    "span_rank": _span_rank(span),
                    "reason_code": reason,
                }
            )
            continue
        selected = span
        break

    if selected is None:
        packet = attention_router_contract.build_route_packet(
            {"case_id": window.get("case_id"), "head_votes": [_head_vote(0.0, "no_valid_span")]}
        )
        packaging = _packaging_summary(window, selected=None, packet=packet, rejected=rejected)
        return {"case_id": _text(window.get("case_id")), "baseline_window": baseline, "packaging": packaging, "packet": packet}

    metadata = _metadata(window, selected)
    stale = metadata["currentness"] in {"stale", "superseded", "needs_reopen"}
    conflicted = metadata["conflict"] not in {"", "none", "unknown"}
    claim_ready_input = (
        bool(window.get("source_open") or selected.get("source_open"))
        and bool(window.get("bounded_scope") or selected.get("bounded_scope"))
        and not stale
        and not conflicted
    )
    reason_code = "context_visible_span_packaged"
    if stale:
        reason_code += "+currentness_check_required"
    if conflicted:
        reason_code += "+counter_evidence_required"
    packet = attention_router_contract.build_route_packet(
        {
            "case_id": window.get("case_id"),
            "source_handles": [_span_handle(selected, window)],
            "source_open": claim_ready_input,
            "bounded_scope": claim_ready_input,
            "head_votes": [_head_vote(_safe_score(selected.get("packaging_score")), reason_code)],
        }
    )
    packaging = _packaging_summary(
        window,
        selected=selected,
        packet=packet,
        rejected=rejected,
        metadata=metadata,
        counter_evidence_handles=_counter_evidence_handles(window, selected) if conflicted else [],
    )
    return {"case_id": _text(window.get("case_id")), "baseline_window": baseline, "packaging": packaging, "packet": packet}


def _head_vote(score: float, reason_code: str) -> dict[str, Any]:
    return {
        "head": "evidence_packaging_head",
        "score": round(score, 3),
        "reason_code": reason_code,
    }


def _packaging_summary(
    window: Mapping[str, Any],
    *,
    selected: Mapping[str, Any] | None,
    packet: Mapping[str, Any],
    rejected: list[dict[str, Any]],
    metadata: Mapping[str, str] | None = None,
    counter_evidence_handles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    currentness = metadata.get("currentness", "unknown")
    conflict = metadata.get("conflict", "unknown")
    selected_rank = _span_rank(selected) if selected is not None else 0
    return {
        "window_radius": int(window.get("source_window_radius") or 0),
        "candidate_count": len(_mappings(window.get("span_candidates"))),
        "selected_span_id": _text(selected.get("span_id")) if selected is not None else "",
        "selected_span_rank": selected_rank,
        "selected_span_reject_reason": "",
        "rejected_span_candidates": rejected,
        "include_currentness_check": currentness in {"stale", "superseded", "needs_reopen"},
        "include_counter_evidence": conflict not in {"", "none", "unknown"},
        "counter_evidence_handles": counter_evidence_handles or [],
        "currentness": currentness,
        "conflict": conflict,
        "claim_permission": _text(packet.get("claim_permission"), "no_claim_before_reopen"),
    }


def build_evidence_packaging_fixture_report() -> dict[str, Any]:
    return package_source_windows(fixture_source_windows())


def fixture_source_windows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "context_visible_span_becomes_bounded_evidence",
            "window_id": "window-public-route",
            "source_id": "clean:attention-router",
            "segment_id": "msg-7",
            "retrieval_rank": 2,
            "retrieval_score": 0.83,
            "source_window_radius": 5,
            "line_range": [40, 58],
            "source_open": True,
            "bounded_scope": True,
            "source_text": "PRIVATE_SOURCE_WINDOW_TEXT_SENTINEL",
            "span_candidates": [
                {
                    "span_id": "span-public-evidence",
                    "candidate_rank": 1,
                    "source_id": "clean:attention-router",
                    "segment_id": "msg-7",
                    "line_range": [45, 53],
                    "char_range": [128, 220],
                    "packaging_score": 0.91,
                    "route_metadata": {"currentness": "current", "conflict": "none", "privacy": "public"},
                    "text": "PRIVATE_SPAN_TEXT_SENTINEL",
                },
                {"span_id": "span-near-context", "candidate_rank": 2, "source_id": "clean:attention-router", "packaging_score": 0.62},
                {"span_id": "span-wide-window", "candidate_rank": 3, "source_id": "clean:attention-router", "packaging_score": 0.41},
            ],
        },
        {
            "case_id": "wrong_source_top_span_rejected",
            "window_id": "window-wrong-source-control",
            "source_id": "clean:attention-router",
            "expected_source_id": "clean:attention-router",
            "segment_id": "msg-8",
            "retrieval_rank": 1,
            "retrieval_score": 0.88,
            "source_window_radius": 5,
            "source_open": True,
            "bounded_scope": True,
            "span_candidates": [
                {"span_id": "span-wrong-source", "candidate_rank": 1, "source_id": "clean:other-thread", "packaging_score": 0.98},
                {"span_id": "span-fallback-valid", "candidate_rank": 2, "source_id": "clean:attention-router", "line_range": [60, 64], "packaging_score": 0.77, "route_metadata": {"currentness": "current", "conflict": "none"}},
            ],
        },
        {
            "case_id": "stale_span_requires_currentness_check",
            "window_id": "window-stale-control",
            "source_id": "clean:attention-router",
            "segment_id": "msg-9",
            "retrieval_rank": 3,
            "retrieval_score": 0.71,
            "source_window_radius": 5,
            "source_open": True,
            "bounded_scope": True,
            "span_candidates": [
                {"span_id": "span-stale", "candidate_rank": 1, "source_id": "clean:attention-router", "line_range": [70, 75], "packaging_score": 0.85, "route_metadata": {"currentness": "stale", "conflict": "none"}},
            ],
        },
        {
            "case_id": "conflicted_span_packages_counter_evidence",
            "window_id": "window-conflict-control",
            "source_id": "clean:attention-router",
            "segment_id": "msg-10",
            "retrieval_rank": 4,
            "retrieval_score": 0.7,
            "source_window_radius": 8,
            "source_open": True,
            "bounded_scope": True,
            "counter_evidence_handles": [
                {"source_id": "clean:attention-router", "segment_id": "counter-conflict-note", "line_range": [90, 92]}
            ],
            "span_candidates": [
                {"span_id": "span-conflicted", "candidate_rank": 1, "source_id": "clean:attention-router", "line_range": [84, 88], "packaging_score": 0.82, "route_metadata": {"currentness": "current", "conflict": "conflicted"}},
            ],
        },
    ]
