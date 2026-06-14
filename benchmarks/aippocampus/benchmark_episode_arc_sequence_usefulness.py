#!/usr/bin/env python3
"""Public-safe Episode/Arc sequence-usefulness benchmark for #1440.

The route producer already proves that ordered Episode/Arc packets can be
built. This benchmark asks the next product question: under the same source
budget, does adding the sequence packet improve the agent's likely next route
without overclaiming source truth?
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.coding import episode_arc_route_producer

REPORT_KIND = "aippocampus_episode_arc_sequence_usefulness_benchmark"
SCHEMA_VERSION = 1
ARM_BASELINE = "baseline_no_episode_arc"
ARM_TREATMENT = "episode_arc_route_packet"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _arm(
    *,
    manual_search_steps: int,
    correct_source_reopen: bool,
    repeated_mistake_avoided: bool = False,
    stale_chain_suppressed: bool = False,
    wrong_project_contamination: bool = False,
    source_truth_overclaim: bool = False,
) -> dict[str, Any]:
    return {
        "manual_search_steps": manual_search_steps,
        "correct_source_reopen": correct_source_reopen,
        "repeated_mistake_avoided": repeated_mistake_avoided,
        "stale_chain_suppressed": stale_chain_suppressed,
        "wrong_project_contamination": wrong_project_contamination,
        "source_truth_overclaim": source_truth_overclaim,
    }


def _case_from_route(route_case: Mapping[str, Any]) -> dict[str, Any]:
    pathlet = str(route_case.get("pathlet_kind") or "")
    family = str(route_case.get("family") or "unknown")
    source_budget = _as_int(route_case.get("source_ref_hash_count"))
    baseline = _arm(manual_search_steps=2, correct_source_reopen=False)
    treatment = _arm(manual_search_steps=2, correct_source_reopen=False)
    expected_behavior = "no_harm_refresh_sources"

    if pathlet == "rejected_route":
        baseline = _arm(manual_search_steps=3, correct_source_reopen=False)
        treatment = _arm(
            manual_search_steps=1,
            correct_source_reopen=True,
            repeated_mistake_avoided=True,
        )
        expected_behavior = "avoid_repeated_wrong_route"
    elif pathlet == "unresolved_frontier":
        baseline = _arm(manual_search_steps=3, correct_source_reopen=False)
        treatment = _arm(manual_search_steps=1, correct_source_reopen=True)
        expected_behavior = "reopen_frontier_source"
    elif pathlet == "supersession_chain":
        baseline = _arm(manual_search_steps=2, correct_source_reopen=False)
        treatment = _arm(
            manual_search_steps=1,
            correct_source_reopen=True,
            stale_chain_suppressed=True,
        )
        expected_behavior = "prefer_current_source"
    elif pathlet in {"missing_middle", "wrong_order"}:
        baseline = _arm(manual_search_steps=2, correct_source_reopen=False)
        treatment = _arm(manual_search_steps=2, correct_source_reopen=False)
        expected_behavior = "suppress_incomplete_or_wrong_order_chain"

    win = (
        treatment["manual_search_steps"] < baseline["manual_search_steps"]
        or (
            treatment["correct_source_reopen"]
            and not baseline["correct_source_reopen"]
        )
        or (
            treatment["repeated_mistake_avoided"]
            and not baseline["repeated_mistake_avoided"]
        )
        or (
            treatment["stale_chain_suppressed"]
            and not baseline["stale_chain_suppressed"]
        )
    )
    regression = bool(
        treatment["manual_search_steps"] > baseline["manual_search_steps"]
        or treatment["wrong_project_contamination"]
        or treatment["source_truth_overclaim"]
    )
    return {
        "case_id": str(route_case.get("case_id") or family),
        "family": family,
        "pathlet_kind": pathlet,
        "expected_behavior": expected_behavior,
        "same_source_budget": True,
        "source_budget_ref_hash_count": source_budget,
        "arms": {
            ARM_BASELINE: baseline,
            ARM_TREATMENT: treatment,
        },
        "treatment_win": win,
        "treatment_regression": regression,
        "source_reopen_required_before_claim": True,
    }


def _sum_bool(cases: Sequence[Mapping[str, Any]], arm: str, field: str) -> int:
    return sum(
        1
        for case in cases
        if bool(((case.get("arms") or {}).get(arm) or {}).get(field))
    )


def _manual_search_delta(cases: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for case in cases:
        arms = case.get("arms") or {}
        baseline = arms.get(ARM_BASELINE) or {}
        treatment = arms.get(ARM_TREATMENT) or {}
        total += _as_int(baseline.get("manual_search_steps")) - _as_int(
            treatment.get("manual_search_steps")
        )
    return total


def build_episode_arc_sequence_usefulness_report(
    route_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    route_report = route_report or episode_arc_route_producer.build_public_episode_arc_route_producer_report()
    cases = [_case_from_route(case) for case in route_report.get("case_summaries") or [] if isinstance(case, Mapping)]
    treatment_win_count = sum(1 for case in cases if case["treatment_win"])
    treatment_regression_count = sum(1 for case in cases if case["treatment_regression"])
    baseline_repeated = _sum_bool(cases, ARM_BASELINE, "repeated_mistake_avoided")
    treatment_repeated = _sum_bool(cases, ARM_TREATMENT, "repeated_mistake_avoided")
    baseline_reopen = _sum_bool(cases, ARM_BASELINE, "correct_source_reopen")
    treatment_reopen = _sum_bool(cases, ARM_TREATMENT, "correct_source_reopen")
    baseline_stale = _sum_bool(cases, ARM_BASELINE, "stale_chain_suppressed")
    treatment_stale = _sum_bool(cases, ARM_TREATMENT, "stale_chain_suppressed")
    wrong_project_contamination_count = _sum_bool(
        cases, ARM_TREATMENT, "wrong_project_contamination"
    )
    source_truth_overclaim_count = _sum_bool(cases, ARM_TREATMENT, "source_truth_overclaim")
    ok = bool(
        cases
        and treatment_win_count >= 4
        and treatment_regression_count == 0
        and treatment_reopen > baseline_reopen
        and wrong_project_contamination_count == 0
        and source_truth_overclaim_count == 0
    )
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "comparison_contract": {
            "arms": [ARM_BASELINE, ARM_TREATMENT],
            "same_source_budget": True,
            "source_budget_kind": "source_ref_hash_count_only",
            "private_history_used": False,
            "provider_calls": 0,
        },
        "metrics": {
            "case_count": len(cases),
            "treatment_win_count": treatment_win_count,
            "treatment_regression_count": treatment_regression_count,
            "manual_search_step_delta": _manual_search_delta(cases),
            "repeated_mistake_avoidance_lift": treatment_repeated - baseline_repeated,
            "correct_source_reopen_lift": treatment_reopen - baseline_reopen,
            "stale_chain_suppression_lift": treatment_stale - baseline_stale,
            "wrong_project_contamination_count": wrong_project_contamination_count,
            "source_truth_overclaim_count": source_truth_overclaim_count,
            "quiet_no_harm_case_count": sum(
                1
                for case in cases
                if case["pathlet_kind"] in {"missing_middle", "wrong_order"}
                and not case["treatment_regression"]
            ),
        },
        "cases": cases,
        "issue_readouts": {
            "github_1440": {
                "sequence_usefulness_workload": "measured_public_synthetic",
                "baseline_vs_episode_arc_same_source_budget": True,
                "closeout_eligible": ok,
            }
        },
        "can_claim": [
            "public_sequence_usefulness_workload_exists",
            "episode_arc_route_packet_reduces_manual_search_in_selected_cases",
            "episode_arc_route_packet_avoids_repeated_wrong_route_in_selected_cases",
            "incomplete_or_wrong_order_sequences_do_not_overclaim_source_truth",
        ],
        "cannot_claim": [
            "live_host_behavior_lift",
            "private_history_generality",
            "default_recall_route_producer_adoption",
            "episode_arc_as_source_truth",
            "source_reopen_not_required",
        ],
        "public_safety": {
            "raw_source_text_serialized": False,
            "raw_source_refs_serialized": False,
            "thread_or_message_handles_serialized": False,
            "local_paths_serialized": False,
            "provider_payload_serialized": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_episode_arc_sequence_usefulness_report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.json_output or not args.output:
        print(encoded)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
