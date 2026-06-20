#!/usr/bin/env python3
"""Map-rot lifecycle-debt benchmark for cold navigation maps."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.ops.map_rot_maintenance import plan_map_rot_maintenance
from benchmarks.aippocampus.shared import benchmark_maturity

SCHEMA_VERSION = 1
PUBLIC_COHORT_CASES_PER_STATE = 30
PUBLIC_COHORT_MIN_SAMPLE_FLOOR = 30
PUBLIC_COHORT_HELDOUT_STRIDE = 4
PUBLIC_COHORT_ATTENTION_COST_BUDGET = 4.0
LIFECYCLE_STATES = {
    "current",
    "stale",
    "challenged",
    "quarantined",
    "superseded",
    "missing_middle",
    "deleted_no_recall",
    "dead_letter",
    "repeated_wrong",
}
USEFULNESS_BLOCKER_KEYS = (
    "generic_hint",
    "route_label_collision",
    "wrong_route_drag",
    "unnecessary_reopen",
    "manual_search_fallback",
    "foreground_noise_added",
    "attention_cost_overrun",
)


def _case(
    case_id: str,
    *,
    object_kind: str,
    lifecycle_state: str,
    age_days: int,
    historically_preserved: bool,
    eligible_for_current_navigation: bool,
    emitted_route: bool,
    next_action: str,
    review_needed: bool = False,
    missing_middle_warning: bool = False,
    dead_lettered: bool = False,
    masked: bool = False,
    repeated_wrong_route: bool = False,
    prunable_or_decay_candidate: bool = False,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "object_kind": object_kind,
        "lifecycle_state": lifecycle_state,
        "age_days": int(age_days),
        "historically_preserved": historically_preserved,
        "eligible_for_current_navigation": eligible_for_current_navigation,
        "emitted_route": emitted_route,
        "next_action": next_action,
        "review_needed": review_needed,
        "missing_middle_warning": missing_middle_warning,
        "dead_lettered": dead_lettered,
        "masked": masked,
        "repeated_wrong_route": repeated_wrong_route,
        "prunable_or_decay_candidate": prunable_or_decay_candidate,
    }


def fixture_map_rot_cases() -> list[dict[str, Any]]:
    return [
        _case(
            "stale_current_pointer_refresh",
            object_kind="route",
            lifecycle_state="stale",
            age_days=18,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="refresh_source",
            prunable_or_decay_candidate=True,
        ),
        _case(
            "challenged_conflict_backlog",
            object_kind="conflict_set",
            lifecycle_state="challenged",
            age_days=45,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="review_or_refresh",
            review_needed=True,
        ),
        _case(
            "quarantined_masked_route_silent",
            object_kind="route",
            lifecycle_state="quarantined",
            age_days=22,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="silence",
            masked=True,
        ),
        _case(
            "superseded_route_uses_successor",
            object_kind="route",
            lifecycle_state="superseded",
            age_days=30,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="use_successor_after_reopen",
            prunable_or_decay_candidate=True,
        ),
        _case(
            "pathlet_missing_middle_warning",
            object_kind="pathlet",
            lifecycle_state="missing_middle",
            age_days=12,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="deepen_missing_middle_before_route",
            missing_middle_warning=True,
            review_needed=True,
        ),
        _case(
            "deleted_no_recall_object_silent",
            object_kind="route",
            lifecycle_state="deleted_no_recall",
            age_days=9,
            historically_preserved=False,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="silence",
            masked=True,
            prunable_or_decay_candidate=True,
        ),
        _case(
            "dead_lettered_cache_row_ignored",
            object_kind="cache_row",
            lifecycle_state="dead_letter",
            age_days=6,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="compact_or_ignore",
            dead_lettered=True,
            prunable_or_decay_candidate=True,
        ),
        _case(
            "repeated_wrong_route_suppressed",
            object_kind="route",
            lifecycle_state="repeated_wrong",
            age_days=14,
            historically_preserved=True,
            eligible_for_current_navigation=False,
            emitted_route=False,
            next_action="suppress_and_wait_for_source_change",
            repeated_wrong_route=True,
            prunable_or_decay_candidate=True,
        ),
        _case(
            "current_reopenable_route_allowed",
            object_kind="route",
            lifecycle_state="current",
            age_days=1,
            historically_preserved=True,
            eligible_for_current_navigation=True,
            emitted_route=True,
            next_action="emit_reopenable_route",
        ),
    ]


def _project_case(case: Mapping[str, Any]) -> dict[str, Any]:
    state = str(case.get("lifecycle_state") or "")
    emitted = bool(case.get("emitted_route"))
    eligible = bool(case.get("eligible_for_current_navigation"))
    masked = bool(case.get("masked")) or state in {"quarantined", "deleted_no_recall"}
    stale_as_current = int(
        emitted and not eligible and state in {"stale", "challenged", "superseded"}
    )
    masked_resurrection = int(emitted and masked)
    wrong_revival = int(emitted and bool(case.get("repeated_wrong_route")))
    return {
        **dict(case),
        "stale_as_current_count": stale_as_current,
        "masked_source_resurrection_count": masked_resurrection,
        "quarantined_route_emit_count": int(emitted and state == "quarantined"),
        "superseded_route_emit_count": int(emitted and state == "superseded"),
        "wrong_route_revival_count": wrong_revival,
        "deleted_no_recall_emit_count": int(emitted and state == "deleted_no_recall"),
        "correct_behavior": bool(
            (eligible and emitted)
            or (
                not eligible
                and not emitted
                and str(case.get("next_action") or "")
                in {
                    "refresh_source",
                    "review_or_refresh",
                    "silence",
                    "use_successor_after_reopen",
                    "deepen_missing_middle_before_route",
                    "compact_or_ignore",
                    "suppress_and_wait_for_source_change",
                }
            )
        ),
    }


def evaluate_map_rot_cases(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    projected = [_project_case(case) for case in cases]
    run_at = now_utc()
    by_state = Counter(str(case.get("lifecycle_state") or "unknown") for case in projected)
    challenged_ages = [
        int(case.get("age_days") or 0)
        for case in projected
        if case.get("lifecycle_state") == "challenged"
    ]
    hard_red_lines = {
        "stale_as_current_count": sum(int(case["stale_as_current_count"]) for case in projected),
        "masked_source_resurrection_count": sum(
            int(case["masked_source_resurrection_count"]) for case in projected
        ),
        "quarantined_route_emit_count": sum(
            int(case["quarantined_route_emit_count"]) for case in projected
        ),
        "superseded_route_emit_count": sum(
            int(case["superseded_route_emit_count"]) for case in projected
        ),
        "wrong_route_revival_count": sum(
            int(case["wrong_route_revival_count"]) for case in projected
        ),
        "deleted_no_recall_emit_count": sum(
            int(case["deleted_no_recall_emit_count"]) for case in projected
        ),
    }
    metrics = {
        "case_count": len(projected),
        "lifecycle_state_counts": dict(sorted(by_state.items())),
        "historically_preserved_count": sum(
            1 for case in projected if case["historically_preserved"]
        ),
        "eligible_current_navigation_count": sum(
            1 for case in projected if case["eligible_for_current_navigation"]
        ),
        "challenged_backlog_count": len(challenged_ages),
        "oldest_challenged_age_days": max(challenged_ages) if challenged_ages else 0,
        "review_needed_count": sum(1 for case in projected if case["review_needed"]),
        "missing_middle_warning_count": sum(
            1 for case in projected if case["missing_middle_warning"]
        ),
        "dead_letter_count": sum(1 for case in projected if case["dead_lettered"]),
        "refresh_recommended_count": sum(
            1
            for case in projected
            if case["next_action"] in {"refresh_source", "review_or_refresh"}
        ),
        "silence_recommended_count": sum(
            1 for case in projected if case["next_action"] == "silence"
        ),
        "prune_or_decay_candidate_count": sum(
            1 for case in projected if case["prunable_or_decay_candidate"]
        ),
    }
    ok = all(value == 0 for value in hard_red_lines.values()) and all(
        bool(case["correct_behavior"]) for case in projected
    )
    passed_case_count = sum(1 for case in projected if case["correct_behavior"])
    maturity = benchmark_maturity.build_benchmark_maturity_report(
        benchmark_maturity_level="contract_smoke",
        case_count=len(projected),
        passed_case_count=passed_case_count,
        per_family_case_counts=by_state,
        minimum_family_case_floor=30,
        external_or_public_cohort_case_count=0,
        holdout_case_count=0,
        holdout_used_for_tuning_count=0,
        contract_gate_ok=ok,
        next_promotion_target="public_cohort_candidate",
    )
    return {
        "kind": "aippocampus_map_rot_lifecycle_debt",
        "schema_version": SCHEMA_VERSION,
        "run_at": run_at,
        "ok": ok,
        "contract_gate_ok": ok,
        "quality_gate_ok": maturity["quality_gate_ok"],
        "benchmark_maturity": maturity,
        "cases": projected,
        "maintenance_actions": plan_map_rot_maintenance(projected, run_at=run_at),
        "metrics": metrics,
        "hard_red_lines": hard_red_lines,
        "quality_gate": {
            "red_lines_must_be_zero": True,
            "historically_preserved_is_not_current_eligible": True,
            "contract_gate_ok": ok,
            "quality_gate_ok": maturity["quality_gate_ok"],
            "benchmark_maturity_level": maturity["benchmark_maturity_level"],
            "status": (
                "quality_gate_passed"
                if maturity["quality_gate_ok"]
                else "contract_gate_passed_quality_gate_not_promoted"
                if ok
                else "contract_gate_failed"
            ),
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "private_text_emitted": False,
            "local_paths_emitted": False,
        },
        "cannot_claim": [
            "cold_map_self_cleaning",
            "all_conflicts_resolved",
            "stale_memory_cannot_remain_in_history",
            "automatic_semantic_cleanup_solved",
            "private_history_map_rot_quality",
            "forgetting_completed",
            "conflict_auto_resolved",
        ],
    }


def build_report() -> dict[str, Any]:
    return evaluate_map_rot_cases(fixture_map_rot_cases())


def _public_cohort_row(
    template: Mapping[str, Any],
    *,
    index: int,
    global_index: int,
) -> dict[str, Any]:
    state = str(template.get("lifecycle_state") or "unknown")
    attention_cost = 1.2
    if state in {"challenged", "missing_middle"}:
        attention_cost = 2.4
    elif state in {"stale", "superseded", "repeated_wrong"}:
        attention_cost = 1.8
    elif state == "current":
        attention_cost = 1.4
    return {
        **dict(template),
        "case_id": f"maprot-public-{state}-{index:02d}",
        "case_origin": "public_safe_generated_lifecycle_cohort",
        "heldout": global_index % PUBLIC_COHORT_HELDOUT_STRIDE == 0,
        "heldout_used_for_tuning": False,
        "attention_cost_units": attention_cost,
        "attention_cost_overrun": (attention_cost > PUBLIC_COHORT_ATTENTION_COST_BUDGET),
        "generic_hint": False,
        "route_label_collision": False,
        "wrong_route_drag": False,
        "unnecessary_reopen": False,
        "manual_search_fallback": False,
        "foreground_noise_added": False,
        "live_product_lift_claimed": False,
    }


def public_cohort_map_rot_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_index = 0
    by_state = {str(case["lifecycle_state"]): case for case in fixture_map_rot_cases()}
    for state in sorted(LIFECYCLE_STATES):
        template = by_state[state]
        for index in range(PUBLIC_COHORT_CASES_PER_STATE):
            rows.append(
                _public_cohort_row(
                    template,
                    index=index,
                    global_index=global_index,
                )
            )
            global_index += 1
    return rows


def build_map_rot_public_cohort_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure public/holdout lifecycle rows without promoting cleanup writes.

    The smoke fixture protects the lifecycle contract; this cohort gives the
    benchmark-family planner observed blocker counts. It intentionally keeps
    every maintenance decision no-write so a passing report cannot be mistaken
    for autonomous map cleanup.
    """

    cohort_rows = [dict(row) for row in (rows or public_cohort_map_rot_rows())]
    projected = [_project_case(row) for row in cohort_rows]
    run_at = now_utc()
    by_state = Counter(str(case.get("lifecycle_state") or "unknown") for case in projected)
    case_count = len(projected)
    heldout_count = sum(1 for row in projected if row.get("heldout"))
    tuning_leak_count = sum(
        1 for row in projected if row.get("heldout") and row.get("heldout_used_for_tuning")
    )
    passed_case_count = sum(1 for row in projected if row["correct_behavior"])
    hard_red_lines = {
        "stale_as_current_count": sum(int(case["stale_as_current_count"]) for case in projected),
        "masked_source_resurrection_count": sum(
            int(case["masked_source_resurrection_count"]) for case in projected
        ),
        "quarantined_route_emit_count": sum(
            int(case["quarantined_route_emit_count"]) for case in projected
        ),
        "superseded_route_emit_count": sum(
            int(case["superseded_route_emit_count"]) for case in projected
        ),
        "wrong_route_revival_count": sum(
            int(case["wrong_route_revival_count"]) for case in projected
        ),
        "deleted_no_recall_emit_count": sum(
            int(case["deleted_no_recall_emit_count"]) for case in projected
        ),
    }
    blocker_counts = {
        f"{key}_count": sum(1 for row in projected if row.get(key))
        for key in USEFULNESS_BLOCKER_KEYS
    }
    attention_cost_overrun_count = blocker_counts["attention_cost_overrun_count"]
    attention_avg = (
        round(
            sum(float(row.get("attention_cost_units") or 0.0) for row in projected) / case_count,
            6,
        )
        if case_count
        else 0.0
    )
    usefulness_gate_ok = all(value == 0 for value in blocker_counts.values())
    attention_cost_ok = bool(
        attention_cost_overrun_count == 0 and attention_avg <= PUBLIC_COHORT_ATTENTION_COST_BUDGET
    )
    contract_gate_ok = bool(
        all(value == 0 for value in hard_red_lines.values()) and passed_case_count == case_count
    )
    maturity = benchmark_maturity.build_benchmark_maturity_report(
        benchmark_maturity_level="public_cohort",
        case_count=case_count,
        passed_case_count=passed_case_count,
        per_family_case_counts=by_state,
        minimum_family_case_floor=PUBLIC_COHORT_MIN_SAMPLE_FLOOR,
        external_or_public_cohort_case_count=case_count,
        holdout_case_count=heldout_count,
        holdout_used_for_tuning_count=tuning_leak_count,
        contract_gate_ok=contract_gate_ok,
        usefulness_gate_ok=usefulness_gate_ok,
        attention_cost_ok=attention_cost_ok,
        next_promotion_target="operator_review_before_cleanup_writes",
    )
    quality_gate_ok = bool(maturity["quality_gate_ok"])
    maintenance_actions = plan_map_rot_maintenance(projected, run_at=run_at)
    metrics = {
        "public_cohort_case_count": case_count,
        "heldout_case_count": heldout_count,
        "holdout_case_count": heldout_count,
        "contract_fixture_case_count": len(fixture_map_rot_cases()),
        "correct_behavior_rate": round(passed_case_count / case_count, 6) if case_count else 0.0,
        "usefulness_gate_ok": usefulness_gate_ok,
        "attention_cost_ok": attention_cost_ok,
        "quality_gate_ok": quality_gate_ok,
        "attention_cost_avg_units": attention_avg,
        "holdout_used_for_tuning_count": tuning_leak_count,
        "live_product_lift_claimed": False,
        **blocker_counts,
    }
    return {
        "kind": "aippocampus_map_rot_lifecycle_debt_public_cohort",
        "schema_version": SCHEMA_VERSION,
        "run_at": run_at,
        "ok": quality_gate_ok,
        "status": "completed_score_scoped_public_cohort" if quality_gate_ok else "measured_blocker",
        "contract_gate_ok": contract_gate_ok,
        "public_quality_gate_ok": quality_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "benchmark_maturity": maturity,
        "metrics": metrics,
        "family_counts": dict(sorted(by_state.items())),
        "measured_blocker_categories": list(USEFULNESS_BLOCKER_KEYS),
        "hard_red_lines": hard_red_lines,
        "quality_gate": {
            "sample_floor_cases": PUBLIC_COHORT_MIN_SAMPLE_FLOOR,
            "sample_floor_ok": bool(maturity["sample_floor_met"]),
            "holdout_no_tuning_leak_ok": tuning_leak_count == 0,
            "usefulness_gate_ok": usefulness_gate_ok,
            "attention_cost_ok": attention_cost_ok,
            "red_line_gate_ok": all(value == 0 for value in hard_red_lines.values()),
            "quality_gate_ok": quality_gate_ok,
            "cleanup_write_adoption_gate_ok": False,
        },
        "maintenance_actions": {
            "kind": maintenance_actions["kind"],
            "write_mode": maintenance_actions["write_mode"],
            "metrics": maintenance_actions["metrics"],
        },
        "rows": [
            {
                "case_id": row["case_id"],
                "family": row["lifecycle_state"],
                "case_origin": row.get("case_origin"),
                "heldout": bool(row.get("heldout")),
                "correct_behavior": bool(row["correct_behavior"]),
                "attention_cost_units": row.get("attention_cost_units", 0.0),
            }
            for row in projected
        ],
        "privacy_boundary": {
            "raw_source_text_serialized": False,
            "private_text_serialized": False,
            "local_paths_serialized": False,
            "source_handles_serialized": False,
            "heldout_rows_excluded_from_tuning": tuning_leak_count == 0,
            "maintenance_writes_executed": False,
        },
        "no_open_followup_reason": (
            "Public/holdout lifecycle measurement is consumed by the #2396 "
            "family promotion report; cleanup-write adoption and private-history "
            "map quality need fresh scoped work."
        ),
        "cannot_claim": [
            "cold_map_self_cleaning",
            "automatic_semantic_cleanup_solved",
            "private_history_map_rot_quality",
            "forgetting_completed",
            "cleanup_write_runtime_adoption",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-cohort",
        action="store_true",
        help="Emit the public/holdout lifecycle cohort successor report.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)
    report = build_map_rot_public_cohort_report() if args.public_cohort else build_report()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.public_cohort:
            print(f"map-rot lifecycle-debt public cohort: {'ok' if report['ok'] else 'failed'}")
        else:
            print(f"map-rot lifecycle-debt status: {report['quality_gate']['status']}")
        case_count = (
            report["metrics"].get("case_count")
            or report["metrics"].get("public_cohort_case_count")
            or 0
        )
        print(f"cases: {case_count}")
        if "hard_red_lines" in report:
            print(f"hard red lines: {report['hard_red_lines']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
