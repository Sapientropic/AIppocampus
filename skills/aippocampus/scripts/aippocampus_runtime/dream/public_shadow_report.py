"""Public Dream-vs-baseline shadow report for #163.

This fixture keeps the second-user review axes reproducible without serializing
private history. It is deliberately not a closeout signal for live delivery,
private-history reviewed quality, or source truth without reopen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_public_dream_vs_baseline_shadow_report"


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _mapping_field(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    return value if isinstance(value, Mapping) else {}


def _public_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "rejected_route_recovery",
            "case_family": "coding_rejected_route",
            "baseline": {
                "source_backed_route_found": False,
                "manual_query_count": 2,
                "verification_cost": 3,
                "action": "repeat_rejected_route",
            },
            "dream": {
                "source_backed_route_found": True,
                "manual_query_count": 0,
                "verification_cost": 1,
                "action": "reopen_rejection_source_before_retry",
                "visible_hint": True,
                "hint_policy": "bounded_action_time_hint",
                "source_reopen_required": True,
                "wrong_hint": False,
            },
            "expected": {
                "route_lift": True,
                "action_delta": "useful",
                "no_harm": False,
            },
        },
        {
            "case_id": "stale_hypothesis_demoted",
            "case_family": "stale_currentness",
            "baseline": {
                "source_backed_route_found": True,
                "manual_query_count": 1,
                "verification_cost": 2,
                "action": "reuse_old_hypothesis_without_currentness_check",
            },
            "dream": {
                "source_backed_route_found": True,
                "manual_query_count": 0,
                "verification_cost": 1,
                "action": "reopen_current_source_and_demote_old_hypothesis",
                "visible_hint": True,
                "hint_policy": "bounded_currentness_check",
                "source_reopen_required": True,
                "wrong_hint": False,
            },
            "expected": {
                "route_lift": True,
                "action_delta": "useful",
                "no_harm": False,
            },
        },
        {
            "case_id": "temporary_concern_stays_quiet",
            "case_family": "temporary_concern_extinction",
            "baseline": {
                "source_backed_route_found": False,
                "manual_query_count": 0,
                "verification_cost": 0,
                "action": "no_recall_needed",
            },
            "dream": {
                "source_backed_route_found": False,
                "manual_query_count": 0,
                "verification_cost": 0,
                "action": "stay_backstage",
                "visible_hint": False,
                "hint_policy": "quiet_no_delivery",
                "source_reopen_required": True,
                "wrong_hint": False,
            },
            "expected": {
                "route_lift": False,
                "action_delta": "quiet",
                "no_harm": True,
                "outcome_class": "no_help_quiet",
            },
        },
        {
            "case_id": "wrong_hint_negative_control",
            "case_family": "irrelevant_or_over_personalized_hint",
            "baseline": {
                "source_backed_route_found": False,
                "manual_query_count": 0,
                "verification_cost": 0,
                "action": "answer_without_memory",
            },
            "dream": {
                "source_backed_route_found": False,
                "manual_query_count": 0,
                "verification_cost": 0,
                "action": "suppress_irrelevant_hint",
                "visible_hint": False,
                "hint_policy": "suppress_wrong_or_over_personalized_hint",
                "source_reopen_required": True,
                "wrong_hint": False,
                "suppressed_wrong_hint": True,
            },
            "expected": {
                "route_lift": False,
                "action_delta": "quiet",
                "no_harm": True,
                "outcome_class": "regression_risk_suppressed",
            },
        },
    ]


def _candidate_review_cases() -> list[dict[str, Any]]:
    """Reviewed public-safe candidate classes for #1365.

    These rows intentionally keep only sanitized candidate families and source
    support shape. They are a quality-review table for Dream nomination, not
    Dream truth or a private-history transcript.
    """

    return [
        {
            "candidate_id": "dream_review_rejected_route",
            "candidate_family": "rejected_route_recovery",
            "review_verdict": "useful",
            "false_positive_category": "none",
            "source_overlap": True,
            "source_reopenable": True,
            "foreground_eligible_after_source_support": True,
            "privacy_blocked": False,
        },
        {
            "candidate_id": "dream_review_currentness_check",
            "candidate_family": "stale_hypothesis_demoted",
            "review_verdict": "useful",
            "false_positive_category": "none",
            "source_overlap": True,
            "source_reopenable": True,
            "foreground_eligible_after_source_support": True,
            "privacy_blocked": False,
        },
        {
            "candidate_id": "dream_review_temporary_concern",
            "candidate_family": "temporary_concern_extinction",
            "review_verdict": "quiet_no_help",
            "false_positive_category": "none",
            "source_overlap": True,
            "source_reopenable": True,
            "foreground_eligible_after_source_support": False,
            "privacy_blocked": False,
        },
        {
            "candidate_id": "dream_review_stale_route",
            "candidate_family": "superseded_route",
            "review_verdict": "rejected",
            "false_positive_category": "stale_route",
            "source_overlap": True,
            "source_reopenable": True,
            "foreground_eligible_after_source_support": False,
            "privacy_blocked": False,
        },
        {
            "candidate_id": "dream_review_generic_vocab_bridge",
            "candidate_family": "generic_semantic_bridge",
            "review_verdict": "rejected",
            "false_positive_category": "noisy_generic_vocab",
            "source_overlap": False,
            "source_reopenable": False,
            "foreground_eligible_after_source_support": False,
            "privacy_blocked": False,
        },
        {
            "candidate_id": "dream_review_sensitive_private_hint",
            "candidate_family": "sensitive_boundary",
            "review_verdict": "blocked",
            "false_positive_category": "privacy_or_safety_boundary",
            "source_overlap": True,
            "source_reopenable": False,
            "foreground_eligible_after_source_support": False,
            "privacy_blocked": True,
        },
    ]


def _case_row(case: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _mapping_field(case, "baseline")
    dream = _mapping_field(case, "dream")
    expected = _mapping_field(case, "expected")
    route_lift = bool(
        expected.get("route_lift")
        and dream.get("source_backed_route_found")
        and (
            not baseline.get("source_backed_route_found")
            or int(dream.get("manual_query_count") or 0)
            < int(baseline.get("manual_query_count") or 0)
        )
    )
    verification_cost_delta = int(dream.get("verification_cost") or 0) - int(
        baseline.get("verification_cost") or 0
    )
    return {
        "case_id": str(case.get("case_id") or "case"),
        "case_family": str(case.get("case_family") or ""),
        "baseline_route_found": bool(baseline.get("source_backed_route_found")),
        "dream_route_found": bool(dream.get("source_backed_route_found")),
        "dream_route_lift": route_lift,
        "baseline_manual_query_count": int(baseline.get("manual_query_count") or 0),
        "dream_manual_query_count": int(dream.get("manual_query_count") or 0),
        "dream_verification_cost_delta": verification_cost_delta,
        "dream_action_delta": str(expected.get("action_delta") or ""),
        "dream_action_delta_useful": expected.get("action_delta") == "useful",
        "dream_no_harm": bool(expected.get("no_harm")),
        "dream_outcome_class": str(expected.get("outcome_class") or ""),
        "dream_no_help": expected.get("outcome_class") == "no_help_quiet",
        "dream_regression": expected.get("outcome_class") == "visible_regression",
        "suppressed_regression_risk": (
            expected.get("outcome_class") == "regression_risk_suppressed"
        ),
        "dream_visible_hint": bool(dream.get("visible_hint")),
        "dream_wrong_hint": bool(dream.get("wrong_hint")),
        "suppressed_wrong_hint": bool(dream.get("suppressed_wrong_hint")),
        "source_reopen_required": bool(dream.get("source_reopen_required")),
        "hint_policy": str(dream.get("hint_policy") or ""),
    }


def _metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    case_count = len(cases)
    route_lift_count = sum(1 for row in cases if row.get("dream_route_lift"))
    useful_action_count = sum(1 for row in cases if row.get("dream_action_delta_useful"))
    wrong_hint_count = sum(1 for row in cases if row.get("dream_wrong_hint"))
    visible_hint_count = sum(1 for row in cases if row.get("dream_visible_hint"))
    no_harm_count = sum(1 for row in cases if row.get("dream_no_harm"))
    suppressed_wrong_hint_count = sum(1 for row in cases if row.get("suppressed_wrong_hint"))
    no_help_count = sum(1 for row in cases if row.get("dream_no_help"))
    regression_count = sum(1 for row in cases if row.get("dream_regression"))
    suppressed_regression_risk_count = sum(
        1 for row in cases if row.get("suppressed_regression_risk")
    )
    source_reopen_required_count = sum(1 for row in cases if row.get("source_reopen_required"))
    verification_cost_delta_total = sum(
        int(row.get("dream_verification_cost_delta") or 0) for row in cases
    )
    return {
        "case_count": case_count,
        "dream_route_lift_count": route_lift_count,
        "dream_route_lift_rate": _ratio(route_lift_count, case_count),
        "dream_win_count": route_lift_count,
        "dream_no_help_count": no_help_count,
        "dream_regression_count": regression_count,
        "suppressed_regression_risk_count": suppressed_regression_risk_count,
        "dream_action_delta_useful_count": useful_action_count,
        "dream_action_delta_useful_rate": _ratio(useful_action_count, case_count),
        "dream_verification_cost_delta_total": verification_cost_delta_total,
        "dream_wrong_hint_count": wrong_hint_count,
        "dream_wrong_hint_rate": _ratio(wrong_hint_count, max(visible_hint_count, 1)),
        "dream_no_harm_count": no_harm_count,
        "dream_no_harm_rate": _ratio(no_harm_count, case_count),
        "suppressed_wrong_hint_count": suppressed_wrong_hint_count,
        "source_reopen_required_count": source_reopen_required_count,
    }


def _candidate_review_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    useful = sum(1 for row in cases if row.get("review_verdict") == "useful")
    quiet_no_help = sum(1 for row in cases if row.get("review_verdict") == "quiet_no_help")
    rejected_or_blocked = sum(
        1 for row in cases if row.get("review_verdict") in {"rejected", "blocked"}
    )
    reopenable = sum(1 for row in cases if row.get("source_reopenable"))
    foreground_leak = sum(
        1
        for row in cases
        if row.get("foreground_eligible_after_source_support")
        and not row.get("source_reopenable")
    )
    false_positive_categories = [
        str(row.get("false_positive_category"))
        for row in cases
        if row.get("false_positive_category") not in {None, "", "none"}
    ]
    return {
        "reviewed_candidate_count": total,
        "useful_candidate_count": useful,
        "quiet_no_help_candidate_count": quiet_no_help,
        "false_positive_candidate_count": rejected_or_blocked,
        "false_positive_candidate_rate": _ratio(rejected_or_blocked, total),
        "source_reopenable_candidate_count": reopenable,
        "source_reopenable_rate": _ratio(reopenable, total),
        "foreground_leak_count": foreground_leak,
        "stale_route_false_positive_count": false_positive_categories.count("stale_route"),
        "noisy_generic_vocab_false_positive_count": false_positive_categories.count(
            "noisy_generic_vocab"
        ),
        "privacy_or_safety_blocked_count": false_positive_categories.count(
            "privacy_or_safety_boundary"
        ),
        "false_positive_categories": sorted(set(false_positive_categories)),
    }


def build_public_dream_vs_baseline_shadow_report() -> dict[str, Any]:
    cases = [_case_row(case) for case in _public_cases()]
    metrics = _metrics(cases)
    candidate_review_cases = _candidate_review_cases()
    candidate_review_metrics = _candidate_review_metrics(candidate_review_cases)
    ok = bool(
        metrics["dream_route_lift_count"] >= 2
        and metrics["dream_action_delta_useful_count"] >= 2
        and metrics["dream_wrong_hint_count"] == 0
        and metrics["suppressed_wrong_hint_count"] >= 1
        and candidate_review_metrics["false_positive_candidate_count"] >= 2
        and candidate_review_metrics["foreground_leak_count"] == 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "ok": ok,
        "claim_level": "public_synthetic_dream_vs_baseline_shadow",
        "metrics": metrics,
        "cases": cases,
        "candidate_quality_review": {
            "kind": "public_synthetic_dream_candidate_quality_review",
            "claim_level": "sanitized_public_candidate_review_table",
            "metrics": candidate_review_metrics,
            "cases": candidate_review_cases,
            "source_reachability_boundary": (
                "Dream may nominate candidate routes, but source-backed support "
                "and source reopen decide foreground use."
            ),
        },
        "issue_readouts": {
            "github_163": {
                "public_dream_vs_baseline_shadow_measured": True,
                "public_candidate_quality_review_measured": True,
                "dream_route_lift_count": metrics["dream_route_lift_count"],
                "dream_action_delta_useful_count": metrics[
                    "dream_action_delta_useful_count"
                ],
                "dream_wrong_hint_rate": metrics["dream_wrong_hint_rate"],
                "live_delivered_quality_measured": False,
                "private_real_history_quality_measured": False,
                "public_safe_closeout_slice_ready": True,
                "closeout_eligible": False,
            },
            "github_1364": {
                "cohort_defined_before_report": True,
                "baseline_arms": ["no_dream_baseline", "bounded_dream_hint"],
                "dream_win_count": metrics["dream_win_count"],
                "dream_no_help_count": metrics["dream_no_help_count"],
                "dream_regression_count": metrics["dream_regression_count"],
                "suppressed_regression_risk_count": metrics[
                    "suppressed_regression_risk_count"
                ],
                "claim_level": "public_safe_shadow_not_live_default",
                "closeout_eligible": True,
            },
            "github_1365": {
                "review_table_recorded": True,
                "reviewed_candidate_count": candidate_review_metrics[
                    "reviewed_candidate_count"
                ],
                "false_positive_candidate_count": candidate_review_metrics[
                    "false_positive_candidate_count"
                ],
                "false_positive_categories": candidate_review_metrics[
                    "false_positive_categories"
                ],
                "source_reopenable_rate": candidate_review_metrics["source_reopenable_rate"],
                "foreground_leak_count": candidate_review_metrics["foreground_leak_count"],
                "closeout_eligible": True,
            }
        },
        "metric_notes": {
            "dream_route_lift_count": (
                "Cases where Dream material finds a source-backed route with fewer "
                "manual queries than the no-Dream baseline."
            ),
            "dream_action_delta_useful_count": (
                "Cases where the bounded Dream hint changes the action after source "
                "verification, such as avoiding a rejected route or checking currentness."
            ),
            "dream_wrong_hint_rate": (
                "Visible Dream hints marked stale, irrelevant, or over-personalized. "
                "Suppressed wrong-hint controls are counted separately."
            ),
            "candidate_quality_review": (
                "Sanitized candidate review counts useful, quiet/no-help, stale, noisy, "
                "and privacy/safety-blocked Dream nominations without raw private text."
            ),
        },
        "policy_boundary": {
            "deterministic_public_fixture_only": True,
            "source_reopen_required_for_claims": True,
            "dream_material_is_navigation_only": True,
            "no_live_delivery": True,
            "no_external_model_calls": True,
            "cannot_claim_causal_user_lift": True,
            "cannot_claim_general_dream_quality": True,
        },
        "privacy": {
            "raw_case_text_serialized": False,
            "raw_source_refs_serialized": False,
            "absolute_paths_serialized": False,
            "fixture_contains_private_user_data": False,
        },
    }
