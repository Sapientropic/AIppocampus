"""Delivery posture helpers for subconscious working-memory routing."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.dream import lifecycle as dream_lifecycle

REOPEN_POSTURES = {
    dream_lifecycle.DELIVERY_NEEDS_REOPEN_CHECK,
    dream_lifecycle.DELIVERY_NEEDS_CONFIRMATION,
    dream_lifecycle.DELIVERY_UNRESOLVED_SOURCE,
    dream_lifecycle.DELIVERY_DIAGNOSTIC_ONLY,
}


def annotate_delivery(row: dict[str, Any], *, prompt: str) -> dict[str, Any]:
    delivery = dream_lifecycle.working_memory_delivery_posture(
        row,
        prompt=prompt,
        route_relevance=True,
    )
    row["public_authority_tier"] = delivery["public_authority_tier"]
    row["delivery_source_posture"] = delivery["delivery_source_posture"]
    row["delivery_next_action"] = delivery["delivery_next_action"]
    row["source_ref_count"] = delivery["source_ref_count"]
    row["delivery_posture_reason"] = delivery["reason"]
    return delivery


def dream_hypothesis_use(row: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any] | None:
    posture = delivery["delivery_source_posture"]
    if posture not in REOPEN_POSTURES:
        return None
    return {
        "action": "ask_to_confirm"
        if posture == dream_lifecycle.DELIVERY_NEEDS_CONFIRMATION
        else "reopen_source",
        "reason": delivery["reason"],
        "truth_boundary": row.get("truth_boundary"),
        "delivery_source_posture": posture,
        "public_authority_tier": delivery["public_authority_tier"],
        "source_ref_count": delivery["source_ref_count"],
        "strong_claim_requires_source_reopen": True,
        "render_boundary": "dream_hypothesis_not_source_fact",
    }


def with_delivery_fields(use: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
    return {
        **use,
        "delivery_source_posture": delivery["delivery_source_posture"],
        "public_authority_tier": delivery["public_authority_tier"],
    }
