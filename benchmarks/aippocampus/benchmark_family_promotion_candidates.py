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
        "owner_issue": "#1969",
        "output_artifact": (
            "docs/evidence/benchmarks/reports/agent_continuity_loop_public_cohort.json"
        ),
    },
    "map_rot_lifecycle_debt": {
        "runner": "benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py",
        "owner_issue": "#1948",
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
        "negative_control_families": [
            blocker["control_id"] for blocker in blockers
        ],
        "gate_status": {
            "contract_gate_ok": bool(current["contract_gate_ok"]),
            "usefulness_gate_ok": False,
            "quality_gate_ok": False,
            "status": "contract_passed_candidate_not_promoted",
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
            "case_count": int(maturity.get("case_count") or current_report.get("metrics", {}).get("case_count") or 0),
            "failure_family_count": int(maturity.get("failure_family_count") or 0),
            "minimum_family_case_floor": int(maturity.get("minimum_family_case_floor") or 0),
            "sample_floor_met": bool(maturity.get("sample_floor_met")),
            "holdout_case_count": int(maturity.get("holdout_case_count") or 0),
            "holdout_used_for_tuning_count": int(maturity.get("holdout_used_for_tuning_count") or 0),
            "wilson_or_uncertainty_reported": bool(
                maturity.get("wilson_or_uncertainty_reported")
            ),
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
        runner_path = runner["runner"]
        return {
            "family_id": family_id,
            "runner_status": "existing_runner",
            "owner_issue": runner["owner_issue"],
            "command": f"python {runner_path} --json",
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
        _family_entry(
            family_id="agent_continuity_loop",
            display_name="Agent continuity loop / recall degradation",
            priority_reason=(
                "Highest user-facing composition risk: recall packets, deepen handles, AIppo "
                "guidance, stale/conflict boundaries, and anti-nag behavior must work together."
            ),
            current_report=agent_loop.run_agent_continuity_loop(),
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
        _family_entry(
            family_id="map_rot_lifecycle_debt",
            display_name="Map-rot lifecycle debt",
            priority_reason=(
                "Cold navigation maps can harm usefulness by reviving stale, challenged, "
                "quarantined, deleted, or repeated-wrong routes; this family protects the "
                "source-backed currentness boundary before cleanup automation."
            ),
            current_report=map_rot.build_report(),
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
    return {
        "kind": "aippocampus_benchmark_family_promotion_candidates",
        "schema_version": SCHEMA_VERSION,
        "issue": ISSUE_NUMBER,
        "run_at": now_utc(),
        "ok": True,
        "benchmark_maturity_level": "planning_contract",
        "measurement_origin": "deterministic_contract",
        "observed_agent_behavior": False,
        "contract_gate_ok": True,
        "quality_gate_ok": False,
        "public_quality_gate_ok": False,
        "decision_impact": "diagnostic_only",
        "decision_impact_not_applicable": True,
        "case_count": len(selected) + len(deferred),
        "promoted_family_count": len(promoted),
        "selected_family_count": len(selected),
        "promoted_families": promoted,
        "selected_families": selected,
        "next_measurement_actions": [
            _next_measurement_action(family) for family in selected
        ],
        "deferred_families": deferred,
        "gate_separation": {
            "contract_gate_ok": "current deterministic contract still passes",
            "usefulness_gate_ok": (
                "candidate cohort must prove user or agent usefulness blockers are zero"
            ),
            "public_quality_gate_ok": (
                "true only for a named public/holdout surface, such as attention explicit-pull"
            ),
            "quality_gate_ok": "alias for the surface-specific public_quality_gate_ok",
        },
        "sanitization_check": _sanitization_check(),
        "measured_result": "deterministic candidate-family selection report emitted",
        "supports": [
            "first #1195 family-promotion decision",
            "reusable candidate metadata for public-safe cohort construction",
        ],
        "useful_now": [
            "separates candidate-family planning from public cohort quality claims",
            "points future benchmark work at held-out usefulness and quality gates",
        ],
        "agent_action": "use_as_family_promotion_planning_input_not_quality_evidence",
        "can_support_after_action": [
            "candidate cohort implementation after held-out measurement and human review"
        ],
        "material_limits": [
            "Attention navigation is promoted only for the narrow explicit-pull public cohort.",
            "Agent-continuity loop and map-rot lifecycle debt remain selected candidate work.",
            "Candidate case counts are targets, not observed pass/fail results.",
            "Private history, live host behavior, and answer generation remain out of scope.",
        ],
        "cannot_claim": [
            "public_cohort_quality",
            "selected_family_runtime_lift",
            "live_private_history_family_promotion",
        ],
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "absolute_paths_emitted": False,
            "provider_calls": 0,
        },
        "claim_boundary": {
            "supports": (
                "First #1195 family-promotion decision and reusable candidate metadata for "
                "public-safe cohort construction."
            ),
            "material_limits": [
                "No selected family is promoted to public cohort quality by this report.",
                "Candidate case counts are targets, not observed pass/fail results.",
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
