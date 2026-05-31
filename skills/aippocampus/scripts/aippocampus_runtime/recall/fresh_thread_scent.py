#!/usr/bin/env python3
"""Fresh-thread scent packet contract for progressive recall.

The packet is a privacy-safe navigation surface for the foreground agent. It is
not evidence, not a summary of memory, and not user-facing narration. Specific
memory-backed claims still need clean-source reopen through the candidate refs.
"""

from __future__ import annotations

from typing import Any

SUPPORT_LEVELS = {"silent_scent", "soft_hypothesis", "source_required", "suppressed"}
CONFIDENCE_BUCKETS = {"low", "medium", "high"}
SENSITIVITY_BUCKETS = {"safe", "caution", "suppress"}
FRESHNESS_BUCKETS = {"current", "possibly_stale", "superseded", "unknown"}
SUGGESTED_ACTIONS = {"ask_light_question", "active_recall", "source_reopen", "ignore"}

PACKET_SCHEMA_VERSION = 1
MAX_CANDIDATE_REFS = 3

BASE_WHEN_NOT_TO_USE = [
    "Do not present this packet as source-backed fact.",
    "Do not expose private details or source ids unless grounding is needed.",
    "Do not personalize a broad prompt after the local task has moved on.",
]

SUPPRESSED_WHEN_NOT_TO_USE = [
    "Do not use suppressed packets for answer content, tone steering, or memory claims.",
    "Do not reopen source unless the user gives a clearer, low-risk memory intent.",
]


def _bucket(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _candidate_ref(row: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in (
        "source_id",
        "stable_source_id",
        "thread_key",
        "message_id",
        "turn_id",
        "turn_index",
        "source_line",
        "line",
        "phase",
    ):
        value = row.get(key)
        if value in {None, ""}:
            continue
        out_key = "line" if key == "source_line" else key
        if out_key == "stable_source_id":
            out_key = "source_id"
        clean[out_key] = value
    return clean


def _refs_from_rows(rows: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    if not isinstance(rows, list):
        return refs
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested_refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, dict)]
        candidates = nested_refs or [row]
        for candidate in candidates:
            ref = _candidate_ref(candidate)
            if not ref:
                continue
            key = tuple(sorted((str(k), str(v)) for k, v in ref.items()))
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
            if len(refs) >= MAX_CANDIDATE_REFS:
                return refs
    return refs


def _candidate_refs(result: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key in ("evidence", "working_memory", "candidates", "cognitive_map"):
        refs.extend(_refs_from_rows(result.get(key) or []))
        if len(refs) >= MAX_CANDIDATE_REFS:
            break
    return refs[:MAX_CANDIDATE_REFS]


def _support_level(
    result: dict[str, Any],
    *,
    sensitivity: str,
    freshness: str,
    candidate_refs: list[dict[str, Any]],
) -> str:
    if sensitivity == "suppress" or freshness == "superseded":
        return "suppressed"
    decision = str(result.get("decision") or "skip")
    if decision == "skip" and not candidate_refs and not result.get("working_memory"):
        return "silent_scent"
    if result.get("evidence"):
        return "source_required"
    if result.get("candidates") or result.get("working_memory") or result.get("cognitive_map"):
        return "soft_hypothesis"
    return "silent_scent"


def _suggested_action(support_level: str, confidence: str) -> str:
    if support_level in {"suppressed", "silent_scent"}:
        return "ignore"
    if support_level == "source_required":
        return "source_reopen"
    return "ask_light_question" if confidence == "low" else "active_recall"


def _route_reason(support_level: str, suggested_action: str) -> str:
    if support_level == "suppressed":
        return "privacy_or_staleness_boundary"
    if support_level == "source_required":
        return "candidate_source_refs_may_matter_before_specific_claim"
    if suggested_action == "active_recall":
        return "possible_resonance_without_source_reopen"
    if suggested_action == "ask_light_question":
        return "weak_resonance_needs_user_anchor"
    return "no_actionable_fresh_thread_memory_signal"


def _when_not_to_use(support_level: str) -> list[str]:
    if support_level == "suppressed":
        return list(SUPPRESSED_WHEN_NOT_TO_USE)
    return list(BASE_WHEN_NOT_TO_USE)


def fresh_thread_scent_packet_from_decision(result: dict[str, Any]) -> dict[str, Any]:
    """Project hook/ambient recall output into the #282 fresh-thread contract."""

    confidence = _bucket(result.get("confidence"), CONFIDENCE_BUCKETS, "low")
    freshness = _bucket(result.get("freshness"), FRESHNESS_BUCKETS, "unknown")
    candidate_refs = _candidate_refs(result)
    sensitivity_default = "safe" if not candidate_refs and not result.get("candidates") else "caution"
    sensitivity = _bucket(result.get("sensitivity"), SENSITIVITY_BUCKETS, sensitivity_default)
    support_level = _support_level(
        result,
        sensitivity=sensitivity,
        freshness=freshness,
        candidate_refs=candidate_refs,
    )
    if support_level == "suppressed":
        candidate_refs = []
    suggested_action = _suggested_action(support_level, confidence)
    return {
        "kind": "aippocampus_fresh_thread_scent_packet",
        "schema_version": PACKET_SCHEMA_VERSION,
        "support_level": support_level,
        "confidence": confidence,
        "sensitivity": "suppress" if support_level == "suppressed" else sensitivity,
        "freshness": freshness,
        "route_reason": _route_reason(support_level, suggested_action),
        "candidate_refs": candidate_refs,
        "suggested_action": suggested_action,
        "when_not_to_use": _when_not_to_use(support_level),
        "source_boundary": {
            "navigation_only_until_source_reopened": True,
            "route_reason_is_not_source_fact": True,
            "candidate_refs_are_ids_only": True,
        },
    }


EXAMPLE_PACKETS = [
    fresh_thread_scent_packet_from_decision({"decision": "skip", "confidence": "low"}),
    fresh_thread_scent_packet_from_decision(
        {
            "decision": "scent",
            "confidence": "medium",
            "candidates": [{"thread_key": "session:example"}],
        }
    ),
    fresh_thread_scent_packet_from_decision(
        {
            "decision": "evidence",
            "confidence": "high",
            "evidence": [{"thread_key": "session:example", "message_id": "m1", "line": 12}],
        }
    ),
    fresh_thread_scent_packet_from_decision(
        {
            "decision": "scent",
            "confidence": "high",
            "sensitivity": "suppress",
            "candidates": [{"thread_key": "session:private"}],
        }
    ),
]
