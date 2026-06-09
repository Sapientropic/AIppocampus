"""Public output projection for subconscious review.

The review model may make semantic judgments over source-backed findings, but
its free text should not flow directly into CLI or append-only staging sinks.
This module keeps those output boundaries small and auditable.
"""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import cli_public_error_object, sanitize_external_model_payload
from aippocampus_runtime.registry.api import unique_preserve

PROMPT_VERSION = "aippocampus-subconscious-review-v0"
PUBLIC_CANDIDATE_TYPES = {
    "concept_edge",
    "hook_trigger",
    "project_memory",
    "preference_review",
    "contradiction_review",
    "dedup_review",
    "question_candidate",
    "frontier_marker",
    "question_link",
    "theme_candidate",
    "archive",
}
PUBLIC_REVIEW_EVENT_KINDS = {
    "aippocampus_promotion_candidate",
    "aippocampus_subconscious_duplicate_group",
    "aippocampus_subconscious_weak_finding",
}
MODEL_TEXT_OUTPUT_BOUNDARY = (
    "model_text_omitted; inspect source_finding_ids in source-backed jobs"
)

def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def public_identifier(value: Any, *, fallback: str = "", max_length: int = 96) -> str:
    text = str(value or "").strip()
    safe = "".join(
        char for char in text[:max_length] if char.isalnum() or char in {"_", "-", ":", "."}
    )
    lowered = safe.casefold()
    if not safe or any(marker in lowered for marker in ("secret", "token", "private")):
        return fallback
    return safe


def public_finding_ids(values: Any, *, limit: int = 12) -> list[str]:
    out: list[str] = []
    for value in values or []:
        safe = public_identifier(value)
        if safe:
            out.append(safe)
    return unique_preserve(out, limit=limit)


def public_model_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, dict):
        return {}
    provider = public_identifier(route.get("provider"), fallback="unknown", max_length=48)
    return {"provider": provider}


def public_usage(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cache_hit_tokens",
        "cache_miss_tokens",
    ):
        if key in usage:
            out[key] = public_count(usage.get(key))
    return out


def public_quality_bucket_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for bucket in ("strong", "usable", "weak", "noise", "unknown"):
        count = public_count(value.get(bucket))
        if count:
            out[bucket] = count
    return out


def public_quality_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    raw_contract = value.get("score_contract")
    contract: dict[str, Any] = raw_contract if isinstance(raw_contract, dict) else {}
    outcomes: dict[str, dict[str, int]] = {}
    raw_outcomes = value.get("review_outcomes_by_bucket")
    if isinstance(raw_outcomes, dict):
        for bucket in ("strong", "usable", "weak", "noise", "unknown"):
            raw_counts = raw_outcomes.get(bucket)
            if not isinstance(raw_counts, dict):
                continue
            counts = {
                key: public_count(raw_counts.get(key))
                for key in (
                    "input_findings",
                    "promotion_candidate_source",
                    "weak_finding",
                    "duplicate_canonical",
                    "duplicate_duplicate",
                )
                if public_count(raw_counts.get(key))
            }
            if counts:
                outcomes[bucket] = counts
    return {
        "score_contract": {
            "score_version": public_identifier(contract.get("score_version"), fallback="unknown"),
            "score_kind": public_identifier(contract.get("score_kind"), fallback="heuristic"),
            "calibrated_probability": bool(contract.get("calibrated_probability")),
            "meaning": str(contract.get("meaning") or "")[:240],
        },
        "bucket_distribution": public_quality_bucket_counts(value.get("bucket_distribution")),
        "review_outcomes_by_bucket": outcomes,
        "interpretation": "heuristic_bucket_outcomes_not_calibration_proof",
    }


def public_review_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = public_identifier(event.get("kind"))
    if kind not in PUBLIC_REVIEW_EVENT_KINDS:
        kind = "aippocampus_subconscious_weak_finding"
    row: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "created_at": str(event.get("created_at") or ""),
        "prompt_version": PROMPT_VERSION,
        "status": "staging",
        "source": public_identifier(event.get("source"), fallback="subconscious_review"),
        "model_route": public_model_route(event.get("model_route")),
        "usage": public_usage(event.get("usage")),
        "batch_id": public_identifier(event.get("batch_id"), fallback="batch"),
        "content_boundary": MODEL_TEXT_OUTPUT_BOUNDARY,
    }
    if kind == "aippocampus_promotion_candidate":
        candidate_type = public_identifier(
            event.get("candidate_type"),
            fallback="project_memory",
            max_length=48,
        )
        if candidate_type not in PUBLIC_CANDIDATE_TYPES:
            candidate_type = "project_memory"
        row.update(
            {
                "candidate_type": candidate_type,
                "confidence": public_confidence(event.get("confidence")),
                "source_finding_ids": public_finding_ids(event.get("source_finding_ids")),
                "source_ref_count": public_count(len(event.get("source_refs") or [])),
                "activation_cue_count": public_count(len(event.get("activation_cues") or [])),
                "focus_score": public_confidence(event.get("focus_score")),
            }
        )
        return row
    if kind == "aippocampus_subconscious_duplicate_group":
        row.update(
            {
                "canonical_finding_id": public_identifier(
                    event.get("canonical_finding_id"),
                    fallback="finding",
                ),
                "duplicate_finding_ids": public_finding_ids(
                    event.get("duplicate_finding_ids"),
                    limit=24,
                ),
            }
        )
        return row
    row.update({"finding_id": public_identifier(event.get("finding_id"), fallback="finding")})
    return row


def public_review_cli_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("error"):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        return {
            "ok": False,
            "error": cli_public_error_object(error)
            or {"code": "runtime_error", "class": "runtime_error"},
            "output_boundary": MODEL_TEXT_OUTPUT_BOUNDARY,
        }
    return {
        "ok": bool(payload.get("ok")),
        "finding_count": public_count(payload.get("finding_count")),
        "promotion_candidate_count": public_count(payload.get("promotion_candidate_count")),
        "duplicate_group_count": public_count(payload.get("duplicate_group_count")),
        "weak_finding_count": public_count(payload.get("weak_finding_count")),
        "wrote": bool(payload.get("wrote")),
        "cache": sanitize_external_model_payload(payload.get("cache") or {}),
        "model_route": public_model_route(payload.get("model_route")),
        "quality_diagnostics": public_quality_diagnostics(payload.get("quality_diagnostics")),
        "output_boundary": MODEL_TEXT_OUTPUT_BOUNDARY,
    }
