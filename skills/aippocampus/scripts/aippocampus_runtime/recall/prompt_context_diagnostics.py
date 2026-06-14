"""Sanitize prompt-hook diagnostics for public debug output."""

from __future__ import annotations

from typing import Any

ROUTE_DELIVERY_FOREGROUND_PROFILES = {"ambient_hot_path", "explicit_recall"}
ROUTE_DELIVERY_REUSE_SOURCES = {
    "none",
    "exact_semantic_cache",
    "semantic_cue_cache",
    "semantic_disabled_by_operator",
    "semantic_unavailable_missing_auth",
    "semantic_provider_timeout",
    "cold_semantic_attempted",
    "cold_semantic_shadowed",
}
ROUTE_DELIVERY_BRIDGE_DIAGNOSTICS = {"semantic_evidence_without_source_bridge"}
ROUTE_DELIVERY_PROFILES = {
    "affective_life_context",
    "coding_current_repo",
    "exact_phrase",
    "generic_recall_meta",
    "journey_frontier",
    "low_value_casual",
    "normal_recall",
    "temporal_revisit",
}
ROUTE_DELIVERY_LANES = {
    "ambient_life_context",
    "journey_navigation",
    "recall_composer",
    "source_current_repo",
    "source_text",
    "stay_silent",
    "temporal_source_spread",
}
FOREGROUND_SUPPRESSION_REASONS = {
    "generic_meta_terms_only",
    "low_value_casual_no_memory_route_intent",
}


def _controlled(value: Any, allowed: set[str]) -> str | None:
    text = str(value or "")
    return text if text in allowed else None


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _foreground_suppression_reasons(raw: Any) -> list[str]:
    return [
        str(reason)
        for reason in raw or []
        if str(reason) in FOREGROUND_SUPPRESSION_REASONS
    ]


def _reason_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(reason) for reason in value}


def legacy_candidate_summary_suppressed(result: dict[str, Any]) -> bool:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    brief = ambient.get("brief_precision") if isinstance(ambient, dict) else {}
    if not isinstance(brief, dict):
        brief = {}
    raw_delivery = result.get("route_delivery_diagnostic")
    delivery: dict[str, Any] = raw_delivery if isinstance(raw_delivery, dict) else {}
    reasons = _reason_set(brief.get("foreground_suppression_reasons")) | _reason_set(
        delivery.get("foreground_suppression_reasons")
    )
    suppressed_count = max(
        _count(brief.get("composer_backstage_count")),
        _count(brief.get("alias_spillover_suppressed_count")),
        _count(brief.get("cross_project_generic_scent_suppressed_count")),
        _count(delivery.get("semantic_trigger_generic_term_suppressed_count")),
    )
    return (
        "generic_meta_terms_only" in reasons
        and _count(brief.get("foreground_card_count")) == 0
        and suppressed_count > 0
    )


def route_delivery_debug_summary(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    summary = {
        "foreground_profile": _controlled(
            raw.get("foreground_profile"), ROUTE_DELIVERY_FOREGROUND_PROFILES
        )
        or "ambient_hot_path",
        "foreground_route_profile": _controlled(
            raw.get("foreground_route_profile"), ROUTE_DELIVERY_PROFILES
        )
        or "normal_recall",
        "foreground_lane": _controlled(raw.get("foreground_lane"), ROUTE_DELIVERY_LANES)
        or "source_text",
        "generic_prompt_term_count": _count(raw.get("generic_prompt_term_count")),
        "specific_prompt_term_count": _count(raw.get("specific_prompt_term_count")),
        "semantic_trigger_generic_term_suppressed_count": _count(
            raw.get("semantic_trigger_generic_term_suppressed_count")
        ),
        "foreground_suppression_reasons": _foreground_suppression_reasons(
            raw.get("foreground_suppression_reasons")
        ),
        "semantic_bridge_diagnostic": _controlled(
            raw.get("semantic_bridge_diagnostic"), ROUTE_DELIVERY_BRIDGE_DIAGNOSTICS
        ),
        "semantic_gate_cache_hit_but_no_source_bridge": bool(
            raw.get("semantic_gate_cache_hit_but_no_source_bridge")
        ),
        "semantic_reuse_source": _controlled(
            raw.get("semantic_reuse_source"), ROUTE_DELIVERY_REUSE_SOURCES
        )
        or "none",
        "semantic_waited": bool(raw.get("semantic_waited")),
        "semantic_partial_failure": bool(raw.get("semantic_partial_failure")),
        "cold_semantic_shadowed": bool(raw.get("cold_semantic_shadowed")),
        "background_scheduled": bool(raw.get("background_scheduled")),
        "hot_path_candidates_after_merge": _count(
            raw.get("hot_path_candidates_after_merge")
        ),
        "final_candidate_count": _count(raw.get("final_candidate_count")),
        "evidence_count": _count(raw.get("evidence_count")),
        "semantic_source_reopen_route": bool(raw.get("semantic_source_reopen_route")),
        "semantic_source_reopen_candidate_count": _count(
            raw.get("semantic_source_reopen_candidate_count")
        ),
    }
    return {key: value for key, value in summary.items() if value is not None}


def brief_precision_debug_summary(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "sort_applied": bool(raw.get("sort_applied")),
        "foreground_route_profile": _controlled(
            raw.get("foreground_route_profile"), ROUTE_DELIVERY_PROFILES
        )
        or "normal_recall",
        "foreground_lane": _controlled(raw.get("foreground_lane"), ROUTE_DELIVERY_LANES)
        or "source_text",
        "foreground_card_count": _count(raw.get("foreground_card_count")),
        "composer_backstage_count": _count(raw.get("composer_backstage_count")),
        "alias_spillover_suppressed_count": _count(
            raw.get("alias_spillover_suppressed_count")
        ),
        "cross_project_generic_scent_suppressed_count": _count(
            raw.get("cross_project_generic_scent_suppressed_count")
        ),
        "foreground_suppression_reasons": _foreground_suppression_reasons(
            raw.get("foreground_suppression_reasons")
        ),
        "generic_prompt_term_count": _count(raw.get("generic_prompt_term_count")),
        "specific_prompt_term_count": _count(raw.get("specific_prompt_term_count")),
        "prompt_issue_ref_count": _count(raw.get("prompt_issue_ref_count")),
        "broad_context_intrusion_count": _count(raw.get("broad_context_intrusion_count")),
        "partial_issue_ref_broad_context_count": _count(
            raw.get("partial_issue_ref_broad_context_count")
        ),
        "same_thread_recentness_mismatch_count": _count(
            raw.get("same_thread_recentness_mismatch_count")
        ),
    }
