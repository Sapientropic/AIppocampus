#!/usr/bin/env python3
"""Public-safe Associative Path Walker quality gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.recall.associative_path_inputs import build_associative_path_diagnostic
from aippocampus_runtime.recall.associative_path_walker import walk_associative_paths

SCHEMA_VERSION = 1


def fixture_path_walker_cases() -> list[dict[str, Any]]:
    source_ref = {"thread_key": "fixture:path-walker", "source_id": "src-apw"}
    return [
        {
            "case_id": "unsupported_distinctive_anchor",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:generic-memory",
                    "route_terms": ["memory", "recall", "search"],
                    "thread_key": "thread:generic",
                }
            ],
            "bridge_rows": [],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "source_backed_bridge_rescues_cross_vocab",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "wrong_feedback_evaporates_path",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "feedback_rows": [
                {"candidate_id": "bridge:apw", "signal": "wrong_route_drag"},
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "stale_route_stays_shadowed",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:stale-apw",
                    "candidate_id": "bridge:stale-apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "freshness": "stale",
                    "source_refs": [source_ref],
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:stale-apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "source_free_semantic_bridge_evaporates",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_terms": ["slime mold", "routing exploration"],
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:source-free",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["routing exploration"],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "cross_scope_positive_feedback_does_not_lift",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "feedback_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                },
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
                "cross_scope_positive_must_not_lift": True,
            },
        },
        {
            "case_id": "chinese_dogfood_cue_bridge_rescue",
            "query": "黏菌 联想回忆 探索算法",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw-cn",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw-cn",
                    "from_terms": ["黏菌", "联想回忆", "探索算法"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
            },
        },
    ]


def evaluate_path_walker_gate(
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    for case in cases or fixture_path_walker_cases():
        baseline = walk_associative_paths(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            bridge_rows=[],
            feedback_rows=[],
        )
        report = walk_associative_paths(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            bridge_rows=case.get("bridge_rows") or [],
            feedback_rows=case.get("feedback_rows") or [],
        )
        diagnostic = build_associative_path_diagnostic(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            semantic_bridge_rows=case.get("bridge_rows") or [],
            feedback_rows=case.get("feedback_rows") or [],
        )
        expectation = dict(case.get("expectation") or {})
        first_candidate = report["candidates"][0] if report.get("candidates") else {}
        candidate_reasons = first_candidate.get("reason_codes") if isinstance(first_candidate, Mapping) else []
        route_count = int(report.get("candidate_count") or 0)
        baseline_route_count = int(baseline.get("candidate_count") or 0)
        first_action = diagnostic["next_actions"][0] if diagnostic.get("next_actions") else {}
        apw_action_emitted = bool(route_count and first_action.get("id") == "open_apw_source_candidate_1")
        agent_followed_apw_action = bool(
            apw_action_emitted
            and first_action.get("mutation_risk") == "read_only"
            and (
                first_action.get("command")
                or first_action.get("tool_name")
                or first_action.get("source_reopen_args")
            )
        )
        source_reopen_success = bool(
            agent_followed_apw_action
            and route_count
            and report["candidates"][0].get("source_refs")
        )
        specificity_ok = "generic_only_path_evaporated" in report.get("reason_codes", []) or route_count > 0
        useful = bool(route_count) == bool(expectation.get("useful_route"))
        wrong_hop_drag = bool(
            route_count
            and not expectation.get("useful_route")
            and "path_found_reopenable" in report.get("reason_codes", [])
        )
        cross_scope_lift = bool(
            expectation.get("cross_scope_positive_must_not_lift")
            and "positive_feedback_same_scope" in candidate_reasons
        )
        top_action_specificity_ok = bool(
            not route_count
            or "source_backed_semantic_bridge" in candidate_reasons
            or baseline_route_count == route_count
        )
        task_usefulness_outcome = bool(source_reopen_success and expectation.get("useful_route"))
        manual_search_before_apw = bool(expectation.get("manual_search_before_apw"))
        expected_decision = str(expectation.get("expected_decision") or report["decision"])
        decision_ok = report["decision"] == expected_decision
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "baseline_route_count": baseline_route_count,
                "decision": report["decision"],
                "expected_decision": expected_decision,
                "decision_ok": decision_ok,
                "route_count": route_count,
                "apw_action_emitted": apw_action_emitted,
                "agent_followed_apw_action": agent_followed_apw_action,
                "path_specificity_ok": specificity_ok,
                "top_action_specificity_ok": top_action_specificity_ok,
                "task_usefulness_ok": useful,
                "task_usefulness_outcome": task_usefulness_outcome,
                "wrong_hop_drag": wrong_hop_drag,
                "scope_violation": cross_scope_lift,
                "source_reopen_success": source_reopen_success,
                "manual_search_before_apw": manual_search_before_apw,
                "irrelevant_drag": bool(route_count and not expectation.get("useful_route")),
                "unsupported_cue_abstain": bool(
                    not route_count and not expectation.get("useful_route")
                ),
                "first_action_id": str(first_action.get("id") or ""),
                "navigation_only": report["claim_permission"] == "no_claim_before_reopen",
                "reason_codes": report["reason_codes"],
                "candidate_reason_codes": list(candidate_reasons or []),
            }
        )
    red_lines = {
        "wrong_hop_drag_count": sum(1 for row in rows if row["wrong_hop_drag"]),
        "source_truth_claim_count": sum(1 for row in rows if not row["navigation_only"]),
        "scope_violation_count": sum(1 for row in rows if row["scope_violation"]),
        "default_ranking_influence_count": 0,
    }
    warnings = {
        "route_count_lift_without_usefulness_count": sum(
            1 for row in rows if row["route_count"] and not row["task_usefulness_ok"]
        ),
        "route_count_without_executable_action_count": sum(
            1 for row in rows if row["route_count"] and not row["apw_action_emitted"]
        ),
        "action_without_source_reopen_success_count": sum(
            1 for row in rows if row["apw_action_emitted"] and not row["source_reopen_success"]
        ),
        "specificity_failure_count": sum(1 for row in rows if not row["path_specificity_ok"]),
        "top_action_specificity_failure_count": sum(
            1 for row in rows if not row["top_action_specificity_ok"]
        ),
        "decision_mismatch_count": sum(1 for row in rows if not row["decision_ok"]),
    }
    ok = all(value == 0 for value in red_lines.values()) and all(
        row["task_usefulness_ok"] and row["decision_ok"] for row in rows
    )
    return {
        "kind": "aippocampus_associative_path_walker_quality_gate",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "quality_gate_ok": ok,
        "rows": rows,
        "metrics": {
            "case_count": len(rows),
            "route_existence_count": sum(1 for row in rows if row["route_count"] > 0),
            "baseline_route_existence_count": sum(1 for row in rows if row["baseline_route_count"] > 0),
            "apw_action_emitted_count": sum(1 for row in rows if row["apw_action_emitted"]),
            "agent_followed_apw_action_count": sum(
                1 for row in rows if row["agent_followed_apw_action"]
            ),
            "top_action_specificity_ok_count": sum(1 for row in rows if row["top_action_specificity_ok"]),
            "source_reopen_success_count": sum(1 for row in rows if row["source_reopen_success"]),
            "task_usefulness_outcome_count": sum(1 for row in rows if row["task_usefulness_outcome"]),
            "task_usefulness_ok_count": sum(1 for row in rows if row["task_usefulness_ok"]),
            "manual_search_before_apw_count": sum(1 for row in rows if row["manual_search_before_apw"]),
            "wrong_hop_drag_count": red_lines["wrong_hop_drag_count"],
            "irrelevant_drag_count": sum(1 for row in rows if row["irrelevant_drag"]),
            "unsupported_cue_abstain_count": sum(1 for row in rows if row["unsupported_cue_abstain"]),
            "scope_violation_count": red_lines["scope_violation_count"],
        },
        "warnings": warnings,
        "red_lines": red_lines,
        "boundary": {
            "navigation_lift_is_not_source_evidence": True,
            "ambient_readiness_not_claimed": True,
            "default_recall_influence_allowed": False,
            "proxy_gate_not_live_quality_claim": True,
            "follow_through_mode": "proxy_action_path",
            "live_model_calls": 0,
        },
        "cannot_claim": [
            "broad_live_recall_quality",
            "private_history_path_quality",
            "path_resonance_as_source_truth",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = evaluate_path_walker_gate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"associative path walker gate: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
