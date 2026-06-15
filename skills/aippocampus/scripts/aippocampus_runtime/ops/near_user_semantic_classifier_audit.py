"""Audit table for near-user semantic classifier placement."""

from __future__ import annotations

from typing import Any

SEVEN_QUESTIONS = (
    "layer",
    "source",
    "artifact",
    "validation",
    "empty_behavior",
    "hook_permission",
    "model_authority",
)


def audit_rows() -> list[dict[str, Any]]:
    return [
        {
            "file": "macro/three_powers.py",
            "function": "infer_active_layer",
            "current_authority": "direction_only",
            "user_nearness": "near_user_route_intent",
            "classification": "demote",
            "proposed_owner": "semantic_profile_or_reviewed_route_cue",
            "phrase_table_role": "fallback_scent_only",
            "fallback_diagnostics": [
                "keyword_fallback_used",
                "semantic_profile_absent",
                "active_layer_unknown_requires_source_reopen",
            ],
            "seven_question_answer": {
                "layer": "runtime_navigation_scent",
                "source": "query text only unless three_powers_layer_profile is supplied",
                "artifact": "layer_profile diagnostic",
                "validation": "unit tests require fallback cannot dominate source-backed routes",
                "empty_behavior": "unknown/ambiguous, never default human",
                "hook_permission": "may rank only as bounded navigation lift",
                "model_authority": "none; no source_open or fact claim",
            },
        },
        {
            "file": "subconscious/event_salience_gate.py",
            "function": "classify_event_salience",
            "current_authority": "navigation_intake_metadata",
            "user_nearness": "near_user_clean_source_turns",
            "classification": "keep_with_sampling_diagnostics",
            "proposed_owner": "subconscious_intake_gate",
            "phrase_table_role": "safety_exact_noise_bootstrap",
            "fallback_diagnostics": ["skipped_by_reason", "missed_high_signal_count"],
            "seven_question_answer": {
                "layer": "subconscious_intake",
                "source": "clean-source turn metadata and source refs",
                "artifact": "event_salience sidecar",
                "validation": "selected/skipped/missed-high-signal counts",
                "empty_behavior": "skip/deprioritize, never delete",
                "hook_permission": "scheduler intake budget only",
                "model_authority": "none",
            },
        },
        {
            "file": "subconscious/question_extraction_gate.py",
            "function": "filter_question_extraction_turns",
            "current_authority": "navigation_intake_metadata",
            "user_nearness": "near_user_question_intent",
            "classification": "keep_with_uncertain_sampling",
            "proposed_owner": "question_tracking_review_queue",
            "phrase_table_role": "bootstrap_prefilter",
            "fallback_diagnostics": ["skipped_by_reason", "uncertain_sampling_recommended"],
            "seven_question_answer": {
                "layer": "subconscious_question_intake",
                "source": "clean-source turn metadata",
                "artifact": "question gate report",
                "validation": "skip reasons and repair feedback",
                "empty_behavior": "sample uncertain later, do not assert no question",
                "hook_permission": "model payload reduction only",
                "model_authority": "none",
            },
        },
        {
            "file": "recall/query_policy.py",
            "function": "query policy phrase fallbacks",
            "current_authority": "direction_only",
            "user_nearness": "foreground_query",
            "classification": "keep",
            "proposed_owner": "recall_policy",
            "phrase_table_role": "safety_exact_fallback",
            "fallback_diagnostics": ["query_policy_fallback_used"],
            "seven_question_answer": {
                "layer": "foreground_recall_policy",
                "source": "stable cues/reviewed policy only",
                "artifact": "query policy diagnostics",
                "validation": "route scoring tests",
                "empty_behavior": "fall back to source search",
                "hook_permission": "bounded route planning",
                "model_authority": "none",
            },
        },
    ]


def audit_report() -> dict[str, Any]:
    rows = audit_rows()
    complete = [
        row
        for row in rows
        if set((row.get("seven_question_answer") or {}).keys()) >= set(SEVEN_QUESTIONS)
    ]
    return {
        "kind": "near_user_semantic_classifier_audit",
        "schema_version": 1,
        "row_count": len(rows),
        "complete_seven_question_rows": len(complete),
        "rows": rows,
        "placement_rule": "No near-user semantic concept should be added without seven-question placement.",
        "fallback_policy": {
            "phrase_tables_are_allowed_for": [
                "safety",
                "exact",
                "noise",
                "bootstrap",
                "fallback",
            ],
            "phrase_tables_must_report": [
                "keyword_fallback_used",
                "semantic_profile_absent",
                "skipped_by_reason",
                "uncertain_sampling_recommended",
            ],
        },
        "cannot_claim": [
            "regex_classifier_is_source_truth",
            "keyword_fallback_can_dominate_source_backed_route",
            "unknown_orientation_defaults_to_human",
        ],
    }


__all__ = ["SEVEN_QUESTIONS", "audit_report", "audit_rows"]
