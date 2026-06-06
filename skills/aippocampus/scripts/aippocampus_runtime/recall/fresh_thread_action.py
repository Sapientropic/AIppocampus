#!/usr/bin/env python3
"""Agent-owned action policy for fresh-thread recall scent packets.

This module intentionally does not parse user prompts or classify emotions from
static phrase lists. Semantic/subconscious judgement belongs upstream in
source-backed packets, reviewed sidecars, active recall locks, or explicit task
context supplied by the foreground agent. The policy here only decides what the
agent is allowed to do with that navigation material.
"""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.recall.fresh_thread_scent import source_reopen_plan_from_refs

ACTION_SCHEMA_VERSION = 1
MAX_CANDIDATE_REFS = 3

IGNORE = "ignore"
USE_SILENTLY = "use_silently"
ASK_LIGHT_QUESTION = "ask_light_question"
MENTION_SOFT_HYPOTHESIS = "mention_soft_hypothesis"
ACTIVE_RECALL = "active_recall"
SOURCE_REOPEN = "source_reopen"

AGENT_ACTIONS = {
    IGNORE,
    USE_SILENTLY,
    ASK_LIGHT_QUESTION,
    MENTION_SOFT_HYPOTHESIS,
    ACTIVE_RECALL,
    SOURCE_REOPEN,
}

SUPPORT_LEVELS = {"silent_scent", "soft_hypothesis", "source_required", "suppressed"}
CONFIDENCE_BUCKETS = {"low", "medium", "high"}
SENSITIVITY_BUCKETS = {"safe", "caution", "suppress"}
FRESHNESS_BUCKETS = {"current", "possibly_stale", "superseded", "unknown"}
ACTIVATION_UPDATES = {"none", "tentative", "confirmed", "rejected", "retired"}
LOCK_STATES = {"ready", "pending", "expired", "failed"}

_LOCK_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")

DEFAULT_WHEN_NOT_TO_USE = [
    "Do not let the hook answer on behalf of the agent.",
    "Do not treat scent, route reasons, or active recall locks as source-backed facts.",
    "Do not personalize broad prompts unless memory would change the current answer, plan, or action.",
]

TASK_CONTEXT_FLAG_PROVENANCE = {
    "memory_may_change_answer": "foreground_agent_or_reviewed_sidecar_judgement",
    "specific_memory_claim": "foreground_agent_or_reviewed_sidecar_judgement",
    "low_specificity_prompt": "foreground_agent_or_reviewed_sidecar_judgement",
    "hard_risk_prompt": "foreground_agent_or_reviewed_sidecar_judgement",
    "broad_or_sensitive_prompt": "legacy_low_specificity_prompt_alias",
    "allow_gentle_hypothesis": "foreground_agent_judgement",
    "user_confirmed_memory_theme": "fresh_thread_activation_or_foreground_user_anchor",
    "route_suppressed_by_activation": "fresh_thread_activation_state",
    "prior_scent_without_new_anchor": "fresh_thread_activation_state",
    "current_checkout_required": "deterministic_repo_or_source_check",
    "current_repo_fact_query": "deterministic_repo_or_source_check",
    "activation_state": "fresh_thread_activation_state",
    "activation_update": "fresh_thread_activation_state",
    "activation_invalidation": "fresh_thread_activation_state",
    "activation_source_reopened": "fresh_thread_activation_state",
}


