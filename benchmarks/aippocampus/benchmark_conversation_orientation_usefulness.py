#!/usr/bin/env python3
"""Conversation orientation usefulness gate for safe-but-useless failures."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1


def fixture_conversation_orientation_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "ordinary_emotional_project_reentry",
            "risk": "low",
            "strict": {"useful_orientation": False, "caveat_items": 5, "source_open_pressure": 3},
            "compact": {"useful_orientation": True, "unknown": True, "source_overclaim": False, "caveat_items": 1},
            "static_summary": {"useful_orientation": True, "unknown": False, "source_overclaim": False},
            "task_orientation": {"useful_orientation": True, "unknown": True, "source_overclaim": False},
        },
        {
            "case_id": "stale_preference_requires_currentness_check",
            "risk": "currentness",
            "strict": {"useful_orientation": True, "caveat_items": 4, "source_open_pressure": 2},
            "compact": {"useful_orientation": True, "unknown": True, "source_overclaim": False, "caveat_items": 1},
            "static_summary": {"useful_orientation": True, "unknown": False, "source_overclaim": True},
            "task_orientation": {"useful_orientation": True, "unknown": True, "source_overclaim": False},
        },
        {
            "case_id": "high_risk_code_change_requires_reopen",
            "risk": "high",
            "strict": {"useful_orientation": True, "caveat_items": 3, "source_open_pressure": 1},
            "compact": {"useful_orientation": True, "unknown": True, "source_overclaim": False, "must_reopen": True, "caveat_items": 1},
            "static_summary": {"useful_orientation": True, "unknown": False, "source_overclaim": True},
            "task_orientation": {"useful_orientation": True, "unknown": True, "source_overclaim": False, "must_reopen": True},
        },
    ]


def evaluate_conversation_orientation_usefulness(
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    for case in cases or fixture_conversation_orientation_cases():
        arms = {
            "strict_source_backed": dict(case.get("strict") or {}),
            "compact_working_orientation": dict(case.get("compact") or {}),
            "static_summary": dict(case.get("static_summary") or {}),
            "task_orientation_packet": dict(case.get("task_orientation") or {}),
        }
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "risk": str(case.get("risk") or "unknown"),
                "arms": arms,
                "strict_safe_but_useless": bool(
                    not arms["strict_source_backed"].get("useful_orientation")
                    or arms["strict_source_backed"].get("caveat_items", 0) > 4
                    or arms["strict_source_backed"].get("source_open_pressure", 0) > 2
                ),
                "compact_pass": bool(
                    arms["compact_working_orientation"].get("useful_orientation")
                    and arms["compact_working_orientation"].get("unknown")
                    and not arms["compact_working_orientation"].get("source_overclaim")
                    and arms["compact_working_orientation"].get("caveat_items", 0) <= 2
                ),
            }
        )
    metrics = {
        "case_count": len(rows),
        "first_useful_orientation_rate": _rate(
            sum(1 for row in rows if row["compact_pass"]),
            len(rows),
        ),
        "strict_safe_but_useless_count": sum(1 for row in rows if row["strict_safe_but_useless"]),
        "load_bearing_unknown_surfaced_rate": _rate(
            sum(
                1
                for row in rows
                if row["arms"]["compact_working_orientation"].get("unknown")
            ),
            len(rows),
        ),
        "source_truth_overclaim_count": sum(
            1
            for row in rows
            if row["arms"]["compact_working_orientation"].get("source_overclaim")
        ),
        "caveat_field_bloat_count": sum(
            1
            for row in rows
            if row["arms"]["compact_working_orientation"].get("caveat_items", 0) > 2
        ),
        "raw_private_text_leak_count": 0,
    }
    ok = (
        metrics["first_useful_orientation_rate"]["rate"] == 1.0
        and metrics["source_truth_overclaim_count"] == 0
        and metrics["raw_private_text_leak_count"] == 0
    )
    return {
        "kind": "aippocampus_conversation_orientation_usefulness_gate",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "quality_gate_ok": ok,
        "private_history_replay": {
            "available": False,
            "aggregate_only_contract": True,
            "raw_private_text_emitted": False,
        },
        "rows": rows,
        "metrics": metrics,
        "claim_boundary": {
            "fixture_slice_only": True,
            "working_orientation_is_not_source_truth": True,
            "high_risk_cases_require_reopen": True,
        },
        "cannot_claim": [
            "broad_live_conversation_quality",
            "private_history_quality_lift_without_opt_in_replay",
            "working_orientation_as_source_truth",
        ],
    }


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = evaluate_conversation_orientation_usefulness()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"conversation orientation usefulness gate: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
