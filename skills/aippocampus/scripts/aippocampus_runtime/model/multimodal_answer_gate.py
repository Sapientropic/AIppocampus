#!/usr/bin/env python3
"""Answer-time multimodal source-reopen gate.

This module owns the #543 prototype boundary. It validates a small candidate
packet after multimodal recall/provider routing and before answer generation.
It does not call vision providers, identify people, index devices, or generate
answers.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from aippocampus_runtime.source import multimodal_manifest

ANSWER_GATE_FIXTURE_SCHEMA_VERSION = "aippocampus.multimodal_answer_gate_fixture.v1"

OUTPUT_STATES = {
    "answer_with_reopened_sources",
    "source_reopen_required",
    "abstain_unsupported_detail",
    "blocked_policy_violation",
    "human_review_required",
}
JOIN_REASONS = {
    "temporal_window",
    "entity_reference",
    "place_event",
    "document_payment_relation",
    "source_authority_precedence",
}
RAW_EVIDENCE_MEDIA_TYPES = {
    "image",
    "video_frame",
    "video_segment",
    "receipt",
    "invoice",
    "document_page",
}
PACKET_REQUIRED_FIELDS = ("packet_id", "join_reasons", "candidates")
CASE_REQUIRED_FIELDS = ("case_id", "request", "candidate_packet", "expected_output_state")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _block(code: str, *, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _blocker_codes(blockers: Sequence[Mapping[str, str]]) -> list[str]:
    return sorted({str(item.get("code") or "") for item in blockers if item.get("code")})


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _missing_blocks(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str,
) -> list[dict[str, str]]:
    return [
        _block(
            f"{prefix}_missing_{field}",
            field=field,
            message=f"{field} is required for multimodal answer-gate packets.",
        )
        for field in fields
        if payload.get(field) in (None, "", [], {})
    ]


def _cases(fixture: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]


def _case_by_id(fixture: Mapping[str, Any], case_id: str) -> Mapping[str, Any] | None:
    for case in _cases(fixture):
        if str(case.get("case_id") or "") == case_id:
            return case
    return None


def _packet(case: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(case.get("candidate_packet"))


def _candidates(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in _packet(case).get("candidates") or [] if isinstance(item, Mapping)]


def _selected_candidates(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in _candidates(case) if item.get("selected") is True]


def _candidate_rank(candidate: Mapping[str, Any]) -> tuple[int, int, str]:
    return (
        int(candidate.get("authority_rank") or 0),
        int(candidate.get("finality_rank") or 0),
        str(candidate.get("captured_at") or ""),
    )


def validate_answer_gate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the public-safe answer-gate fixture and packet shape."""

    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != ANSWER_GATE_FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _block(
                "fixture_unsupported_schema_version",
                field="schema_version",
                message="Unsupported multimodal answer-gate fixture schema version.",
            )
        )
    join_reasons: set[str] = set()
    for case in _cases(fixture):
        blockers.extend(_missing_blocks(case, CASE_REQUIRED_FIELDS, prefix="case"))
        packet = _packet(case)
        blockers.extend(_missing_blocks(packet, PACKET_REQUIRED_FIELDS, prefix="packet"))
        unknown_join_reasons = set(_as_list(packet.get("join_reasons"))) - JOIN_REASONS
        if unknown_join_reasons:
            blockers.append(
                _block(
                    "packet_unknown_join_reason",
                    field="candidate_packet.join_reasons",
                    message="Join reasons must come from the #543 taxonomy.",
                )
            )
        join_reasons.update(_as_list(packet.get("join_reasons")))
        for candidate in _candidates(case):
            media_type = str(candidate.get("media_type") or "")
            origin_policy = str(candidate.get("origin_policy") or "")
            if media_type and media_type not in multimodal_manifest.MEDIA_TYPES:
                blockers.append(
                    _block(
                        "candidate_unknown_media_type",
                        field="media_type",
                        message="Candidate media_type must match the multimodal source taxonomy.",
                    )
                )
            if origin_policy and origin_policy not in multimodal_manifest.MEDIA_ORIGIN_POLICIES:
                blockers.append(
                    _block(
                        "candidate_unknown_origin_policy",
                        field="origin_policy",
                        message="Candidate origin_policy must match the source-manifest taxonomy.",
                    )
                )
    return {
        "ok": not blockers,
        "schema_version": ANSWER_GATE_FIXTURE_SCHEMA_VERSION,
        "case_count": len(_cases(fixture)),
        "join_reasons": sorted(join_reasons),
        "truth_boundary": {
            "candidate_packet_is_not_answer": True,
            "join_reasons_are_navigation_only": True,
            "source_reopen_required_for_visual_document_claims": True,
        },
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
    }


