#!/usr/bin/env python3
"""Project familiarity sidecars into source-backed avatar posture.

Avatar illumination is a thin consumer of existing source-backed familiarity
cards. It may bias attention and posture, but it never turns a card, shadow, or
semantic invalidation signal into claim-ready evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.navigation.avatar_illumination_support import (
    ACTION_GRAMMAR_BLOCKED,
    ACTION_GRAMMAR_SHADOW,
    AUTHORITY_LEVEL,
    CLAIM_PERMISSION,
    DECISION_SHADOW_KIND,
    FOREGROUND_KIND,
    SCHEMA_VERSION,
    STATE_KIND,
    activation,
    active_task_facets,
    attention_bias,
    card_state,
    code,
    decision_shadow_action,
    facet_illumination,
    guidance_text,
    mapping,
    posture_line,
    posture_tensions,
    privacy_state,
    semantic_invalidation_state,
    strings,
    task_relevant,
    text,
)
from aippocampus_runtime.ops.route_readiness import safe_source_refs


def build_source_backed_avatar_state(
    card: Mapping[str, Any],
    *,
    task: str = "",
    semantic_invalidation_events: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a source-backed posture state from one familiarity card."""

    refs = safe_source_refs(card.get("source_refs"))
    semantic_state = semantic_invalidation_state(semantic_invalidation_events)
    state, lifecycle_state, action_grammar = card_state(card, semantic_state, refs)
    illumination = facet_illumination(card, task, refs)
    selected_for_task = task_relevant(card, task)
    task_relevance = {
        "status": "selected_for_task" if selected_for_task else "irrelevant_to_task",
        "task_present": bool(text(task, 80)),
    }
    active = lifecycle_state in {"active", "weak", "narrowed"}
    narrow_to = list(semantic_state.get("narrow_to_facets") or []) if lifecycle_state == "narrowed" else []
    if lifecycle_state == "narrowed" and not narrow_to:
        narrow_to = ["archivist"]
    active_facets = active_task_facets(illumination, narrow_to_facets=narrow_to) if active else []
    if lifecycle_state == "active" and max((item["weight"] for item in active_facets), default=0.0) < 0.5:
        lifecycle_state = "weak"

    first_source = text(semantic_state.get("first_source_to_reopen"), 220) or text(
        card.get("first_source_to_reopen"), 220
    )
    if not first_source and refs:
        first_source = text(refs[0].get("path") or refs[0].get("source_id"), 220)
    shadow_record = _shadow_record(
        state=state,
        semantic_state=semantic_state,
        freshness=card.get("freshness"),
        first_source=first_source,
    )
    return {
        "kind": STATE_KIND,
        "schema_version": SCHEMA_VERSION,
        "avatar_state_id": stable_json_join_id(
            "avatar",
            card.get("card_id"),
            task,
            semantic_state.get("reason_codes"),
            sep="\0",
            length=18,
        ),
        "source_card_id": text(card.get("card_id"), 140),
        "domain": text(card.get("domain"), 60) or "unknown",
        "landmark": text(card.get("landmark"), 140),
        "card_state": state,
        "lifecycle_state": lifecycle_state,
        "source_refs": refs,
        "source_ref_count": len(refs),
        "first_source_to_reopen": first_source,
        "stop_after": text(card.get("stop_after"), 260),
        "do_not_use_for": strings(card.get("do_not_use_for"), limit=8),
        "task_relevance": task_relevance,
        "selected_for_task": selected_for_task,
        "semantic_invalidation": semantic_state,
        "facet_illumination": illumination,
        "active_facets": active_facets,
        "posture_tensions": posture_tensions(active_facets),
        "shadow_record": shadow_record,
        "activation": activation(active=active, refs=refs, state=state, illumination=illumination),
        "foreground_effect": {
            "attention_bias": attention_bias(active_facets, action_grammar=action_grammar),
            "posture": posture_line(active_facets, lifecycle_state=lifecycle_state),
            "avoid": ["factual_claim_from_avatar_state", *strings(card.get("do_not_use_for"), limit=4)],
        },
        "action_grammar": action_grammar,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_reopen_required_before_claim": True,
        "consumer_policy": {
            "posture_only": True,
            "may_raise_authority": False,
            "may_emit_foreground_fact": False,
            "requires_source_reopen_before_claim": True,
        },
    }


def _shadow_record(
    *,
    state: str,
    semantic_state: Mapping[str, Any],
    freshness: Any,
    first_source: str,
) -> dict[str, Any]:
    if state == "partial_invalidation":
        return {
            "status": "shadow_candidate",
            "broader_scope_status": "suspect_until_reopened",
            "reason_codes": list(semantic_state.get("reason_codes") or []),
            "first_source_to_reopen": first_source,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
        }
    if state == "suspect":
        return {
            "status": "reopen_required",
            "reason_codes": list(semantic_state.get("reason_codes") or []) or [f"freshness_{code(freshness)}"],
            "first_source_to_reopen": first_source,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
        }
    return {}


