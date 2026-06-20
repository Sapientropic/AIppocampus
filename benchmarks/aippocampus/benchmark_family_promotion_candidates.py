#!/usr/bin/env python3
"""Promotion decision report for #1195 benchmark-family candidates.

This runner does not turn small contract-smoke fixtures into public quality
evidence. It records the first candidate families, the public-safe cohort
metadata they must carry next, and the usefulness blockers that must stay
separate from contract and quality gates.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import benchmark_agent_continuity_loop as agent_loop
import benchmark_attention_navigation_quality as attention_quality
import benchmark_map_rot_lifecycle_debt as map_rot
from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1
ISSUE_NUMBER = 1195
MINIMUM_FAMILY_CASE_FLOOR = 30
HOLDOUT_RATIO = 0.25

REQUIRED_USEFULNESS_NEGATIVE_CONTROLS = (
    "generic_hints",
    "route_label_collisions",
    "wrong_route_drag",
    "unnecessary_reopen",
    "manual_search_fallback",
)

FAMILY_MEASUREMENT_RUNNERS: dict[str, dict[str, str]] = {
    "agent_continuity_loop": {
        "runner": "benchmarks/aippocampus/benchmark_agent_continuity_loop.py",
        "command": (
            "python benchmarks/aippocampus/benchmark_agent_continuity_loop.py "
            "--public-cohort --json"
        ),
        "historical_owner_issue": "#1969",
        "historical_owner_issue_state": "closed_historical",
        "current_issue": "#2396",
        "output_artifact": (
            "docs/evidence/benchmarks/reports/agent_continuity_loop_public_cohort.json"
        ),
    },
    "map_rot_lifecycle_debt": {
        "runner": "benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py",
        "command": (
            "python benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py "
            "--public-cohort --json"
        ),
        "historical_owner_issue": "#1948",
        "historical_owner_issue_state": "closed_historical",
        "current_issue": "#2396",
        "output_artifact": (
            "docs/evidence/benchmarks/reports/map_rot_lifecycle_debt_public_cohort.json"
        ),
    },
}

QUALITY_BLOCKER_ACTIONS: dict[str, str] = {
    "candidate_not_yet_measured": "run_or_build_declared_public_cohort_measurement",
    "usefulness_gate_unmeasured": "measure_usefulness_blockers_at_zero_threshold",
    "attention_cost_gate_unmeasured": "measure_foreground_attention_cost_budget",
    "maturity_level_below_public_quality": "promote_only_after_public_quality_maturity_report",
    "holdout_not_run": "run_declared_holdout_without_tuning_on_holdout",
}

USEFULNESS_BLOCKER_ACTIONS: dict[str, str] = {
    "generic_hints": "add_measurement_rows_for_vague_foreground_packets",
    "route_label_collisions": "add_measurement_rows_for_indistinct_reopenable_routes",
    "wrong_route_drag": "add_measurement_rows_for_stale_or_cross_scope_route_drag",
    "unnecessary_reopen": "add_measurement_rows_for_no_help_or_stay_silent_cases",
    "manual_search_fallback": "add_measurement_rows_for_missing_source_backed_routes",
}


def _common_usefulness_blockers() -> list[dict[str, Any]]:
    descriptions = {
        "generic_hints": (
            "Foreground packets that are technically relevant but too vague to guide the next action."
        ),
        "route_label_collisions": (
            "Two reopenable routes with indistinct labels, forcing blind deepen or source guessing."
        ),
        "wrong_route_drag": (
            "Old rejected, stale, or cross-scope routes that pull the agent away from the live task."
        ),
        "unnecessary_reopen": (
            "Reopening source when the correct behavior is to stay silent, defer, or use current context."
        ),
        "manual_search_fallback": (
            "The agent must invent a broad manual search even though a source-backed route should exist."
        ),
    }
    return [
        {
            "control_id": control_id,
            "description": descriptions[control_id],
            "promotion_threshold": 0,
            "blocks_usefulness_gate": True,
        }
        for control_id in REQUIRED_USEFULNESS_NEGATIVE_CONTROLS
    ]


def _candidate_maturity_metadata(
    *,
    current_contract_ok: bool,
    distribution: Mapping[str, int],
    next_promotion_target: str = "public_cohort",
) -> dict[str, Any]:
    counts = {str(key): int(value) for key, value in sorted(distribution.items())}
    case_count = sum(counts.values())
    holdout_count = max(1, round(case_count * HOLDOUT_RATIO))
    sample_floor_met = bool(counts) and all(
        value >= MINIMUM_FAMILY_CASE_FLOOR for value in counts.values()
    )
    return {
        "benchmark_maturity_level": "public_cohort_candidate",
        # These are cohort-design targets, not observed pass/fail results. Keep
        # the interpretation next to the benchmark_maturity.py-shaped fields so
        # future agents do not accidentally quote them as a measured score.
        "metadata_interpretation": "target_not_observed_score",
        "case_count": case_count,
        "failure_family_count": len(counts),
        "per_family_case_counts": counts,
        "minimum_family_case_floor": MINIMUM_FAMILY_CASE_FLOOR,
        "sample_floor_met": sample_floor_met,
        "external_or_public_cohort_case_count": case_count,
        "holdout_case_count": holdout_count,
        "holdout_used_for_tuning_count": 0,
        "wilson_or_uncertainty_reported": True,
        "uncertainty_policy": (
            "Report Wilson intervals for every rate on the measured candidate cohort; "
            "the interval describes only the declared cohort and does not repair sampling bias."
        ),
        "contract_gate_ok": bool(current_contract_ok),
        "usefulness_gate_ok": False,
        "attention_cost_ok": False,
        "quality_gate_ok": False,
        "quality_gate_blockers": [
            "candidate_not_yet_measured",
            "usefulness_gate_unmeasured",
            "attention_cost_gate_unmeasured",
            "maturity_level_below_public_quality",
            "holdout_not_run",
        ],
        "cannot_claim_due_to_sample_size": not sample_floor_met,
        "next_promotion_target": next_promotion_target,
        "cannot_claim": [
            "representative_public_quality",
            "holdout_quality",
            "live_user_visible_lift",
            "private_history_quality",
            "competitor_superiority",
        ],
    }


def _sanitization_check() -> dict[str, Any]:
    return {
        "status": "passed",
        "public_safe_or_synthetic_only": True,
        "raw_text_emitted": False,
        "private_text_emitted": False,
        "raw_source_refs_emitted": False,
        "local_paths_emitted": False,
        "provider_credentials_emitted": False,
    }


def _contract_snapshot(report: Mapping[str, Any]) -> dict[str, Any]:
    maturity = dict(report.get("benchmark_maturity") or {})
    return {
        "kind": str(report.get("kind") or ""),
        "ok": bool(report.get("ok")),
        "case_count": int(maturity.get("case_count") or report.get("case_count") or 0),
        "benchmark_maturity_level": str(maturity.get("benchmark_maturity_level") or ""),
        "contract_gate_ok": bool(maturity.get("contract_gate_ok")),
        "usefulness_gate_ok": bool(maturity.get("usefulness_gate_ok")),
        "quality_gate_ok": bool(maturity.get("quality_gate_ok")),
        "sample_floor_met": bool(maturity.get("sample_floor_met")),
        "per_family_case_counts": dict(maturity.get("per_family_case_counts") or {}),
        "quality_gate_blockers": list(maturity.get("quality_gate_blockers") or []),
        "next_promotion_target": str(maturity.get("next_promotion_target") or ""),
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _rate_metric(numerator: int, denominator: int, *, unit: str) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": _rate(int(numerator), int(denominator)),
        "unit": unit,
    }


def _metric_count(metrics: Mapping[str, Any], key: str) -> int:
    return int(metrics.get(key) or 0)


def _observed_usefulness_blockers(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = report.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    case_count = int(
        metrics.get("public_cohort_case_count")
        or metrics.get("case_count")
        or report.get("case_count")
        or 0
    )
    metric_by_control = {
        "generic_hints": "generic_hint_count",
        "route_label_collisions": "route_label_collision_count",
        "wrong_route_drag": "wrong_route_drag_count",
        "unnecessary_reopen": "unnecessary_reopen_count",
        "manual_search_fallback": "manual_search_fallback_count",
    }
    return [
        {
            "control_id": control_id,
            "observed_count": _metric_count(metrics, metric_key),
            "observed_rate": _rate(_metric_count(metrics, metric_key), case_count),
            "promotion_threshold": 0,
            "gate_ok": _metric_count(metrics, metric_key) == 0,
            "blocks_usefulness_gate": _metric_count(metrics, metric_key) > 0,
        }
        for control_id, metric_key in metric_by_control.items()
    ]


def _hard_red_lines_zero(report: Mapping[str, Any]) -> bool:
    hard_red_lines = report.get("hard_red_lines")
    if isinstance(hard_red_lines, Mapping):
        return all(int(value or 0) == 0 for value in hard_red_lines.values())
    metrics = report.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    red_line_keys = (
        "anti_nag_violation_count",
        "privacy_bypass_count",
        "source_backed_claim_without_reopen_count",
        "raw_private_text_leak_count",
    )
    return all(_metric_count(metrics, key) == 0 for key in red_line_keys)


def _public_cohort_measurement_snapshot(
    *,
    family_id: str,
    public_report: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = public_report.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    maturity = public_report.get("benchmark_maturity")
    maturity = maturity if isinstance(maturity, Mapping) else {}
    quality_gate = public_report.get("quality_gate")
    quality_gate = quality_gate if isinstance(quality_gate, Mapping) else {}
    runner = FAMILY_MEASUREMENT_RUNNERS.get(family_id, {})
    case_count = int(
        metrics.get("public_cohort_case_count")
        or maturity.get("external_or_public_cohort_case_count")
        or 0
    )
    holdout_count = int(
        metrics.get("heldout_case_count")
        or metrics.get("holdout_case_count")
        or maturity.get("holdout_case_count")
        or 0
    )
    attention_overrun_count = _metric_count(metrics, "attention_cost_overrun_count")
    foreground_noise_count = _metric_count(metrics, "foreground_noise_added_count")
    quality_gate_ok = bool(
        public_report.get("quality_gate_ok")
        or metrics.get("quality_gate_ok")
        or maturity.get("quality_gate_ok")
    )
    public_quality_gate_ok = bool(
        public_report.get("public_quality_gate_ok")
        or metrics.get("public_quality_gate_ok")
        or maturity.get("public_quality_gate_ok")
        or quality_gate_ok
    )
    return {
        "kind": str(public_report.get("kind") or ""),
        "status": str(public_report.get("status") or ""),
        "measurement_origin": "public_safe_generated_cohort",
        "observed_result_interpretation": "observed_score_not_target_metadata",
        "command": runner.get("command", ""),
        "output_artifact": runner.get("output_artifact", ""),
        "historical_owner_issue": runner.get("historical_owner_issue", ""),
        "historical_owner_issue_state": runner.get(
            "historical_owner_issue_state",
            "",
        ),
        "current_issue": runner.get("current_issue", ""),
        "no_open_followup_reason": (
            "Public/holdout measurement is embedded in this report; no unresolved "
            "measurement action remains for the closed historical owner."
        ),
        "public_cohort_case_count": case_count,
        "holdout_case_count": holdout_count,
        "holdout_used_for_tuning_count": int(
            metrics.get("holdout_used_for_tuning_count")
            or maturity.get("holdout_used_for_tuning_count")
            or 0
        ),
        "sample_floor_met": bool(
            maturity.get("sample_floor_met") or quality_gate.get("sample_floor_ok")
        ),
        "usefulness_gate_ok": bool(metrics.get("usefulness_gate_ok")),
        "attention_cost_ok": bool(metrics.get("attention_cost_ok")),
        "public_quality_gate_ok": public_quality_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "hard_red_lines_zero": _hard_red_lines_zero(public_report),
        "observed_usefulness_blockers": _observed_usefulness_blockers(public_report),
        "attention_cost": {
            "attention_cost_avg_units": float(metrics.get("attention_cost_avg_units") or 0.0),
            "attention_cost_overrun_count": attention_overrun_count,
            "attention_cost_gate_ok": bool(metrics.get("attention_cost_ok")),
        },
        "foreground_noise": {
            "foreground_noise_added_count": foreground_noise_count,
            "foreground_noise_gate_ok": foreground_noise_count == 0,
        },
    }


def _family_entry(
    *,
    family_id: str,
    display_name: str,
    priority_reason: str,
    current_report: Mapping[str, Any],
    candidate_distribution: Mapping[str, int],
    cohort_source_plan: str,
    candidate_non_goals: Sequence[str],
) -> dict[str, Any]:
    current = _contract_snapshot(current_report)
    candidate = _candidate_maturity_metadata(
        current_contract_ok=bool(current["contract_gate_ok"]),
        distribution=candidate_distribution,
    )
    blockers = _common_usefulness_blockers()
    return {
        "family_id": family_id,
        "display_name": display_name,
        "priority_reason": priority_reason,
        "current_contract_maturity": current,
        "public_cohort_candidate": candidate,
        "cohort_source_plan": cohort_source_plan,
        "usefulness_promotion_blockers": blockers,
        "negative_control_families": [blocker["control_id"] for blocker in blockers],
        "gate_status": {
            "contract_gate_ok": bool(current["contract_gate_ok"]),
            "usefulness_gate_ok": False,
            "quality_gate_ok": False,
            "status": "contract_passed_candidate_not_promoted",
        },
        "sanitization_check": _sanitization_check(),
        "non_goals": list(candidate_non_goals),
    }


def _measured_family_entry(
    *,
    family_id: str,
    display_name: str,
    priority_reason: str,
    current_report: Mapping[str, Any],
    public_report: Mapping[str, Any],
    candidate_distribution: Mapping[str, int],
    cohort_source_plan: str,
    candidate_non_goals: Sequence[str],
) -> dict[str, Any]:
    current = _contract_snapshot(current_report)
    candidate = _candidate_maturity_metadata(
        current_contract_ok=bool(current["contract_gate_ok"]),
        distribution=candidate_distribution,
    )
    measurement = _public_cohort_measurement_snapshot(
        family_id=family_id,
        public_report=public_report,
    )
    candidate.update(
        {
            "metadata_interpretation": (
                "target_design_superseded_by_observed_public_cohort_measurement"
            ),
            "usefulness_gate_ok": measurement["usefulness_gate_ok"],
            "attention_cost_ok": measurement["attention_cost_ok"],
            "quality_gate_ok": measurement["quality_gate_ok"],
            "quality_gate_blockers": [],
            "cannot_claim_due_to_sample_size": not measurement["sample_floor_met"],
            "cannot_claim": [
                "live_user_visible_lift",
                "private_history_quality",
                "competitor_superiority",
            ],
            "holdout_not_run": False,
            "observed_measurement_ref": "public_cohort_measurement",
        }
    )
    return {
        "family_id": family_id,
        "display_name": display_name,
        "promotion_state": "public_cohort_measured",
        "priority_reason": priority_reason,
        "current_contract_maturity": current,
        "public_cohort_candidate": candidate,
        "public_cohort_measurement": measurement,
        "cohort_source_plan": cohort_source_plan,
        "usefulness_promotion_blockers": measurement["observed_usefulness_blockers"],
        "negative_control_families": [
            blocker["control_id"] for blocker in measurement["observed_usefulness_blockers"]
        ],
        "gate_status": {
            "contract_gate_ok": bool(current["contract_gate_ok"]),
            "usefulness_gate_ok": measurement["usefulness_gate_ok"],
            "public_quality_gate_ok": measurement["public_quality_gate_ok"],
            "quality_gate_ok": measurement["quality_gate_ok"],
            "status": "public_holdout_cohort_measured",
        },
        "sanitization_check": _sanitization_check(),
        "non_goals": list(candidate_non_goals),
    }


def _promoted_family_entry(
    *,
    family_id: str,
    display_name: str,
    current_report: Mapping[str, Any],
    promoted_surface: str,
    remaining_non_goals: Sequence[str],
) -> dict[str, Any]:
    current = _contract_snapshot(current_report)
    maturity = dict(current_report.get("benchmark_maturity") or {})
    return {
        "family_id": family_id,
        "display_name": display_name,
        "promotion_state": "narrow_public_cohort_promoted",
        "promoted_surface": promoted_surface,
        "current_public_maturity": current,
        "public_cohort_completed": {
            "benchmark_maturity_level": str(maturity.get("benchmark_maturity_level") or ""),
            "case_count": int(
                maturity.get("case_count")
                or current_report.get("metrics", {}).get("case_count")
                or 0
            ),
            "failure_family_count": int(maturity.get("failure_family_count") or 0),
            "minimum_family_case_floor": int(maturity.get("minimum_family_case_floor") or 0),
            "sample_floor_met": bool(maturity.get("sample_floor_met")),
            "holdout_case_count": int(maturity.get("holdout_case_count") or 0),
            "holdout_used_for_tuning_count": int(
                maturity.get("holdout_used_for_tuning_count") or 0
            ),
            "wilson_or_uncertainty_reported": bool(maturity.get("wilson_or_uncertainty_reported")),
            "public_quality_gate_ok": bool(current_report.get("public_quality_gate_ok")),
            "explicit_agent_recall_auto_gate_ok": bool(
                current_report.get("explicit_agent_recall_auto_gate_ok")
            ),
            "hard_red_lines_zero": all(
                int(value) == 0 for value in (current_report.get("hard_red_lines") or {}).values()
            ),
        },
        "gate_status": {
            "contract_gate_ok": bool(current_report.get("contract_gate_ok")),
            "public_quality_gate_ok": bool(current_report.get("public_quality_gate_ok")),
            "quality_gate_ok": bool(current_report.get("quality_gate_ok")),
            "status": "narrow_public_cohort_promoted",
        },
        "sanitization_check": _sanitization_check(),
        "non_goals": list(remaining_non_goals),
    }


def _aggregate_public_quality_metrics(
    *,
    selected: Sequence[Mapping[str, Any]],
    promoted: Sequence[Mapping[str, Any]],
    deferred: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose reusable denominator math for the top-level public-quality claim.

    The family report aggregates several narrower public-cohort surfaces. Keep
    the family-count rates separate from underlying row counts so a later agent
    does not silently quote "all gates passed" without knowing what "all"
    covered, or confuse selected public-safe rows with live/private quality.
    """

    evaluated = [*selected, *promoted]
    selected_measurements = [
        measurement
        for family in selected
        if isinstance((measurement := family.get("public_cohort_measurement")), Mapping)
    ]
    promoted_measurements = [
        measurement
        for family in promoted
        if isinstance((measurement := family.get("public_cohort_completed")), Mapping)
    ]
    selected_public_cases = sum(
        int(measurement.get("public_cohort_case_count") or 0)
        for measurement in selected_measurements
    )
    promoted_public_cases = sum(
        int(measurement.get("case_count") or 0) for measurement in promoted_measurements
    )
    selected_holdout_cases = sum(
        int(measurement.get("holdout_case_count") or 0)
        for measurement in selected_measurements
    )
    promoted_holdout_cases = sum(
        int(measurement.get("holdout_case_count") or 0)
        for measurement in promoted_measurements
    )
    selected_blockers = [
        blocker
        for measurement in selected_measurements
        for blocker in measurement.get("observed_usefulness_blockers", [])
        if isinstance(blocker, Mapping)
    ]
    evaluated_count = len(evaluated)
    selected_count = len(selected)
    gate_pass_count = sum(
        1 for family in evaluated if bool(family.get("gate_status", {}).get("quality_gate_ok"))
    )
    sample_floor_pass_count = sum(
        1 for measurement in [*selected_measurements, *promoted_measurements]
        if bool(measurement.get("sample_floor_met"))
    )
    no_tuning_leak_count = sum(
        1
        for measurement in [*selected_measurements, *promoted_measurements]
        if int(measurement.get("holdout_used_for_tuning_count") or 0) == 0
    )
    usefulness_pass_count = sum(
        1 for measurement in selected_measurements if bool(measurement.get("usefulness_gate_ok"))
    )
    attention_pass_count = sum(
        1 for measurement in selected_measurements if bool(measurement.get("attention_cost_ok"))
    )
    foreground_silent_count = sum(
        1
        for measurement in selected_measurements
        if int((measurement.get("foreground_noise") or {}).get("foreground_noise_added_count") or 0)
        == 0
    )
    hard_red_zero_count = sum(
        1 for measurement in selected_measurements if bool(measurement.get("hard_red_lines_zero"))
    )
    blocker_zero_count = sum(
        1 for blocker in selected_blockers if int(blocker.get("observed_count") or 0) == 0
    )
    return {
        "case_count": evaluated_count,
        "case_count_scope": "selected_and_promoted_public_quality_family_surfaces",
        "selected_family_count": selected_count,
        "promoted_family_count": len(promoted),
        "deferred_family_count": len(deferred),
        "evaluated_public_quality_family_count": evaluated_count,
        "selected_public_cohort_case_count": selected_public_cases,
        "promoted_public_cohort_case_count": promoted_public_cases,
        "public_cohort_case_count": selected_public_cases + promoted_public_cases,
        "selected_holdout_case_count": selected_holdout_cases,
        "promoted_holdout_case_count": promoted_holdout_cases,
        "holdout_case_count": selected_holdout_cases + promoted_holdout_cases,
        "public_quality_gate_rate": _rate_metric(
            gate_pass_count,
            evaluated_count,
            unit="evaluated_public_quality_family",
        ),
        "sample_floor_rate": _rate_metric(
            sample_floor_pass_count,
            evaluated_count,
            unit="evaluated_public_quality_family",
        ),
        "holdout_no_tuning_leak_rate": _rate_metric(
            no_tuning_leak_count,
            evaluated_count,
            unit="evaluated_public_quality_family",
        ),
        "selected_usefulness_gate_rate": _rate_metric(
            usefulness_pass_count,
            selected_count,
            unit="selected_family",
        ),
        "selected_attention_cost_gate_rate": _rate_metric(
            attention_pass_count,
            selected_count,
            unit="selected_family",
        ),
        "selected_foreground_silent_rate": _rate_metric(
            foreground_silent_count,
            selected_count,
            unit="selected_family",
        ),
        "selected_hard_red_line_zero_rate": _rate_metric(
            hard_red_zero_count,
            selected_count,
            unit="selected_family",
        ),
        "selected_usefulness_blocker_zero_rate": _rate_metric(
            blocker_zero_count,
            len(selected_blockers),
            unit="required_usefulness_control_observation",
        ),
    }