def _conflict_precedence_blocks(case: Mapping[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    selected_by_conflict = {
        str(candidate.get("conflict_set_id") or ""): candidate
        for candidate in _selected_candidates(case)
        if candidate.get("conflict_set_id")
    }
    for conflict_set_id, selected in selected_by_conflict.items():
        members = [
            candidate
            for candidate in _candidates(case)
            if str(candidate.get("conflict_set_id") or "") == conflict_set_id
        ]
        if not members:
            continue
        best = max(members, key=_candidate_rank)
        if best.get("source_id") != selected.get("source_id"):
            blockers.append(
                _block(
                    "source_authority_precedence_violation",
                    field="conflict_set_id",
                    message="Selected conflicting evidence is not the latest/final/strongest source.",
                )
            )
    return blockers


def _candidate_blocks(case: Mapping[str, Any]) -> tuple[list[dict[str, str]], dict[str, int]]:
    blockers: list[dict[str, str]] = []
    metrics = {
        "source_reopen_required_violation_count": 0,
        "background_scan_violation_count": 0,
        "hidden_durable_write_violation_count": 0,
    }
    request = _as_mapping(case.get("request"))
    depends_on_raw = bool(set(_as_list(request.get("depends_on_raw_media_types"))))
    requires_visible_detail = request.get("requires_visible_detail") is True
    selected = _selected_candidates(case)

    for candidate in selected:
        media_type = str(candidate.get("media_type") or "")
        origin_policy = str(candidate.get("origin_policy") or "")
        raw_media_claim = depends_on_raw or media_type in RAW_EVIDENCE_MEDIA_TYPES
        background_denied = origin_policy == "background_filesystem_media" and candidate.get(
            "explicitly_selected_or_onboarded"
        ) is not True
        if background_denied:
            metrics["background_scan_violation_count"] += 1
            blockers.append(
                _block(
                    "background_media_denied_by_default",
                    field="origin_policy",
                    message="Background media cannot support answer-time claims without selection.",
                )
            )
        if (
            raw_media_claim
            and not background_denied
            and candidate.get("reopened_original_source") is not True
        ):
            metrics["source_reopen_required_violation_count"] += 1
            blockers.append(
                _block(
                    "source_reopen_required",
                    field="candidate_packet.candidates.reopened_original_source",
                    message="Visual/document claims require reopening the original source anchor.",
                )
            )
        task_access = _as_mapping(candidate.get("task_scoped_access"))
        if task_access.get("hidden_durable_write_performed") is True:
            metrics["hidden_durable_write_violation_count"] += 1
            blockers.append(
                _block(
                    "hidden_durable_write_performed",
                    field="task_scoped_access.hidden_durable_write_performed",
                    message="Task-scoped media use must not silently write durable memory.",
                )
            )

    if requires_visible_detail and not any(
        candidate.get("supports_requested_detail") is True for candidate in selected
    ):
        blockers.append(
            _block(
                "unsupported_detail_not_visible",
                field="request.requested_detail",
                message="Requested detail is not visible or source-backed in reopened evidence.",
            )
        )
    blockers.extend(_conflict_precedence_blocks(case))
    return blockers, metrics


def _output_state(blockers: Sequence[Mapping[str, str]]) -> str:
    codes = set(_blocker_codes(blockers))
    if {"background_media_denied_by_default", "hidden_durable_write_performed"} & codes:
        return "blocked_policy_violation"
    if "source_reopen_required" in codes:
        return "source_reopen_required"
    if "unsupported_detail_not_visible" in codes:
        return "abstain_unsupported_detail"
    if "source_authority_precedence_violation" in codes:
        return "human_review_required"
    return "answer_with_reopened_sources"


def evaluate_answer_gate_case(
    fixture: Mapping[str, Any],
    *,
    case_id: str,
) -> dict[str, Any]:
    """Evaluate one candidate packet and return a sanitized answer-gate report."""

    case = _case_by_id(fixture, case_id)
    if case is None:
        blockers = [
            _block(
                "missing_answer_gate_case",
                field="case_id",
                message="Answer-gate case id does not exist.",
            )
        ]
        metrics = {
            "source_reopen_required_violation_count": 0,
            "background_scan_violation_count": 0,
            "hidden_durable_write_violation_count": 0,
        }
        packet: Mapping[str, Any] = {}
        selected: list[Mapping[str, Any]] = []
        raw_prompt = ""
    else:
        blockers, metrics = _candidate_blocks(case)
        packet = _packet(case)
        selected = _selected_candidates(case)
        raw_prompt = str(_as_mapping(case.get("request")).get("raw_prompt_text") or "")
    output_state = _output_state(blockers)
    return {
        "case_id": case_id,
        "packet_id": packet.get("packet_id"),
        "output_state": output_state,
        "can_emit_answer": output_state == "answer_with_reopened_sources",
        "join_reasons": _as_list(packet.get("join_reasons")),
        "selected_source_ids": sorted(str(item.get("source_id") or "") for item in selected),
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
        "metrics": metrics,
        "candidate_packet_boundary": {
            "candidate_packet_is_not_answer": True,
            "source_reopen_required": True,
            "join_reasons_are_navigation_only": True,
        },
        "cannot_claim": sorted(
            {
                "join_packet_is_answer",
                "derived_artifact_is_source_truth",
                "live_vision_quality",
            }
        ),
        "input_sha1": _sha1_text(raw_prompt) if raw_prompt else None,
        "raw_media_bytes_emitted": False,
        "raw_prompt_text_emitted": False,
    }


def run_answer_gate_smoke(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Run all public-safe answer-gate cases and aggregate #528 metrics."""

    fixture_report = validate_answer_gate_fixture(fixture)
    cases = [
        evaluate_answer_gate_case(fixture, case_id=str(case.get("case_id") or ""))
        for case in _cases(fixture)
        if case.get("case_id")
    ]
    expected = {
        str(case.get("case_id") or ""): str(case.get("expected_output_state") or "")
        for case in _cases(fixture)
        if case.get("case_id")
    }
    unexpected = [
        case
        for case in cases
        if expected.get(str(case.get("case_id") or ""))
        and case.get("output_state") != expected[str(case.get("case_id") or "")]
    ]
    metric_names = (
        "source_reopen_required_violation_count",
        "background_scan_violation_count",
        "hidden_durable_write_violation_count",
    )
    return {
        "kind": "aippocampus_multimodal_answer_gate_smoke",
        "schema_version": 1,
        "ok": bool(fixture_report["ok"] and not unexpected),
        "fixture": fixture_report,
        "metrics": {
            "case_count": len(cases),
            "allowed_answer_count": sum(
                1 for case in cases if case.get("output_state") == "answer_with_reopened_sources"
            ),
            "unexpected_output_state_count": len(unexpected),
            **{
                name: sum(int(_as_mapping(case.get("metrics")).get(name) or 0) for case in cases)
                for name in metric_names
            },
        },
        "cases": cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_media_bytes_emitted": False,
            "raw_prompt_text_emitted": False,
            "absolute_paths_emitted": False,
            "hidden_durable_write_payload_emitted": False,
            "output_shape": "sanitized_ids_hashes_join_reasons_blocker_codes_and_metrics",
        },
        "cannot_claim": [
            "live_provider_vision_quality",
            "full_device_indexing",
            "face_recognition_identity_graph",
            "join_packet_is_answer",
        ],
    }
