#!/usr/bin/env python3
"""Deterministic public-safe fresh-thread recall demo benchmark.

This runner wraps the runtime #285 demo fixtures in the repository benchmark
envelope. It is intentionally deterministic and synthetic: it proves the
fresh-thread scent/action/activation/source-reopen contract shape, not
real-history recall quality or a leaderboard claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall import fresh_thread_demo

SCHEMA_VERSION = 1


def _quality_gates(report: dict[str, Any]) -> dict[str, Any]:
    audit = report.get("audit") or fresh_thread_demo.validate_fresh_thread_demo_report(report)
    metrics = report.get("metrics") or {}
    gates = {
        "privacy_safe": audit.get("privacy_failure_count") == 0,
        "no_unsupported_evidence": audit.get("unsupported_evidence_count") == 0,
        "negative_controls_pass": audit.get("negative_control_active_recall_count") == 0,
        "positive_flows_present": metrics.get("positive_flow_count") == 4,
        "negative_controls_present": metrics.get("negative_control_count") == 4,
        "three_arms_present": set(report.get("arms") or []) == set(fresh_thread_demo.DEMO_ARMS),
    }
    return {
        **gates,
        "ok": all(gates.values()),
        "audit": audit,
    }


def run_benchmark(
    *,
    flow_ids: Sequence[str] | None = None,
    arms: Sequence[str] | None = None,
) -> dict[str, Any]:
    report = fresh_thread_demo.run_fresh_thread_demo(flow_ids=flow_ids, arms=arms)
    gates = _quality_gates(report)
    return {
        "kind": "aippocampus_fresh_thread_recall_demo_benchmark",
        "schema_version": SCHEMA_VERSION,
        "ok": gates["ok"],
        "status": "passed" if gates["ok"] else "failed",
        "config": {
            "flows": list(flow_ids or []),
            "arms": list(arms or fresh_thread_demo.DEMO_ARMS),
            "uses_live_model": False,
            "uses_private_history": False,
        },
        "metrics": report["metrics"],
        "quality_gates": gates,
        "privacy_boundary": {
            "public_safe_synthetic_fixtures": True,
            "public_cue_text_in_report": True,
            "private_raw_prompt_text_in_report": False,
            "raw_source_snippets_in_report": False,
            "absolute_paths_in_report": False,
        },
        "cannot_claim": [
            "real-history fresh-thread recall quality",
            "live semantic-model quality",
            "competitor or leaderboard superiority",
            "private family or emotional-memory coverage",
        ],
        "demo_report": report,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", action="append", dest="flows")
    parser.add_argument("--arm", action="append", dest="arms", choices=fresh_thread_demo.DEMO_ARMS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", help="Optional path for the JSON report.")
    args = parser.parse_args(argv)

    payload = run_benchmark(flow_ids=args.flows, arms=args.arms)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output or args.output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"flows: {payload['metrics']['flow_count']}")
        print(f"quality gates ok: {payload['quality_gates']['ok']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
