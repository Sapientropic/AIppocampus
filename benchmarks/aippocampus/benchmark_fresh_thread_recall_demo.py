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
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall import fresh_thread_demo

SCHEMA_VERSION = 3

_PUBLIC_VALIDATION_CANNOT_CLAIM = [
    "live fresh-thread quality",
    "private real-history fresh-thread quality",
    "universal fresh-thread recall quality",
    "foreground-hook-only sufficiency",
    "base model innate memory",
]


def _quality_gates(report: dict[str, Any]) -> dict[str, Any]:
    audit = report.get("audit") or fresh_thread_demo.validate_fresh_thread_demo_report(report)
    metrics = report.get("metrics") or {}
    gates = {
        "privacy_safe": audit.get("privacy_failure_count") == 0,
        "no_unsupported_evidence": audit.get("unsupported_evidence_count") == 0,
        "negative_controls_pass": audit.get("negative_control_active_recall_count") == 0,
        "positive_flows_present": metrics.get("positive_flow_count", 0) >= 5,
        "negative_controls_present": metrics.get("negative_control_count", 0) >= 5,
        "three_arms_present": set(report.get("arms") or []) == set(fresh_thread_demo.DEMO_ARMS),
        "long_turn_flow_present": metrics.get("max_turn_depth", 0) >= 3
        and metrics.get("multi_turn_flow_count", 0) >= 2,
        "correction_controls_present": metrics.get("correction_control_count", 0) >= 1,
        "threshold_edge_controls_present": metrics.get("threshold_edge_control_count", 0) >= 1,
    }
    return {
        **gates,
        "ok": all(gates.values()),
        "audit": audit,
    }


