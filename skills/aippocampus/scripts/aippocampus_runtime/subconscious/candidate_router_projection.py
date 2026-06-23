"""Foreground-safe projection for routed subconscious candidates."""

from __future__ import annotations

from typing import Any


def strip_for_hook(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
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
                "source_refs": row.get("source_refs") or [],
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
