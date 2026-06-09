#!/usr/bin/env python3
"""Fresh-thread scent packet contract for progressive recall.

The packet is a privacy-safe navigation surface for the foreground agent. It is
not evidence, not a summary of memory, and not user-facing narration. Specific
memory-backed claims still need clean-source reopen through the candidate refs.
"""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.question.source_refs import source_ref_key
from aippocampus_runtime.recall.authority import with_trust_fields

SUPPORT_LEVELS = {"silent_scent", "soft_hypothesis", "source_required", "suppressed"}
CONFIDENCE_BUCKETS = {"low", "medium", "high"}
SENSITIVITY_BUCKETS = {"safe", "caution", "suppress"}
FRESHNESS_BUCKETS = {"current", "possibly_stale", "superseded", "unknown"}
ADVISORY_ACTIONS = {"ask_light_question", "active_recall", "source_reopen", "ignore"}
# Public compatibility name for older cards/tests that imported the old packet
# vocabulary. Do not treat this alias as permission to make it the final action.
SUGGESTED_ACTIONS = ADVISORY_ACTIONS

PACKET_SCHEMA_VERSION = 1
MAX_CANDIDATE_REFS = 3
SOURCE_REOPEN_FAILURE_REASON_CODES = [
    "stale_handle",
    "source_missing",
    "permission_block",
    "index_stale_lkg_needed",
]

BASE_WHEN_NOT_TO_USE = [
    "Do not present this packet as source-backed fact.",
    "Do not assert unreopened source details or source ids as answer content.",
    "Do not personalize a broad prompt after the local task has moved on.",
]

SUPPRESSED_WHEN_NOT_TO_USE = [
    "Do not use suppressed packets for answer content, tone steering, or memory claims.",
    "Do not reopen source when the route is secret/property-risk, stale, or explicitly suppressed.",
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


def _is_reopenable_ref(ref: dict[str, Any]) -> bool:
    if not isinstance(ref, dict):
        return False
    thread_key, message_id, turn_anchor, line = source_ref_key(ref)
    return bool(thread_key and (message_id or turn_anchor or line or ref.get("thread_key")))


def _reopenable_ref_count(refs: list[dict[str, Any]]) -> int:
    return sum(1 for ref in refs if _is_reopenable_ref(ref))


def _primary_reopenable_ref(refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ref in refs:
        if _is_reopenable_ref(ref):
            return dict(ref)
    return None


def _reopen_arguments(ref: dict[str, Any]) -> dict[str, Any]:
    selectors = {
        key: ref[key]
        for key in ("message_id", "turn_id", "turn_index")
        if key in ref
    }
    if selectors:
        return selectors
    return {key: ref[key] for key in ("thread_key", "line") if key in ref}


def _recommended_reopen_tool(ref: dict[str, Any] | None) -> str:
    if not ref:
        return "source_ref_reopen"
    if any(key in ref for key in ("message_id", "turn_id", "turn_index")):
        return "get_turn_context"
    if ref.get("thread_key") and not any(key in ref for key in ("line", "source_id")):
        return "reopen_registry_thread_source_index"
    return "source_ref_reopen"


def source_reopen_plan_from_refs(
    *,
    support_level: str,
    candidate_refs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build the ids-only #707 source reopen plan for source-required packets."""

    if support_level != "source_required":
        return None
    primary_ref = _primary_reopenable_ref(candidate_refs)
    reopenable_count = _reopenable_ref_count(candidate_refs)
    reason_codes = ["source_required"]
    if primary_ref:
        reason_codes.append("candidate_source_ref_reopenable")
    elif candidate_refs:
        reason_codes.append("no_reopenable_source_ref")
    else:
        reason_codes.append("no_candidate_source_ref")

    plan: dict[str, Any] = {
        "kind": "source_ref_reopen",
        "status": "ready" if primary_ref else "blocked",
        "recommended_tool": _recommended_reopen_tool(primary_ref),
        "arguments": _reopen_arguments(primary_ref) if primary_ref else {},
        "candidate_ref_count": len(candidate_refs),
        "reopenable_ref_count": reopenable_count,
        "reason_codes": reason_codes,
        "failure_reason_codes": list(SOURCE_REOPEN_FAILURE_REASON_CODES),
        "manual_query_invention_expected": False,
    }
    if primary_ref:
        plan["primary_ref"] = primary_ref
    else:
        plan["blocked_recovery_action"] = "ask_light_question"
        plan["blocked_recovery_goal"] = "recover_a_reopenable_source_anchor_without_guessing"
        plan["blocked_recovery_boundary"] = (
            "Ask for a minimal source anchor or permission to search; do not answer "
            "from the packet and do not invent manual query terms from private scent."
        )
    return plan


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
    if result.get("semantic_source_reopen_route") and candidate_refs:
        return "source_required"
    if result.get("candidates") or result.get("working_memory") or result.get("cognitive_map"):
        return "soft_hypothesis"
    return "silent_scent"


def _advisory_action(support_level: str, confidence: str) -> str:
    if support_level in {"suppressed", "silent_scent"}:
        return "ignore"
    if support_level == "source_required":
        return "source_reopen"
    return "ask_light_question" if confidence == "low" else "active_recall"


def _route_reason(support_level: str, advisory_action: str) -> str:
    if support_level == "suppressed":
        return "hard_risk_or_staleness_boundary"
    if support_level == "source_required":
        return "candidate_source_refs_may_matter_before_specific_claim"
    if advisory_action == "active_recall":
        return "possible_resonance_without_source_reopen"
    if advisory_action == "ask_light_question":
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
    advisory_action = _advisory_action(support_level, confidence)
    packet = {
        "kind": "aippocampus_fresh_thread_scent_packet",
        "schema_version": PACKET_SCHEMA_VERSION,
        "support_level": support_level,
        "confidence": confidence,
        "sensitivity": "suppress" if support_level == "suppressed" else sensitivity,
        "freshness": freshness,
        "route_reason": _route_reason(support_level, advisory_action),
        "candidate_refs": candidate_refs,
        "candidate_ref_count": len(candidate_refs),
        "reopenable_ref_count": _reopenable_ref_count(candidate_refs),
        "advisory_action": advisory_action,
        # Back-compat alias for older cards and reports. The action policy owns
        # final decisions and may intentionally diverge from this packet hint.
        "suggested_action": advisory_action,
        "when_not_to_use": _when_not_to_use(support_level),
        "source_boundary": {
            "navigation_only_until_source_reopened": True,
            "route_reason_is_not_source_fact": True,
            "candidate_refs_are_ids_only": True,
            "reopen_plan_is_navigation_not_evidence": True,
            "advisory_action_is_not_final_agent_action": True,
            "final_action_owned_by_fresh_thread_action_policy": True,
        },
    }
    reopen_plan = source_reopen_plan_from_refs(
        support_level=support_level,
        candidate_refs=candidate_refs,
    )
    if reopen_plan is not None:
        packet["reopen_plan"] = reopen_plan
    return with_trust_fields(packet)


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
