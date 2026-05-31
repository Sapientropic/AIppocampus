#!/usr/bin/env python3
"""Bounded model-backed dream workers over ready source packs.

Dream workers are background-only hypothesis generators. They may use an
external model to propose compensatory or amplification candidates, but they do
not mutate clean source, do not run from foreground hooks, and cannot project
anything to working memory until the existing background source-ref adjudicator
accepts it.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_payload
from aippocampus_runtime.dream.worker_contract import (
    PROMPT_ORDER,
    stable_worker_contract,
    variable_run_directive,
)
from aippocampus_runtime.dream.working_memory import (
    adjudicated_dream_findings_to_working_memory,
    background_adjudicate_dream_findings,
)
from aippocampus_runtime.model.client import (
    ChatClientConfig,
    cache_metrics_from_response,
    chat_json,
)

SCHEMA_VERSION = 1
WORKER_KIND = "aippocampus_dream_worker_run"
SUMMARY_KIND = "aippocampus_dream_worker_summary"
FINDING_KIND = "dream_synthesized"
PACK_KIND = "aippocampus_dream_input_pack"
READY_STATUS = "ready_for_dream_worker"
MODEL_PHASE = "phase4_model_backed_pack_worker"
EXECUTION_MODE = "detached_background"
MAX_MODEL_CONFIDENCE = 0.86

CANDIDATE_KINDS_BY_FUNCTION = {
    "compensatory": {
        "blind_spot",
        "approach_bias",
        "emotional_balance_note",
    },
    "amplification": {
        "cross_thread_resonance",
        "theme_deepening",
        "journey_pattern_resonance",
    },
    "prospective": {
        "emergence_signal",
        "trajectory_hint",
        "pre_articulation_marker",
    },
    "active_imagination": {
        "synthesis_hypothesis",
        "bridge_concept",
        "question_not_yet_asked",
    },
}

ACTIVE_IMAGINATION_RISK_TERMS = {
    "diagnosis",
    "mental health",
    "personality",
    "preference",
    "prefers",
    "profile",
    "secretly",
    "trauma",
    "人格",
    "创伤",
    "偏好",
    "诊断",
}

ModelCall = Callable[[list[dict[str, str]], ChatClientConfig], dict[str, Any]]


def stable_digest(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def safe_float(value: object, default: float = 0.0) -> float:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return max(0.0, min(1.0, number))


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_now(now: str | datetime | None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    parsed = parse_utc(str(now)) if now else parse_utc(now_utc())
    return parsed or datetime.now(timezone.utc)


def future_utc(*, days: int, now: str | datetime | None = None) -> str:
    return format_utc(normalize_now(now) + timedelta(days=max(1, int(days))))


def string_list(value: object, *, limit: int = 8, max_chars: int = 180) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = compact_text(str(item or ""), max_chars)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_line") or ref.get("line") or ""),
    )


def clean_source_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    clean = {
        "thread_key": ref.get("thread_key") or ref.get("thread_id"),
        "message_id": ref.get("message_id"),
        "turn_id": ref.get("turn_id"),
        "line": ref.get("line") or ref.get("source_line"),
        "turn_index": ref.get("turn_index"),
        "project_label": ref.get("project_label"),
        "title": ref.get("title"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def source_ref_inventory(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in pack.get("source_refs") or []:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        inventory.append({"source_ref_id": f"sr{len(inventory)}", **clean_source_ref(item)})
    return inventory


def source_refs_by_id(pack: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("source_ref_id")): {key: value for key, value in item.items() if key != "source_ref_id"}
        for item in source_ref_inventory(pack)
    }


def safe_pack_payload(pack: Mapping[str, Any]) -> dict[str, Any]:
    audit_value = pack.get("source_ref_audit")
    audit: Mapping[str, Any] = audit_value if isinstance(audit_value, Mapping) else {}
    payload = {
        "pack_id": pack.get("pack_id"),
        "pack_kind": pack.get("pack_kind"),
        "status": pack.get("status"),
        "selection": pack.get("selection") or {},
        "objective": pack.get("objective"),
        "themes": pack.get("themes") or [],
        "concepts": pack.get("concepts") or [],
        "questions": pack.get("questions") or [],
        "frontiers": pack.get("frontiers") or [],
        "negative_contexts": pack.get("negative_contexts") or [],
        "source_seed_ids": pack.get("source_seed_ids") or [],
        "source_seed_kinds": pack.get("source_seed_kinds") or [],
        "source_contributions": pack.get("source_contributions") or [],
        "source_ref_audit": {
            "status": audit.get("status"),
            "source_ref_count": audit.get("source_ref_count"),
            "source_thread_count": audit.get("source_thread_count"),
            "clean_source_resolution": audit.get("clean_source_resolution"),
        },
        "source_ref_inventory": source_ref_inventory(pack),
        "truth_boundary": pack.get("truth_boundary"),
    }
    return sanitize_external_model_payload(payload)


def build_worker_messages(
    pack: Mapping[str, Any],
    *,
    dream_function: str,
    max_samples: int = 1,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": json.dumps(
                stable_worker_contract(CANDIDATE_KINDS_BY_FUNCTION),
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"prompt_part": "source_pack_payload", "source_pack": safe_pack_payload(pack)},
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                variable_run_directive(
                    dream_function,
                    max_samples=max_samples,
                    candidate_kinds_by_function=CANDIDATE_KINDS_BY_FUNCTION,
                ),
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
    ]


def model_response_json(response: Mapping[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], Mapping):
        raise ValueError("model response has no choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise ValueError("model response content is empty")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("model response JSON root must be an object")
    return parsed


def resolve_refs(source_ref_ids: object, by_id: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(source_ref_ids, str):
        raw_ids = [source_ref_ids]
    elif isinstance(source_ref_ids, list):
        raw_ids = source_ref_ids
    else:
        raw_ids = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw_id in raw_ids:
        ref = by_id.get(str(raw_id))
        if not ref:
            continue
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append(dict(ref))
    return refs


def bridge_claims_from_candidate(
    candidate: Mapping[str, Any],
    *,
    by_id: Mapping[str, dict[str, Any]],
    fallback_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in candidate.get("bridge_claims") or []:
        if not isinstance(item, Mapping):
            continue
        refs = resolve_refs(item.get("source_ref_ids"), by_id)
        claims.append({"claim": compact_text(str(item.get("claim") or ""), 240), "source_refs": refs[:8]})
    return claims


def has_active_imagination_sensitive_risk(*parts: object) -> bool:
    text = " ".join(str(part or "") for part in parts).casefold()
    return any(term in text for term in ACTIVE_IMAGINATION_RISK_TERMS)


def finding_from_candidate(
    candidate: Mapping[str, Any],
    *,
    pack: Mapping[str, Any],
    dream_function: str,
    candidate_index: int,
    by_id: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    allowed_kinds = CANDIDATE_KINDS_BY_FUNCTION[dream_function]
    candidate_kind = str(candidate.get("candidate_kind") or "")
    if candidate_kind not in allowed_kinds:
        return None, {"reason": "unsupported_candidate_kind", "candidate_kind": candidate_kind}

    title = compact_text(str(candidate.get("title") or ""), 160)
    summary = compact_text(str(candidate.get("summary") or ""), 720)
    if not title or not summary:
        return None, {"reason": "missing_title_or_summary", "candidate_kind": candidate_kind}

    confidence = safe_float(candidate.get("confidence"), 0.0)
    activation_cues = string_list(
        candidate.get("activation_cues") or candidate.get("route_cues"),
        limit=8,
        max_chars=120,
    )
    refs = resolve_refs(candidate.get("source_ref_ids"), by_id)
    failures: list[str] = []
    if not activation_cues:
        failures.append("missing_activation_cues")
    if not refs:
        failures.append("missing_or_unknown_source_ref_ids")
    if confidence > MAX_MODEL_CONFIDENCE:
        failures.append("overconfident_model_dream_claim")

    bridge_claims = bridge_claims_from_candidate(candidate, by_id=by_id, fallback_refs=refs)
    if not bridge_claims or not all(claim.get("source_refs") for claim in bridge_claims):
        failures.append("bridge_claims_missing_source_refs")

    source_thread_count = len({str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")})
    prospective_fields: dict[str, Any] = {}
    if dream_function == "prospective":
        counter_evidence = string_list(candidate.get("counter_evidence"), limit=6)
        if not counter_evidence:
            failures.append("missing_counter_evidence")
        prospective_fields = {
            "emergence_signal": compact_text(
                str(candidate.get("emergence_signal") or title),
                240,
            ),
            "trajectory_hint": compact_text(
                str(candidate.get("trajectory_hint") or summary),
                360,
            ),
            "counter_evidence": counter_evidence,
            "review_after": future_utc(days=14),
            "expires_at": future_utc(days=45),
            "language_boundary": "hypothesis_not_prediction",
            "validation_boundary": "requires_retrospective_source_evidence",
        }
    active_imagination_fields: dict[str, Any] = {}
    if dream_function == "active_imagination":
        why_not_fact = compact_text(str(candidate.get("why_this_is_not_fact") or ""), 360)
        counter_evidence = string_list(candidate.get("counter_evidence"), limit=6)
        sensitive_risk = has_active_imagination_sensitive_risk(
            candidate_kind,
            title,
            summary,
            why_not_fact,
            " ".join(counter_evidence),
        )
        if source_thread_count < 2:
            failures.append("insufficient_independent_source_anchors")
        if not why_not_fact:
            failures.append("missing_why_this_is_not_fact")
        if not counter_evidence:
            failures.append("missing_counter_evidence")
        if sensitive_risk:
            failures.append("sensitive_or_profile_claim_requires_human_review")
        active_imagination_fields = {
            "why_this_is_not_fact": why_not_fact,
            "counter_evidence": counter_evidence,
            "sandbox_boundary": "active_imagination_candidate_not_fact",
            "audit_gate": "two_source_anchors_plus_counter_evidence",
            "human_review_required": sensitive_risk,
        }

    source_ref_audit_status = "model_candidate_source_ref_validated" if not failures else "failed"
    pack_id = str(pack.get("pack_id") or "")
    finding = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_dream_finding",
        "finding_kind": FINDING_KIND,
        "dream_function": dream_function,
        "dream_phase": MODEL_PHASE,
        "candidate_kind": candidate_kind,
        "compensatory_kind": candidate_kind if dream_function == "compensatory" else None,
        "support_level": "candidate",
        "review_state": "needs_review",
        "foreground_eligible": False,
        "human_review_required": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "fingerprint": stable_digest(pack_id, dream_function, candidate_index, candidate_kind, title, prefix="dream_model"),
        "title": title,
        "summary": summary,
        "activation_cues": activation_cues,
        "confidence": round(confidence, 4),
        "source_refs": refs,
        "source_ref_audit": {
            "status": source_ref_audit_status,
            "source_ref_count": len(refs),
            "source_thread_count": source_thread_count,
            "clean_source_resolution": "not_reopened_by_model_worker",
            "failed_checks": failures,
        },
        "source_pack_id": pack_id,
        "source_seed_ids": pack.get("source_seed_ids") or [],
        "bridge_claims": bridge_claims,
        "downstream_use": ["working_memory", "reflection_space"],
        "truth_boundary": "dream_synthesized_candidate_not_fact",
        "worker_validation": {
            "status": "failed" if failures else "passed",
            "failed_checks": failures,
            "max_model_confidence": MAX_MODEL_CONFIDENCE,
        },
    }
    if prospective_fields:
        # Prospective dreams are scoped possibilities, never predictions. The
        # expiry/review horizon keeps old trajectory hints from quietly becoming
        # ambient truth after the source situation has moved on.
        finding.update(prospective_fields)
    if active_imagination_fields:
        finding.update(active_imagination_fields)
    return {key: value for key, value in finding.items() if value is not None}, None


def validated_findings_from_model_output(
    parsed: Mapping[str, Any],
    *,
    pack: Mapping[str, Any],
    dream_function: str,
    max_samples: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = source_refs_by_id(pack)
    findings: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(parsed.get("findings") or []):
        if len(findings) >= max(1, int(max_samples)):
            break
        if not isinstance(item, Mapping):
            rejected.append({"reason": "candidate_not_object"})
            continue
        finding, rejection = finding_from_candidate(
            item,
            pack=pack,
            dream_function=dream_function,
            candidate_index=index,
            by_id=by_id,
        )
        if finding is not None:
            findings.append(finding)
        elif rejection is not None:
            rejected.append(rejection)
    return findings, rejected


def worker_status(*, findings: list[dict[str, Any]], adjudicated: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> str:
    if any((finding.get("adjudication_result") or {}).get("status") == "accepted" for finding in adjudicated):
        return "candidate_emitted"
    if adjudicated and all((finding.get("adjudication_result") or {}).get("status") == "parked" for finding in adjudicated):
        return "candidate_parked"
    if rejected and not findings:
        return "model_output_rejected"
    return "no_candidate"


def run_model_backed_dream_worker(
    pack: Mapping[str, Any],
    *,
    dream_function: str,
    config: ChatClientConfig,
    model_call: ModelCall = chat_json,
    max_samples: int = 1,
    no_write: bool = True,
) -> dict[str, Any]:
    if dream_function not in CANDIDATE_KINDS_BY_FUNCTION:
        raise ValueError(f"unsupported dream_function: {dream_function}")
    if pack.get("kind") != PACK_KIND or pack.get("status") != READY_STATUS:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": WORKER_KIND,
            "created_at": now_utc(),
            "status": "skipped_pack_not_ready",
            "pack_id": pack.get("pack_id"),
            "dream_function": dream_function,
            "findings": [],
            "adjudicated_findings": [],
            "dream_working_memory_rows": [],
            "rejected_candidates": [],
            "no_write": True,
        }

    messages = build_worker_messages(pack, dream_function=dream_function, max_samples=max_samples)
    rejected: list[dict[str, Any]] = []
    try:
        response = model_call(messages, config)
        parsed = model_response_json(response)
        findings, rejected = validated_findings_from_model_output(
            parsed,
            pack=pack,
            dream_function=dream_function,
            max_samples=max_samples,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        response = {}
        findings = []
        rejected = [{"reason": "malformed_model_output", "message": compact_text(str(exc), 240)}]

    adjudicated = background_adjudicate_dream_findings(
        findings,
        source_pack=pack,
        adjudication_source="model_backed_dream_worker",
    )
    working_rows = [] if no_write else adjudicated_dream_findings_to_working_memory(adjudicated)
    accepted_count = sum(1 for item in adjudicated if (item.get("adjudication_result") or {}).get("status") == "accepted")
    parked_count = sum(1 for item in adjudicated if (item.get("adjudication_result") or {}).get("status") == "parked")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": WORKER_KIND,
        "created_at": now_utc(),
        "status": worker_status(findings=findings, adjudicated=adjudicated, rejected=rejected),
        "pack_id": pack.get("pack_id"),
        "dream_function": dream_function,
        "execution_mode": EXECUTION_MODE,
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "cache_contract": config.cache_contract,
        "prompt_order": list(PROMPT_ORDER),
        "findings": findings,
        "adjudicated_findings": adjudicated,
        "dream_working_memory_rows": working_rows,
        "rejected_candidates": rejected,
        "counts": {
            "findings": len(findings),
            "accepted": accepted_count,
            "parked": parked_count,
            "rejected": len(rejected),
        },
        "usage": dict(response.get("usage") or {}) if isinstance(response, Mapping) else {},
        "cache": cache_metrics_from_response(dict(response), config) if isinstance(response, Mapping) else {},
        "no_write": bool(no_write),
        "policy": {
            "foreground_model_calls_allowed": False,
            "clean_source_mutation_allowed": False,
            "requires_background_adjudication": True,
            "max_samples": max(1, int(max_samples)),
        },
    }


def prospective_finding_id(finding: Mapping[str, Any]) -> str:
    return str(finding.get("dream_finding_id") or finding.get("fingerprint") or finding.get("id") or "")


def validation_targets(row: Mapping[str, Any]) -> set[str]:
    raw: list[object] = [
        row.get("target_finding_id"),
        row.get("target_fingerprint"),
        row.get("prospective_finding_id"),
    ]
    for key in ("target_finding_ids", "source_finding_ids"):
        value = row.get(key)
        if isinstance(value, list):
            raw.extend(value)
    return {str(item) for item in raw if item not in {None, ""}}


def validation_status_from_row(row: Mapping[str, Any]) -> str:
    raw = str(
        row.get("validation_status")
        or row.get("prospective_validation_status")
        or row.get("retrospective_status")
        or ""
    ).casefold()
    if raw in {"supported", "support", "confirmed", "later_supported"}:
        return "supported"
    if raw in {"refuted", "refute", "contradicted", "later_refuted"}:
        return "refuted"
    return ""


def has_source_refs(row: Mapping[str, Any]) -> bool:
    refs = row.get("source_refs")
    if not isinstance(refs, list):
        return False
    return any(isinstance(ref, Mapping) and any(source_ref_key(ref)) for ref in refs)


def explicit_validation_evidence(later_rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    evidence: dict[str, dict[str, int]] = {}
    for row in later_rows:
        if not isinstance(row, Mapping):
            continue
        status = validation_status_from_row(row)
        targets = validation_targets(row)
        if status not in {"supported", "refuted"} or not targets or not has_source_refs(row):
            continue
        for target in targets:
            bucket = evidence.setdefault(target, {"supported": 0, "refuted": 0, "source_ref_count": 0})
            bucket[status] += 1
            bucket["source_ref_count"] += len(row.get("source_refs") or [])
    return evidence


def retrospective_validate_prospective_findings(
    findings: list[Mapping[str, Any]],
    later_rows: list[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Bucket prospective hypotheses against explicit later source evidence.

    Similar terms are deliberately ignored. Retrospective support/refutation
    requires a later row that names the prospective finding id and carries clean
    source refs; otherwise the result stays unknown or stale after expiry.
    """

    now_dt = normalize_now(now)
    evidence = explicit_validation_evidence(later_rows)
    items: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        if finding.get("finding_kind") != FINDING_KIND or finding.get("dream_function") != "prospective":
            continue
        finding_id = prospective_finding_id(finding)
        if not finding_id:
            continue
        bucket = evidence.get(finding_id, {})
        expires_at = parse_utc(str(finding.get("expires_at") or ""))
        if int(bucket.get("refuted") or 0) > 0:
            status = "refuted"
        elif int(bucket.get("supported") or 0) > 0:
            status = "supported"
        elif expires_at and expires_at <= now_dt:
            status = "stale"
        else:
            status = "unknown"
        items.append(
            {
                "finding_id": finding_id,
                "validation_status": status,
                "evidence_ref_count": int(bucket.get("source_ref_count") or 0),
                "expires_at": finding.get("expires_at"),
            }
        )
    counts = {key: count for key, count in sorted(Counter(item["validation_status"] for item in items).items())}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_prospective_retrospective_validation",
        "created_at": format_utc(now_dt),
        "items": items,
        "counts": counts,
        "policy": {
            "term_overlap_alone_counts_as_evidence": False,
            "requires_explicit_target_finding_id": True,
            "requires_source_handles": True,
            "public_output_omits_source_handles": True,
        },
    }


def public_worker_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") or {}
    cache = payload.get("cache") or {}
    usage = payload.get("usage") or {}
    return {
        "kind": SUMMARY_KIND,
        "status": payload.get("status"),
        "pack_id": payload.get("pack_id"),
        "dream_function": payload.get("dream_function"),
        "counts": dict(counts),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
            "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
        },
        "cache": {
            "kind": cache.get("kind"),
            "available": cache.get("available"),
            "hit_rate": cache.get("hit_rate"),
            "hit_tokens": cache.get("hit_tokens"),
            "miss_tokens": cache.get("miss_tokens"),
        },
        "foreground_model_calls_allowed": False,
        "execution_mode": payload.get("execution_mode"),
        "no_write": bool(payload.get("no_write")),
    }
