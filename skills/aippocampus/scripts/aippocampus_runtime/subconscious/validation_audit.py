#!/usr/bin/env python3
"""Non-text validation diagnostics for subconscious model findings."""

from __future__ import annotations

from collections import Counter
from typing import Any

from aippocampuslib import compact_text
from semantic_scope_labels import filtered_semantic_scope_labels
from subconscious_job_circuits import JOB_SPECS
from subconscious_job_validation import (
    ALLOWED_QUESTION_FINDING_KINDS,
    QUESTION_TEXT_MAX_CHARS,
    compact_string_list,
    exact_message_refs_for_semantic_label,
    refs_for_finding,
    short_question_fallback,
    validate_cognitive_map_fields,
)
from subconscious_worker import clamp_confidence


def validation_rejection_reason(
    job: str, item: Any, source_bank: dict[str, dict[str, Any]]
) -> str | None:
    if not isinstance(item, dict):
        return "not_object"
    confidence = clamp_confidence(item.get("confidence"))
    if confidence < 0.45:
        return "missing_or_low_confidence"
    refs = refs_for_finding(item, source_bank)
    if not refs:
        return "missing_or_unresolved_source_refs"
    summary = compact_text(str(item.get("summary") or item.get("why") or ""), 480)
    if job == "concept_edges":
        src = compact_text(str(item.get("src") or ""), 100)
        dst = compact_text(str(item.get("dst") or ""), 100)
        if not src or not dst:
            return "concept_edge_missing_src_or_dst"
        if src.casefold() == dst.casefold():
            return "concept_edge_self_edge"
    if job == "question_extraction":
        kind = str(item.get("kind") or "").strip()
        if kind not in ALLOWED_QUESTION_FINDING_KINDS:
            kind = "question_candidate"
        if kind == "question_candidate":
            raw_question_text = str(item.get("question_text") or item.get("question") or "").strip()
            if len(raw_question_text) > QUESTION_TEXT_MAX_CHARS and not short_question_fallback(item):
                return "question_text_too_long_without_short_label"
            if not compact_text(raw_question_text, QUESTION_TEXT_MAX_CHARS):
                return "question_missing_question_text"
        else:
            boundary_reason = compact_text(
                str(item.get("boundary_reason") or item.get("summary") or ""), 260
            )
            if not boundary_reason:
                return "frontier_missing_boundary_reason"
    if job == "cognitive_map":
        landmarks = compact_string_list(item.get("landmarks") or item.get("concepts"), limit=10)
        route_cues = compact_string_list(item.get("route_cues") or item.get("aliases"), limit=16)
        if not landmarks:
            return "cognitive_map_missing_landmarks"
        if not route_cues:
            return "cognitive_map_missing_route_cues"
        if not validate_cognitive_map_fields(item, refs):
            return "cognitive_map_unresolved_target_thread"
    if job == "semantic_scope_labeling":
        message_id = str(item.get("message_id") or item.get("target_message_id") or "").strip()
        labels = filtered_semantic_scope_labels(
            item, list(item.get("scope_labels") or item.get("labels") or [])
        )
        if not message_id:
            return "semantic_scope_missing_message_id"
        if not labels:
            return "semantic_scope_missing_valid_labels"
        if not exact_message_refs_for_semantic_label(message_id, refs):
            return "semantic_scope_unresolved_message_ref"
    if job == "theme_emergence":
        shared_concepts = compact_string_list(
            item.get("shared_concepts") or item.get("concepts"), limit=12
        )
        source_link_ids = compact_string_list(
            item.get("source_question_link_ids") or item.get("question_link_ids"),
            limit=12,
            chars=120,
        )
        theme_label = compact_text(str(item.get("theme_label") or item.get("title") or ""), 140)
        theme_short = compact_text(
            str(item.get("theme_short") or (shared_concepts[0] if shared_concepts else "")), 90
        )
        cluster_method = compact_text(str(item.get("cluster_method") or ""), 80)
        if not (theme_label and theme_short and cluster_method and shared_concepts and source_link_ids):
            return "theme_candidate_missing_required_fields"
        if "llm" in cluster_method.casefold():
            return "theme_candidate_llm_cluster_method"
        shared_short_keys = {compact_text(concept, 90).casefold() for concept in shared_concepts}
        if theme_short.casefold() not in shared_short_keys:
            return "theme_candidate_short_not_shared_concept"
    if not summary and job != "concept_edges":
        return "missing_summary"
    return None


def validation_audit(
    job: str, parsed: dict[str, Any], source_bank: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    spec = JOB_SPECS[job]
    raw_findings = parsed.get("findings") if isinstance(parsed, dict) else None
    if not isinstance(raw_findings, list):
        return {
            "job": job,
            "raw_finding_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "raw_by_kind": {},
            "accepted_by_kind": {},
            "rejection_reasons": {"findings_not_list": 1},
        }
    raw_by_kind: Counter[str] = Counter()
    accepted_by_kind: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    for item in raw_findings:
        kind = (
            str(item.get("kind") or spec["finding_kind"])
            if isinstance(item, dict)
            else "not_object"
        )
        raw_by_kind[kind] += 1
        reason = validation_rejection_reason(job, item, source_bank)
        if reason:
            rejection_reasons[reason] += 1
        else:
            accepted_by_kind[kind] += 1
    return {
        "job": job,
        "raw_finding_count": len(raw_findings),
        "accepted_count": sum(accepted_by_kind.values()),
        "rejected_count": sum(rejection_reasons.values()),
        "raw_by_kind": dict(sorted(raw_by_kind.items())),
        "accepted_by_kind": dict(sorted(accepted_by_kind.items())),
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
    }
