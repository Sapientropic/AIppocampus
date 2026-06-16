"""Preregistered #378 slice readouts for continuous-memory reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Sequence

PREREGISTRATION_ID = "aippocampus-continuous-memory-v1"
PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM = 5
CONTRACT_SMOKE_RUNNER_PROFILE = "public_synthetic_contract_smoke"
PREREGISTERED_REPEAT_RUNNER_PROFILE = "public_synthetic_preregistered_repeat"
EXPECTED_NULL_INTERPRETATION_LABEL = (
    "no demonstrated net advantage over modeled fresh-context spec loop"
)
DETERMINISTIC_REPEAT_BOUNDARY = "deterministic replicated lower-bound rows, not independent trials"
CONTEXT_LOSS_CONTINUITY_SLICE_ID = "github_1153_context_loss_public_continuity_v1"
CONTEXT_LOSS_EXPECTED_NULL_ROW_ID = "continuous_memory.preregistered_repeat_profile_2026_06_08"
CONTEXT_LOSS_REQUIRED_FAMILIES = (
    "incomplete_handoff_recovery",
    "post_compaction_rejected_route",
    "post_compaction_scope_constraint",
    "public_vcs_temporal_override",
    "transient_concern_expiry",
    "public_vcs_anti_drift_negative",
)
CONTEXT_LOSS_STRATEGY_ARMS = {
    "fresh_missing_context": "no_memory",
    "summary_only_host_native": "host_native_continuous_no_aippocampus",
    "aippocampus_route_packet": "true_aippocampus_memory",
    "sham_unrelated_memory": "sham_unrelated_memory",
    "stale_wrong_memory": "stale_wrong_memory",
    "oracle_full_context": "oracle_memory",
}

_REMEDIATION_BY_FAMILY = {
    "post_compaction_rejected_route": {
        "failure_mode": "useful_route_but_complete_spec_baseline_already_has_source",
        "repair_hypothesis": (
            "Keep the rejected-route handle source-backed, but make the route packet "
            "cheaper and more directly actionable before changing scoring."
        ),
        "product_surface": ["route_packet", "source_reopen", "cost_harm_accounting"],
        "fresh_context_advantage": ("modeled reset loop already carries the rejected-route source"),
    },
    "post_compaction_scope_constraint": {
        "failure_mode": "useful_constraint_but_prompt_hook_cost_drag",
        "repair_hypothesis": (
            "Reduce prompt-hook and route overhead for simple scope constraints; "
            "do not add more memory text to complete-spec tasks."
        ),
        "product_surface": ["prompt_hook", "route_packet", "cost_harm_accounting"],
        "fresh_context_advantage": "modeled reset loop has the full scope constraint",
    },
    "transient_concern_expiry": {
        "failure_mode": "memory_silence_expected_for_expired_concern",
        "repair_hypothesis": (
            "Treat this as a restraint/no-op path: keep old concerns quiet unless "
            "source reopening changes the foreground action."
        ),
        "product_surface": ["no_harm_hint_suppression", "stale_memory_gate"],
        "fresh_context_advantage": "fresh context or silence is cheap and safe",
    },
    "incomplete_handoff_recovery": {
        "failure_mode": "source_miss_abstention_counts_as_task_failure",
        "repair_hypothesis": (
            "Improve source-reopen fallback and abstention usefulness without "
            "rewarding unsupported answers."
        ),
        "product_surface": ["source_reopen", "abstention_usefulness", "route_packet"],
        "fresh_context_advantage": "modeled reset loop has the missing source",
    },
    "public_vcs_temporal_override": {
        "failure_mode": "correct_memory_still_loses_net_value_to_complete_spec",
        "repair_hypothesis": (
            "Memory correctness is not the failure; inspect route minimality and "
            "source-reopen cost before scoring changes."
        ),
        "product_surface": ["route_packet", "source_reopen", "cost_harm_accounting"],
        "fresh_context_advantage": "modeled reset loop already has the current source",
    },
    "public_vcs_anti_drift_negative": {
        "failure_mode": "irrelevant_route_suppression_must_happen_earlier",
        "repair_hypothesis": (
            "Suppress irrelevant hints before foreground injection and avoid charging "
            "avoidable memory work in no-harm cases."
        ),
        "product_surface": ["no_harm_hint_suppression", "prompt_hook"],
        "fresh_context_advantage": "fresh context wins by staying silent",
    },
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def repeat_seed_hash(case_family: str, case_id: str, repeat_index: int) -> str:
    return sha256_text(
        "".join(
            (
                PREREGISTRATION_ID,
                "|",
                case_family,
                "|",
                case_id,
                "|",
                str(repeat_index),
            )
        )
    )


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _row_cost_units(row: dict[str, Any]) -> float:
    cost = row["cost_components"]
    foreground = (
        float(cost["foreground_tokens"]) / 100.0
        + float(cost["wall_clock_latency_ms"]) / 1000.0
        + float(cost["source_reopen_count"]) * 0.25
    )
    background = (
        float(cost["background_tokens"]) / 100.0
        + float(cost["background_api_calls"]) * 2.0
        + float(cost["indexing_maintenance_ms"]) / 1000.0
        + float(cost["storage_growth_bytes"]) / 4096.0
    )
    recovery = (
        float(cost["retry_recovery_count"]) * 1.5
        + float(cost["human_correction_count"]) * 2.0
        + float(cost["human_correction_minutes"]) * 0.25
    )
    return round(foreground + background + recovery, 4)


def _success_rate(rows: list[dict[str, Any]]) -> float:
    return _rate(sum(1 for row in rows if row["success"]), len(rows))


def build_evaluation_rows(
    *,
    cases: Sequence[Any],
    selected_arms: Sequence[str],
    repeat_count_per_case_arm: int,
    evaluate_case_fn: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    if repeat_count_per_case_arm < 1:
        raise ValueError("repeat_count_per_case_arm must be >= 1")
    return [
        evaluate_case_fn(case, arm, repeat_index=repeat_index)
        for repeat_index in range(repeat_count_per_case_arm)
        for case in cases
        for arm in selected_arms
    ]


def case_manifest_digest(rows: list[dict[str, Any]]) -> str:
    case_manifest: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_hash = str(row["case_id_sha1"])
        case_manifest.setdefault(
            case_hash,
            {
                "case_id_sha1": case_hash,
                "case_family": row["case_family"],
                "scenario_provenance": row["scenario_provenance"],
                "source_ref_sha256": row["source_ref_sha256"],
                "source_window_sha256": row["source_window_sha256"],
                "prompt_threshold_tuning_role": row["prompt_threshold_tuning_role"],
                "scenario_negative_control_kind": row["scenario_negative_control_kind"],
            },
        )
    encoded = json.dumps(
        sorted(case_manifest.values(), key=lambda item: item["case_id_sha1"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(encoded)


def build_paired_repeat_readout(
    *,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    repeat_count_per_case_arm: int,
    net_value_for_rows: Callable[[list[dict[str, Any]]], dict[str, Any]],
    fresh_context_net_for_case_count: Callable[[int], dict[str, Any]],
) -> dict[str, Any]:
    repeat_indexes = sorted({int(row["repeat_index"]) for row in rows})
    paired_repeat_power_gate_passed = (
        repeat_count_per_case_arm >= PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM
    )
    required_arm_rows_present = any(row["arm"] == "true_aippocampus_memory" for row in rows)
    lower_bound_rule_evaluated = bool(paired_repeat_power_gate_passed and required_arm_rows_present)

    paired_deltas: list[dict[str, Any]] = []
    for repeat_index in repeat_indexes:
        true_rows = [
            row
            for row in rows
            if row["repeat_index"] == repeat_index and row["arm"] == "true_aippocampus_memory"
        ]
        true_net = net_value_for_rows(true_rows)
        fresh_net = fresh_context_net_for_case_count(int(metrics["case_count"]))
        delta = round(float(true_net["net_value_units"]) - float(fresh_net["net_value_units"]), 4)
        paired_deltas.append(
            {
                "repeat_index": repeat_index,
                "true_aippocampus_memory_net_value_units": true_net["net_value_units"],
                "fresh_context_spec_loop_net_value_units": fresh_net["net_value_units"],
                "delta_units": delta,
                "winning_strategy": (
                    "true_aippocampus_memory" if delta > 0 else "fresh_context_spec_loop"
                ),
            }
        )

    delta_values = [float(item["delta_units"]) for item in paired_deltas]
    lower_bound_units = (
        round(min(delta_values), 4) if lower_bound_rule_evaluated and delta_values else None
    )
    mean_delta_units = round(sum(delta_values) / len(delta_values), 4) if delta_values else None
    lower_bound_passed = bool(lower_bound_units is not None and lower_bound_units > 0)
    winner_distribution: dict[str, int] = {}
    for item in paired_deltas:
        winner = str(item["winning_strategy"])
        winner_distribution[winner] = winner_distribution.get(winner, 0) + 1
    seed_digest = sha256_text(
        json.dumps(
            sorted({str(row["repeat_seed_sha256"]) for row in rows}),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return {
        "schema_version": 1,
        "runner_profile": (
            PREREGISTERED_REPEAT_RUNNER_PROFILE
            if repeat_count_per_case_arm > 1
            else CONTRACT_SMOKE_RUNNER_PROFILE
        ),
        "repeat_count_per_case_arm": repeat_count_per_case_arm,
        "required_repeat_count_per_case_arm": (PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM),
        "paired_repeat_power_gate_passed": paired_repeat_power_gate_passed,
        "same_task_seed_pairs_across_arms": True,
        "seed_derivation": (
            "sha256(preregistration_id + scenario_family + case_id + repeat_index)"
        ),
        "repeat_seed_digest_sha256": seed_digest,
        "repeat_seed_count": len({row["repeat_seed_sha256"] for row in rows}),
        "paired_unit": "repeat_index_over_all_selected_cases",
        "paired_delta_field": (
            "true_aippocampus_memory_net_value_minus_fresh_context_spec_loop_units"
        ),
        "lower_bound_method": (
            "minimum_observed_paired_delta_for_deterministic_public_synthetic_repeats"
        ),
        "lower_bound_rule_evaluated": lower_bound_rule_evaluated,
        "lower_bound_units": lower_bound_units,
        "mean_delta_units": mean_delta_units,
        "lower_bound_passed": lower_bound_passed,
        "paired_net_value_deltas_by_repeat": paired_deltas,
        "winner_distribution_by_repeat": winner_distribution,
        "decision_label": (
            "candidate continuous memory advantage"
            if lower_bound_passed
            else "no demonstrated memory advantage"
        ),
        "interpretation_label": (
            "candidate continuous memory advantage"
            if lower_bound_passed
            else EXPECTED_NULL_INTERPRETATION_LABEL
        ),
        "repeat_independence_boundary": DETERMINISTIC_REPEAT_BOUNDARY,
        "cannot_claim": [
            "live host-native cost or compaction telemetry",
            "private real-history generality",
            "public-quality continuous-memory advantage when lower_bound_units <= 0",
            "statistical power beyond deterministic public-synthetic repeated rows",
        ],
    }


def build_expected_null_remediation(
    *,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    cost_harm_ledger: dict[str, Any],
    paired_repeat_readout: dict[str, Any],
    product_path_change: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cost = cost_harm_ledger["cost"]
    true_cost = cost["by_arm"]["true_aippocampus_memory"]
    fresh_cost = cost["comparison_baselines"]["fresh_context_spec_loop"]
    net_value = cost_harm_ledger["net_value_under_equalized_cost"]
    product_change = product_path_change or {}
    product_change_implemented = (
        product_change.get("status") == "implemented_source_miss_recovery_action"
    )
    product_change_status = (
        "implemented_rerun"
        if product_change_implemented and paired_repeat_readout.get("lower_bound_rule_evaluated")
        else (
            "implemented_contract_probe"
            if product_change_implemented
            else "candidate_identified_not_implemented"
        )
    )
    per_family: list[dict[str, Any]] = []
    for family in sorted({str(row["case_family"]) for row in rows}):
        family_rows = [row for row in rows if row["case_family"] == family]
        true_rows = [row for row in family_rows if row["arm"] == "true_aippocampus_memory"]
        no_rows = [row for row in family_rows if row["arm"] == "no_memory"]
        sham_rows = [row for row in family_rows if row["arm"] == "sham_unrelated_memory"]
        true_success = _success_rate(true_rows)
        no_success = _success_rate(no_rows)
        sham_success = _success_rate(sham_rows)
        true_success_count = sum(1 for row in true_rows if row["success"])
        true_cost_per_success = (
            round(sum(_row_cost_units(row) for row in true_rows) / true_success_count, 4)
            if true_success_count
            else None
        )
        remediation = _REMEDIATION_BY_FAMILY.get(
            family,
            {
                "failure_mode": "unclassified_public_synthetic_case_family",
                "repair_hypothesis": "Review source-backed behavior before changing scoring.",
                "product_surface": ["route_packet"],
                "fresh_context_advantage": "not classified",
            },
        )
        source_miss_abstention: dict[str, Any] = {
            "true_memory_abstention_count": sum(
                1 for row in true_rows if row["abstained_on_missing_source"]
            ),
            "true_memory_source_backed_hit_rate": _rate(
                sum(1 for row in true_rows if row["source_backed_hit"]),
                len(true_rows),
            ),
        }
        if family == "incomplete_handoff_recovery" and product_change:
            source_miss_abstention.update(
                {
                    "source_miss_recovery_action": product_change.get(
                        "source_miss_recovery_action"
                    ),
                    "source_miss_recovery_reason": product_change.get(
                        "source_miss_recovery_reason"
                    ),
                    "reopen_plan_status": product_change.get("reopen_plan_status"),
                    "manual_query_invention_expected": bool(
                        product_change.get("manual_query_invention_expected")
                    ),
                    "answer_from_packet_allowed": bool(
                        product_change.get("answer_from_packet_allowed")
                    ),
                }
            )
        per_family.append(
            {
                "case_family": family,
                "failure_mode": remediation["failure_mode"],
                "repair_hypothesis": remediation["repair_hypothesis"],
                "product_surface": remediation["product_surface"],
                "success_lift": {
                    "true_aippocampus_memory_success_rate": true_success,
                    "no_memory_success_rate": no_success,
                    "sham_unrelated_memory_success_rate": sham_success,
                    "true_over_no_memory_delta": round(true_success - no_success, 4),
                    "true_over_sham_delta": round(true_success - sham_success, 4),
                },
                "source_miss_abstention": source_miss_abstention,
                "fresh_context_advantage": remediation["fresh_context_advantage"],
                "memory_cost_drag": {
                    "true_memory_cost_per_successful_slice": true_cost_per_success,
                    "fresh_context_cost_per_successful_slice": fresh_cost[
                        "amortized_cost_per_successful_slice"
                    ],
                    "true_minus_fresh_cost_per_successful_slice": (
                        round(
                            float(true_cost_per_success)
                            - float(fresh_cost["amortized_cost_per_successful_slice"]),
                            4,
                        )
                        if true_cost_per_success is not None
                        else None
                    ),
                },
            }
        )

    return {
        "schema_version": 1,
        "issue": "github_960",
        "status": "remediation_taxonomy_recorded_negative_result_preserved",
        "claim_level": "expected_null_remediation_diagnostic",
        "primary_endpoint_changed": False,
        "benchmark_thresholds_changed": False,
        "product_change_status": product_change_status,
        "product_failure_mode_changed": product_change_implemented,
        "product_path_change": product_change,
        "decision_label_preserved": paired_repeat_readout["decision_label"],
        "interpretation_label": paired_repeat_readout["interpretation_label"],
        "repeat_independence_boundary": paired_repeat_readout["repeat_independence_boundary"],
        "original_failure_changed": product_change_implemented,
        "primary_endpoint_winner": net_value["highest_net_value_fair_strategy"],
        "overall": {
            "true_aippocampus_memory_success_rate": metrics["by_arm"]["true_aippocampus_memory"][
                "success_rate"
            ],
            "no_memory_success_rate": metrics["by_arm"]["no_memory"]["success_rate"],
            "sham_unrelated_memory_success_rate": metrics["by_arm"]["sham_unrelated_memory"][
                "success_rate"
            ],
            "host_native_success_rate": metrics["by_arm"]["host_native_continuous_no_aippocampus"][
                "success_rate"
            ],
            "true_memory_net_value_units": net_value["by_arm"]["true_aippocampus_memory"][
                "net_value_units"
            ],
            "fresh_context_spec_loop_net_value_units": net_value["comparison_baselines"][
                "fresh_context_spec_loop"
            ]["net_value_units"],
            "true_memory_cost_per_successful_slice": true_cost[
                "amortized_cost_per_successful_slice"
            ],
            "fresh_context_cost_per_successful_slice": fresh_cost[
                "amortized_cost_per_successful_slice"
            ],
        },
        "per_case_family": per_family,
        "secondary_user_visible_friction": {
            "primary_endpoint_participation": False,
            "status": "candidate_metrics_not_yet_calibrated",
            "dimensions": [
                "repeated_restatement_burden",
                "manual_search_cost",
                "context_reconstruction_time",
                "adhd_context_switch_drag",
            ],
            "current_proxy_boundary": (
                "The repeat profile models source-rebuild and memory work costs, "
                "but it does not yet measure user-visible restatement burden or "
                "ADHD/context-switch drag as calibrated outcome variables."
            ),
            "candidate_next_surface": [
                "route_actionability",
                "source_reopen_fallback",
                "no_harm_hint_suppression",
                "cost_harm_accounting",
            ],
        },
        "cannot_claim": [
            "continuous-memory advantage",
            "product change improved the preregistered endpoint",
            "calibrated user-visible friction reduction",
            "independent repeat-trial statistical power",
        ],
    }


def build_preregistration(
    cost_harm_ledger: dict[str, Any],
    *,
    paired_repeat_readout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    net_value = cost_harm_ledger["net_value_under_equalized_cost"]
    fair_winner = net_value["highest_net_value_fair_strategy"]
    lower_bound_evaluated = bool(
        paired_repeat_readout and paired_repeat_readout["lower_bound_rule_evaluated"]
    )
    if lower_bound_evaluated:
        assert paired_repeat_readout is not None
        claim_allowed = bool(
            fair_winner == "true_aippocampus_memory" and paired_repeat_readout["lower_bound_passed"]
        )
        evaluated_as = "public_synthetic_preregistered_repeat_readout"
        reason = (
            "paired lower_bound_units={lower_bound} for true_aippocampus_memory "
            "over fresh_context_spec_loop; {outcome}."
        ).format(
            lower_bound=paired_repeat_readout["lower_bound_units"],
            outcome=(
                "registered lower-bound rule passed"
                if claim_allowed
                else "registered lower-bound rule did not support an advantage claim"
            ),
        )
    else:
        claim_allowed = fair_winner == "true_aippocampus_memory"
        evaluated_as = "contract_smoke_preview"
        reason = (
            f"{fair_winner} wins the current fair-strategy net-value preview; "
            "contract smoke reports cannot satisfy the public-quality lower-bound rule."
        )
    decision_label = (
        "candidate continuous memory advantage"
        if claim_allowed
        else "no demonstrated memory advantage"
    )
    interpretation_label = (
        "candidate continuous memory advantage"
        if claim_allowed
        else EXPECTED_NULL_INTERPRETATION_LABEL
    )
    return {
        "id": PREREGISTRATION_ID,
        "status": "pre_registered_design_contract",
        "applies_to": "public_quality_continuous_memory_claims_for_#378",
        "current_report_role": (
            "public_synthetic_preregistered_repeat_evidence"
            if lower_bound_evaluated
            else "contract_smoke_preview_not_public_quality_evidence"
        ),
        "primary_endpoint": {
            "name": "source_grounded_task_success_under_equalized_cost",
            "scope": "context_loss_or_instability",
            "does_not_apply_when": [
                "complete_spec_short_task_current_prompt_sufficient",
            ],
            "why_chosen": (
                "Combines task success with source support, equalized cost, "
                "and severe false positives so memory cannot win by hiding "
                "background work or stale unsafe recall."
            ),
            "point_estimate_field": (
                "cost_harm_ledger.net_value_under_equalized_cost.highest_net_value_fair_strategy"
            ),
            "hard_gates": [
                "privacy_breach_count == 0",
                "raw_prompt_or_source_leak_count == 0",
                "source_reopen_obedience_rate passes for source-required memory claims",
                "no severe stale-memory harm gate breach",
            ],
        },
        "public_quality_minimums": {
            "scenario_families": 3,
            "repeats_per_scenario_arm": (PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM),
            "external_or_holdout_scenario_share": 0.30,
            "arms_required": [
                "fresh_context_spec_loop",
                "host_native_continuous_no_aippocampus",
                "true_aippocampus_memory",
                "sham_unrelated_memory",
                "stale_wrong_memory",
            ],
            "oracle_role": "upper_bound_only_excluded_from_fair_winner",
        },
        "scenario_provenance_policy": {
            "categories": [
                "author_written_synthetic",
                "external_written_synthetic",
                "public_log_or_vcs_derived",
                "private_real_history_aggregate",
                "holdout_blind",
            ],
            "report_each_slice_separately": True,
            "public_quality_non_self_derived_sources": [
                "external_written_synthetic",
                "public_log_or_vcs_derived",
                "holdout_blind",
            ],
            "author_written_only_claim_level": "diagnostic_contract_smoke_only",
            "scenario_scripts_record_generation_context": True,
        },
        "holdout_policy": {
            "holdout_blind_prompt_threshold_tuning_role": "holdout_excluded",
            "holdout_used_for_prompt_or_threshold_tuning_allowed": False,
            "blind_or_holdout_scenarios_reported_as_slices": True,
        },
        "negative_control_policy": {
            "scenario_level_negative_controls_required": True,
            "penalize_unnecessary_memory_intervention": True,
            "examples": [
                "memory_should_not_help",
                "old_project_fact_pollutes_current_work",
                "fresh_context_spec_loop_should_plausibly_win",
            ],
        },
        "seed_repeat_strategy": {
            "same_task_seed_pairs_across_arms": True,
            "public_quality_min_repeats_per_scenario_arm": (
                PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM
            ),
            "seed_derivation": (
                "sha256(preregistration_id + scenario_family + case_id + repeat_index)"
            ),
            "contract_smoke_seed_policy": ("deterministic_public_safe_cases_no_random_seed"),
        },
        "confidence_rule": {
            "primary_rule": (
                "continuous memory advantage requires the paired lower_bound "
                "for true_aippocampus_memory over fresh_context_spec_loop to "
                "be greater than 0 after hard gates pass"
            ),
            "interval_methods": [
                "paired_bootstrap_for_net_value_delta",
                "wilson_lower_bound_for_binary_success_and_harm_rates",
            ],
            "contract_smoke_rule": "point_preview_only_no_public_quality_claim",
        },
        "secondary_endpoints": [
            "memory_presence_effect",
            "memory_correctness_effect",
            "stale_memory_harm",
            "oracle_headroom",
            "source_reopen_obedience_by_arm",
            "harm_weighted_false_positive_cost",
            "amortized_cost_per_successful_slice",
        ],
        "secondary_metrics_policy": ("exploratory_unless_named_in_primary_decision_rule"),
        "multiple_comparison_handling": (
            "secondary metrics are descriptive unless promoted before a run; "
            "do not select a positive headline from the metric grid after seeing results"
        ),
        "no_advantage_rule": (
            "If the primary endpoint does not beat the baseline under the "
            "registered lower-bound rule, reports must say no demonstrated "
            "memory advantage even when secondary metrics favor AIppocampus."
        ),
        "current_report_decision": {
            "evaluated_as": evaluated_as,
            "primary_endpoint_winner": fair_winner,
            "continuous_memory_advantage_claim_allowed": bool(claim_allowed),
            "decision_label": decision_label,
            "interpretation_label": interpretation_label,
            "reason": reason,
        },
    }


def _arm_rows(rows: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["arm"] == arm]


def _arm_task_success(
    *,
    metrics: dict[str, Any],
    selected_arms: set[str],
    strategy: str,
    arm: str,
) -> dict[str, Any]:
    summary = metrics["by_arm"][arm]
    return {
        "strategy": strategy,
        "report_arm": arm,
        "observed": arm in selected_arms,
        "success_count": summary["success_count"],
        "case_count": summary["case_count"],
        "success_rate": summary["success_rate"],
        "harm_score_avg": summary["harm_score_avg"],
    }


def _arm_cost_tokens(
    cost_harm_ledger: dict[str, Any],
    arm: str,
) -> dict[str, Any]:
    cost = cost_harm_ledger["cost"]["by_arm"][arm]
    return {
        "foreground_tokens": cost["foreground_tokens"],
        "background_tokens": cost["background_tokens"],
        "wall_clock_latency_ms": cost["wall_clock_latency_ms"],
        "source_reopen_count": cost["source_reopen_count"],
        "retry_recovery_count": cost["retry_recovery_count"],
        "human_correction_count": cost["human_correction_count"],
        "human_correction_minutes": cost["human_correction_minutes"],
        "foreground_cost_units": cost["foreground_cost_units"],
        "background_cost_units": cost["background_cost_units"],
        "recovery_cost_units": cost["recovery_cost_units"],
        "total_cost_units": cost["total_cost_units"],
        "amortized_cost_per_successful_slice": cost["amortized_cost_per_successful_slice"],
    }


def build_context_loss_continuity_slice(
    *,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    scenario_controls: dict[str, Any],
    cost_harm_ledger: dict[str, Any],
    preregistration: dict[str, Any],
    selected_arms: Sequence[str],
    paired_repeat_readout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_arm_set = set(selected_arms)
    families = set(metrics.get("by_scenario_family", {}))
    missing_families = [
        family for family in CONTEXT_LOSS_REQUIRED_FAMILIES if family not in families
    ]
    required_arms_present = all(
        arm in selected_arm_set for arm in CONTEXT_LOSS_STRATEGY_ARMS.values()
    )
    true_rows = _arm_rows(rows, "true_aippocampus_memory")
    stale_rows = _arm_rows(rows, "stale_wrong_memory")
    true_required = [row for row in true_rows if row["source_reopen_required"]]
    true_hits = [row for row in true_required if row["source_backed_hit"]]
    true_abstentions = [row for row in true_required if row["abstained_on_missing_source"]]
    stale_revival_rows = [
        row for row in stale_rows if row["harm_components"]["memory_false_positive"]
    ]
    negative_interventions = scenario_controls["negative_control_memory_intervention_by_arm"]
    negative_unnecessary = scenario_controls["negative_control_unnecessary_intervention_by_arm"]
    true_negative_interventions = negative_interventions["true_aippocampus_memory"]
    true_negative_unnecessary = negative_unnecessary["true_aippocampus_memory"]
    no_memory = metrics["by_arm"]["no_memory"]
    host_native = metrics["by_arm"]["host_native_continuous_no_aippocampus"]
    true_memory = metrics["by_arm"]["true_aippocampus_memory"]
    no_memory_cost = cost_harm_ledger["cost"]["by_arm"]["no_memory"]
    host_native_cost = cost_harm_ledger["cost"]["by_arm"]["host_native_continuous_no_aippocampus"]
    true_memory_cost = cost_harm_ledger["cost"]["by_arm"]["true_aippocampus_memory"]
    complete_spec_cost = cost_harm_ledger["cost"]["comparison_baselines"]["fresh_context_spec_loop"]
    complete_spec_net = cost_harm_ledger["net_value_under_equalized_cost"]["comparison_baselines"][
        "fresh_context_spec_loop"
    ]
    source_reopen_gate_passed = (
        metrics["source_reopen_obedience_by_arm"]["true_aippocampus_memory"] == 1.0
    )
    stale_revival_rate = _rate(len(stale_revival_rows), len(stale_rows))
    no_remember_precision = (
        _rate(
            true_negative_interventions - true_negative_unnecessary,
            true_negative_interventions,
        )
        if true_negative_interventions
        else 1.0
    )
    contract_gate_ok = bool(
        required_arms_present
        and not missing_families
        and source_reopen_gate_passed
        and stale_revival_rate > 0
        and no_remember_precision == 1.0
    )
    can_claim = [
        "stable preregistered context-loss diagnostic slice is present",
        (
            "missing-context, host-native summary-only, source-backed route, "
            "sham, stale, and oracle controls are separated"
        ),
        (
            "selected public-safe deterministic cases expose task success, "
            "source reopen, stale revival, memory drag, manual restatement "
            "proxy, and token/latency cost fields"
        ),
    ]
    if contract_gate_ok:
        can_claim.append("selected public-safe context-loss contract gate passes")

    return {
        "schema_version": 1,
        "issue": "github_1153",
        "slice_id": CONTEXT_LOSS_CONTINUITY_SLICE_ID,
        "status": (
            "context_loss_contract_gate_passed"
            if contract_gate_ok
            else "context_loss_contract_gate_incomplete"
        ),
        "claim_level": "preregistered_context_loss_diagnostic_slice",
        "runner_profile": (
            str(paired_repeat_readout["runner_profile"])
            if paired_repeat_readout
            else "public_synthetic_contract_smoke"
        ),
        "stable_slice_id": True,
        "contract_gate_ok": contract_gate_ok,
        "quality_gate_ok": False,
        "quality_gate_reason": (
            "diagnostic slice only; no public-quality lower-bound or live "
            "long-dialogue prediction run"
        ),
        "expected_null_preservation": {
            "historical_row_id": CONTEXT_LOSS_EXPECTED_NULL_ROW_ID,
            "supersedes_historical_row": False,
            "preserved_decision_label": (
                paired_repeat_readout["decision_label"]
                if paired_repeat_readout
                else preregistration["current_report_decision"]["decision_label"]
            ),
            "preserved_interpretation_label": (
                paired_repeat_readout["interpretation_label"]
                if paired_repeat_readout
                else preregistration["current_report_decision"]["interpretation_label"]
            ),
            "boundary": (
                "The 2026-06-08/09 repeat profile remains the short "
                "complete-spec expected-null row; this slice evaluates a "
                "missing-context condition and cannot rewrite that result."
            ),
        },
        "source_cohorts": {
            "primary": ("public-safe synthetic and public VCS-derived context-loss contract cases"),
            "public_dialogue_control": {
                "role": (
                    "optional same-dialogue evidence-id control, not the "
                    "primary coding continuity truth source"
                ),
                "surfaces": [
                    "benchmark_corpus/locomo_manifest.json",
                    "benchmarks/aippocampus/benchmark_locomo_public_users.py",
                    "benchmarks/aippocampus/benchmark_locomo_qa.py",
                ],
                "raw_dataset_checked_in": False,
                "kept_separate_from_claim": True,
            },
            "private_history_role": (
                "optional secondary dogfood after public-safe contract behavior is visible"
            ),
        },
        "scenario_families": {
            "required": list(CONTEXT_LOSS_REQUIRED_FAMILIES),
            "observed": sorted(families),
            "missing": missing_families,
            "case_count": metrics["case_count"],
            "external_or_holdout_case_share": scenario_controls["external_or_holdout_case_share"],
        },
        "arms": {
            strategy: {
                "report_arm": arm,
                "observed": arm in selected_arm_set,
            }
            for strategy, arm in CONTEXT_LOSS_STRATEGY_ARMS.items()
        }
        | {
            "fresh_context_spec_loop_complete_spec": {
                "report_arm": "fresh_context_spec_loop",
                "observed": True,
                "role": "historical_complete_spec_boundary_baseline",
                "primary_context_loss_opponent": False,
            }
        },
        "metrics": {
            "task_success_by_strategy": {
                strategy: _arm_task_success(
                    metrics=metrics,
                    selected_arms=selected_arm_set,
                    strategy=strategy,
                    arm=arm,
                )
                for strategy, arm in CONTEXT_LOSS_STRATEGY_ARMS.items()
            },
            "source_reopen_behavior": {
                "aippocampus_required_count": len(true_required),
                "aippocampus_attempt_count": sum(
                    1 for row in true_rows if row["source_reopen_attempted"]
                ),
                "aippocampus_source_backed_hit_count": len(true_hits),
                "aippocampus_abstained_on_missing_source_count": len(true_abstentions),
                "aippocampus_source_reopen_obedience_rate": metrics[
                    "source_reopen_obedience_by_arm"
                ]["true_aippocampus_memory"],
                "evidence_id_recall_proxy_rate": _rate(
                    len(true_hits),
                    len(true_required),
                ),
                "oracle_source_backed_hit_rate": metrics["by_arm"]["oracle_memory"][
                    "source_reopen_obedience_rate"
                ],
            },
            "memory_drag": {
                "aippocampus_total_cost_units": true_memory_cost["total_cost_units"],
                "fresh_missing_context_total_cost_units": no_memory_cost["total_cost_units"],
                "summary_only_host_native_total_cost_units": host_native_cost["total_cost_units"],
                "aippocampus_minus_fresh_missing_context_total_cost_units": round(
                    float(true_memory_cost["total_cost_units"])
                    - float(no_memory_cost["total_cost_units"]),
                    4,
                ),
                "aippocampus_minus_summary_only_total_cost_units": round(
                    float(true_memory_cost["total_cost_units"])
                    - float(host_native_cost["total_cost_units"]),
                    4,
                ),
                "background_cost_units": true_memory_cost["background_cost_units"],
                "amortized_cost_per_successful_slice": true_memory_cost[
                    "amortized_cost_per_successful_slice"
                ],
            },
            "stale_revival": {
                "stale_wrong_memory_false_positive_count": len(stale_revival_rows),
                "stale_wrong_memory_false_positive_rate": stale_revival_rate,
                "stale_wrong_memory_harm_weighted_cost": cost_harm_ledger["harm"]["by_arm"][
                    "stale_wrong_memory"
                ]["harm_weighted_false_positive_cost"],
                "wrong_constraint_adopted_count": cost_harm_ledger["harm"]["by_arm"][
                    "stale_wrong_memory"
                ]["wrong_constraint_adopted_count"],
                "risky_action_before_source_reopen_count": cost_harm_ledger["harm"]["by_arm"][
                    "stale_wrong_memory"
                ]["risky_action_before_source_reopen_count"],
            },
            "manual_restatement_context_rebuild_cost": {
                "fresh_missing_context_failure_count": (
                    no_memory["case_count"] - no_memory["success_count"]
                ),
                "summary_only_host_native_failure_count": (
                    host_native["case_count"] - host_native["success_count"]
                ),
                "aippocampus_success_delta_vs_fresh_missing_context": round(
                    float(true_memory["success_rate"]) - float(no_memory["success_rate"]),
                    4,
                ),
                "aippocampus_success_delta_vs_summary_only_host_native": round(
                    float(true_memory["success_rate"]) - float(host_native["success_rate"]),
                    4,
                ),
                "modeled_missing_context_retry_recovery_count": no_memory_cost[
                    "retry_recovery_count"
                ],
                "modeled_missing_context_recovery_cost_units": no_memory_cost[
                    "recovery_cost_units"
                ],
                "user_minutes_calibrated": False,
            },
            "latency_token_cost": {
                strategy: _arm_cost_tokens(cost_harm_ledger, arm)
                for strategy, arm in CONTEXT_LOSS_STRATEGY_ARMS.items()
            },
            "no_remember_controls": {
                "negative_control_case_count": scenario_controls["negative_control_case_count"],
                "aippocampus_negative_control_intervention_count": (true_negative_interventions),
                "aippocampus_unnecessary_negative_intervention_count": (true_negative_unnecessary),
                "aippocampus_no_remember_precision": no_remember_precision,
                "stale_unnecessary_negative_intervention_count": (
                    negative_unnecessary["stale_wrong_memory"]
                ),
            },
        },
        "complete_spec_boundary_reference": {
            "strategy": "fresh_context_spec_loop_complete_spec",
            "success_count": complete_spec_cost["success_count"],
            "total_cost_units": complete_spec_cost["total_cost_units"],
            "net_value_units": complete_spec_net["net_value_units"],
            "primary_context_loss_opponent": False,
        },
        "can_claim": can_claim,
        "cannot_claim": [
            f"superseding {CONTEXT_LOSS_EXPECTED_NULL_ROW_ID}",
            "full #378 continuous-memory superiority",
            "public-quality continuous-memory advantage",
            "live host-native cost or compaction telemetry",
            "private real-history generality",
            "public long-dialogue continuity quality from LoCoMo without a scored prediction run",
            "cross-conversation or life-wide memory quality from same-dialogue controls",
            "calibrated user-visible restatement burden reduction",
            "answer-generation model quality",
            "competitor or leaderboard superiority",
        ],
    }


def build_preregistered_slices(
    *,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    scenario_controls: dict[str, Any],
    cost_harm_ledger: dict[str, Any],
    preregistration: dict[str, Any],
    selected_arms: Sequence[str],
    scenario_selection_role: str,
    paired_repeat_readout: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    decision = preregistration["current_report_decision"]
    required_fair_strategies = preregistration["public_quality_minimums"]["arms_required"]
    selected_fair_strategies = set(selected_arms) | {"fresh_context_spec_loop"}
    true_memory_obedience = metrics["source_reopen_obedience_by_arm"].get("true_aippocampus_memory")
    true_memory_harm = cost_harm_ledger["harm"]["by_arm"]["true_aippocampus_memory"]
    required_fair_arms_present = set(required_fair_strategies) <= selected_fair_strategies
    source_reopen_gate_passed = true_memory_obedience == 1.0
    true_memory_false_positive_gate_passed = true_memory_harm["memory_false_positive_count"] == 0
    scenario_provenance_gate_passed = bool(
        scenario_controls["public_quality_external_or_holdout_share_gate_passed"]
    )
    privacy_gates_passed = True
    repeat_count_per_case_arm = (
        int(paired_repeat_readout["repeat_count_per_case_arm"]) if paired_repeat_readout else 1
    )
    runner_profile = (
        str(paired_repeat_readout["runner_profile"])
        if paired_repeat_readout
        else "public_synthetic_contract_smoke"
    )
    paired_repeat_power_gate_passed = bool(
        paired_repeat_readout and paired_repeat_readout["paired_repeat_power_gate_passed"]
    )
    lower_bound_rule_evaluated = bool(
        paired_repeat_readout and paired_repeat_readout["lower_bound_rule_evaluated"]
    )
    lower_bound_passed = bool(paired_repeat_readout and paired_repeat_readout["lower_bound_passed"])
    hard_gates_passed = bool(
        required_fair_arms_present
        and source_reopen_gate_passed
        and true_memory_false_positive_gate_passed
        and privacy_gates_passed
    )
    public_quality_claim_ready = bool(
        hard_gates_passed
        and scenario_provenance_gate_passed
        and paired_repeat_power_gate_passed
        and lower_bound_rule_evaluated
        and lower_bound_passed
    )
    repeated_readout = lower_bound_rule_evaluated or repeat_count_per_case_arm > 1

    # Keep these as frozen slice descriptors, not second scoring layers. They
    # prevent future #378/#1153 runs from retrofitting positive headlines after
    # looking at exploratory metrics while keeping each contract smoke useful as
    # a preregistered runner target.
    github_378_slice = {
        "schema_version": 1,
        "issue": "github_378",
        "slice_id": "github_378_continuous_memory_public_synthetic_v1",
        "status": (
            "public_synthetic_repeated_lower_bound_evaluated"
            if repeated_readout
            else "diagnostic_contract_smoke"
        ),
        "claim_level": (
            "preregistered_repeated_public_synthetic_slice"
            if repeated_readout
            else "preregistered_diagnostic_slice"
        ),
        "runner_profile": runner_profile,
        "scenario_selection_role": scenario_selection_role,
        "scenario_family": "continuous_agent_memory_attribution",
        "case_count": metrics["case_count"],
        "arm_count": len(selected_arms),
        "row_count": metrics["row_count"],
        "case_manifest_digest_sha256": case_manifest_digest(rows),
        "frozen_inputs": {
            "case_manifest": "sanitized_case_hashes_and_public_metadata_only",
            "scenario_provenance": scenario_controls["reported_provenance_slices"],
            "case_ids_are_hashed": True,
            "raw_source_or_prompt_text_included": False,
            "seed_policy": preregistration["seed_repeat_strategy"]["contract_smoke_seed_policy"],
            "repeat_count_per_case_arm": repeat_count_per_case_arm,
        },
        "fair_strategies_required": required_fair_strategies,
        "fair_strategies_observed": sorted(selected_fair_strategies),
        "primary_endpoint": {
            "name": preregistration["primary_endpoint"]["name"],
            "point_estimate_field": preregistration["primary_endpoint"]["point_estimate_field"],
            "scope": preregistration["primary_endpoint"]["scope"],
        },
        "decision": {
            "evaluated_as": decision["evaluated_as"],
            "primary_endpoint_winner": decision["primary_endpoint_winner"],
            "continuous_memory_advantage_claim_allowed": decision[
                "continuous_memory_advantage_claim_allowed"
            ],
            "decision_label": decision["decision_label"],
            "reason": decision["reason"],
        },
        "public_quality_gates": {
            "required_fair_arms_present": required_fair_arms_present,
            "scenario_provenance_gate_passed": scenario_provenance_gate_passed,
            "source_reopen_gate_passed": source_reopen_gate_passed,
            "true_memory_false_positive_gate_passed": (true_memory_false_positive_gate_passed),
            "privacy_gates_passed": privacy_gates_passed,
            "paired_repeat_power_gate_passed": paired_repeat_power_gate_passed,
            "lower_bound_rule_evaluated": lower_bound_rule_evaluated,
            "hard_gates_passed": hard_gates_passed,
            "public_quality_claim_ready": public_quality_claim_ready,
        },
        "paired_repeat_readout": paired_repeat_readout,
        "diagnostic_result_fields": [
            "metrics.memory_correctness_effect",
            "metrics.stale_memory_harm",
            "cost_harm_ledger.net_value_under_equalized_cost.highest_net_value_fair_strategy",
            "cost_harm_ledger.sensitivity_analysis.true_memory_margin_vs_best_baseline_units",
        ],
        "cannot_claim": [
            "full #378 continuous-memory superiority",
            (
                "public-quality continuous-memory advantage from this repeated public-synthetic slice"
                if repeated_readout
                else "public-quality continuous-memory advantage from this single diagnostic slice"
            ),
            "live host-native cost or compaction telemetry",
            "private real-history generality",
            "cost-weight robust continuous-memory advantage",
        ],
    }
    context_loss_slice = build_context_loss_continuity_slice(
        rows=rows,
        metrics=metrics,
        scenario_controls=scenario_controls,
        cost_harm_ledger=cost_harm_ledger,
        preregistration=preregistration,
        selected_arms=selected_arms,
        paired_repeat_readout=paired_repeat_readout,
    )
    return [github_378_slice, context_loss_slice]
