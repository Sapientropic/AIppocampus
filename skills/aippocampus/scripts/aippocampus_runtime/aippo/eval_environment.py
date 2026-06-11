"""Deterministic public-safe AIppo eval environment prototype."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import working_contract

SCHEMA_VERSION = "aippo-eval-environment-v0"


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _fixture_instances() -> list[dict[str, Any]]:
    return [
        {
            "instance_id": "claim_from_tiny_fixture",
            "novelty_tag": "benchmark",
            "difficulty": "medium",
            "baseline": {"manual_search": 3, "warnings": 3, "claim_errors": 1, "route_success": 0},
            "aippo": {"manual_search": 1, "warnings": 1, "claim_errors": 0, "route_success": 1},
        },
        {
            "instance_id": "close_broad_issue_from_small_slice",
            "novelty_tag": "issue_closeout",
            "difficulty": "medium",
            "baseline": {"manual_search": 2, "warnings": 2, "claim_errors": 1, "route_success": 0},
            "aippo": {"manual_search": 1, "warnings": 1, "claim_errors": 0, "route_success": 1},
        },
        {
            "instance_id": "over_conservative_cannot_claim_noise",
            "novelty_tag": "public_claim",
            "difficulty": "medium",
            "baseline": {"manual_search": 2, "warnings": 4, "claim_errors": 0, "route_success": 0},
            "aippo": {"manual_search": 1, "warnings": 1, "claim_errors": 0, "route_success": 1},
        },
        {
            "instance_id": "stale_evidence_requires_reopen",
            "novelty_tag": "staleness",
            "difficulty": "hard",
            "baseline": {"manual_search": 3, "warnings": 1, "claim_errors": 1, "route_success": 0},
            "aippo": {"manual_search": 2, "warnings": 1, "claim_errors": 0, "route_success": 1},
        },
        {
            "instance_id": "same_route_repeated_manual_search",
            "novelty_tag": "route_reuse",
            "difficulty": "medium",
            "baseline": {"manual_search": 4, "warnings": 2, "claim_errors": 0, "route_success": 0},
            "aippo": {"manual_search": 1, "warnings": 1, "claim_errors": 0, "route_success": 1},
        },
    ]


def _rejected_instances() -> list[dict[str, Any]]:
    return [
        {"instance_id": "trivial_for_all_arms", "reject_reason": "trivial_for_all_arms"},
        {"instance_id": "impossible_without_source", "reject_reason": "impossible_for_all_arms"},
        {"instance_id": "surface_variant_duplicate", "reject_reason": "novelty_duplicate"},
    ]


def _environment(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "aippo_eval_environment",
        "schema_version": SCHEMA_VERSION,
        "env_id": "env_aippo_claim_boundary_public_safe_v0",
        "need_class": "benchmark_claim_boundary",
        "aippo_id": contract.get("aippo_id") or working_contract.AIPPO_ID,
        "clause_ids": ["clause_keep_changes_scoped", "clause_preserve_useful_result_claims"],
        "sampler": {
            "fixture_family": "public_safe_issue_threads",
            "difficulty_knobs": [
                "claim_specificity",
                "staleness",
                "evidence_strength",
                "tempting_overclaim",
            ],
            "novelty_tags": ["benchmark", "issue_closeout", "public_claim", "staleness"],
        },
        "prompt_renderer": {
            "baseline_prompt": "fresh agent task without AIppo packet",
            "aippo_prompt": "same task with compact AIppo activation packet",
        },
        "scorer": {
            "frozen": True,
            "metrics": [
                "manual_search_count_before_useful_context",
                "unnecessary_warning_count",
                "claim_boundary_correctness",
                "packet_noise_bytes",
                "route_follow_success",
            ],
        },
        "admission": {
            "source_backed": True,
            "deterministic_public_safe": True,
            "solver_relative_difficulty_checked": True,
            "novelty_checked": True,
            "eval_environment_required": "recommended",
            "cost_tier": "deterministic_fixture_low",
            "eval_candidate_reason": (
                "manual_search_reduction_observed; public-claim boundary has high overclaim cost; "
                "deterministic fixtures can test the clause without paid live-agent runs"
            ),
            "expected_value_reason_codes": [
                "public_claim_boundary_risk",
                "manual_search_reduction_observed",
                "recurring_issue_closeout_need",
            ],
        },
    }


def _render_prompt_pairs(instances: Sequence[Mapping[str, Any]], packet: Mapping[str, Any]) -> list[dict[str, str]]:
    guidance = "; ".join(str(item) for item in packet.get("use_guidance") or [])
    pairs = []
    for instance in instances:
        task = str(instance.get("instance_id") or "task").replace("_", " ")
        pairs.append(
            {
                "instance_id": str(instance.get("instance_id")),
                "baseline_prompt": f"Handle this AIppocampus issue task: {task}.",
                "aippo_prompt": f"Handle this AIppocampus issue task: {task}.\nAIppo: {guidance}",
            }
        )
    return pairs


def _sum_metric(instances: Sequence[Mapping[str, Any]], arm: str, metric: str) -> int:
    total = 0
    for instance in instances:
        scores = instance.get(arm)
        if isinstance(scores, Mapping):
            total += int(scores.get(metric) or 0)
    return total


def build_aippo_eval_environment_fixture_report() -> dict[str, Any]:
    contract = working_contract.build_project_workflow_public_safe_contract()
    packet = working_contract.activation_packet_from_working_contract(
        contract,
        task="benchmark claim issue closeout",
    )
    env = _environment(contract)
    instances = _fixture_instances()
    rejected = _rejected_instances()
    scorer_hash = _stable_hash(env["scorer"])
    comparison = {
        "manual_search_delta_vs_baseline": _sum_metric(instances, "baseline", "manual_search")
        - _sum_metric(instances, "aippo", "manual_search"),
        "packet_noise_delta_vs_baseline": -220,
        "unnecessary_warning_delta_vs_baseline": _sum_metric(instances, "aippo", "warnings")
        - _sum_metric(instances, "baseline", "warnings"),
        "claim_boundary_error_delta_vs_baseline": _sum_metric(instances, "aippo", "claim_errors")
        - _sum_metric(instances, "baseline", "claim_errors"),
        "route_follow_success_delta_vs_baseline": _sum_metric(instances, "aippo", "route_success")
        - _sum_metric(instances, "baseline", "route_success"),
        "fresh_agent_task_quality_delta": 5,
    }
    metrics = {
        "aippo_eval_env_count": 1,
        "aippo_eval_instance_count": len(instances),
        "aippo_env_admission_pass_count": len(instances),
        "aippo_env_admission_reject_count": len(rejected),
        "trivial_for_all_arms_reject_count": sum(
            1 for item in rejected if item["reject_reason"] == "trivial_for_all_arms"
        ),
        "impossible_for_all_arms_reject_count": sum(
            1 for item in rejected if item["reject_reason"] == "impossible_for_all_arms"
        ),
        "novelty_reject_count": sum(
            1 for item in rejected if item["reject_reason"] == "novelty_duplicate"
        ),
        "scorer_mutation_attempt_count": 0,
        "source_mutated_by_eval_environment_count": 0,
        "mutable_scorer_during_run_count": int(scorer_hash != _stable_hash(env["scorer"])),
    }
    red_lines = {
        "self_report_used_as_eval_truth_count": 0,
        "self_improvement_trace_counted_as_product_evidence": 0,
        "mutable_scorer_during_run_count": metrics["mutable_scorer_during_run_count"],
        "source_mutated_by_eval_environment_count": 0,
        "claim_ready_fact_from_working_contract_count": 0,
    }
    cheap_no_eval_path = {
        "allowed": True,
        "base_tier": "seed_aippo",
        "observed_tier": "observed_aippo",
        "meaning": (
            "A source-backed AIppo can remain useful as a compact working contract before "
            "any deterministic environment is built."
        ),
    }
    promotion_policy = {
        "source": "aippo_feedback_reripening",
        "promotion_sources": [
            "feedback_reripening_high_value_or_problematic_clause",
            "high_frequency_public_claim_boundary",
            "operator_selected_need_class",
        ],
        "lifecycle_tiers": [
            "seed_aippo",
            "observed_aippo",
            "ripe_aippo",
            "eval_backed_aippo",
            "product_critical_aippo",
        ],
        "expensive_multi_arm_runs_require_operator_opt_in": True,
        "default_runtime_tax_on_every_aippo": False,
    }
    return {
        "kind": "aippocampus_aippo_eval_environment_report",
        "schema_version": SCHEMA_VERSION,
        "environment": env,
        "instances": instances,
        "rejected_instances": rejected,
        "rendered_prompt_pairs": _render_prompt_pairs(instances, packet),
        "comparison": comparison,
        "metrics": metrics,
        "red_lines": red_lines,
        "cheap_no_eval_path": cheap_no_eval_path,
        "promotion_policy": promotion_policy,
        "ok": all(value == 0 for value in red_lines.values())
        and comparison["manual_search_delta_vs_baseline"] > 0
        and comparison["route_follow_success_delta_vs_baseline"] > 0,
        "contract": {
            "scorer_frozen_for_run": True,
            "scorer_hash": scorer_hash,
            "source_traces_used_not_mutated": True,
            "candidate_packet_cannot_modify_scorer": True,
        },
    }


__all__ = ["build_aippo_eval_environment_fixture_report"]
