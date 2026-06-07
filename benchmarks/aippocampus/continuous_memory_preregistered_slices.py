"""Preregistered #378 slice readouts for continuous-memory reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


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


def build_preregistered_slices(
    *,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    scenario_controls: dict[str, Any],
    cost_harm_ledger: dict[str, Any],
    preregistration: dict[str, Any],
    selected_arms: Sequence[str],
    scenario_selection_role: str,
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
    paired_repeat_power_gate_passed = False
    lower_bound_rule_evaluated = False
    hard_gates_passed = bool(
        required_fair_arms_present
        and source_reopen_gate_passed
        and true_memory_false_positive_gate_passed
        and privacy_gates_passed
    )

    # Keep this as a frozen slice descriptor, not a second scoring layer. It
    # prevents future #378 runs from retrofitting a positive headline after
    # looking at exploratory metrics while still keeping this contract smoke
    # useful as a preregistered runner target.
    return [
        {
            "schema_version": 1,
            "issue": "github_378",
            "slice_id": "github_378_continuous_memory_public_synthetic_v1",
            "status": "diagnostic_contract_smoke",
            "claim_level": "preregistered_diagnostic_slice",
            "runner_profile": "public_synthetic_contract_smoke",
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
                "repeat_count_per_case_arm": 1,
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
                "public_quality_claim_ready": False,
            },
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
                "public-quality continuous-memory advantage from this single diagnostic slice",
                "live host-native cost or compaction telemetry",
                "private real-history generality",
                "cost-weight robust continuous-memory advantage",
            ],
        }
    ]
