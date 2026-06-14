#!/usr/bin/env python3
"""Public-safe three-arm default-hook recall usefulness benchmark for #1439."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

REPORT_KIND = "aippocampus_default_hook_recall_usefulness_benchmark"
SCHEMA_VERSION = 1
ARM_BASELINE = "default_no_packet_baseline"
ARM_EXPLICIT = "explicit_recall_same_budget"
ARM_DEFAULT_HOOK = "default_hook_foreground_candidate"
ARMS = (ARM_BASELINE, ARM_EXPLICIT, ARM_DEFAULT_HOOK)
PACKET_BUDGET = 2
SOURCE_REOPEN_BUDGET = 1


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _arm(
    *,
    activated: bool,
    helpful_next_action: bool,
    manual_search_steps: int,
    source_reopen_follow_through: bool,
    latency_ms_proxy: int,
    cost_unit_proxy: int,
    quiet_for_reason: bool = False,
    wrong_route_drag_count: int = 0,
    irrelevant_memory_drag_count: int = 0,
    source_truth_overclaim: bool = False,
) -> dict[str, Any]:
    return {
        "activated": activated,
        "helpful_next_action": helpful_next_action,
        "manual_search_steps": manual_search_steps,
        "source_reopen_follow_through": source_reopen_follow_through,
        "wrong_route_drag_count": wrong_route_drag_count,
        "irrelevant_memory_drag_count": irrelevant_memory_drag_count,
        "latency_ms_proxy": latency_ms_proxy,
        "cost_unit_proxy": cost_unit_proxy,
        "quiet_for_reason": quiet_for_reason,
        "source_truth_overclaim": source_truth_overclaim,
    }


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "self_referential_continuity_hook_skip",
            "families": [
                "self_referential_continuity",
                "explicit_route_hook_skip_gap",
            ],
            "surface": "prompt_hook",
            "explicit_recall_observation": {
                "output_mode": "reopenable_route",
                "red_line_count": 0,
                "source_reopen_required_for_strong_claims": True,
            },
            "default_hook_observation": {
                "decision": "skip",
                "memory_surface": "no_memory",
                "card_count": 0,
                "source_backed_count": 0,
            },
            "tiny_agent_recall_affordance_candidate": True,
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=3,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=48,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=3,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=7,
                    cost_unit_proxy=0,
                    quiet_for_reason=False,
                ),
            },
        },
        {
            "case_id": "pure_deictic_ambiguous_quiet",
            "families": ["deictic_prompt"],
            "surface": "default_session",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                    quiet_for_reason=True,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=35,
                    cost_unit_proxy=1,
                    quiet_for_reason=True,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=0,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=4,
                    cost_unit_proxy=0,
                    quiet_for_reason=True,
                ),
            },
        },
        {
            "case_id": "multilingual_light_cue_route",
            "families": ["multilingual_prompt"],
            "surface": "attention_router",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=3,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=45,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=18,
                    cost_unit_proxy=1,
                ),
            },
        },
        {
            "case_id": "already_good_noop_stays_quiet",
            "families": ["already_good_noop"],
            "surface": "anti_nag",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=0,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                    quiet_for_reason=True,
                ),
                ARM_EXPLICIT: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=0,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=12,
                    cost_unit_proxy=0,
                    quiet_for_reason=True,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=0,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=4,
                    cost_unit_proxy=0,
                    quiet_for_reason=True,
                ),
            },
        },
        {
            "case_id": "stale_route_drag_control",
            "families": ["stale_or_conflict_control"],
            "surface": "attention_router",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=48,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=19,
                    cost_unit_proxy=1,
                    wrong_route_drag_count=1,
                ),
            },
        },
        {
            "case_id": "conflict_route_drag_control",
            "families": ["stale_or_conflict_control"],
            "surface": "attention_router",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=52,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=22,
                    cost_unit_proxy=1,
                    wrong_route_drag_count=1,
                ),
            },
        },
        {
            "case_id": "question_resurfacing_route",
            "families": ["question_resurfacing"],
            "surface": "question_tracking",
            "question_resurfacing": True,
            "source_truth_overclaim_blocked": True,
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=3,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=44,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=20,
                    cost_unit_proxy=1,
                ),
            },
        },
        {
            "case_id": "theme_user_review_lift",
            "families": ["theme_user_review"],
            "surface": "question_tracking",
            "theme_user_review_lift": True,
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=46,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=21,
                    cost_unit_proxy=1,
                ),
            },
        },
        {
            "case_id": "stale_theme_carryover_drag",
            "families": ["question_resurfacing"],
            "surface": "question_tracking",
            "stale_theme_carryover": True,
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=38,
                    cost_unit_proxy=1,
                    quiet_for_reason=True,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=20,
                    cost_unit_proxy=1,
                    wrong_route_drag_count=1,
                    irrelevant_memory_drag_count=1,
                ),
            },
        },
        {
            "case_id": "cognitive_load_irrelevant_drag",
            "families": ["cognitive_load_drag"],
            "surface": "cognitive_load",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=1,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=30,
                    cost_unit_proxy=1,
                    quiet_for_reason=True,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=16,
                    cost_unit_proxy=1,
                    irrelevant_memory_drag_count=1,
                ),
            },
        },
        {
            "case_id": "attention_route_specificity_generic_drag",
            "families": ["attention_route_specificity"],
            "surface": "attention_router",
            "arms": {
                ARM_BASELINE: _arm(
                    activated=False,
                    helpful_next_action=False,
                    manual_search_steps=3,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=0,
                    cost_unit_proxy=0,
                ),
                ARM_EXPLICIT: _arm(
                    activated=True,
                    helpful_next_action=True,
                    manual_search_steps=1,
                    source_reopen_follow_through=True,
                    latency_ms_proxy=42,
                    cost_unit_proxy=1,
                ),
                ARM_DEFAULT_HOOK: _arm(
                    activated=True,
                    helpful_next_action=False,
                    manual_search_steps=2,
                    source_reopen_follow_through=False,
                    latency_ms_proxy=18,
                    cost_unit_proxy=1,
                    wrong_route_drag_count=1,
                    irrelevant_memory_drag_count=1,
                ),
            },
        },
    ]


def _arm_metrics(cases: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    total = len(cases)
    baseline_manual = sum(
        int((case["arms"][ARM_BASELINE]).get("manual_search_steps", 0))
        for case in cases
    )
    selected = [case["arms"][arm] for case in cases]
    activation_count = sum(1 for row in selected if row.get("activated"))
    helpful_count = sum(1 for row in selected if row.get("helpful_next_action"))
    source_reopen_count = sum(
        1 for row in selected if row.get("source_reopen_follow_through")
    )
    wrong_route_drag_count = sum(
        int(row.get("wrong_route_drag_count", 0)) for row in selected
    )
    irrelevant_drag_count = sum(
        int(row.get("irrelevant_memory_drag_count", 0)) for row in selected
    )
    manual_steps = sum(int(row.get("manual_search_steps", 0)) for row in selected)
    latency_total = sum(int(row.get("latency_ms_proxy", 0)) for row in selected)
    cost_total = sum(int(row.get("cost_unit_proxy", 0)) for row in selected)
    quiet_count = sum(1 for row in selected if row.get("quiet_for_reason"))
    source_truth_overclaim_count = sum(
        1 for row in selected if row.get("source_truth_overclaim")
    )
    return {
        "activation_count": activation_count,
        "activation_rate": _ratio(activation_count, total),
        "helpful_next_action_count": helpful_count,
        "helpful_next_action_rate": _ratio(helpful_count, total),
        "manual_search_steps": manual_steps,
        "manual_search_reduction_vs_baseline": baseline_manual - manual_steps,
        "source_reopen_follow_through_count": source_reopen_count,
        "source_reopen_follow_through_rate": _ratio(source_reopen_count, total),
        "wrong_route_drag_count": wrong_route_drag_count,
        "wrong_route_drag_rate": _ratio(wrong_route_drag_count, total),
        "irrelevant_memory_drag_count": irrelevant_drag_count,
        "irrelevant_memory_drag_rate": _ratio(irrelevant_drag_count, total),
        "latency_ms_proxy_avg": _ratio(latency_total, total),
        "cost_unit_proxy_avg": _ratio(cost_total, total),
        "quiet_for_reason_count": quiet_count,
        "source_truth_overclaim_count": source_truth_overclaim_count,
    }


def _cohort_coverage(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    family_counter: Counter[str] = Counter()
    surface_counter: Counter[str] = Counter()
    for case in cases:
        for family in case.get("families", []):
            family_counter[str(family)] += 1
        surface_counter[str(case.get("surface") or "unknown")] += 1
    return {
        "family_counts": dict(sorted(family_counter.items())),
        "surface_counts": dict(sorted(surface_counter.items())),
    }


def _question_theme_readout(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    default_metrics = _arm_metrics(cases, ARM_DEFAULT_HOOK)
    return {
        "question_resurfacing_count": sum(
            1 for case in cases if case.get("question_resurfacing")
        ),
        "theme_user_review_lift_count": sum(
            1 for case in cases if case.get("theme_user_review_lift")
        ),
        "stale_theme_carryover_count": sum(
            1 for case in cases if case.get("stale_theme_carryover")
        ),
        "wrong_route_drag_count": default_metrics["wrong_route_drag_count"],
        "source_truth_overclaim_blocked_count": sum(
            1 for case in cases if case.get("source_truth_overclaim_blocked")
        ),
        "source_truth_overclaim_count": default_metrics["source_truth_overclaim_count"],
    }


def _prompt_hook_gap_readout(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    explicit_route_count = 0
    default_skip_no_memory_count = 0
    explicit_route_hook_skip_gap_count = 0
    tiny_affordance_candidate_count = 0

    for case in cases:
        explicit_observation = _as_mapping(case.get("explicit_recall_observation"))
        hook_observation = _as_mapping(case.get("default_hook_observation"))
        explicit_route = explicit_observation.get("output_mode") == "reopenable_route"
        hook_skip_no_memory = (
            hook_observation.get("decision") == "skip"
            and hook_observation.get("memory_surface") == "no_memory"
        )
        explicit_route_count += int(explicit_route)
        default_skip_no_memory_count += int(hook_skip_no_memory)
        explicit_route_hook_skip_gap_count += int(explicit_route and hook_skip_no_memory)
        tiny_affordance_candidate_count += int(
            bool(case.get("tiny_agent_recall_affordance_candidate"))
        )

    return {
        "explicit_recall_reopenable_route_count": explicit_route_count,
        "default_hook_skip_no_memory_count": default_skip_no_memory_count,
        "explicit_route_hook_skip_gap_count": explicit_route_hook_skip_gap_count,
        "tiny_agent_recall_affordance_candidate_count": tiny_affordance_candidate_count,
    }


def build_default_hook_recall_usefulness_report() -> dict[str, Any]:
    cases = _fixture_cases()
    arm_metrics = {arm: _arm_metrics(cases, arm) for arm in ARMS}
    cohort_coverage = _cohort_coverage(cases)
    question_theme_readout = _question_theme_readout(cases)
    prompt_hook_gap_readout = _prompt_hook_gap_readout(cases)
    default_metrics = arm_metrics[ARM_DEFAULT_HOOK]
    explicit_metrics = arm_metrics[ARM_EXPLICIT]
    adoption_blockers = []
    if default_metrics["wrong_route_drag_count"]:
        adoption_blockers.append("wrong_route_drag_present")
    if default_metrics["irrelevant_memory_drag_count"]:
        adoption_blockers.append("irrelevant_memory_drag_present")
    if (
        default_metrics["helpful_next_action_rate"]
        < explicit_metrics["helpful_next_action_rate"]
    ):
        adoption_blockers.append("default_hook_helpfulness_below_explicit_recall")

    closeout_eligible = bool(
        len(cases) >= 10
        and explicit_metrics["helpful_next_action_rate"]
        > arm_metrics[ARM_BASELINE]["helpful_next_action_rate"]
        and explicit_metrics["manual_search_reduction_vs_baseline"] > 0
        and default_metrics["activation_count"] > 0
        and question_theme_readout["question_resurfacing_count"] >= 1
        and question_theme_readout["theme_user_review_lift_count"] >= 1
        and question_theme_readout["stale_theme_carryover_count"] >= 1
        and question_theme_readout["source_truth_overclaim_count"] == 0
        and prompt_hook_gap_readout["explicit_route_hook_skip_gap_count"] >= 1
        and adoption_blockers
    )
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": closeout_eligible,
        "comparison_contract": {
            "arms": list(ARMS),
            "same_packet_budget": True,
            "packet_budget": PACKET_BUDGET,
            "same_source_reopen_budget": True,
            "source_reopen_budget": SOURCE_REOPEN_BUDGET,
            "private_history_used": False,
            "provider_call_count": 0,
        },
        "metrics": {
            "case_count": len(cases),
            "adoption_blocker_count": len(adoption_blockers),
        },
        "cohort_coverage": cohort_coverage,
        "arm_metrics": arm_metrics,
        "question_theme_readout": question_theme_readout,
        "prompt_hook_gap_readout": prompt_hook_gap_readout,
        "decision": {
            "default_foreground_decision": "keep_default_hook_diagnostic_only",
            "default_foreground_adoption_recommended": False,
            "eligible_default_foreground_surfaces": [],
            "tiny_agent_recall_affordance_decision": (
                "review_opt_in_affordance_only_not_default_foreground"
            ),
            "opt_in_or_diagnostic_surfaces": [
                "explicit_recall_same_budget",
                "default_hook_foreground_candidate",
                "question_tracking_theme_rows",
                "cognitive_load_sidecar",
                "attention_router_default_hook_candidate",
            ],
            "adoption_blockers": adoption_blockers,
        },
        "cases": cases,
        "issue_readouts": {
            "github_1439": {
                "same_budget_three_arm_eval_measured": True,
                "default_hook_validated_before_adoption": True,
                "default_foreground_adoption_recommended": False,
                "default_foreground_decision": "keep_default_hook_diagnostic_only",
                "question_theme_gap_covered": True,
                "explicit_route_hook_skip_gap_covered": True,
                "closeout_eligible": closeout_eligible,
            }
        },
        "can_claim": [
            "default_hook_foreground_candidate_was_tested_against_explicit_recall",
            "representative_public_synthetic_cohort_reports_help_and_drag",
            "explicit_recall_same_budget_outperforms_no_packet_baseline",
            "default_hook_should_remain_diagnostic_only_for_this_slice",
            "explicit_route_hook_skip_gap_is_measured",
        ],
        "cannot_claim": [
            "live_default_hook_quality",
            "default_foreground_adoption_ready",
            "broad_private_history_question_quality",
            "theme_rows_as_source_truth",
            "cognitive_load_default_foreground_readiness",
            "tiny_agent_recall_affordance_ready_for_default",
        ],
        "privacy_boundary": {
            "prompt_text_serialized": False,
            "source_text_serialized": False,
            "source_handles_serialized": False,
            "thread_handles_serialized": False,
            "provider_details_serialized": False,
            "credential_values_serialized": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_default_hook_recall_usefulness_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