def project_avatar_state_for_foreground(
    state: Mapping[str, Any],
    *,
    max_packet_bytes: int = 900,
) -> dict[str, Any]:
    """Return the tiny foreground-safe posture packet for an avatar state."""

    lifecycle = code(state.get("lifecycle_state"))
    action_grammar = text(state.get("action_grammar"), 80) or ACTION_GRAMMAR_BLOCKED
    selected_for_task = state.get("selected_for_task") is not False
    emitted = (
        selected_for_task
        and lifecycle in {"active", "weak", "narrowed"}
        and action_grammar != ACTION_GRAMMAR_BLOCKED
    )
    effect = mapping(state.get("foreground_effect"))
    blocked_reason = "irrelevant_to_task" if not selected_for_task else ""
    packet = {
        "kind": FOREGROUND_KIND,
        "schema_version": SCHEMA_VERSION,
        "avatar_state_id": text(state.get("avatar_state_id"), 140),
        "source_card_id": text(state.get("source_card_id"), 140),
        "emitted": emitted,
        "lifecycle_state": lifecycle,
        "posture": text(effect.get("posture"), 220),
        "attention_bias": strings(effect.get("attention_bias"), limit=4),
        "first_source_to_reopen": text(state.get("first_source_to_reopen"), 220),
        "stop_after": text(state.get("stop_after"), 240),
        "recommended_next": (
            "continue_with_posture"
            if emitted and lifecycle != "narrowed"
            else ("continue_without_avatar" if blocked_reason else "reopen_source")
        ),
        "source_reopen_required_before_claim": True,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "action_grammar": action_grammar,
    }
    if blocked_reason:
        packet["reason"] = blocked_reason
        packet["posture"] = ""
        packet["attention_bias"] = []
    packet_size = _packet_size(packet)
    if packet_size > max_packet_bytes:
        packet["stop_after"] = text(packet.get("stop_after"), 120)
        packet["first_source_to_reopen"] = text(packet.get("first_source_to_reopen"), 140)
        packet_size = _packet_size(packet)
    if packet_size > max_packet_bytes:
        packet.pop("source_card_id", None)
        packet.pop("stop_after", None)
        packet_size = _packet_size(packet)
    if packet_size > max_packet_bytes:
        packet.update(
            {
                "emitted": False,
                "recommended_next": "reopen_source",
                "reason": "packet_byte_budget_exceeded",
                "attention_bias": ["source_reopen_first"],
                "posture": "reopen the cited source before using avatar posture",
            }
        )
        packet_size = _packet_size(packet)
    packet["packet_bytes"] = packet_size
    return packet


def _packet_size(packet: Mapping[str, Any]) -> int:
    return len(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def decision_shadow_negative_attention(
    card: Mapping[str, Any],
    *,
    task: str = "",
    semantic_invalidation_events: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project decision_shadow as negative attention, not a permanent ban."""

    shadow = mapping(card.get("decision_shadow"))
    refs = safe_source_refs(card.get("source_refs"))
    semantic_state = semantic_invalidation_state(semantic_invalidation_events)
    base = {
        "kind": DECISION_SHADOW_KIND,
        "schema_version": SCHEMA_VERSION,
        "source_card_id": text(card.get("card_id"), 140),
        "source_refs": refs,
        "first_source_to_reopen": text(
            semantic_state.get("first_source_to_reopen") or card.get("first_source_to_reopen"),
            220,
        ),
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "still_rejected_claim_allowed": False,
        "permanent_blacklist": False,
        "source_reopen_required_before_claim": True,
    }
    if not shadow:
        return {**base, "emitted": False, "reason": "missing_decision_shadow"}
    if not refs:
        return {**base, "emitted": False, "reason": "missing_source_refs"}
    if privacy_state(card) in {"blocked", "private", "sensitive", "partition_blocked", "ignore_or_blocked"}:
        return {**base, "emitted": False, "reason": "blocked_boundary", "action_grammar": ACTION_GRAMMAR_BLOCKED}
    if task and not task_relevant(card, task):
        return {**base, "emitted": False, "reason": "irrelevant_to_task"}
    if semantic_state.get("active"):
        return {
            **base,
            "emitted": True,
            "status": "shadow_candidate",
            "guidance_action": "reopen_first",
            "old_rejection_reason_invalidated": True,
            "reason_codes": list(semantic_state.get("reason_codes") or []),
            "action_grammar": ACTION_GRAMMAR_SHADOW,
            "guidance": "old rejection weakened; reopen source before repeating or reviving the route",
        }
    action = decision_shadow_action(shadow)
    return {
        **base,
        "emitted": True,
        "status": "active_negative_attention",
        "guidance_action": action,
        "old_rejection_reason_invalidated": False,
        "source_thickness": text(shadow.get("source_thickness"), 40) or "usable",
        "action_grammar": ACTION_GRAMMAR_SHADOW,
        "guidance": guidance_text(action),
    }
