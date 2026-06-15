#!/usr/bin/env python3
"""Public-safe state-dependent preactivation benchmark.

This benchmark evaluates whether phase/frontier/cache state can prepare route
handles more selectively than a simple warm ambient baseline. It is intentionally
no-write and navigation-only: predicted routes are handles to reopen later, not
memory truth and not foreground reminders.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.warm_ambient.prewarm_planner import prewarm_planner_report

PREACTIVATION_BENCHMARK_KIND = "aippocampus_state_dependent_preactivation_benchmark"
PREACTIVATION_BENCHMARK_SCHEMA_VERSION = 1
CLI_SUCCESS_PAYLOAD: dict[str, object] = {
    "kind": "aippocampus_state_dependent_preactivation_cli_summary",
    "ok": True,
    "status": "sufficient",
}
CLI_FAILURE_PAYLOAD: dict[str, object] = {
    "kind": "aippocampus_state_dependent_preactivation_cli_summary",
    "ok": False,
    "status": "failed",
}

PREACTIVATION_PHASES = {"debugging_loop", "implementation", "review", "handoff"}
UNSAFE_FRESHNESS = {"stale", "expired", "superseded", "unknown", "conflicted", "refuted", "uncertain"}


@dataclass(frozen=True)
class PreactivationCase:
    case_id: str
    phase_context: str
    frontier_marker: str
    salience_score: float
    ambient_cache_state: str
    active_recall_lock: bool
    candidates: tuple[dict[str, Any], ...]


def _case_signals(case: PreactivationCase) -> dict[str, Any]:
    return {
        "phase_context": case.phase_context,
        "frontier_marker": case.frontier_marker,
        "salience_score": case.salience_score,
        "ambient_cache_state": case.ambient_cache_state,
        "active_recall_lock": case.active_recall_lock,
    }


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items: Iterable[Any] = (value,)
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = ()
    return tuple(str(item or "").strip() for item in items if str(item or "").strip())


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("domain_id") or candidate.get("route_id") or "")


def _route_is_intrinsically_unsafe(candidate: Mapping[str, Any]) -> bool:
    freshness = str(candidate.get("freshness") or "unknown").strip().casefold()
    privacy = str(candidate.get("privacy_state") or candidate.get("privacy") or "").strip().casefold()
    return (
        freshness in UNSAFE_FRESHNESS
        or privacy in {"blocked", "restricted", "partition_blocked"}
        or bool(candidate.get("privacy_blocked") or candidate.get("blocked_by_privacy"))
    )


def _state_allows_candidate(case: PreactivationCase, candidate: Mapping[str, Any]) -> bool:
    if _route_is_intrinsically_unsafe(candidate):
        return False
    phase = case.phase_context.strip().casefold()
    candidate_phases = {item.casefold() for item in _as_tuple(candidate.get("phase_contexts"))}
    frontier_markers = {item.casefold() for item in _as_tuple(candidate.get("frontier_markers"))}
    route_handles = {item.casefold() for item in _as_tuple(candidate.get("route_handles"))}
    frontier = case.frontier_marker.strip().casefold()

    if frontier and frontier in frontier_markers:
        return True
    if phase in PREACTIVATION_PHASES and (not candidate_phases or phase in candidate_phases):
        return True
    if case.active_recall_lock and bool(candidate.get("lock_compatible")):
        return True
    if (
        case.ambient_cache_state in {"miss", "weak"}
        and case.salience_score >= 0.75
        and (frontier in route_handles or phase in candidate_phases)
    ):
        return True
    return False


def _state_gated_candidates(case: PreactivationCase) -> list[dict[str, Any]]:
    gated: list[dict[str, Any]] = []
    for candidate in case.candidates:
        row = dict(candidate)
        if not _state_allows_candidate(case, row):
            # Keep a suppressed diagnostic row instead of dropping the candidate:
            # state-dependent preactivation needs to show quiet failure modes,
            # not make unsafe or off-state routes disappear from evaluation.
            row["expected_value"] = min(float(row.get("expected_value") or 0.0), 0.0)
            row["state_gate"] = "suppressed_by_phase_frontier_state"
        else:
            row["state_gate"] = "accepted_by_phase_frontier_state"
        gated.append(row)
    return gated


def _planner_rows(
    *,
    arm: str,
    case: PreactivationCase,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    planner = prewarm_planner_report(candidates, now_unix=1_780_000_000.0)
    rows: list[dict[str, Any]] = []
    for candidate, row in zip(candidates, planner.get("predicted_domains") or [], strict=False):
        expected_prepare = bool(candidate.get("expected_prepare"))
        unsafe = bool(candidate.get("expected_foreground_suppressed")) or _route_is_intrinsically_unsafe(candidate)
        rows.append(
            {
                **row,
                "candidate_id": _candidate_id(candidate),
                "expected_prepare": expected_prepare,
                "expected_foreground_suppressed": unsafe or not expected_prepare,
                "state_gate": candidate.get("state_gate") or "baseline_no_state_gate",
            }
        )
    metrics = _arm_metrics(rows)
    return {
        "arm": arm,
        "planner_kind": planner.get("kind"),
        "predicted_domains": rows,
        "metrics": metrics,
    }


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _arm_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected = [row for row in rows if row.get("expected_prepare")]
    negatives = [row for row in rows if not row.get("expected_prepare")]
    prepared = [row for row in rows if row.get("status") == "ready"]
    hits = [row for row in prepared if row.get("expected_prepare")]
    false_prepared = [row for row in prepared if not row.get("expected_prepare")]
    noise_candidates = [row for row in rows if row.get("expected_foreground_suppressed")]
    noise_suppressed = [row for row in noise_candidates if row.get("status") != "ready"]
    source_reopen_success = [
        row
        for row in hits
        if int(row.get("source_ref_count") or 0) > 0 and row.get("source_reopen_path")
    ]
    ready_count = len(prepared)
    candidate_count = len(rows)
    return {
        "candidate_count": candidate_count,
        "prepared_count": ready_count,
        "expected_prepare_count": len(expected),
        "hit_count": len(hits),
        "false_preactivation_count": len(false_prepared),
        "foreground_noise_candidate_count": len(noise_candidates),
        "foreground_noise_suppressed_count": len(noise_suppressed),
        "source_reopen_success_count": len(source_reopen_success),
        "preactivation_hit_rate": _rate(len(hits), len(expected)),
        "false_preactivation_rate": _rate(len(false_prepared), len(negatives)),
        "source_reopen_success_rate": _rate(len(source_reopen_success), len(expected)),
        "foreground_noise_suppression_rate": _rate(len(noise_suppressed), len(noise_candidates)),
        "latency_cost_proxy": {
            "model_call_count": 0,
            "candidate_scan_count": candidate_count,
            "source_reopen_attempt_cost_units": ready_count,
            "local_state_gate_cost_units": candidate_count,
            "estimated_total_cost_units": candidate_count + ready_count * 3,
        },
        "action_grammar_violation_count": sum(
            1
            for row in rows
            if row.get("action_grammar")
            not in {"direction_only", "direction_with_ref", "reopenable_route"}
        ),
        "source_open_without_reopen_count": sum(
            1 for row in rows if row.get("action_grammar") == "source_open"
        ),
    }


def _combine_metrics(arms: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        row
        for arm in arms
        for row in arm.get("predicted_domains") or []
        if isinstance(row, Mapping)
    ]
    return _arm_metrics(rows)


def builtin_cases() -> tuple[PreactivationCase, ...]:
    return (
        PreactivationCase(
            case_id="debugging_frontier_prepares_route",
            phase_context="debugging_loop",
            frontier_marker="db-timeout",
            salience_score=0.92,
            ambient_cache_state="weak",
            active_recall_lock=False,
            candidates=(
                {
                    "candidate_id": "timeout-route",
                    "domain_id": "timeout-route",
                    "title": "Timeout debug route",
                    "owner_surface": "frontier_marker",
                    "freshness": "current",
                    "created_unix": 1_779_999_900,
                    "ttl_seconds": 900,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "phase_contexts": ["debugging_loop"],
                    "frontier_markers": ["db-timeout"],
                    "route_handles": ["db-timeout"],
                    "expected_prepare": True,
                    "source_refs": [{"source_id": "clean:debug-route", "message_id": "m-debug"}],
                },
                {
                    "candidate_id": "review-doc-route",
                    "domain_id": "review-doc-route",
                    "title": "Review-only doc route",
                    "owner_surface": "theme_candidate",
                    "freshness": "current",
                    "created_unix": 1_779_999_900,
                    "ttl_seconds": 900,
                    "expected_value": 4,
                    "estimated_cost": 1,
                    "phase_contexts": ["review"],
                    "frontier_markers": ["doc-boundary"],
                    "expected_prepare": False,
                    "source_refs": [{"source_id": "clean:review-route", "message_id": "m-review"}],
                },
            ),
        ),
        PreactivationCase(
            case_id="planning_without_frontier_stays_silent",
            phase_context="planning",
            frontier_marker="",
            salience_score=0.35,
            ambient_cache_state="warm",
            active_recall_lock=False,
            candidates=(
                {
                    "candidate_id": "generic-plan-route",
                    "domain_id": "generic-plan-route",
                    "title": "Generic planning route",
                    "owner_surface": "warm_ambient",
                    "freshness": "current",
                    "created_unix": 1_779_999_920,
                    "ttl_seconds": 900,
                    "expected_value": 4,
                    "estimated_cost": 1,
                    "phase_contexts": ["implementation"],
                    "expected_prepare": False,
                    "source_refs": [{"source_id": "clean:generic-plan", "message_id": "m-plan"}],
                },
            ),
        ),
        PreactivationCase(
            case_id="handoff_lock_enriches_route",
            phase_context="handoff",
            frontier_marker="",
            salience_score=0.81,
            ambient_cache_state="weak",
            active_recall_lock=True,
            candidates=(
                {
                    "candidate_id": "handoff-route",
                    "domain_id": "handoff-route",
                    "title": "Handoff active lock route",
                    "owner_surface": "active_recall_lock",
                    "freshness": "current",
                    "created_unix": 1_779_999_950,
                    "ttl_seconds": 900,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "lock_compatible": True,
                    "phase_contexts": ["handoff"],
                    "expected_prepare": True,
                    "source_refs": [{"source_id": "clean:handoff", "message_id": "m-handoff"}],
                },
            ),
        ),
        PreactivationCase(
            case_id="unsafe_candidates_suppressed",
            phase_context="implementation",
            frontier_marker="risk-frontier",
            salience_score=0.9,
            ambient_cache_state="miss",
            active_recall_lock=True,
            candidates=(
                {
                    "candidate_id": "stale-route",
                    "domain_id": "stale-route",
                    "title": "Stale route",
                    "owner_surface": "dream",
                    "freshness": "stale",
                    "created_unix": 1_779_999_000,
                    "ttl_seconds": 600,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "expected_prepare": False,
                    "expected_foreground_suppressed": True,
                    "source_refs": [{"source_id": "clean:stale", "message_id": "m-stale"}],
                },
                {
                    "candidate_id": "restricted-route",
                    "domain_id": "restricted-route",
                    "title": "Restricted route",
                    "owner_surface": "warm_ambient",
                    "freshness": "current",
                    "created_unix": 1_779_999_970,
                    "ttl_seconds": 900,
                    "privacy_state": "blocked",
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "expected_prepare": False,
                    "expected_foreground_suppressed": True,
                    "source_refs": [
                        {
                            "source_id": "clean:restricted",
                            "message_id": "m-restricted",
                        }
                    ],
                },
                {
                    "candidate_id": "conflicted-route",
                    "domain_id": "conflicted-route",
                    "title": "Conflicted route",
                    "owner_surface": "retrieval_reconsolidation",
                    "freshness": "conflicted",
                    "created_unix": 1_779_999_970,
                    "ttl_seconds": 900,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "expected_prepare": False,
                    "expected_foreground_suppressed": True,
                    "source_refs": [{"source_id": "clean:conflict", "message_id": "m-conflict"}],
                },
            ),
        ),
    )


def _case_report(case: PreactivationCase) -> dict[str, Any]:
    baseline_candidates = [dict(candidate) for candidate in case.candidates]
    state_candidates = _state_gated_candidates(case)
    baseline = _planner_rows(
        arm="simple_warm_baseline",
        case=case,
        candidates=baseline_candidates,
    )
    stateful = _planner_rows(
        arm="state_dependent",
        case=case,
        candidates=state_candidates,
    )
    return {
        "case_id": case.case_id,
        "signals": _case_signals(case),
        "arms": {
            "simple_warm_baseline": baseline,
            "state_dependent": stateful,
        },
    }


def run_state_dependent_preactivation_benchmark(
    cases: Iterable[PreactivationCase] | None = None,
) -> dict[str, Any]:
    selected_cases = tuple(cases or builtin_cases())
    case_reports = [_case_report(case) for case in selected_cases]
    baseline_arms = [
        case["arms"]["simple_warm_baseline"]
        for case in case_reports
        if isinstance(case.get("arms"), Mapping)
    ]
    stateful_arms = [
        case["arms"]["state_dependent"]
        for case in case_reports
        if isinstance(case.get("arms"), Mapping)
    ]
    baseline_metrics = _combine_metrics(baseline_arms)
    stateful_metrics = _combine_metrics(stateful_arms)
    comparison = {
        "state_dependent_hit_rate_delta": round(
            stateful_metrics["preactivation_hit_rate"] - baseline_metrics["preactivation_hit_rate"],
            4,
        ),
        "state_dependent_false_preactivation_delta": round(
            stateful_metrics["false_preactivation_rate"] - baseline_metrics["false_preactivation_rate"],
            4,
        ),
        "state_dependent_source_reopen_cost_delta": (
            stateful_metrics["latency_cost_proxy"]["source_reopen_attempt_cost_units"]
            - baseline_metrics["latency_cost_proxy"]["source_reopen_attempt_cost_units"]
        ),
        "state_dependent_estimated_total_cost_delta": (
            stateful_metrics["latency_cost_proxy"]["estimated_total_cost_units"]
            - baseline_metrics["latency_cost_proxy"]["estimated_total_cost_units"]
        ),
    }
    quality_gates = {
        "passed": (
            stateful_metrics["preactivation_hit_rate"] >= 1.0
            and stateful_metrics["false_preactivation_rate"] == 0.0
            and stateful_metrics["source_reopen_success_rate"] >= 1.0
            and stateful_metrics["foreground_noise_suppression_rate"] >= 1.0
            and stateful_metrics["action_grammar_violation_count"] == 0
            and stateful_metrics["source_open_without_reopen_count"] == 0
        ),
        "thresholds": {
            "min_state_dependent_hit_rate": 1.0,
            "max_state_dependent_false_preactivation_rate": 0.0,
            "min_source_reopen_success_rate": 1.0,
            "min_foreground_noise_suppression_rate": 1.0,
            "max_action_grammar_violation_count": 0,
        },
    }
    quality_gates["failed"] = [
        gate_name
        for gate_name, failed in (
            ("preactivation_hit_rate", stateful_metrics["preactivation_hit_rate"] < 1.0),
            ("false_preactivation_rate", stateful_metrics["false_preactivation_rate"] != 0.0),
            ("source_reopen_success_rate", stateful_metrics["source_reopen_success_rate"] < 1.0),
            (
                "foreground_noise_suppression_rate",
                stateful_metrics["foreground_noise_suppression_rate"] < 1.0,
            ),
            (
                "action_grammar_violation_count",
                stateful_metrics["action_grammar_violation_count"] != 0,
            ),
            (
                "source_open_without_reopen_count",
                stateful_metrics["source_open_without_reopen_count"] != 0,
            ),
        )
        if failed
    ]
    return {
        "kind": PREACTIVATION_BENCHMARK_KIND,
        "schema_version": PREACTIVATION_BENCHMARK_SCHEMA_VERSION,
        "ok": bool(selected_cases) and bool(quality_gates["passed"]),
        "contract_gate_ok": bool(selected_cases) and bool(quality_gates["passed"]),
        "quality_gate_ok": False,
        "public_quality_gate_ok": False,
        "benchmark_maturity_level": "contract_smoke",
        "quality_gate_kind": "fixture_contract_not_public_quality",
        "status": "sufficient" if selected_cases and quality_gates["passed"] else "insufficient",
        "case_count": len(selected_cases),
        "sample_size": len(selected_cases),
        "metrics": {
            "simple_warm_baseline": baseline_metrics,
            "state_dependent": stateful_metrics,
        },
        "comparison": comparison,
        "quality_gates": quality_gates,
        "cases": case_reports,
        "privacy_boundary": {
            "input_text_leak_emitted": False,
            "source_text_leak_emitted": False,
            "local_paths_emitted": False,
            "unredacted_literal_emitted": False,
            "foreground_user_visible_reminder_emitted": False,
        },
        "contract": {
            "no_write_report_only": True,
            "navigation_only": True,
            "foreground_hook_waits_for_model": False,
            "predicted_routes_are_memory_truth": False,
            "source_reopen_required_before_claim": True,
            "source_open_action_grammar_allowed_without_reopen": False,
        },
        "can_claim": [
            "state_dependent_preactivation_fixture_exists",
            "state_dependent_arm_compared_with_simple_warm_baseline",
            "stale_privacy_conflicted_routes_are_suppressed_in_fixture",
            "preactivation_metrics_are_reported_separately",
        ],
        "cannot_claim": [
            "preactivation_route_is_memory_truth",
            "live_foreground_preactivation_is_enabled",
            "adhd_productivity_lift_is_proven",
            "live_latency_savings_are_proven",
            "general_proactive_agent_behavior_is_validated",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", help="Optional sanitized full-report JSON path.")
    args = parser.parse_args()
    payload = run_state_dependent_preactivation_benchmark()
    passed = payload.get("ok") is True
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    if args.json_output:
        sys.stdout.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    else:
        sys.stdout.write(
            "state-dependent preactivation benchmark: "
            f"status={'sufficient' if passed else 'failed'}"
            "\n"
        )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