def _bucket(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _context_flag(context: dict[str, Any], key: str) -> bool:
    return bool(context.get(key))


def _activation_update(context: dict[str, Any]) -> str:
    return _bucket(context.get("activation_update"), ACTIVATION_UPDATES, "none")


def _packet_action_hint(packet: dict[str, Any]) -> str:
    hint = str(packet.get("advisory_action") or packet.get("suggested_action") or "").strip()
    return hint if hint in AGENT_ACTIONS else ""


def _hint_divergence_reason(action: str, hint: str, reason: str) -> str:
    if not hint:
        return "packet_did_not_provide_action_hint"
    if action == hint:
        return "final_policy_aligned_with_packet_hint"
    if action == IGNORE:
        return f"final_policy_suppressed_packet_hint:{reason}"
    if action == SOURCE_REOPEN:
        return f"final_policy_required_source_before_hint:{reason}"
    if hint == ACTIVE_RECALL:
        return f"final_policy_requires_task_context_or_source_before_active_recall:{reason}"
    return f"final_policy_overrode_packet_hint:{reason}"


def _task_context_contract(context: dict[str, Any]) -> dict[str, Any]:
    observed = {key: context[key] for key in sorted(context) if key in TASK_CONTEXT_FLAG_PROVENANCE}
    return {
        "semantic_flags_are_upstream_judgement": True,
        "policy_parses_raw_prompt": False,
        "policy_uses_static_phrase_lists": False,
        "known_flag_provenance": dict(sorted(TASK_CONTEXT_FLAG_PROVENANCE.items())),
        "observed_flags": observed,
        "unknown_flags": sorted(key for key in context if key not in TASK_CONTEXT_FLAG_PROVENANCE),
    }


def _clean_lock_id(value: Any) -> str:
    text = str(value or "").strip()
    if _LOCK_ID_RE.fullmatch(text):
        return text
    return ""


def _lock_state(active_recall_lock: dict[str, Any] | None) -> str:
    if not isinstance(active_recall_lock, dict):
        return "missing"
    state = str(active_recall_lock.get("state") or active_recall_lock.get("lock_state") or "").strip()
    return state if state in LOCK_STATES else "missing"


def _lock_id_for_state(active_recall_lock: dict[str, Any] | None, state: str) -> str:
    if state not in {"ready", "pending"} or not isinstance(active_recall_lock, dict):
        return ""
    return _clean_lock_id(active_recall_lock.get("lock_id"))


def _lock_reopenable_ref_count(active_recall_lock: dict[str, Any] | None) -> int | None:
    if not isinstance(active_recall_lock, dict):
        return None
    raw = active_recall_lock.get("reopenable_ref_count")
    if raw is None and isinstance(active_recall_lock.get("diagnostics"), dict):
        raw = active_recall_lock["diagnostics"].get("reopenable_ref_count")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


def _lock_handling(action: str, active_recall_lock: dict[str, Any] | None) -> tuple[str, str]:
    if action != ACTIVE_RECALL:
        return "none", ""
    state = _lock_state(active_recall_lock)
    if state == "ready":
        if _lock_reopenable_ref_count(active_recall_lock) == 0:
            return "wait_or_probe_lock", _lock_id_for_state(active_recall_lock, state)
        return "use_ready_lock", _lock_id_for_state(active_recall_lock, state)
    if state == "pending":
        return "wait_or_probe_lock", _lock_id_for_state(active_recall_lock, state)
    return "start_lock", ""


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


def _candidate_refs(packet: dict[str, Any], *, expose: bool) -> list[dict[str, Any]]:
    if not expose:
        return []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    raw_refs = packet.get("candidate_refs") or []
    if not isinstance(raw_refs, list):
        return refs
    for row in raw_refs:
        if not isinstance(row, dict):
            continue
        ref = _candidate_ref(row)
        if not ref:
            continue
        key = tuple(sorted((str(k), str(v)) for k, v in ref.items()))
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= MAX_CANDIDATE_REFS:
            break
    return refs


def _allowed_surface(action: str) -> str:
    if action == IGNORE:
        return "none"
    if action in {USE_SILENTLY, ACTIVE_RECALL}:
        return "internal_only"
    if action in {ASK_LIGHT_QUESTION, MENTION_SOFT_HYPOTHESIS}:
        return "gentle_hypothesis"
    if action == SOURCE_REOPEN:
        return "source_backed"
    return "none"


def _base_result(
    *,
    action: str,
    reason: str,
    packet: dict[str, Any],
    context: dict[str, Any],
    active_recall_lock: dict[str, Any] | None,
    specific_memory_claim: bool,
) -> dict[str, Any]:
    requires_source_reopen = action == SOURCE_REOPEN or specific_memory_claim
    expose_refs = action in {ACTIVE_RECALL, SOURCE_REOPEN}
    candidate_refs = _candidate_refs(packet, expose=expose_refs)
    support_level = _bucket(packet.get("support_level"), SUPPORT_LEVELS, "silent_scent")
    plan_support_level = (
        "source_required"
        if support_level == "source_required" or specific_memory_claim
        else support_level
    )
    reopen_plan = source_reopen_plan_from_refs(
        support_level=plan_support_level,
        candidate_refs=_candidate_refs(packet, expose=True),
    )
    lock_handling, lock_id = _lock_handling(action, active_recall_lock)
    source_refs_allowed = action == SOURCE_REOPEN
    packet_action_hint = _packet_action_hint(packet)
    result = {
        "kind": "aippocampus_fresh_thread_action_policy",
        "schema_version": ACTION_SCHEMA_VERSION,
        "agent_action": action,
        "reason": reason,
        "packet_action_hint": packet_action_hint,
        "packet_action_hint_authoritative": False,
        "hint_divergence_reason": _hint_divergence_reason(action, packet_action_hint, reason),
        "allowed_surface": _allowed_surface(action),
        "should_call_active_recall": action == ACTIVE_RECALL,
        "requires_source_reopen": requires_source_reopen,
        "source_refs_allowed": source_refs_allowed,
        "candidate_refs": candidate_refs,
        "lock_handling": lock_handling,
        "lock_id": lock_id,
        "activation_update": _activation_update(context),
        "source_rule": {
            "specific_claim_requires_source_reopen": True,
            "scent_and_lock_are_navigation_only": True,
            "source_refs_allowed_only_after_reopen": source_refs_allowed,
        },
        "privacy_boundary": {
            "rule": _privacy_rule(action, reason),
            "lock_boundary": "active_recall_locks_are_route_handles_not_facts",
            "prompt_text_serialized": False,
            "raw_snippets_serialized": False,
        },
        "task_context_contract": _task_context_contract(context),
        "when_not_to_use": list(DEFAULT_WHEN_NOT_TO_USE),
    }
    if reopen_plan is not None:
        result["reopen_plan"] = reopen_plan
        result["manual_query_invention_expected"] = bool(
            reopen_plan.get("manual_query_invention_expected")
        )
        result["manual_query_invention_count"] = 0
    return result


def _privacy_rule(action: str, reason: str) -> str:
    if reason == "hard_risk_prompt_blocked":
        return "Hard-risk route blocked or redacted; do not use memory material for answer content."
    if action == IGNORE:
        return "Suppressed, stale, or non-actionable scent must not steer answer or tone."
    if action == USE_SILENTLY:
        return "Internal resonance only; do not mention a memory theme without user anchor or source."
    if action == ASK_LIGHT_QUESTION:
        return "Ask for an anchor instead of asserting unreopened or low-confidence history."
    if action == MENTION_SOFT_HYPOTHESIS:
        return "Name only a soft hypothesis; reopen source before specific claims."
    if action == ACTIVE_RECALL:
        return "Probe memory routes deliberately; do not present lock or scent material as facts."
    if action == SOURCE_REOPEN:
        return "Use clean source before any specific memory-backed claim."
    return "Navigation material is not source-backed fact."


def fresh_thread_action_from_packet(
    packet: dict[str, Any] | None,
    *,
    task_context: dict[str, Any] | None = None,
    active_recall_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose the foreground agent action for a #282 fresh-thread scent packet.

    `task_context` carries explicit upstream flags such as
    `memory_may_change_answer`, `specific_memory_claim`,
    `low_specificity_prompt`, `hard_risk_prompt`,
    `allow_gentle_hypothesis`, and
    `user_confirmed_memory_theme`. Those flags come from foreground agent
    judgement, activation state, reviewed sidecars, active recall locks, or
    deterministic repo/source checks. This keeps semantic judgement out of this
    deterministic policy layer.
    """

    context = task_context or {}
    if not isinstance(packet, dict):
        return _base_result(
            action=IGNORE,
            reason="no_fresh_thread_packet",
            packet={},
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=False,
        )

    support_level = _bucket(packet.get("support_level"), SUPPORT_LEVELS, "silent_scent")
    confidence = _bucket(packet.get("confidence"), CONFIDENCE_BUCKETS, "low")
    sensitivity = _bucket(packet.get("sensitivity"), SENSITIVITY_BUCKETS, "caution")
    freshness = _bucket(packet.get("freshness"), FRESHNESS_BUCKETS, "unknown")
    refs = _candidate_refs(packet, expose=True)
    source_required_plan = source_reopen_plan_from_refs(
        support_level="source_required",
        candidate_refs=refs,
    )
    has_reopenable_refs = bool(
        source_required_plan and int(source_required_plan.get("reopenable_ref_count") or 0) > 0
    )

    specific_memory_claim = _context_flag(context, "specific_memory_claim")
    memory_may_change_answer = _context_flag(context, "memory_may_change_answer")
    user_confirmed_theme = _context_flag(context, "user_confirmed_memory_theme")
    low_specificity_prompt = _context_flag(context, "low_specificity_prompt") or _context_flag(
        context, "broad_or_sensitive_prompt"
    )
    hard_risk_prompt = _context_flag(context, "hard_risk_prompt")
    allow_gentle_hypothesis = _context_flag(context, "allow_gentle_hypothesis")
    route_suppressed_by_activation = _context_flag(context, "route_suppressed_by_activation")
    prior_scent_without_new_anchor = _context_flag(context, "prior_scent_without_new_anchor")
    current_checkout_required = _context_flag(context, "current_checkout_required") or _context_flag(
        context, "current_repo_fact_query"
    )

    if support_level == "suppressed" or sensitivity == "suppress" or freshness == "superseded":
        return _base_result(
            action=IGNORE,
            reason="suppressed_or_superseded_packet",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=False,
        )

    if route_suppressed_by_activation:
        return _base_result(
            action=IGNORE,
            reason="activation_state_suppressed_route",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=False,
        )

    if hard_risk_prompt:
        return _base_result(
            action=IGNORE,
            reason="hard_risk_prompt_blocked",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=False,
        )

    if current_checkout_required:
        return _base_result(
            action=IGNORE,
            reason="current_checkout_required_read_current_repo_first",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=False,
        )

    if specific_memory_claim and refs and not has_reopenable_refs:
        return _base_result(
            action=IGNORE,
            reason="specific_memory_claim_has_no_reopenable_source_ref",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=True,
        )

    if specific_memory_claim and refs:
        return _base_result(
            action=SOURCE_REOPEN,
            reason="specific_memory_claim_requires_source_reopen",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=True,
        )

    if prior_scent_without_new_anchor and refs:
        return _base_result(
            action=USE_SILENTLY,
            reason="activation_state_holds_prior_scent_internal",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if support_level == "source_required" and refs and not has_reopenable_refs:
        return _base_result(
            action=IGNORE,
            reason="source_required_packet_has_no_reopenable_source_ref",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if support_level == "source_required" and refs:
        return _base_result(
            action=SOURCE_REOPEN,
            reason="source_required_packet_has_candidate_refs",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if support_level == "silent_scent" or not refs:
        return _base_result(
            action=IGNORE,
            reason="no_actionable_fresh_thread_route",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if confidence == "low" and low_specificity_prompt:
        return _base_result(
            action=USE_SILENTLY,
            reason="weak_low_specificity_scent_kept_internal",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if confidence == "low":
        return _base_result(
            action=ASK_LIGHT_QUESTION,
            reason="weak_scent_needs_user_anchor",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if memory_may_change_answer or user_confirmed_theme:
        return _base_result(
            action=ACTIVE_RECALL,
            reason="scent_could_change_answer_plan_or_action",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    if allow_gentle_hypothesis and sensitivity == "safe":
        return _base_result(
            action=MENTION_SOFT_HYPOTHESIS,
            reason="safe_soft_hypothesis_can_be_named_gently",
            packet=packet,
            context=context,
            active_recall_lock=active_recall_lock,
            specific_memory_claim=specific_memory_claim,
        )

    return _base_result(
        action=ASK_LIGHT_QUESTION,
        reason="soft_hypothesis_needs_agent_or_user_anchor",
        packet=packet,
        context=context,
        active_recall_lock=active_recall_lock,
        specific_memory_claim=specific_memory_claim,
    )


_SOFT_DESIGN_PACKET = {
    "support_level": "soft_hypothesis",
    "confidence": "medium",
    "sensitivity": "safe",
    "freshness": "current",
    "advisory_action": "active_recall",
    "candidate_refs": [{"source_id": "clean:demo:design", "thread_key": "session:design"}],
}

_CONFIRMED_THEME_PACKET = {
    "support_level": "soft_hypothesis",
    "confidence": "high",
    "sensitivity": "safe",
    "freshness": "current",
    "advisory_action": "active_recall",
    "candidate_refs": [{"source_id": "clean:demo:theme", "thread_key": "session:theme"}],
}

_SOURCE_REQUIRED_PACKET = {
    "support_level": "source_required",
    "confidence": "high",
    "sensitivity": "safe",
    "freshness": "current",
    "advisory_action": "source_reopen",
    "candidate_refs": [
        {"source_id": "clean:demo:profile", "thread_key": "session:profile", "line": 12}
    ],
}

_LOW_BROAD_PACKET = {
    "support_level": "soft_hypothesis",
    "confidence": "low",
    "sensitivity": "caution",
    "freshness": "unknown",
    "suggested_action": "ask_light_question",
    "candidate_refs": [{"source_id": "clean:demo:pressure", "thread_key": "session:pressure"}],
}

_SILENT_PACKET = {
    "support_level": "silent_scent",
    "confidence": "low",
    "sensitivity": "safe",
    "freshness": "unknown",
    "suggested_action": "ignore",
    "candidate_refs": [],
}

_SUPPRESSED_PACKET = {
    "support_level": "suppressed",
    "confidence": "high",
    "sensitivity": "suppress",
    "freshness": "unknown",
    "suggested_action": "ignore",
    "candidate_refs": [],
}

EXAMPLE_ACTION_DECISIONS = [
    {
        "case_type": "positive",
        "scenario": "portable_design_preference_could_change_next_step",
        "decision": fresh_thread_action_from_packet(
            _SOFT_DESIGN_PACKET,
            task_context={"memory_may_change_answer": True},
            active_recall_lock={"state": "ready", "lock_id": "lock_demo_design"},
        ),
    },
    {
        "case_type": "positive",
        "scenario": "user_confirmed_prior_theme_uses_active_recall_lock",
        "decision": fresh_thread_action_from_packet(
            _CONFIRMED_THEME_PACKET,
            task_context={"user_confirmed_memory_theme": True},
            active_recall_lock={"state": "pending", "lock_id": "lock_demo_theme"},
        ),
    },
    {
        "case_type": "positive",
        "scenario": "specific_profile_claim_requires_source_reopen",
        "decision": fresh_thread_action_from_packet(
            _SOURCE_REQUIRED_PACKET,
            task_context={"specific_memory_claim": True},
        ),
    },
    {
        "case_type": "negative_control",
        "scenario": "low_specificity_first_turn_stays_internal",
        "decision": fresh_thread_action_from_packet(
            _LOW_BROAD_PACKET,
            task_context={"low_specificity_prompt": True},
        ),
    },
    {
        "case_type": "negative_control",
        "scenario": "generic_prompt_without_route_is_ignored",
        "decision": fresh_thread_action_from_packet(_SILENT_PACKET),
    },
    {
        "case_type": "negative_control",
        "scenario": "suppressed_or_stale_packet_is_ignored",
        "decision": fresh_thread_action_from_packet(_SUPPRESSED_PACKET),
    },
]
