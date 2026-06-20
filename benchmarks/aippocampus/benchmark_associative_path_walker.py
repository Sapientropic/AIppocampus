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
    ]


def evaluate_path_walker_gate(
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    for case in cases or fixture_path_walker_cases():
        report = walk_associative_paths(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            bridge_rows=case.get("bridge_rows") or [],
            feedback_rows=case.get("feedback_rows") or [],
        )
        expectation = dict(case.get("expectation") or {})
        route_count = int(report.get("candidate_count") or 0)
        specificity_ok = "generic_only_path_evaporated" in report.get("reason_codes", []) or route_count > 0
        useful = bool(route_count) == bool(expectation.get("useful_route"))
        wrong_hop_drag = bool(
            route_count
            and not expectation.get("useful_route")
            and "path_found_reopenable" in report.get("reason_codes", [])
        )
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "decision": report["decision"],
                "route_count": route_count,
                "path_specificity_ok": specificity_ok,
                "task_usefulness_ok": useful,
                "wrong_hop_drag": wrong_hop_drag,
                "source_reopen_success": bool(route_count and report["candidates"][0].get("source_refs")),
                "navigation_only": report["claim_permission"] == "no_claim_before_reopen",
                "reason_codes": report["reason_codes"],
            }
        )
    red_lines = {
        "wrong_hop_drag_count": sum(1 for row in rows if row["wrong_hop_drag"]),
        "source_truth_claim_count": sum(1 for row in rows if not row["navigation_only"]),
    }
    warnings = {
        "route_count_lift_without_usefulness_count": sum(
            1 for row in rows if row["route_count"] and not row["task_usefulness_ok"]
        ),
        "specificity_failure_count": sum(1 for row in rows if not row["path_specificity_ok"]),
    }
    ok = all(value == 0 for value in red_lines.values()) and all(
        row["task_usefulness_ok"] for row in rows
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
            "source_reopen_success_count": sum(1 for row in rows if row["source_reopen_success"]),
            "task_usefulness_ok_count": sum(1 for row in rows if row["task_usefulness_ok"]),
            "wrong_hop_drag_count": red_lines["wrong_hop_drag_count"],
        },
        "warnings": warnings,
        "red_lines": red_lines,
        "boundary": {
            "navigation_lift_is_not_source_evidence": True,
            "ambient_readiness_not_claimed": True,
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
