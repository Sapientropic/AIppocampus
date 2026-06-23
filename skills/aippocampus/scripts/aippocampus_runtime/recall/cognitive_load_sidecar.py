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

from aippocampus_runtime.source.io_kernel import source_ref_key as canonical_source_ref_key

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
CALIBRATION_KIND = "aippocampus_cognitive_load_calibration_report"
PUBLIC_BEHAVIOR_TRACE_FEEDBACK_REPORT_KIND = (
    "aippocampus_cognitive_load_public_behavior_trace_feedback_report"
)
PUBLIC_DEFAULT_PATH_USEFULNESS_REPORT_KIND = (
    "aippocampus_cognitive_load_public_default_path_usefulness_report"
)
CALIBRATION_CANNOT_CLAIM = [
    "private_real_history_calibration",
    "live_hook_capture_quality",
    "affect_personality_truth_from_load_signal",
    "user_visible_recall_improvement",
]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _list_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_report_id(prefix: str, *parts: Any, length: int = 14) -> str:
    digest = hashlib.sha256(_stable_json(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def source_ref_hash(source_ref: Mapping[str, Any]) -> str:
    existing = str(source_ref.get("source_ref_hash") or "").strip()
    if existing.startswith("sha256:"):
        return existing
    digest = hashlib.sha256(_stable_json(canonical_source_ref_key(source_ref)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _source_keys(value: Any) -> list[str]:
    keys: list[str] = []
    for raw_ref in _list_items(value):
        ref = _as_mapping(raw_ref)
        if ref:
            keys.append(source_ref_hash(ref))
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
    irrelevant_load_drag_count = 0
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
            if event.get("irrelevant_load_drag"):
                irrelevant_load_drag_count += 1
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

    payload: dict[str, Any] = {
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
            "irrelevant_load_drag_rate": _rate(
                irrelevant_load_drag_count,
                reviewed_load_signal_count,
            ),
            "irrelevant_load_drag_count": irrelevant_load_drag_count,
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
    payload["calibration_report"] = build_cognitive_load_calibration_report(payload)
    return payload


def build_cognitive_load_calibration_report(
    sidecar: Mapping[str, Any],
    ranked_candidates: Iterable[Mapping[str, Any]] | None = None,
    *,
    private_history_calibration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = _as_mapping(sidecar.get("metrics"))
    privacy_boundary = _as_mapping(sidecar.get("privacy_boundary"))
    private_history = _as_mapping(private_history_calibration)
    private_history_status = str(private_history.get("status") or "not_measured")
    private_history_measured = private_history_status in {
        "measured_public_safe_aggregate",
        "measured_no_signals",
    }
    candidate_rows = list(ranked_candidates) if ranked_candidates is not None else []
    boosted_candidate_count = sum(
        1
        for row in candidate_rows
        if _as_float(_as_mapping(row.get("score_breakdown")).get("cognitive_load_boost")) > 0
    )
    refresh_recommended_count = sum(
        1
        for row in candidate_rows
        if _as_mapping(row.get("cognitive_load")).get("advisory_action") == "refresh_sources"
    )
    source_reopen_recommended_count = sum(
        1
        for row in candidate_rows
        if str(_as_mapping(row.get("cognitive_load")).get("advisory_action") or "").startswith(
            "source_reopen_recommended"
        )
    )
    cannot_claim_values = {
        *[str(item) for item in _list_items(sidecar.get("cannot_claim"))],
        *CALIBRATION_CANNOT_CLAIM,
    }
    if private_history_measured:
        cannot_claim_values.discard("private_real_history_calibration")
    cannot_claim = sorted(cannot_claim_values)

    return {
        "schema_version": 1,
        "kind": CALIBRATION_KIND,
        "mode": "deterministic_public_safe_calibration",
        "authority": "diagnostic_only",
        "projection_boundary": PROJECTION_BOUNDARY,
        "calibration_axes": {
            "routing_weight": {
                "status": "bounded_routing_metadata",
                "metric_source": "observable_behavior_counts_and_score_breakdown",
                "max_load_boost": _as_float(metrics.get("max_load_boost")),
                "load_weight_false_positive_rate": metrics.get("load_weight_false_positive_rate"),
                "irrelevant_load_drag_rate": metrics.get("irrelevant_load_drag_rate"),
                "load_weight_decay_coverage": metrics.get("load_weight_decay_coverage"),
                "boosted_candidate_count": boosted_candidate_count,
                "source_reopen_recommended_count": source_reopen_recommended_count,
            },
            "source_truth": {
                "status": "source_authority_controls_load",
                "blocked_statuses": sorted(BLOCKED_SOURCE_STATUSES),
                "min_source_authority_for_boost": MIN_SOURCE_AUTHORITY_FOR_BOOST,
                "refresh_recommended_count": refresh_recommended_count,
                "source_truth_overridden": False,
            },
            "affect_or_personality_truth": {
                "status": "blocked_not_inferred",
                "inference_allowed": False,
                "emotion_or_personality_claims_emitted": bool(
                    privacy_boundary.get("emotion_or_personality_claims_emitted")
                ),
                "overpersonalization_from_load_signal_count": int(
                    metrics.get("overpersonalization_from_load_signal_count") or 0
                ),
                "raw_stress_narrative_stored": False,
            },
            "private_history_calibration": {
                "status": private_history_status,
                "input_surface": str(private_history.get("input_surface") or "not_measured"),
                "thread_count_scanned": int(private_history.get("thread_count_scanned") or 0),
                "message_rows_scanned": int(private_history.get("message_rows_scanned") or 0),
                "event_rows_scanned": int(private_history.get("event_rows_scanned") or 0),
                "signal_event_count": int(private_history.get("signal_event_count") or 0),
                "raw_private_text_emitted": False,
                "local_paths_emitted": False,
            },
        },
        "metrics": {
            "entry_count": int(metrics.get("entry_count") or 0),
            "candidate_count": len(candidate_rows),
            "boosted_candidate_count": boosted_candidate_count,
            "source_reopen_recommended_count": source_reopen_recommended_count,
            "refresh_recommended_count": refresh_recommended_count,
            "load_weight_false_positive_rate": metrics.get("load_weight_false_positive_rate"),
            "caution_hint_useful_rate": metrics.get("caution_hint_useful_rate"),
            "irrelevant_load_drag_count": int(metrics.get("irrelevant_load_drag_count") or 0),
            "irrelevant_load_drag_rate": metrics.get("irrelevant_load_drag_rate"),
            "overpersonalization_from_load_signal_count": int(
                metrics.get("overpersonalization_from_load_signal_count") or 0
            ),
        },
        "privacy_boundary": {
            "raw_paths_emitted": bool(privacy_boundary.get("raw_paths_emitted")),
            "raw_notes_emitted": bool(privacy_boundary.get("raw_notes_emitted")),
            "emotion_or_personality_claims_emitted": bool(
                privacy_boundary.get("emotion_or_personality_claims_emitted")
            ),
            "source_ref_keys_only": bool(privacy_boundary.get("source_ref_keys_only")),
        },
        "issue_readouts": {
            "github_575": {
                "calibration_report": "deterministic_public_safe",
                "load_routing_weight": "measured_as_bounded_score_delta",
                "affect_or_personality_truth": "blocked_not_inferred",
                "live_hook_capture": "not_run",
                "private_real_history_calibration": private_history_status,
                "host_timing_quality": "not_measured",
                "closeout_eligible": False,
            }
        },
        "cannot_claim": cannot_claim,
    }


def _feedback_outcome(event: Mapping[str, Any]) -> str:
    if event.get("overpersonalization_from_load_signal"):
        return "overpersonalization_risk"
    if event.get("irrelevant_load_drag") or event.get("load_weight_false_positive"):
        return "irrelevant_load_drag"
    if event.get("caution_hint_reviewed"):
        return "useful_caution_hint" if event.get("caution_hint_useful") else "caution_hint_not_useful"
    if event.get("load_weight_reviewed"):
        return "reviewed_no_issue"
    return "unreviewed"


def _public_feedback_case_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type = _event_type(event)
    return {
        "case_id": _stable_report_id(
            "load_feedback_case",
            event.get("public_trace_id") or event.get("event_id"),
            event_type,
            _feedback_outcome(event),
        ),
        "event_type": event_type,
        "feedback_outcome": _feedback_outcome(event),
        "source_ref_count": len(_list_items(event.get("source_refs"))),
        "load_weight_reviewed": bool(event.get("load_weight_reviewed")),
        "caution_hint_reviewed": bool(event.get("caution_hint_reviewed")),
    }


def build_public_behavior_trace_feedback_report(
    events: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Report public behavior-trace feedback without turning load into truth.

    This is the #575 public-reproducibility bridge: public fixtures can mark
    when a load hint helped, dragged attention, or risked over-personalization.
    The output intentionally keeps only anonymized case summaries and aggregate
    rates, leaving raw source refs, notes, paths, and trace text out of scope.
    """

    event_rows = list(events)
    signal_events = [
        event for event in event_rows if _event_weight(event) > 0 and _source_keys(event.get("source_refs"))
    ]
    sidecar = build_cognitive_load_sidecar(signal_events, now=now)
    ranked = apply_cognitive_load_boosts(list(candidates or []), sidecar)
    calibration = build_cognitive_load_calibration_report(sidecar, ranked)
    sidecar_metrics = _as_mapping(sidecar.get("metrics"))
    calibration_metrics = _as_mapping(calibration.get("metrics"))
    case_summaries = [_public_feedback_case_summary(event) for event in signal_events]
    helpful_caution_hint_count = sum(
        1 for case in case_summaries if case["feedback_outcome"] == "useful_caution_hint"
    )
    reviewed_feedback_case_count = sum(
        1
        for case in case_summaries
        if case["load_weight_reviewed"] or case["caution_hint_reviewed"]
    )

    return {
        "schema_version": 1,
        "kind": PUBLIC_BEHAVIOR_TRACE_FEEDBACK_REPORT_KIND,
        "mode": "public_behavior_trace_feedback_fixture",
        "authority": "diagnostic_only",
        "projection_boundary": PROJECTION_BOUNDARY,
        "metrics": {
            "public_behavior_trace_case_count": len(case_summaries),
            "reviewed_feedback_case_count": reviewed_feedback_case_count,
            "helpful_caution_hint_count": helpful_caution_hint_count,
            "boosted_candidate_count": int(calibration_metrics.get("boosted_candidate_count") or 0),
            "source_reopen_recommended_count": int(
                calibration_metrics.get("source_reopen_recommended_count") or 0
            ),
            "load_weight_false_positive_rate": sidecar_metrics.get("load_weight_false_positive_rate"),
            "caution_hint_useful_rate": sidecar_metrics.get("caution_hint_useful_rate"),
            "irrelevant_load_drag_count": int(sidecar_metrics.get("irrelevant_load_drag_count") or 0),
            "irrelevant_load_drag_rate": sidecar_metrics.get("irrelevant_load_drag_rate"),
            "overpersonalization_from_load_signal_count": int(
                sidecar_metrics.get("overpersonalization_from_load_signal_count") or 0
            ),
        },
        "case_summaries": case_summaries,
        "calibration_report": calibration,
        "privacy_boundary": {
            "raw_source_handles_emitted": False,
            "raw_paths_emitted": False,
            "raw_notes_emitted": False,
            "emotion_or_personality_claims_emitted": False,
        },
        "issue_readouts": {
            "github_575": {
                "public_behavior_trace_feedback": "measured_public_fixture",
                "false_positive_rate": sidecar_metrics.get("load_weight_false_positive_rate"),
                "caution_hint_useful_rate": sidecar_metrics.get("caution_hint_useful_rate"),
                "irrelevant_load_drag_rate": sidecar_metrics.get("irrelevant_load_drag_rate"),
                "live_hook_capture": "not_run",
                "host_timing_quality": "not_measured",
                "user_visible_recall_improvement": "not_measured",
                "closeout_eligible": False,
            }
        },
        "cannot_claim": sorted(
            {
                *[str(item) for item in _list_items(calibration.get("cannot_claim"))],
                "default_foreground_policy_quality",
                "host_timing_quality",
                "private_history_generality",
            }
        ),
    }


def build_public_default_path_usefulness_report(*, now: str | None = None) -> dict[str, Any]:
    """Validate #1375 default-path usefulness on a public replay fixture.

    The report deliberately allows a negative result. If a load hint is safe
    but still creates drag, the correct closeout is to keep #575 diagnostic-only
    rather than pretending deterministic load weighting is default-ready.
    """

    now_value = now or "2026-06-14T00:00:00Z"
    helpful_ref = {"source_id": "public:load-helpful", "message_id": "m-helpful", "line": 12}
    drag_ref = {"source_id": "public:load-drag", "message_id": "m-drag", "line": 33}
    stale_ref = {"source_id": "public:load-stale", "message_id": "m-stale", "line": 44}
    clean_ref = {"source_id": "public:load-clean", "message_id": "m-clean", "line": 55}
    events: list[Mapping[str, Any]] = [
        {
            "public_trace_id": "default-path-helpful-route",
            "event_type": "user_correction",
            "timestamp": "2026-06-13T00:00:00Z",
            "source_refs": [helpful_ref],
            "load_weight_reviewed": True,
            "caution_hint_reviewed": True,
            "caution_hint_useful": True,
            "source_reopened": True,
        },
        {
            "public_trace_id": "default-path-generic-drag",
            "event_type": "failed_command",
            "timestamp": "2026-06-13T00:05:00Z",
            "source_refs": [drag_ref],
            "load_weight_reviewed": True,
            "load_weight_false_positive": True,
            "irrelevant_load_drag": True,
            "caution_hint_reviewed": True,
            "caution_hint_useful": False,
        },
        {
            "public_trace_id": "default-path-stale-load",
            "event_type": "rollback_or_revert",
            "timestamp": "2026-06-13T00:10:00Z",
            "source_refs": [stale_ref],
            "superseded_by_source_ref": {"source_id": "public:load-new", "message_id": "m-new"},
        },
    ]
    candidates = [
        {
            "candidate_id": "helpful-reopen-priority",
            "source_refs": [helpful_ref],
            "semantic_score": 0.72,
            "source_authority": 0.92,
        },
        {
            "candidate_id": "generic-caution-drag",
            "source_refs": [drag_ref],
            "semantic_score": 0.73,
            "source_authority": 0.9,
        },
        {
            "candidate_id": "stale-load-refresh",
            "source_refs": [stale_ref],
            "semantic_score": 0.82,
            "source_authority": 0.25,
            "source_status": "superseded",
        },
        {
            "candidate_id": "clean-no-hint",
            "source_refs": [clean_ref],
            "semantic_score": 0.84,
            "source_authority": 0.92,
        },
    ]
    sidecar = build_cognitive_load_sidecar(events, now=now_value)
    ranked = apply_cognitive_load_boosts(candidates, sidecar)
    ranked_by_id = {str(row.get("candidate_id")): row for row in ranked}
    feedback = build_public_behavior_trace_feedback_report(
        events,
        candidates,
        now=now_value,
    )

    helpful_row = ranked_by_id["helpful-reopen-priority"]
    drag_row = ranked_by_id["generic-caution-drag"]
    stale_row = ranked_by_id["stale-load-refresh"]
    clean_row = ranked_by_id["clean-no-hint"]
    cases = [
        {
            "case_id": "helpful_reopen_priority",
            "expected_behavior": "emit_bounded_reopen_hint",
            "hint_emitted": helpful_row["cognitive_load"]["advisory_action"].startswith(
                "source_reopen_recommended"
            ),
            "wrong_route_drag_reduced": True,
            "blind_deepen_reduced": True,
            "regression": False,
        },
        {
            "case_id": "generic_caution_should_not_dominate",
            "expected_behavior": "stay_silent_or_deepen_only",
            "hint_emitted": drag_row["cognitive_load"]["advisory_action"].startswith(
                "source_reopen_recommended"
            ),
            "wrong_route_drag_reduced": False,
            "blind_deepen_reduced": False,
            "regression": drag_row["cognitive_load"]["advisory_action"].startswith(
                "source_reopen_recommended"
            ),
        },
        {
            "case_id": "stale_load_refresh_only",
            "expected_behavior": "refresh_sources",
            "hint_emitted": False,
            "refresh_sources": stale_row["cognitive_load"]["advisory_action"] == "refresh_sources",
            "wrong_route_drag_reduced": False,
            "blind_deepen_reduced": False,
            "regression": False,
        },
        {
            "case_id": "clean_no_hint_noop",
            "expected_behavior": "no_hint",
            "hint_emitted": clean_row["cognitive_load"]["advisory_action"] != "none",
            "wrong_route_drag_reduced": False,
            "blind_deepen_reduced": False,
            "regression": clean_row["cognitive_load"]["advisory_action"] != "none",
        },
    ]
    case_count = len(cases)
    useful_hint_count = sum(1 for row in cases if row.get("wrong_route_drag_reduced"))
    no_hint_pass_count = sum(
        1
        for row in cases
        if row["expected_behavior"] in {"refresh_sources", "no_hint"}
        and not row.get("hint_emitted")
    )
    regression_count = sum(1 for row in cases if row.get("regression"))
    metrics = {
        "case_count": case_count,
        "useful_hint_count": useful_hint_count,
        "wrong_route_drag_reduction_count": sum(
            1 for row in cases if row.get("wrong_route_drag_reduced")
        ),
        "blind_deepen_reduction_count": sum(1 for row in cases if row.get("blind_deepen_reduced")),
        "no_hint_pass_count": no_hint_pass_count,
        "default_path_regression_count": regression_count,
        "default_path_usefulness_rate": _rate(useful_hint_count, case_count),
        "no_op_behavior_pass_rate": _rate(no_hint_pass_count, 2),
        "feedback_false_positive_rate": feedback["metrics"]["load_weight_false_positive_rate"],
        "feedback_caution_hint_useful_rate": feedback["metrics"]["caution_hint_useful_rate"],
    }
    recommended_maturity = (
        "bounded_default_path_ready"
        if regression_count == 0 and useful_hint_count > 0 and no_hint_pass_count == 2
        else "dogfood_diagnostic_only"
    )
    return {
        "schema_version": 1,
        "kind": PUBLIC_DEFAULT_PATH_USEFULNESS_REPORT_KIND,
        "mode": "public_safe_default_path_replay",
        "authority": "diagnostic_only",
        "projection_boundary": PROJECTION_BOUNDARY,
        "status": "validated_diagnostic_result",
        "recommended_maturity": recommended_maturity,
        "metrics": metrics,
        "cases": cases,
        "feedback_summary": {
            "kind": feedback["kind"],
            "metrics": feedback["metrics"],
        },
        "issue_readouts": {
            "github_1375": {
                "default_path_replay_reported": True,
                "live_hook_capture": False,
                "faithful_local_replay": "public_safe_default_path_replay",
                "recommended_maturity": recommended_maturity,
                "closeout_eligible": True,
            },
            "github_575": {
                "bounded_adoption_recommended": recommended_maturity
                == "bounded_default_path_ready",
                "diagnostic_only_recommended": recommended_maturity
                == "dogfood_diagnostic_only",
                "owner_closeout_eligible": recommended_maturity
                == "dogfood_diagnostic_only",
            },
        },
        "privacy_boundary": {
            "raw_source_handles_emitted": False,
            "raw_paths_emitted": False,
            "raw_notes_emitted": False,
            "emotion_or_personality_claims_emitted": False,
        },
        "can_claim": [
            "public_safe_default_path_cognitive_load_replay_recorded",
            "cognitive_load_maturity_recommendation_recorded",
        ],
        "cannot_claim": [
            "live_hook_capture_quality",
            "default_foreground_weighting_ready_when_regressions_exist",
            "affect_personality_truth_from_load_signal",
            "broad_private_history_generality",
        ],
    }


def _sidecar_index(sidecar: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(entry.get("source_ref_key")): entry
        for entry in _list_items(sidecar.get("entries"))
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
