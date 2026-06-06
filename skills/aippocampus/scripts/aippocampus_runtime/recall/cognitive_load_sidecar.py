#!/usr/bin/env python3
"""Bounded cognitive-load routing hints keyed by source refs.

The sidecar is deliberately operational metadata: observable collaboration
strain can make a source ref worth reopening sooner, but it cannot become an
emotion/personality claim or override source authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

PROJECTION_BOUNDARY = "routing_caution_not_affect_or_personality_truth"
MAX_LOAD_BOOST = 0.16
HALF_LIFE_DAYS = 30.0
MIN_SOURCE_AUTHORITY_FOR_BOOST = 0.5
BLOCKED_SOURCE_STATUSES = {"refuted", "superseded", "untrusted", "forbidden"}

SIGNAL_WEIGHTS = {
    "user_correction": 0.07,
    "explicit_pitfall_marker": 0.08,
    "failed_test": 0.06,
    "failed_command": 0.05,
    "rollback_or_revert": 0.06,
    "rejected_route_retry": 0.06,
    "source_conflict": 0.05,
    "human_intervention": 0.04,
    "repeated_source_reopen": 0.03,
    "downstream_turn_affected": 0.03,
    "high_risk_action_repaired": 0.05,
    "clarification": 0.01,
}

SIDE_CAR_CANNOT_CLAIM = [
    "cognitive_load_as_affect_or_user_trait",
    "source_truth_not_overridden",
    "semantic_relevance_replaced_by_load_weight",
    "private_stress_narrative_stored",
]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _now(value: str | None) -> datetime:
    parsed = _parse_time(value)
    return parsed or datetime.now(timezone.utc)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_ref_key(source_ref: Mapping[str, Any]) -> str:
    existing = str(source_ref.get("source_ref_hash") or "").strip()
    if existing.startswith("sha256:"):
        return existing
    public_ref = {
        "source_id": source_ref.get("source_id"),
        "thread_id": source_ref.get("thread_id"),
        "turn_id": source_ref.get("turn_id"),
        "message_id": source_ref.get("message_id"),
        "line": source_ref.get("line"),
        "source_line": source_ref.get("source_line"),
    }
    digest = hashlib.sha256(_stable_json(public_ref).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _source_keys(value: Any) -> list[str]:
    keys: list[str] = []
    for raw_ref in _as_list(value):
        ref = _as_mapping(raw_ref)
        if ref:
            keys.append(source_ref_key(ref))
    return sorted(set(keys))


def _event_type(event: Mapping[str, Any]) -> str:
    return str(event.get("event_type") or event.get("kind") or "").strip()


def _event_weight(event: Mapping[str, Any]) -> float:
    event_type = _event_type(event)
    try:
        multiplier = max(0.0, float(event.get("count") or 1.0))
    except (TypeError, ValueError):
        multiplier = 1.0
    return SIGNAL_WEIGHTS.get(event_type, 0.0) * multiplier


def _age_days(timestamp: datetime | None, now: datetime) -> float:
    if timestamp is None:
        return 0.0
    return max(0.0, (now - timestamp).total_seconds() / 86400.0)


def _decay_factor(age_days: float) -> float:
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def _bucket(boost: float) -> str:
    if boost >= 0.12:
        return "high"
    if boost >= 0.06:
        return "medium"
    if boost > 0:
        return "low"
    return "none"


def _entry_boost(raw_boost: float, latest_age_days: float, invalidated: bool) -> float:
    if invalidated:
        return 0.0
    return round(min(MAX_LOAD_BOOST, raw_boost * _decay_factor(latest_age_days)), 6)


def build_cognitive_load_sidecar(
    events: Iterable[Mapping[str, Any]],
    *,
    now: str | None = None,
) -> dict[str, Any]:
    now_dt = _now(now)
    grouped: dict[str, dict[str, Any]] = {}
    ignored_event_count = 0
    signal_event_count = 0
    source_reopen_event_count = 0
    pitfall_repetition_event_count = 0
    reviewed_load_signal_count = 0
    load_weight_false_positive_count = 0
    reviewed_caution_hint_count = 0
    useful_caution_hint_count = 0
    overpersonalization_from_load_signal_count = 0

    for event in events:
        keys = _source_keys(event.get("source_refs"))
        weight = _event_weight(event)
        if not keys or weight <= 0:
            ignored_event_count += 1
            continue
        signal_event_count += 1
        event_type = _event_type(event)
        if event.get("source_reopened") or event_type == "source_reopen":
            source_reopen_event_count += 1
        if event.get("pitfall_repeated_after_signal"):
            pitfall_repetition_event_count += 1
        if event.get("load_weight_reviewed"):
            reviewed_load_signal_count += 1
            if event.get("load_weight_false_positive"):
                load_weight_false_positive_count += 1
        if event.get("caution_hint_reviewed"):
            reviewed_caution_hint_count += 1
            if event.get("caution_hint_useful"):
                useful_caution_hint_count += 1
        if event.get("overpersonalization_from_load_signal"):
            overpersonalization_from_load_signal_count += 1
        timestamp = _parse_time(event.get("timestamp"))
        for key in keys:
            entry = grouped.setdefault(
                key,
                {
                    "source_ref_key": key,
                    "raw_boost": 0.0,
                    "strain_signal_counts": {},
                    "event_count": 0,
                    "latest_timestamp": None,
                    "latest_age_days": 0.0,
                    "invalidated_by_supersession": False,
                    "reason_codes": set(),
                },
            )
            entry["raw_boost"] += weight
            entry["event_count"] += 1
            counts = entry["strain_signal_counts"]
            counts[event_type] = int(counts.get(event_type) or 0) + 1
            entry["reason_codes"].add(event_type)
            if event.get("superseded_by_source_ref") or event.get("invalidated_by_supersession"):
                entry["invalidated_by_supersession"] = True
            latest = _parse_time(entry.get("latest_timestamp"))
            if timestamp and (latest is None or timestamp > latest):
                entry["latest_timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
                entry["latest_age_days"] = round(_age_days(timestamp, now_dt), 4)

    entries: list[dict[str, Any]] = []
    for entry in grouped.values():
        boost = _entry_boost(
            float(entry["raw_boost"]),
            float(entry.get("latest_age_days") or 0.0),
            bool(entry.get("invalidated_by_supersession")),
        )
        entries.append(
            {
                "source_ref_key": entry["source_ref_key"],
                "load_boost": boost,
                "load_bucket": _bucket(boost),
                "strain_signal_counts": dict(sorted(entry["strain_signal_counts"].items())),
                "reason_codes": sorted(entry["reason_codes"]),
                "event_count": int(entry["event_count"]),
                "decay": {
                    "applied": True,
                    "half_life_days": HALF_LIFE_DAYS,
                    "latest_age_days": float(entry.get("latest_age_days") or 0.0),
                },
                "caps": {"max_load_boost": MAX_LOAD_BOOST},
                "invalidated_by_supersession": bool(entry.get("invalidated_by_supersession")),
                "projection_boundary": PROJECTION_BOUNDARY,
            }
        )
    entries.sort(key=lambda row: (-float(row["load_boost"]), row["source_ref_key"]))

    return {
        "schema_version": 1,
        "kind": "aippocampus_cognitive_load_sidecar",
        "status": "ready",
        "projection_boundary": PROJECTION_BOUNDARY,
        "entries": entries,
        "metrics": {
            "entry_count": len(entries),
            "ignored_event_count": ignored_event_count,
            "invalidated_entry_count": sum(1 for row in entries if row["invalidated_by_supersession"]),
            "max_load_boost": max((float(row["load_boost"]) for row in entries), default=0.0),
            "load_weight_decay_coverage": 1.0 if entries else 0.0,
            "high_load_source_reopen_rate": _rate(source_reopen_event_count, signal_event_count),
            "pitfall_repetition_rate_after_high_load_signal": _rate(
                pitfall_repetition_event_count,
                signal_event_count,
            ),
            "load_weight_false_positive_rate": _rate(
                load_weight_false_positive_count,
                reviewed_load_signal_count,
            ),
            "caution_hint_useful_rate": _rate(
                useful_caution_hint_count,
                reviewed_caution_hint_count,
            ),
            "overpersonalization_from_load_signal_count": (
                overpersonalization_from_load_signal_count
            ),
        },
        "privacy_boundary": {
            "raw_paths_emitted": False,
            "raw_notes_emitted": False,
            "emotion_or_personality_claims_emitted": False,
            "source_ref_keys_only": True,
        },
        "cannot_claim": SIDE_CAR_CANNOT_CLAIM,
    }


def _sidecar_index(sidecar: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(entry.get("source_ref_key")): entry
        for entry in _as_list(sidecar.get("entries"))
        if isinstance(entry, Mapping)
    }


def _candidate_source_keys(candidate: Mapping[str, Any]) -> list[str]:
    keys = _source_keys(candidate.get("source_refs"))
    if not keys and candidate.get("source_ref_key"):
        keys = [str(candidate.get("source_ref_key"))]
    return keys


def _authority(candidate: Mapping[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(candidate.get("source_authority") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _semantic(candidate: Mapping[str, Any]) -> float:
    try:
        return max(0.0, float(candidate.get("semantic_score") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _source_blocks_load(candidate: Mapping[str, Any], authority: float) -> bool:
    status = str(candidate.get("source_status") or "current").strip()
    return status in BLOCKED_SOURCE_STATUSES or authority < MIN_SOURCE_AUTHORITY_FOR_BOOST


def _best_load_entry(
    candidate: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    matches = [index[key] for key in _candidate_source_keys(candidate) if key in index]
    if not matches:
        return None
    return max(matches, key=lambda row: float(row.get("load_boost") or 0.0))


def apply_cognitive_load_boosts(
    candidates: Iterable[Mapping[str, Any]],
    sidecar: Mapping[str, Any],
) -> list[dict[str, Any]]:
    index = _sidecar_index(sidecar)
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        semantic = _semantic(candidate)
        authority = _authority(candidate)
        entry = _best_load_entry(candidate, index)
        raw_load_boost = float(entry.get("load_boost") or 0.0) if entry else 0.0
        source_blocked = _source_blocks_load(candidate, authority)
        load_boost = 0.0 if source_blocked else raw_load_boost
        authority_boost = round(max(0.0, authority - 0.5) * 0.05, 6)
        final_score = round(semantic + authority_boost + load_boost, 6)
        cannot_claim = ["semantic_relevance_replaced_by_load_weight"]
        advisory_action = "source_reopen_recommended:caution_hint" if load_boost else "none"
        if source_blocked:
            cannot_claim.append("source_truth_not_overridden")
            advisory_action = "refresh_sources"

        row = dict(candidate)
        row["final_score"] = final_score
        row["score_breakdown"] = {
            "semantic_score": semantic,
            "source_authority": authority,
            "source_authority_boost": authority_boost,
            "cognitive_load_boost": round(load_boost, 6),
        }
        row["cognitive_load"] = {
            "present": bool(entry),
            "load_bucket": str(entry.get("load_bucket") or "none") if entry else "none",
            "reason_codes": list(entry.get("reason_codes") or []) if entry else [],
            "advisory_action": advisory_action,
            "projection_boundary": PROJECTION_BOUNDARY,
            "cannot_claim": cannot_claim,
        }
        ranked.append(row)
    ranked.sort(key=lambda row: (-float(row["final_score"]), str(row.get("candidate_id") or "")))
    return ranked
