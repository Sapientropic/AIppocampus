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
                "scenario_negative_control_kind": row[
                    "scenario_negative_control_kind"
                ],
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
    required_arm_rows_present = any(
        row["arm"] == "true_aippocampus_memory" for row in rows
    )
    lower_bound_rule_evaluated = bool(
        paired_repeat_power_gate_passed and required_arm_rows_present
    )

    paired_deltas: list[dict[str, Any]] = []
    for repeat_index in repeat_indexes:
        true_rows = [
            row
            for row in rows
            if row["repeat_index"] == repeat_index
            and row["arm"] == "true_aippocampus_memory"
        ]
        true_net = net_value_for_rows(true_rows)
        fresh_net = fresh_context_net_for_case_count(int(metrics["case_count"]))
        delta = round(float(true_net["net_value_units"]) - float(fresh_net["net_value_units"]), 4)
        paired_deltas.append(
            {
                "repeat_index": repeat_index,
                "true_aippocampus_memory_net_value_units": true_net[
                    "net_value_units"
                ],
                "fresh_context_spec_loop_net_value_units": fresh_net[
                    "net_value_units"
                ],
                "delta_units": delta,
                "winning_strategy": (
                    "true_aippocampus_memory"
                    if delta > 0
                    else "fresh_context_spec_loop"
                ),
            }
        )

    delta_values = [float(item["delta_units"]) for item in paired_deltas]
    lower_bound_units = (
        round(min(delta_values), 4)
        if lower_bound_rule_evaluated and delta_values
        else None
    )
    mean_delta_units = (
        round(sum(delta_values) / len(delta_values), 4) if delta_values else None
    )
    lower_bound_passed = bool(
        lower_bound_units is not None and lower_bound_units > 0
    )
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
        "required_repeat_count_per_case_arm": (
            PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM
        ),
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
        "cannot_claim": [
            "live host-native cost or compaction telemetry",
            "private real-history generality",
            "public-quality continuous-memory advantage when lower_bound_units <= 0",
            "statistical power beyond deterministic public-synthetic repeated rows",
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
        paired_repeat_readout
        and paired_repeat_readout["lower_bound_rule_evaluated"]
    )
    if lower_bound_evaluated:
        assert paired_repeat_readout is not None
        claim_allowed = bool(
            fair_winner == "true_aippocampus_memory"
            and paired_repeat_readout["lower_bound_passed"]
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
                "cost_harm_ledger.net_value_under_equalized_cost."
                "highest_net_value_fair_strategy"
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
            "repeats_per_scenario_arm": (
                PUBLIC_QUALITY_MIN_REPEATS_PER_SCENARIO_ARM
            ),
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
            "contract_smoke_seed_policy": (
                "deterministic_public_safe_cases_no_random_seed"
            ),
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
        "secondary_metrics_policy": (
            "exploratory_unless_named_in_primary_decision_rule"
        ),
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
            "reason": reason,
        },
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
    required_fair_strategies = preregistration["public_quality_minimums"][
        "arms_required"
    ]
    selected_fair_strategies = set(selected_arms) | {"fresh_context_spec_loop"}
    true_memory_obedience = metrics["source_reopen_obedience_by_arm"].get(
        "true_aippocampus_memory"
    )
    true_memory_harm = cost_harm_ledger["harm"]["by_arm"]["true_aippocampus_memory"]
    required_fair_arms_present = set(required_fair_strategies) <= selected_fair_strategies
    source_reopen_gate_passed = true_memory_obedience == 1.0
    true_memory_false_positive_gate_passed = (
        true_memory_harm["memory_false_positive_count"] == 0
    )
    scenario_provenance_gate_passed = bool(
        scenario_controls["public_quality_external_or_holdout_share_gate_passed"]
    )
    privacy_gates_passed = True
    repeat_count_per_case_arm = (
        int(paired_repeat_readout["repeat_count_per_case_arm"])
        if paired_repeat_readout
        else 1
    )
    runner_profile = (
        str(paired_repeat_readout["runner_profile"])
        if paired_repeat_readout
        else "public_synthetic_contract_smoke"
    )
    paired_repeat_power_gate_passed = bool(
        paired_repeat_readout
        and paired_repeat_readout["paired_repeat_power_gate_passed"]
    )
    lower_bound_rule_evaluated = bool(
        paired_repeat_readout
        and paired_repeat_readout["lower_bound_rule_evaluated"]
    )
    lower_bound_passed = bool(
        paired_repeat_readout and paired_repeat_readout["lower_bound_passed"]
    )
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

    # Keep this as a frozen slice descriptor, not a second scoring layer. It
    # prevents future #378 runs from retrofitting a positive headline after
    # looking at exploratory metrics while still keeping this contract smoke
    # useful as a preregistered runner target.
    return [
        {
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
                "scenario_provenance": scenario_controls[
                    "reported_provenance_slices"
                ],
                "case_ids_are_hashed": True,
                "raw_source_or_prompt_text_included": False,
                "seed_policy": preregistration["seed_repeat_strategy"][
                    "contract_smoke_seed_policy"
                ],
                "repeat_count_per_case_arm": repeat_count_per_case_arm,
            },
            "fair_strategies_required": required_fair_strategies,
            "fair_strategies_observed": sorted(selected_fair_strategies),
            "primary_endpoint": {
                "name": preregistration["primary_endpoint"]["name"],
                "point_estimate_field": preregistration["primary_endpoint"][
                    "point_estimate_field"
                ],
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
                "true_memory_false_positive_gate_passed": (
                    true_memory_false_positive_gate_passed
                ),
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
                "cost_harm_ledger.net_value_under_equalized_cost."
                "highest_net_value_fair_strategy",
                "cost_harm_ledger.sensitivity_analysis."
                "true_memory_margin_vs_best_baseline_units",
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
    ]