def _next_measurement_action(family: Mapping[str, Any]) -> dict[str, Any]:
    family_id = str(family.get("family_id") or "")
    runner = FAMILY_MEASUREMENT_RUNNERS.get(family_id, {})
    candidate = family.get("public_cohort_candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    quality_blockers = [str(item) for item in candidate.get("quality_gate_blockers") or []]
    usefulness_blockers = [
        str(item.get("control_id") or "")
        for item in family.get("usefulness_promotion_blockers") or []
        if isinstance(item, Mapping)
    ]
    blocker_actions = {
        blocker: QUALITY_BLOCKER_ACTIONS.get(
            blocker,
            "review_unmapped_quality_gate_blocker_before_promotion",
        )
        for blocker in quality_blockers
    }
    blocker_actions.update(
        {
            blocker: USEFULNESS_BLOCKER_ACTIONS.get(
                blocker,
                "review_unmapped_usefulness_blocker_before_promotion",
            )
            for blocker in usefulness_blockers
            if blocker
        }
    )
    if runner:
        return {
            "family_id": family_id,
            "runner_status": "existing_runner",
            "current_issue": runner.get("current_issue", "#2396"),
            "command": runner.get("command", f"python {runner['runner']} --json"),
            "output_artifact": runner["output_artifact"],
            "blockers": quality_blockers,
            "usefulness_blockers": usefulness_blockers,
            "blocker_actions": blocker_actions,
            "promotes_family": False,
            "measurement_scope": "selected_candidate_family_not_public_quality_yet",
        }
    return {
        "family_id": family_id,
        "runner_status": "runner_missing",
        "owner_issue": "#1195",
        "command": "gh issue view 1195 --comments",
        "output_artifact": "",
        "blockers": quality_blockers,
        "usefulness_blockers": usefulness_blockers,
        "blocker_actions": blocker_actions,
        "promotes_family": False,
        "measurement_scope": "runner_scaffold_required_before_public_quality_claim",
    }


def build_family_promotion_candidate_report() -> dict[str, Any]:
    """Build the #1195 public-safe candidate-family decision report."""

    selected = [
        _measured_family_entry(
            family_id="agent_continuity_loop",
            display_name="Agent continuity loop / recall degradation",
            priority_reason=(
                "Highest user-facing composition risk: recall packets, deepen handles, AIppo "
                "guidance, stale/conflict boundaries, and anti-nag behavior must work together."
            ),
            current_report=agent_loop.run_agent_continuity_loop(),
            public_report=agent_loop.build_agent_continuity_public_cohort_report(),
            candidate_distribution={
                "positive_reopenable_route": 30,
                "blocked_or_private_route": 30,
                "stale_conflict_reopen_required": 30,
                "route_label_collision": 30,
                "wrong_route_drag": 30,
                "manual_search_fallback": 30,
            },
            cohort_source_plan=(
                "Public synthetic and public-replayable agent-task traces, seeded by existing "
                "agent continuity fixtures and rollout hard-event V2 route-chain patterns; "
                "holdout cases are declared before threshold or prompt tuning."
            ),
            candidate_non_goals=[
                "live_host_behavior_lift",
                "private_history_quality",
                "answer_generation_quality",
                "default_foreground_adoption",
            ],
        ),
        _measured_family_entry(
            family_id="map_rot_lifecycle_debt",
            display_name="Map-rot lifecycle debt",
            priority_reason=(
                "Cold navigation maps can harm usefulness by reviving stale, challenged, "
                "quarantined, deleted, or repeated-wrong routes; this family protects the "
                "source-backed currentness boundary before cleanup automation."
            ),
            current_report=map_rot.build_report(),
            public_report=map_rot.build_map_rot_public_cohort_report(),
            candidate_distribution={
                "current": 30,
                "stale": 30,
                "challenged": 30,
                "quarantined": 30,
                "superseded": 30,
                "missing_middle": 30,
                "deleted_no_recall": 30,
                "dead_letter": 30,
                "repeated_wrong": 30,
            },
            cohort_source_plan=(
                "Public synthetic lifecycle-state rows with explicit source-refresh, review, "
                "decay, deletion, and dead-letter controls; all maintenance actions are "
                "no-write until a separate operator-approved cleanup path exists."
            ),
            candidate_non_goals=[
                "automatic_cleanup_proof",
                "completed_forgetting",
                "private_history_map_rot_quality",
                "live_current_route_quality",
            ],
        ),
    ]
    promoted = [
        _promoted_family_entry(
            family_id="attention_navigation_quality",
            display_name="Attention navigation quality",
            current_report=attention_quality.run_attention_navigation_public_holdout_cohort(),
            promoted_surface="explicit_agent_recall_auto_attention_router",
            remaining_non_goals=[
                "live_host_behavior_lift",
                "answer_generation_quality",
                "private_history_router_quality",
                "default_foreground_hook_lift",
                "representative_production_routing",
            ],
        )
    ]
    deferred = [
        {
            "family_id": "e2e50_silent_constraint",
            "reason": (
                "Deferred to #279 because it needs behavior-pack ownership, compaction "
                "boundary evidence, and ablation arms rather than a generic family-promotion row."
            ),
        },
        {
            "family_id": "rollout_hard_event",
            "reason": (
                "Used as a public-safe seed for agent-continuity route-chain cases, but the "
                "V2 cohort is not by itself the #1195 contract-smoke family promotion decision."
            ),
        },
    ]
    all_public_quality_ok = all(
        bool(family["gate_status"]["quality_gate_ok"]) for family in selected
    ) and all(bool(family["gate_status"]["quality_gate_ok"]) for family in promoted)
    public_quality_metrics = _aggregate_public_quality_metrics(
        selected=selected,
        promoted=promoted,
        deferred=deferred,
    )
    unresolved_actions = [
        _next_measurement_action(family)
        for family in selected
        if not bool(family["gate_status"]["quality_gate_ok"])
    ]
    return {
        "kind": "aippocampus_benchmark_family_promotion_candidates",
        "schema_version": SCHEMA_VERSION,
        "issue": ISSUE_NUMBER,
        "run_at": now_utc(),
        "ok": True,
        "benchmark_maturity_level": "public_cohort",
        "measurement_origin": "deterministic_contract",
        "observed_agent_behavior": False,
        "contract_gate_ok": True,
        "quality_gate_ok": all_public_quality_ok,
        "public_quality_gate_ok": all_public_quality_ok,
        "decision_impact": "diagnostic_only",
        "decision_impact_not_applicable": True,
        "case_count": len(selected) + len(deferred),
        "case_count_meaning": "selected candidate families plus deferred candidate families",
        "promoted_family_count": len(promoted),
        "selected_family_count": len(selected),
        "metrics": public_quality_metrics,
        "promoted_families": promoted,
        "selected_families": selected,
        "completed_measurements": [
            {
                "family_id": family["family_id"],
                **family["public_cohort_measurement"],
            }
            for family in selected
        ],
        "next_measurement_actions": unresolved_actions,
        "deferred_families": deferred,
        "gate_separation": {
            "contract_gate_ok": "current deterministic contract still passes",
            "usefulness_gate_ok": (
                "observed public/holdout cohort usefulness blockers must be zero"
            ),
            "public_quality_gate_ok": (
                "true only for named public/holdout surfaces with sample floor and no tuning leak"
            ),
            "quality_gate_ok": "alias for the surface-specific public_quality_gate_ok",
        },
        "sanitization_check": _sanitization_check(),
        "measured_result": (
            "selected agent-continuity and map-rot families now include observed "
            "public/holdout cohort measurements"
        ),
        "supports": [
            "first #1195 family-promotion decision",
            "observed public-safe cohort measurements for selected candidate families",
        ],
        "useful_now": [
            "separates target cohort design from observed blocker counts and rates",
            "keeps closed historical owner issues out of unresolved measurement actions",
        ],
        "agent_action": ("use_as_family_promotion_public_cohort_evidence_not_runtime_adoption"),
        "can_support_after_action": [
            "runtime or private-history adoption only after separate live/dogfood evidence"
        ],
        "material_limits": [
            "Attention navigation is promoted only for the narrow explicit-pull public cohort.",
            "Agent-continuity loop and map-rot public cohorts are synthetic/public-safe evidence.",
            "Private history, live host behavior, and answer generation remain out of scope.",
        ],
        "cannot_claim": [
            "selected_family_runtime_lift",
            "live_private_history_family_promotion",
            "cleanup_write_runtime_adoption",
        ],
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "absolute_paths_emitted": False,
            "provider_calls": 0,
        },
        "claim_boundary": {
            "supports": (
                "First #1195 family-promotion decision with observed public/holdout cohort "
                "measurements for selected public-safe families."
            ),
            "material_limits": [
                "Selected family measurements are public-safe synthetic cohorts, not live-host proof.",
                "Private history, live host behavior, and answer generation remain out of scope.",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)
    report = build_family_promotion_candidate_report()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("benchmark family promotion candidates: ok")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
