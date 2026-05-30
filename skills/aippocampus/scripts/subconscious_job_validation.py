#!/usr/bin/env python3
"""Source-backed finding validation for subconscious job outputs.

The runner should only ask the model, call tools, and coordinate writes. This
module owns the contract that turns model `findings` into durable staging rows:
source refs must resolve, confidence must be high enough, and job-specific
fields must be compact and safe for later promotion/review.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from aippocampuslib import compact_text
from build_clean_source import SCOPE_LABEL_ORDER
from semantic_scope_labels import filtered_semantic_scope_labels, label_evidence_for_labels
from subconscious_job_circuits import JOB_SPECS
from subconscious_worker import ALLOWED_EDGE_TYPES, clamp_confidence


def normalize_for_fingerprint(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def finding_fingerprint(finding: dict[str, Any]) -> str:
    parts = [
        normalize_for_fingerprint(str(finding.get("job") or "")),
        normalize_for_fingerprint(str(finding.get("kind") or finding.get("finding_kind") or "")),
        normalize_for_fingerprint(str(finding.get("title") or "")),
        normalize_for_fingerprint(str(finding.get("src") or "")),
        normalize_for_fingerprint(str(finding.get("dst") or "")),
        normalize_for_fingerprint(str(finding.get("edge_type") or "")),
        normalize_for_fingerprint(str(finding.get("question_text") or "")),
        normalize_for_fingerprint(str(finding.get("frontier_type") or "")),
        normalize_for_fingerprint(str(finding.get("theme_cluster_id") or "")),
        normalize_for_fingerprint(str(finding.get("theme_label") or "")),
        normalize_for_fingerprint(str(finding.get("message_id") or "")),
        normalize_for_fingerprint(
            " ".join(str(label) for label in finding.get("scope_labels") or [])
        ),
    ]
    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"sf_{digest}"


def quality_bucket(score: float) -> str:
    if score >= 0.82:
        return "strong"
    if score >= 0.64:
        return "usable"
    if score >= 0.48:
        return "weak"
    return "noise"


def estimate_finding_quality(job: str, finding: dict[str, Any]) -> dict[str, Any]:
    refs = [ref for ref in finding.get("source_refs") or [] if isinstance(ref, dict)]
    confidence = clamp_confidence(finding.get("confidence"))
    ref_count = len(refs)
    thread_count = len({str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")})
    final_refs = sum(
        1
        for ref in refs
        if ref.get("assistant_line") or ref.get("source_line") or ref.get("message_id")
    )
    summary_len = len(str(finding.get("summary") or finding.get("why") or ""))
    recommendation = bool(str(finding.get("recommendation") or "").strip())
    evidence_strength = min(1.0, 0.35 + ref_count * 0.16 + thread_count * 0.10 + final_refs * 0.06)
    specificity = min(
        1.0, 0.25 + min(summary_len, 420) / 600 + min(len(finding.get("concepts") or []), 6) * 0.04
    )
    actionability = 0.35 + (0.28 if recommendation else 0.0)
    if job in {
        "question_extraction",
        "decision_evolution",
        "project_drift",
        "preference_candidates",
        "contradiction_scan",
    }:
        actionability += 0.12
    if job == "cognitive_map":
        actionability += 0.10
    novelty = 0.58
    if job == "concept_edges":
        novelty += 0.08 if finding.get("src") and finding.get("dst") else -0.12
    drift_risk = 0.20
    if job in {"contradiction_scan", "preference_candidates"}:
        drift_risk += 0.20
    if confidence < 0.65:
        drift_risk += 0.15
    promotion_readiness = (
        confidence * 0.34
        + evidence_strength * 0.26
        + specificity * 0.18
        + actionability * 0.14
        + novelty * 0.08
        - drift_risk * 0.12
    )
    promotion_readiness = max(0.0, min(1.0, promotion_readiness))
    return {
        "evidence_strength": round(evidence_strength, 4),
        "specificity": round(specificity, 4),
        "novelty": round(novelty, 4),
        "actionability": round(min(1.0, actionability), 4),
        "drift_risk": round(min(1.0, drift_risk), 4),
        "promotion_readiness": round(promotion_readiness, 4),
        "bucket": quality_bucket(promotion_readiness),
        "signals": {
            "source_ref_count": ref_count,
            "source_thread_count": thread_count,
            "has_recommendation": recommendation,
        },
    }


def normalize_ref_id(ref_item: Any) -> str:
    if isinstance(ref_item, str):
        return ref_item.strip()
    if isinstance(ref_item, dict):
        return str(
            ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or ""
        ).strip()
    return ""


def refs_for_finding(
    finding: dict[str, Any], source_bank: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref_item in finding.get("source_refs") or []:
        ref_id = normalize_ref_id(ref_item)
        source = source_bank.get(ref_id)
        if not source:
            continue
        ref = {
            "ref": ref_id,
            "turn_ref": source.get("turn_ref"),
            "thread_key": source.get("thread_key"),
            "title": source.get("title"),
            "project_label": source.get("project_label"),
            "turn_id": source.get("turn_id"),
            "turn_index": source.get("turn_index"),
            "user_line": source.get("user_line"),
            "assistant_line": source.get("assistant_line"),
            "source_line": source.get("source_line"),
            "message_id": source.get("message_id"),
            "timestamp": source.get("timestamp"),
        }
        scope_labels = canonical_scope_labels(source.get("scope_labels"))
        semantic_scope_labels = canonical_scope_labels(source.get("semantic_scope_labels"))
        if scope_labels:
            ref["scope_labels"] = scope_labels
        if semantic_scope_labels:
            ref["semantic_scope_labels"] = semantic_scope_labels
        message_refs = compact_source_message_refs(source.get("source_refs"), source)
        if message_refs:
            ref["message_refs"] = message_refs
        refs.append(ref)
    return refs[:5]


def compact_source_message_refs(values: Any, source: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            continue
        out.append(
            {
                "ref": source.get("ref"),
                "turn_ref": source.get("turn_ref"),
                "thread_key": item.get("thread_key") or source.get("thread_key"),
                "message_id": message_id,
                "turn_id": item.get("turn_id") or source.get("turn_id"),
                "source_line": item.get("source_line"),
                "role": item.get("role"),
                "phase": item.get("phase") or "",
            }
        )
    return out[:8]


def compact_string_list(values: Any, *, limit: int = 12, chars: int = 90) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, list):
        source = values
    else:
        source = []
    out: list[str] = []
    for value in source:
        text = compact_text(str(value or "").strip(), chars)
        if text:
            out.append(text)
    return list(dict.fromkeys(out))[:limit]


def validate_cognitive_map_fields(
    item: dict[str, Any], refs: list[dict[str, Any]]
) -> dict[str, Any] | None:
    landmarks = compact_string_list(item.get("landmarks") or item.get("concepts"), limit=10)
    regions = compact_string_list(item.get("regions"), limit=8)
    route_cues = compact_string_list(item.get("route_cues") or item.get("aliases"), limit=16)
    if not landmarks or not route_cues:
        return None
    ref_threads = list(
        dict.fromkeys(str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key"))
    )
    requested = compact_string_list(item.get("target_thread_keys"), limit=16)
    target_thread_keys = [key for key in requested if key in ref_threads] or ref_threads
    if not target_thread_keys:
        return None
    route_kind = str(item.get("route_kind") or "association").strip() or "association"
    if route_kind not in {"association", "preplay", "detour", "blocked_route"}:
        route_kind = "association"
    return {
        "landmarks": landmarks,
        "regions": regions,
        "route_cues": route_cues,
        "negative_cues": compact_string_list(item.get("negative_cues"), limit=10),
        "target_thread_keys": target_thread_keys,
        "route_kind": route_kind,
    }


ALLOWED_QUESTION_FINDING_KINDS = {"question_candidate", "frontier_marker"}
ALLOWED_FRONTIER_TYPES = {
    "unresolved",
    "blocked",
    "deferred",
    "unsatisfied",
    "needs_external_evidence",
    "scope_boundary",
}
QUESTION_TEXT_MAX_CHARS = 140


def short_question_fallback(item: dict[str, Any]) -> str:
    for key in ("question_short", "title"):
        value = compact_text(str(item.get(key) or ""), QUESTION_TEXT_MAX_CHARS)
        if value:
            return value
    return ""


def validate_question_fields(item: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(item.get("kind") or "").strip()
    if kind not in ALLOWED_QUESTION_FINDING_KINDS:
        kind = "question_candidate"
    if kind == "question_candidate":
        raw_question_text = str(item.get("question_text") or item.get("question") or "").strip()
        question_text = compact_text(raw_question_text, QUESTION_TEXT_MAX_CHARS)
        question_text_compressed = False
        if len(raw_question_text) > QUESTION_TEXT_MAX_CHARS:
            fallback = short_question_fallback(item)
            if not fallback:
                return None
            question_text = fallback
            question_text_compressed = True
        if not question_text:
            return None
        return {
            "kind": kind,
            "question_text": question_text,
            "question_text_compressed": question_text_compressed,
            "question_short": compact_text(
                str(item.get("question_short") or item.get("title") or ""), 90
            ),
            "intent_orientation": compact_text(str(item.get("intent_orientation") or ""), 80),
            "what_features": compact_string_list(
                item.get("what_features") or item.get("concepts"), limit=10
            ),
            "where_context": compact_string_list(item.get("where_context"), limit=8),
            "phase_context": compact_text(str(item.get("phase_context") or ""), 80),
            "collaboration_context": compact_string_list(
                item.get("collaboration_context"), limit=8
            ),
        }

    frontier_type = str(item.get("frontier_type") or "unresolved").strip()
    if frontier_type not in ALLOWED_FRONTIER_TYPES:
        frontier_type = "unresolved"
    boundary_reason = compact_text(
        str(item.get("boundary_reason") or item.get("summary") or ""), 260
    )
    if not boundary_reason:
        return None
    return {
        "kind": kind,
        "frontier_type": frontier_type,
        "boundary_reason": boundary_reason,
        "linked_question_short": compact_text(
            str(item.get("linked_question_short") or item.get("question_short") or ""), 90
        ),
        "intent_orientation": compact_text(str(item.get("intent_orientation") or ""), 80),
        "where_context": compact_string_list(item.get("where_context"), limit=8),
        "phase_context": compact_text(str(item.get("phase_context") or ""), 80),
        "collaboration_context": compact_string_list(item.get("collaboration_context"), limit=8),
    }


def canonical_scope_labels(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    present = {str(value) for value in values if isinstance(value, str)}
    return [label for label in SCOPE_LABEL_ORDER if label in present]


def scope_label_fields_from_source_refs(refs: list[dict[str, Any]]) -> dict[str, Any]:
    base_labels: list[str] = []
    semantic_labels: list[str] = []
    for ref in refs:
        base_labels.extend(str(label) for label in ref.get("scope_labels") or [])
        semantic_labels.extend(str(label) for label in ref.get("semantic_scope_labels") or [])
    semantic_scope_labels = canonical_scope_labels(semantic_labels)
    scope_labels = canonical_scope_labels([*base_labels, *semantic_scope_labels])
    out: dict[str, Any] = {}
    if scope_labels:
        out["scope_labels"] = scope_labels
    if semantic_scope_labels:
        out["semantic_scope_labels"] = semantic_scope_labels
    return out


def exact_message_refs_for_semantic_label(
    message_id: str, refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    for ref in refs:
        if str(ref.get("message_id") or "").strip() == message_id:
            exact.append(
                {
                    "ref": ref.get("ref"),
                    "turn_ref": ref.get("turn_ref"),
                    "thread_key": ref.get("thread_key"),
                    "message_id": ref.get("message_id"),
                    "turn_id": ref.get("turn_id"),
                    "source_line": ref.get("source_line"),
                }
            )
        for message_ref in ref.get("message_refs") or []:
            if not isinstance(message_ref, dict):
                continue
            if str(message_ref.get("message_id") or "").strip() != message_id:
                continue
            exact.append(
                {
                    "ref": message_ref.get("ref") or ref.get("ref"),
                    "turn_ref": message_ref.get("turn_ref") or ref.get("turn_ref"),
                    "thread_key": message_ref.get("thread_key") or ref.get("thread_key"),
                    "message_id": message_ref.get("message_id"),
                    "turn_id": message_ref.get("turn_id") or ref.get("turn_id"),
                    "source_line": message_ref.get("source_line"),
                    "role": message_ref.get("role"),
                    "phase": message_ref.get("phase") or "",
                }
            )
    deduped = {
        str(item.get("message_id") or "") + ":" + str(item.get("source_line") or ""): item
        for item in exact
    }
    return list(deduped.values())[:5]


def validate_semantic_scope_label_fields(
    item: dict[str, Any], refs: list[dict[str, Any]]
) -> dict[str, Any] | None:
    message_id = str(item.get("message_id") or item.get("target_message_id") or "").strip()
    labels = filtered_semantic_scope_labels(
        item, list(item.get("scope_labels") or item.get("labels") or [])
    )
    if not message_id or not labels:
        return None
    exact_refs = exact_message_refs_for_semantic_label(message_id, refs)
    if not exact_refs:
        return None
    return {
        "kind": "semantic_scope_labels",
        "message_id": message_id,
        "scope_labels": labels,
        "source_refs": exact_refs,
        "label_evidence": label_evidence_for_labels(item, labels),
        "rationale": compact_text(
            str(item.get("rationale") or item.get("summary") or item.get("why") or ""), 260
        ),
    }


def validate_theme_candidate_fields(item: dict[str, Any]) -> dict[str, Any] | None:
    shared_concepts = compact_string_list(item.get("shared_concepts") or item.get("concepts"), limit=12)
    source_link_ids = compact_string_list(
        item.get("source_question_link_ids") or item.get("question_link_ids"),
        limit=12,
        chars=120,
    )
    theme_label = compact_text(str(item.get("theme_label") or item.get("title") or ""), 140)
    theme_short = compact_text(str(item.get("theme_short") or (shared_concepts[0] if shared_concepts else "")), 90)
    cluster_method = compact_text(str(item.get("cluster_method") or ""), 80)
    if not (theme_label and theme_short and cluster_method and shared_concepts and source_link_ids):
        return None
    if "llm" in cluster_method.casefold():
        return None
    shared_short_keys = {compact_text(concept, 90).casefold() for concept in shared_concepts}
    if theme_short.casefold() not in shared_short_keys:
        return None
    return {
        "kind": "theme_candidate",
        "theme_cluster_id": compact_text(str(item.get("theme_cluster_id") or ""), 100),
        "theme_label": theme_label,
        "theme_short": theme_short,
        "cluster_method": cluster_method,
        "shared_concepts": shared_concepts,
        "source_question_link_ids": source_link_ids,
        "linked_question_count": safe_nonnegative_int(item.get("linked_question_count")),
        "thread_span": safe_nonnegative_int(item.get("thread_span")),
        "boundary_map": item.get("boundary_map") if isinstance(item.get("boundary_map"), dict) else {},
    }


def safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def validate_findings(
    job: str, parsed: dict[str, Any], source_bank: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    spec = JOB_SPECS[job]
    out: list[dict[str, Any]] = []
    for item in parsed.get("findings") or []:
        if not isinstance(item, dict):
            continue
        confidence = clamp_confidence(item.get("confidence"))
        refs = refs_for_finding(item, source_bank)
        if confidence < 0.45 or not refs:
            continue
        finding: dict[str, Any] = {
            "job": job,
            "kind": str(item.get("kind") or spec["finding_kind"]),
            "title": compact_text(str(item.get("title") or ""), 140),
            "summary": compact_text(str(item.get("summary") or item.get("why") or ""), 480),
            "confidence": round(confidence, 4),
            "source_refs": refs,
            "concepts": [
                compact_text(str(value), 80)
                for value in item.get("concepts") or []
                if str(value).strip()
            ][:12],
            "recommendation": compact_text(
                str(item.get("recommendation") or item.get("suggested_next_action") or ""), 260
            ),
        }
        if job == "concept_edges":
            src = compact_text(str(item.get("src") or ""), 100)
            dst = compact_text(str(item.get("dst") or ""), 100)
            edge_type = str(item.get("edge_type") or "related")
            if not src or not dst or src.casefold() == dst.casefold():
                continue
            if edge_type not in ALLOWED_EDGE_TYPES:
                edge_type = "related"
            finding.update(
                {
                    "src": src,
                    "dst": dst,
                    "edge_type": edge_type,
                    "why": compact_text(str(item.get("why") or item.get("summary") or ""), 220),
                }
            )
        if job == "question_extraction":
            question_fields = validate_question_fields(item)
            if not question_fields:
                continue
            finding.update(question_fields)
            # Question extraction may receive weak or invented labels from the
            # model. Preserve only labels already attached to the selected
            # source turns/messages, so downstream dream work can use life-wide
            # signals without turning the extractor into a second labeler.
            finding.update(scope_label_fields_from_source_refs(refs))
        if job == "cognitive_map":
            route_fields = validate_cognitive_map_fields(item, refs)
            if not route_fields:
                continue
            finding.update(route_fields)
        if job == "semantic_scope_labeling":
            semantic_scope_fields = validate_semantic_scope_label_fields(item, refs)
            if not semantic_scope_fields:
                continue
            finding.update(semantic_scope_fields)
        if job == "theme_emergence":
            theme_fields = validate_theme_candidate_fields(item)
            if not theme_fields:
                continue
            finding.update(theme_fields)
        if not finding["title"]:
            if job == "concept_edges":
                finding["title"] = f"{finding.get('src')} -> {finding.get('dst')}"
            elif job == "question_extraction" and finding.get("question_short"):
                finding["title"] = finding["question_short"]
            elif job == "cognitive_map":
                landmark_titles = [str(value) for value in finding.get("landmarks") or []]
                finding["title"] = " -> ".join(landmark_titles)[:120]
            else:
                finding["title"] = compact_text(str(finding["summary"]), 120)
        if not finding["summary"] and job != "concept_edges":
            continue
        finding["fingerprint"] = finding_fingerprint(finding)
        finding["quality"] = estimate_finding_quality(job, finding)
        out.append(finding)
    return out