def _turns(flow: Mapping[str, Any], arm: str) -> list[Mapping[str, Any]]:
    arm_payload = (flow.get("arms") or {}).get(arm) if isinstance(flow.get("arms"), dict) else {}
    rows = arm_payload.get("turns") if isinstance(arm_payload, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _issue_281_public_validation_readout(
    report: Mapping[str, Any],
    gates: Mapping[str, Any],
) -> dict[str, Any]:
    flows = [flow for flow in report.get("flows") or [] if isinstance(flow, Mapping)]
    positive_flows = [flow for flow in flows if flow.get("kind") == "positive_demo"]
    negative_flows = [flow for flow in flows if flow.get("kind") == "negative_control"]

    positive_first_turns = [
        turns[0]
        for flow in positive_flows
        if (turns := _turns(flow, "active_recall"))
    ]
    negative_first_turns = [
        turns[0]
        for flow in negative_flows
        if (turns := _turns(flow, "active_recall"))
    ]
    positive_first_turn_success_count = sum(
        1
        for turn in positive_first_turns
        if turn.get("agent_action")
        in {"use_silently", "ask_light_question", "active_recall", "source_reopen"}
    )
    first_turn_false_activation_count = sum(
        1
        for turn in negative_first_turns
        if turn.get("should_call_active_recall")
        or turn.get("source_refs_allowed")
        or turn.get("allowed_surface") == "source_backed"
    )

    multi_turn_positive_flows = [
        flow for flow in positive_flows if len(_turns(flow, "active_recall")) > 1
    ]
    progressive_success_count = sum(
        1
        for flow in multi_turn_positive_flows
        if any(
            turn.get("agent_action") in {"active_recall", "source_reopen"}
            for turn in _turns(flow, "active_recall")[1:]
        )
    )

    active_turns = [
        turn
        for flow in flows
        for turn in _turns(flow, "active_recall")
    ]
    source_required_turns = [
        turn for turn in active_turns if turn.get("packet_support_level") == "source_required"
    ]
    source_reopen_success_count = sum(
        1
        for turn in source_required_turns
        if turn.get("agent_action") == "source_reopen"
        and turn.get("requires_source_reopen")
    )
    negative_turns = [
        turn
        for flow in negative_flows
        for turn in _turns(flow, "active_recall")
    ]
    irrelevant_memory_drag_count = sum(
        1
        for turn in negative_turns
        if turn.get("should_call_active_recall")
        or turn.get("source_refs_allowed")
        or turn.get("allowed_surface") == "source_backed"
    )
    manual_query_invention_count = sum(
        int(turn.get("manual_query_invention_count") or 0)
        for turn in active_turns
    )
    manual_query_expected_count = sum(
        1 for turn in active_turns if turn.get("manual_query_invention_expected")
    )
    ready_lock_use_count = sum(
        1 for turn in active_turns if turn.get("lock_handling") == "use_ready_lock"
    )
    audit = gates.get("audit") or {}
    unsupported_evidence_count = int(audit.get("unsupported_evidence_count") or 0)
    negative_active_recall_count = int(audit.get("negative_control_active_recall_count") or 0)
    overpersonalization_count = (
        first_turn_false_activation_count
        + irrelevant_memory_drag_count
        + unsupported_evidence_count
        + negative_active_recall_count
    )

    first_turn_scent_precision = _rate(
        positive_first_turn_success_count,
        positive_first_turn_success_count + first_turn_false_activation_count,
    )
    metrics = {
        "positive_public_flow_count": len(positive_flows),
        "negative_public_control_count": len(negative_flows),
        "first_turn_positive_route_success_count": positive_first_turn_success_count,
        "first_turn_false_activation_count": first_turn_false_activation_count,
        "first_turn_scent_precision": first_turn_scent_precision,
        "progressive_activation_gain": _rate(
            progressive_success_count,
            len(multi_turn_positive_flows),
        ),
        "source_reopen_before_specific_claim_rate": _rate(
            source_reopen_success_count,
            len(source_required_turns),
        ),
        "irrelevant_memory_drag_rate": _rate(
            irrelevant_memory_drag_count,
            len(negative_turns),
        ),
        "overpersonalization_count": overpersonalization_count,
        "manual_query_invention_count": manual_query_invention_count,
        "manual_query_expected_count": manual_query_expected_count,
        "ready_lock_use_count": ready_lock_use_count,
        "unsupported_evidence_count": unsupported_evidence_count,
        "negative_control_active_recall_count": negative_active_recall_count,
    }
    closeout_eligible = bool(
        gates.get("ok")
        and len(positive_flows) >= 5
        and len(negative_flows) >= 5
        and first_turn_scent_precision == 1.0
        and metrics["progressive_activation_gain"] == 1.0
        and metrics["source_reopen_before_specific_claim_rate"] == 1.0
        and metrics["irrelevant_memory_drag_rate"] == 0.0
        and overpersonalization_count == 0
        and manual_query_invention_count == 0
        and manual_query_expected_count == 0
        and ready_lock_use_count >= 2
    )
    return {
        "public_validation_measured": True,
        "claim_level": "public_safe_fixture_validation",
        "closeout_eligible": closeout_eligible,
        "basis": (
            "fresh-thread public demo fixtures with positive, negative, "
            "multi-turn, correction, threshold, active-recall, and source-reopen controls"
        ),
        "metrics": metrics,
        "can_claim": [
            "public_fixture_first_turn_scent_precision_recorded",
            "public_fixture_progressive_activation_gain_recorded",
            "source_reopen_before_specific_claim_recorded",
            "negative_control_memory_drag_and_overpersonalization_suppressed",
            "active_recall_route_handles_avoid_manual_query_invention",
        ],
        "cannot_claim": list(_PUBLIC_VALIDATION_CANNOT_CLAIM),
        "remaining_followups_should_use_new_scoped_issue": [
            "live_host_fresh_thread_quality",
            "private_real_history_generalization",
            "public_external_dataset_fresh_thread_quality",
        ],
    }


def _issue_1749_first_magic_moment_readout(
    report: Mapping[str, Any],
    gates: Mapping[str, Any],
) -> dict[str, Any]:
    flows = [flow for flow in report.get("flows") or [] if isinstance(flow, Mapping)]
    positive_flows = [flow for flow in flows if flow.get("kind") == "positive_demo"]
    active_turns = [
        turn
        for flow in positive_flows
        for turn in _turns(flow, "active_recall")
    ]
    recall_turns = [
        turn
        for turn in active_turns
        if turn.get("agent_action") in {"active_recall", "source_reopen"}
        or turn.get("should_call_active_recall")
    ]
    source_reopened_turns = [
        turn
        for turn in active_turns
        if turn.get("agent_action") == "source_reopen"
        and turn.get("requires_source_reopen")
    ]
    friction_count = sum(
        1
        for turn in active_turns
        if int(turn.get("manual_query_invention_count") or 0) > 0
    )
    metrics = {
        "fresh_thread_public_case_count": len(positive_flows),
        "agent_chose_recall_count": len(recall_turns),
        "route_found_count": sum(1 for turn in recall_turns if int(turn.get("candidate_ref_count") or 0) > 0),
        "source_reopened_count": len(source_reopened_turns),
        "answer_helpful_count": len(recall_turns),
        "user_reprompt_needed_count": sum(
            1 for turn in active_turns if turn.get("manual_query_invention_expected")
        ),
        "foreground_friction_count": friction_count,
    }
    return {
        "public_fixture_measured": True,
        "claim_level": "product_e2e_fixture_evidence",
        "basis": "fresh-thread public demo active-recall arm over vague continuity prompts",
        "closeout_eligible": bool(
            gates.get("ok")
            and metrics["agent_chose_recall_count"] > 0
            and metrics["source_reopened_count"] > 0
            and metrics["user_reprompt_needed_count"] == 0
            and metrics["foreground_friction_count"] == 0
        ),
        "metrics": metrics,
        "privacy_boundary_ok": bool((gates.get("audit") or {}).get("privacy_failure_count") == 0),
        "can_claim": [
            "public_fixture_fresh_thread_to_route_to_source_reopen_path",
            "negative_controls_suppress_irrelevant_memory_drag",
        ],
        "cannot_claim": [
            "live first-magic-moment quality",
            "private real-history first-magic-moment quality",
            "foreground-hook-only sufficiency",
            "base model innate memory",
        ],
    }


def _issue_1750_agent_initiative_readout(
    report: Mapping[str, Any],
    gates: Mapping[str, Any],
) -> dict[str, Any]:
    flows = [flow for flow in report.get("flows") or [] if isinstance(flow, Mapping)]
    positive_flows = [flow for flow in flows if flow.get("kind") == "positive_demo"]
    negative_flows = [flow for flow in flows if flow.get("kind") == "negative_control"]
    active_positive_turns = [
        turn
        for flow in positive_flows
        for turn in _turns(flow, "active_recall")
    ]
    active_negative_turns = [
        turn
        for flow in negative_flows
        for turn in _turns(flow, "active_recall")
    ]
    agent_chose_recall_count = sum(
        1
        for turn in active_positive_turns
        if turn.get("agent_action") in {"active_recall", "source_reopen"}
        or turn.get("should_call_active_recall")
    )
    source_reopen_followthrough_count = sum(
        1
        for turn in active_positive_turns
        if turn.get("agent_action") == "source_reopen"
        and turn.get("requires_source_reopen")
    )
    negative_wrong_recall_count = sum(
        1
        for turn in active_negative_turns
        if turn.get("should_call_active_recall")
        or turn.get("source_refs_allowed")
        or turn.get("allowed_surface") == "source_backed"
    )
    high_risk_count = sum(
        1
        for turn in [*active_positive_turns, *active_negative_turns]
        if turn.get("requires_source_reopen")
        or turn.get("packet_support_level") == "source_required"
    )
    metrics = {
        "continuity_sensitive_case_count": len(positive_flows),
        "agent_chose_recall_count": agent_chose_recall_count,
        "deepen_followthrough_count": source_reopen_followthrough_count,
        "source_reopen_followthrough_count": source_reopen_followthrough_count,
        "manual_search_avoided_count": agent_chose_recall_count,
        "negative_control_wrong_recall_count": negative_wrong_recall_count,
        "wrong_context_drag_count": negative_wrong_recall_count,
        "user_reprompt_needed_count": sum(
            1
            for turn in active_positive_turns
            if turn.get("manual_query_invention_expected")
            or int(turn.get("manual_query_invention_count") or 0) > 0
        ),
        "high_risk_source_reopen_case_count": high_risk_count,
    }
    return {
        "public_fixture_measured": True,
        "claim_level": "agent_initiative_policy_fixture",
        "case_groups": {
            "weak_hint": [
                flow.get("flow_id")
                for flow in positive_flows
                if flow.get("cue_family") in {"stress", "planning", "website"}
            ],
            "explicit_hint": [
                flow.get("flow_id")
                for flow in positive_flows
                if flow.get("cue_family") in {"coding", "gift"}
            ],
            "negative_control": [flow.get("flow_id") for flow in negative_flows],
            "high_risk": [
                flow.get("flow_id")
                for flow in flows
                if any(turn.get("requires_source_reopen") for turn in _turns(flow, "active_recall"))
            ],
        },
        "closeout_eligible": bool(
            gates.get("ok")
            and agent_chose_recall_count > 0
            and negative_wrong_recall_count == 0
        ),
        "metrics": metrics,
        "cannot_claim": [
            "live_agent_initiative_rate",
            "universal_every_turn_recall_policy",
            "private_history_agent_initiative_quality",
        ],
    }


def run_benchmark(
    *,
    flow_ids: Sequence[str] | None = None,
    arms: Sequence[str] | None = None,
) -> dict[str, Any]:
    report = fresh_thread_demo.run_fresh_thread_demo(flow_ids=flow_ids, arms=arms)
    gates = _quality_gates(report)
    issue_281 = _issue_281_public_validation_readout(report, gates)
    issue_1749 = _issue_1749_first_magic_moment_readout(report, gates)
    issue_1750 = _issue_1750_agent_initiative_readout(report, gates)
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
        "issue_readouts": {
            "github_281": issue_281,
            "github_1749_first_magic_moment": issue_1749,
            "github_1750_agent_initiative": issue_1750,
        },
        "cannot_claim": [
            "real-history fresh-thread recall quality",
            "live semantic-model quality",
            "live correction-extraction quality",
            "competitor or leaderboard superiority",
            "private family or emotional-memory coverage",
            *_PUBLIC_VALIDATION_CANNOT_CLAIM,
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
