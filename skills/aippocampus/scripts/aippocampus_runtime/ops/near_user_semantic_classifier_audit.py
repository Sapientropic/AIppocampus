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

REQUIRED_AUDIT_SURFACES = frozenset(
    {
        "macro/three_powers.py",
        "subconscious/event_salience_gate.py",
        "subconscious/question_extraction_gate.py",
        "recall/query_policy.py",
        "recall/prompt_cue_catalog.py",
        "recall/strategy_planner.py",
        "subconscious/candidate_router.py",
        "recall/semantic_recall_gate.py",
    }
)

SUSPECT_AUDIT_SURFACES = frozenset(
    {
        "recall/prompt_cue_catalog.py",
        "recall/strategy_planner.py",
        "subconscious/candidate_router.py",
        "recall/semantic_recall_gate.py",
    }
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
        {
            "file": "recall/prompt_cue_catalog.py",
            "function": "prompt cue catalog matchers",
            "current_authority": "direction_only",
            "user_nearness": "foreground_prompt_text",
            "classification": "keep_with_false_positive_diagnostics",
            "proposed_owner": "foreground_recall_bootstrap_cell",
            "phrase_table_role": "evidence_request_trigger_not_evidence",
            "fallback_diagnostics": [
                "prompt_cue_matched",
                "prompt_cue_false_positive_guard",
                "no_match_continues_other_gates",
            ],
            "seven_question_answer": {
                "layer": "foreground_recall_bootstrap_cell",
                "source": "current prompt text plus static cue and pattern tables",
                "artifact": "matched cue and route diagnostics only",
                "validation": "prompt cue, hot-path, and false-positive tests",
                "empty_behavior": "no forced recall; continue other gates",
                "hook_permission": "allowed only as cheap deterministic matching",
                "model_authority": "none; scent or evidence-request trigger only",
            },
        },
        {
            "file": "recall/strategy_planner.py",
            "function": "plan_recall_strategy",
            "current_authority": "direction_only",
            "user_nearness": "foreground_query",
            "classification": "keep_with_policy_payload_diagnostics",
            "proposed_owner": "foreground_recall_policy",
            "phrase_table_role": "strategy_bootstrap_not_classifier_truth",
            "fallback_diagnostics": [
                "explicit_strategy_present",
                "source_ref_bias_reported",
                "default_llm_classifier_false",
            ],
            "seven_question_answer": {
                "layer": "foreground_recall_policy",
                "source": "query text, explicit strategy, and source refs",
                "artifact": "strategy payload with top_k, fanout, authority floor, filters, diagnostics",
                "validation": "source-ref, exact, exploratory, history, current, and default strategy tests",
                "empty_behavior": "default route_recall and make no fact claim",
                "hook_permission": "bounded route planning only",
                "model_authority": "none; default_llm_classifier remains false",
            },
        },
        {
            "file": "subconscious/candidate_router.py",
            "function": "working-memory candidate router",
            "current_authority": "candidate_navigation_metadata",
            "user_nearness": "foreground_working_memory_reader",
            "classification": "keep_with_source_confidence_thresholds",
            "proposed_owner": "subconscious_working_memory_router",
            "phrase_table_role": "candidate_match_bootstrap",
            "fallback_diagnostics": [
                "candidate_skipped_by_source_ref_count",
                "candidate_parked_low_confidence",
                "foreground_match_stripped",
            ],
            "seven_question_answer": {
                "layer": "subconscious_working_memory_router",
                "source": "promotion candidates, subconscious jobs, source refs, activation cues, concepts, title, summary",
                "artifact": "working_memory.jsonl, working_memory_summary.json, and hook-stripped active rows",
                "validation": "source/ref count, confidence, route threshold, generic/noise filter, and match tests",
                "empty_behavior": "skip malformed rows; park low-source or low-confidence rows; emit no foreground match",
                "hook_permission": "writer should not run in hooks; hook may read stripped active rows only",
                "model_authority": "candidate only; source refs support reopen, not source truth",
            },
        },
        {
            "file": "recall/semantic_recall_gate.py",
            "function": "semantic recall gate",
            "current_authority": "semantic_scent_candidate",
            "user_nearness": "foreground_prompt_and_registry_catalog",
            "classification": "keep_with_fail_open_deadline_and_redaction",
            "proposed_owner": "semantic_subregion_inside_recall_gate",
            "phrase_table_role": "semantic_trigger_bootstrap",
            "fallback_diagnostics": [
                "semantic_gate_disabled_or_no_key",
                "semantic_deadline_fail_open",
                "semantic_decision_redacted",
            ],
            "seven_question_answer": {
                "layer": "semantic_subregion inside recall gate",
                "source": "sanitized prompt, registry catalog, associations, working memory, semantic triggers and cues",
                "artifact": "semantic gate result, public payload, optional semantic_recall_cache.json",
                "validation": "JSON parse, decision enum, confidence clamp, alias sanitization, secret redaction, risk cap, and cache-key tests",
                "empty_behavior": "disabled, no key, empty, hard-block, error, or deadline returns skip/fail-open",
                "hook_permission": "only foreground=true with explicit deadline and worker timeout within that deadline",
                "model_authority": "scent, candidate, or search hint only; evidence decision still requires source reopen",
            },
        },
    ]


def audit_report() -> dict[str, Any]:
    rows = audit_rows()
    row_files = [str(row.get("file") or "") for row in rows]
    missing_required = sorted(REQUIRED_AUDIT_SURFACES - set(row_files))
    duplicate_files = sorted({file for file in row_files if row_files.count(file) > 1})
    complete = [
        row
        for row in rows
        if set((row.get("seven_question_answer") or {}).keys()) >= set(SEVEN_QUESTIONS)
    ]
    suspect_rows = [row for row in rows if row.get("file") in SUSPECT_AUDIT_SURFACES]
    return {
        "kind": "near_user_semantic_classifier_audit",
        "schema_version": 1,
        "row_count": len(rows),
        "complete_seven_question_rows": len(complete),
        "required_surface_count": len(REQUIRED_AUDIT_SURFACES),
        "suspect_surface_count": len(SUSPECT_AUDIT_SURFACES),
        "missing_required_surfaces": missing_required,
        "duplicate_surface_files": duplicate_files,
        "suspect_surface_reviewed_count": len(suspect_rows),
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


__all__ = [
    "REQUIRED_AUDIT_SURFACES",
    "SEVEN_QUESTIONS",
    "SUSPECT_AUDIT_SURFACES",
    "audit_report",
    "audit_rows",
]
