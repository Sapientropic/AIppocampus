"""Foreground-safe projection for routed subconscious candidates."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.dream import lifecycle as dream_lifecycle


def _delivery_fields(row: dict[str, Any]) -> dict[str, Any]:
    delivery = dream_lifecycle.working_memory_delivery_posture(row)
    return {
        "public_authority_tier": row.get("public_authority_tier")
        or delivery["public_authority_tier"],
        "delivery_source_posture": row.get("delivery_source_posture")
        or delivery["delivery_source_posture"],
        "delivery_next_action": row.get("delivery_next_action")
        or delivery["delivery_next_action"],
        "delivery_posture_reason": row.get("delivery_posture_reason")
        or delivery["reason"],
        "source_ref_count": row.get("source_ref_count")
        or delivery["source_ref_count"],
        "raw_source_refs_emitted": False,
    }


def strip_for_hook(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        delivery_fields = _delivery_fields(row)
        out.append(
            {
                "route": row.get("route"),
                "ask_policy": row.get("ask_policy"),
                "risk": row.get("risk"),
                "candidate_key": row.get("candidate_key"),
                "candidate_type": row.get("candidate_type"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "recommendation": row.get("recommendation"),
                "confidence": row.get("confidence"),
                "project_label": row.get("project_label"),
                "matched_terms": row.get("matched_terms") or [],
                "source_finding_ids": row.get("source_finding_ids") or [],
                **delivery_fields,
                "score": row.get("score"),
                "truth_boundary": row.get("truth_boundary"),
                "dream_function": row.get("dream_function"),
                "foreground_use": row.get("foreground_use"),
                "sensitive_use_gate": row.get("sensitive_use_gate"),
                "dream_hypothesis_use": row.get("dream_hypothesis_use"),
                "constructive_artifact": row.get("constructive_artifact"),
                "prospective_invitation": row.get("prospective_invitation"),
                "journey_bridge_hypothesis": row.get("journey_bridge_hypothesis"),
            }
        )
    return out
