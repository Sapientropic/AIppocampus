#!/usr/bin/env python3
"""Deterministic precision policies for dream hypotheses.

These policies are lifecycle controls, not truth estimators. They keep hard
source-boundary gates separate from soft attention/ranking pressure so future
coefficient changes can recompute decisions from raw deterministic components
without rewriting old dream findings or promoting model self-ratings.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from aippocampus_runtime.core import compact_text

SCHEMA_VERSION = 1
POLICY_VERSION = "dream_precision_policy_v1"
DEFAULT_COEFFICIENT_VERSION = "conservative_v1"

RETENTION_KIND = "aippocampus_dream_retention_policy"
ACTIVATION_KIND = "aippocampus_dream_activation_policy"
RETROSPECTIVE_KIND = "aippocampus_dream_retrospective_policy"

DREAM_FINDING_KIND = "dream_synthesized"
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"
ADJUDICATED_REVIEW_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}

STAY_SILENT = "stay_silent"
SILENT_TUNING = "silent_tuning"
ACTIVE_GENTLE_NUDGE = "active_gentle_nudge"
SOURCE_BACKED_RECALL_CARD = "source_backed_recall_card"

DEFAULT_RETENTION_COEFFICIENTS = {
    "source_anchor_strength": 0.42,
    "structural_divergence": 0.24,
    "counterweight_value": 0.14,
    "novelty": 0.10,
    "expiry_horizon": 0.10,
}

LOW_SIGNAL_TERMS = {
    "candidate",
    "continuity",
    "dream",
    "finding",
    "hypothesis",
    "source",
    "summary",
    "thread",
}
SENSITIVE_TERMS = {
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


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def stable_digest(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def parse_utc(value: object) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_now(now: str | datetime | None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    return parse_utc(now) or datetime.now(timezone.utc)


def string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item not in {None, ""}]
    return []


def text_terms(text: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[\w\u4e00-\u9fff]+", text.casefold(), flags=re.UNICODE)
        if len(term) >= 4 and term not in LOW_SIGNAL_TERMS
    ]


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_line") or ref.get("line") or ""),
    )


def normalize_source_refs(value: object) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raw_items = value
    else:
        raw_items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append(dict(item))
    return refs


def source_thread_count(refs: Iterable[Mapping[str, Any]]) -> int:
    return len({str(ref.get("thread_key") or ref.get("thread_id") or "") for ref in refs if ref.get("thread_key") or ref.get("thread_id")})


def bridge_claim_ref_count(probe: Mapping[str, Any]) -> int:
    count = 0
    for claim in probe.get("bridge_claims") or []:
        if isinstance(claim, Mapping):
            count += len(normalize_source_refs(claim.get("source_refs")))
    return count


def bridge_claims_have_source_refs(probe: Mapping[str, Any]) -> bool:
    claims = [claim for claim in probe.get("bridge_claims") or [] if isinstance(claim, Mapping)]
    return bool(claims) and all(normalize_source_refs(claim.get("source_refs")) for claim in claims)


def source_anchor_component(probe: Mapping[str, Any]) -> dict[str, Any]:
    refs = normalize_source_refs(probe.get("source_refs"))
    thread_count = source_thread_count(refs)
    bridge_ref_count = bridge_claim_ref_count(probe)
    value = clamp(min(len(refs), 4) / 4 * 0.45 + min(thread_count, 3) / 3 * 0.4 + min(bridge_ref_count, 4) / 4 * 0.15)
    return {
        "value": round(value, 4),
        "raw": {
            "source_ref_count": len(refs),
            "source_thread_count": thread_count,
            "bridge_claim_source_ref_count": bridge_ref_count,
        },
    }


def sensitive_probe(probe: Mapping[str, Any]) -> bool:
    text = " ".join(
        [
            str(probe.get("title") or ""),
            str(probe.get("summary") or ""),
            " ".join(string_values(probe.get("counter_evidence"))),
        ]
    ).casefold()
    return any(term in text for term in SENSITIVE_TERMS)


def hard_gate_failures(probe: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    refs = normalize_source_refs(probe.get("source_refs"))
    if not refs:
        failures.append("source_refs_present")
    if not bridge_claims_have_source_refs(probe):
        failures.append("bridge_claims_source_refs")
    if probe.get("foreground_eligible") is True:
        failures.append("foreground_eligible_false")
    if sensitive_probe(probe) or (probe.get("sensitive_use_gate") or {}).get("state") == "blocked":
        failures.append("sensitive_profile_claim_parked")
    if str(probe.get("dream_function") or "") == "active_imagination":
        if source_thread_count(refs) < 2:
            failures.append("active_imagination_two_source_anchors")
        if not compact_text(str(probe.get("why_this_is_not_fact") or ""), 300):
            failures.append("active_imagination_why_not_fact")
        if not string_values(probe.get("counter_evidence")):
            failures.append("active_imagination_counter_evidence")
    return failures


def structural_divergence_component(voices: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    anchored = [dict(voice) for voice in voices or [] if normalize_source_refs(voice.get("source_refs"))]
    voice_ids = {str(voice.get("voice_id") or voice.get("dream_function") or "") for voice in anchored}
    candidate_keys = {
        stable_digest(
            voice.get("candidate_kind"),
            compact_text(str(voice.get("title") or voice.get("summary") or ""), 120),
            prefix="voice",
            length=12,
        )
        for voice in anchored
    }
    frontier_ids = {str(voice.get("frontier_id") or "") for voice in anchored if voice.get("frontier_id")}
    thread_keys = {
        str(ref.get("thread_key") or ref.get("thread_id") or "")
        for voice in anchored
        for ref in normalize_source_refs(voice.get("source_refs"))
        if ref.get("thread_key") or ref.get("thread_id")
    }
    self_ratings = [safe_float(voice.get("model_self_rating"), 0.0) for voice in anchored if voice.get("model_self_rating") is not None]
    value = clamp(
        min(max(len(voice_ids) - 1, 0), 3) / 3 * 0.38
        + min(max(len(candidate_keys) - 1, 0), 3) / 3 * 0.44
        + min(len(thread_keys), 3) / 3 * 0.18
    )
    return {
        "value": round(value, 4),
        "raw": {
            "anchored_voice_count": len(anchored),
            "distinct_voice_count": len({item for item in voice_ids if item}),
            "distinct_candidate_count": len(candidate_keys),
            "frontier_count": len(frontier_ids),
            "source_thread_count": len(thread_keys),
        },
        "ignored_model_self_rating_max": round(max(self_ratings), 4) if self_ratings else None,
        "meaning": "deterministic_disagreement_proxy_not_model_self_rating",
    }


def counterweight_component(probe: Mapping[str, Any]) -> dict[str, Any]:
    counter_evidence = string_values(probe.get("counter_evidence"))
    function_bonus = 0.25 if str(probe.get("dream_function") or "") in {"compensatory", "active_imagination"} else 0.0
    value = clamp(min(len(counter_evidence), 4) / 4 * 0.75 + function_bonus)
    return {"value": round(value, 4), "raw": {"counter_evidence_count": len(counter_evidence), "function_bonus": function_bonus}}


def novelty_component(probe: Mapping[str, Any]) -> dict[str, Any]:
    terms = set(text_terms(" ".join([str(probe.get("title") or ""), str(probe.get("summary") or "")])))
    cues = set(term.casefold() for term in string_values(probe.get("activation_cues")))
    value = clamp(min(len(terms | cues), 8) / 8)
    return {"value": round(value, 4), "raw": {"distinct_term_count": len(terms | cues)}}


def expiry_horizon_component(probe: Mapping[str, Any], *, now: str | datetime | None = None) -> dict[str, Any]:
    expires_at = parse_utc(probe.get("expires_at"))
    now_dt = normalize_now(now)
    if not expires_at:
        return {"value": 0.4, "raw": {"days_until_expiry": None, "has_expiry": False}}
    days = (expires_at - now_dt).total_seconds() / 86400
    value = 0.0 if days <= 0 else clamp(min(days, 45) / 45)
    return {"value": round(value, 4), "raw": {"days_until_expiry": round(days, 3), "has_expiry": True}}


def raw_retention_components(
    probe: Mapping[str, Any],
    *,
    structural_voices: Iterable[Mapping[str, Any]] | None = None,
    now: str | datetime | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "source_anchor_strength": source_anchor_component(probe),
        "structural_divergence": structural_divergence_component(structural_voices),
        "counterweight_value": counterweight_component(probe),
        "novelty": novelty_component(probe),
        "expiry_horizon": expiry_horizon_component(probe, now=now),
    }


def normalize_coefficients(coefficients: Mapping[str, float] | None) -> dict[str, float]:
    merged = dict(DEFAULT_RETENTION_COEFFICIENTS)
    if coefficients:
        for key, value in coefficients.items():
            if key in merged:
                merged[key] = max(0.0, safe_float(value, merged[key]))
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_RETENTION_COEFFICIENTS)
    return {key: round(value / total, 6) for key, value in merged.items()}


def aggregate_retention_pressure(
    components: Mapping[str, Mapping[str, Any]],
    coefficients: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    normalized = normalize_coefficients(coefficients)
    pressure = 0.0
    contributions: dict[str, float] = {}
    for key, weight in normalized.items():
        value = safe_float((components.get(key) or {}).get("value"), 0.0)
        contributions[key] = round(value * weight, 4)
        pressure += value * weight
    return {
        "retention_pressure": round(clamp(pressure), 4),
        "component_contributions": contributions,
        "meaning": "attention_lifecycle_not_truth",
    }


def recompute_retention_from_components(
    raw_components: Mapping[str, Mapping[str, Any]],
    *,
    coefficients: Mapping[str, float] | None = None,
    coefficient_version: str = DEFAULT_COEFFICIENT_VERSION,
) -> dict[str, Any]:
    aggregate = aggregate_retention_pressure(raw_components, coefficients)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RETENTION_KIND,
        "policy_version": POLICY_VERSION,
        "coefficient_version": coefficient_version,
        "raw_components": {key: dict(value) for key, value in raw_components.items()},
        "coefficients": normalize_coefficients(coefficients),
        "aggregate": aggregate,
    }


def retention_policy_for_probe(
    probe: Mapping[str, Any],
    *,
    structural_voices: Iterable[Mapping[str, Any]] | None = None,
    coefficients: Mapping[str, float] | None = None,
    coefficient_version: str = DEFAULT_COEFFICIENT_VERSION,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    failures = hard_gate_failures(probe)
    raw_components = raw_retention_components(probe, structural_voices=structural_voices, now=now)
    recomputed = recompute_retention_from_components(
        raw_components,
        coefficients=coefficients,
        coefficient_version=coefficient_version,
    )
    pressure = safe_float(recomputed["aggregate"]["retention_pressure"], 0.0)
    if failures:
        decision = "park_for_review"
    elif pressure >= 0.45:
        decision = "retain_for_review"
    else:
        decision = "drop_low_pressure"
    return {
        **recomputed,
        "probe_id": str(probe.get("dream_finding_id") or probe.get("fingerprint") or probe.get("id") or ""),
        "hard_gate": {"passed": not failures, "failures": failures},
        "decision": decision,
        "ignored_model_self_rating": {
            "input_model_confidence": safe_float(probe.get("confidence"), 0.0) if probe.get("confidence") is not None else None,
            "reason": "model_self_rating_is_not_truth_or_gate_input",
        },
    }


def topic_fit_component(row: Mapping[str, Any], prompt: str, route_relevance: bool | None) -> dict[str, Any]:
    if route_relevance is not None:
        return {"value": 1.0 if route_relevance else 0.0, "raw": {"source": "explicit_route_relevance"}}
    haystack = " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("summary") or ""),
            " ".join(string_values(row.get("trigger_terms"))),
            " ".join(string_values(row.get("concepts"))),
        ]
    ).casefold()
    prompt_terms = text_terms(prompt)
    matched = [term for term in prompt_terms if term in haystack]
    value = clamp(len(matched) / max(1, min(len(prompt_terms), 4)))
    return {"value": round(value, 4), "raw": {"prompt_term_count": len(prompt_terms), "matched_term_count": len(matched)}}


def activation_hard_gate_failures(row: Mapping[str, Any], *, now: str | datetime | None = None) -> list[str]:
    failures: list[str] = []
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        failures.append("not_dream_hypothesis")
    if str(row.get("review_state") or "") not in ADJUDICATED_REVIEW_STATES:
        failures.append("not_adjudicated")
    if (row.get("sensitive_use_gate") or {}).get("state") == "blocked" or row.get("human_review_required"):
        failures.append("sensitive_review_required")
    expires_at = parse_utc(row.get("expires_at"))
    if expires_at and expires_at <= normalize_now(now):
        failures.append("dream_hypothesis_expired")
    if not normalize_source_refs(row.get("source_refs")):
        failures.append("source_refs_present")
    return failures


def activation_policy_for_row(
    row: Mapping[str, Any],
    *,
    prompt: str = "",
    route_relevance: bool | None = None,
    source_visible: bool = False,
    annoyance_risk: str = "low",
    visibility_budget: float = 1.0,
    strong_user_facing_claim: bool = False,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    hard_failures = activation_hard_gate_failures(row, now=now)
    topic_fit = topic_fit_component(row, prompt, route_relevance)
    source_anchor = source_anchor_component(row)
    budget = clamp(safe_float(visibility_budget, 1.0))
    pressure = clamp(topic_fit["value"] * 0.5 + budget * 0.25 + source_anchor["value"] * 0.25)
    reason = "activation_pressure"
    requires_source_reopen = False
    if hard_failures:
        visibility = STAY_SILENT
        reason = hard_failures[0]
    elif source_visible:
        visibility = STAY_SILENT
        reason = "source_already_visible"
    elif str(annoyance_risk or "").casefold() in {"high", "annoying", "noisy"}:
        visibility = STAY_SILENT
        reason = "annoyance_risk_high"
    elif strong_user_facing_claim:
        visibility = SOURCE_BACKED_RECALL_CARD
        reason = "strong_claim_requires_source_reopen"
        requires_source_reopen = True
    elif topic_fit["value"] <= 0:
        visibility = STAY_SILENT
        reason = "no_route_relevance"
    elif budget < 0.35 or str(row.get("route") or "") == "use_silently":
        visibility = SILENT_TUNING
        reason = "visibility_budget_or_silent_route"
    else:
        visibility = ACTIVE_GENTLE_NUDGE
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVATION_KIND,
        "policy_version": POLICY_VERSION,
        "hard_gate": {"passed": not hard_failures, "failures": hard_failures},
        "raw_components": {
            "current_topic_fit": topic_fit,
            "visibility_budget": {"value": budget, "raw": {"input_budget": visibility_budget}},
            "source_anchor_strength": source_anchor,
            "source_visible": {"value": 1.0 if source_visible else 0.0},
            "annoyance_risk": {"value": str(annoyance_risk or "low")},
        },
        "aggregate": {
            "activation_pressure": round(pressure, 4),
            "meaning": "attention_lifecycle_not_truth",
        },
        "activation_policy": {
            "visibility": visibility,
            "reason": reason,
            "requires_source_reopen": requires_source_reopen,
            "maps_to_existing_visibility": True,
        },
    }


def probe_id(probe: Mapping[str, Any]) -> str:
    return str(probe.get("dream_finding_id") or probe.get("fingerprint") or probe.get("id") or "")


def validation_targets(row: Mapping[str, Any]) -> set[str]:
    raw: list[object] = [
        row.get("target_finding_id"),
        row.get("target_fingerprint"),
        row.get("prospective_finding_id"),
        row.get("active_imagination_finding_id"),
    ]
    for key in ("target_finding_ids", "source_finding_ids"):
        value = row.get(key)
        if isinstance(value, list):
            raw.extend(value)
    return {str(item) for item in raw if item not in {None, ""}}


def validation_status(row: Mapping[str, Any]) -> str:
    raw = str(row.get("validation_status") or row.get("retrospective_status") or "").casefold()
    if raw in {"supported", "support", "confirmed", "later_supported"}:
        return "supported"
    if raw in {"refuted", "refute", "contradicted", "later_refuted"}:
        return "refuted"
    return ""


def retrospective_policy_for_probe(
    probe: Mapping[str, Any],
    later_rows: Iterable[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    target_id = probe_id(probe)
    supported = 0
    refuted = 0
    evidence_refs = 0
    for row in later_rows:
        if not isinstance(row, Mapping):
            continue
        if target_id not in validation_targets(row):
            continue
        refs = normalize_source_refs(row.get("source_refs"))
        if not refs:
            continue
        status = validation_status(row)
        if status == "supported":
            supported += 1
            evidence_refs += len(refs)
        elif status == "refuted":
            refuted += 1
            evidence_refs += len(refs)
    expires_at = parse_utc(probe.get("expires_at"))
    if refuted:
        status = "refuted"
    elif supported:
        status = "supported"
    elif expires_at and expires_at <= normalize_now(now):
        status = "stale"
    else:
        status = "unknown"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RETROSPECTIVE_KIND,
        "policy_version": POLICY_VERSION,
        "probe_id": target_id,
        "hard_gate": {
            "requires_explicit_target_id": True,
            "requires_later_source_handles": True,
            "term_overlap_counts_as_support": False,
        },
        "raw_components": {
            "later_source_support": {"value": supported, "raw": {"event_count": supported}},
            "later_source_refutation": {"value": refuted, "raw": {"event_count": refuted}},
            "evidence_ref_count": {"value": evidence_refs},
        },
        "aggregate": {"meaning": "retrospective_source_support_not_predictive_validity"},
        "retrospective_policy": {
            "status": status,
            "supported_event_count": supported,
            "refuted_event_count": refuted,
            "evidence_ref_count": evidence_refs,
        },
    }
