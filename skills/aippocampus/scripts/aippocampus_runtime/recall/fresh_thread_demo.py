#!/usr/bin/env python3
"""Public-safe fresh-thread recall demo runner.

The fixture catalog is deliberately synthetic. It models upstream
semantic/subconscious output so the demo can exercise the real
fresh_thread_scent/action/activation contracts without classifying raw prompts
through a static phrase list. This is product-shape evidence, not a benchmark
or a claim about private-history quality.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any, Literal, Sequence

from aippocampus_runtime.recall.fresh_thread_action import (
    TASK_CONTEXT_FLAG_PROVENANCE,
    fresh_thread_action_from_packet,
)
from aippocampus_runtime.recall.fresh_thread_activation import (
    advance_fresh_thread_activation,
    fresh_thread_activation_context,
)
from aippocampus_runtime.recall.fresh_thread_demo_fixtures import (
    DemoFlow,
    DemoTurn,
    fresh_thread_demo_flows,
)
from aippocampus_runtime.recall.fresh_thread_scent import fresh_thread_scent_packet_from_decision

DEMO_SCHEMA_VERSION = 2
DemoArm = Literal["no_memory", "hook_only", "active_recall"]
DEMO_ARMS: tuple[DemoArm, ...] = ("no_memory", "hook_only", "active_recall")

_PUBLIC_WORKSPACE = "public-demo-workspace"
_REGISTRY_FINGERPRINT = {"demo_fixture": "fresh_thread_public_v2"}
_DENYLIST = (
    "raw private",
    "private source",
    "sk_test",
    "sk-test",
    "E:\\",
    "C:\\",
    "/private/",
)


def _selected_flows(flow_ids: Sequence[str] | None) -> tuple[DemoFlow, ...]:
    flows = fresh_thread_demo_flows()
    if not flow_ids:
        return flows
    wanted = set(flow_ids)
    return tuple(flow for flow in flows if flow.flow_id in wanted)


def _selected_arms(arms: Sequence[str] | None) -> tuple[DemoArm, ...]:
    if not arms:
        return DEMO_ARMS
    selected: list[DemoArm] = []
    for arm in arms:
        if arm not in DEMO_ARMS:
            raise ValueError(f"unknown demo arm: {arm}")
        selected.append(arm)
    return tuple(selected)


def _packet_for_turn(turn: DemoTurn) -> dict[str, Any]:
    return fresh_thread_scent_packet_from_decision(turn.upstream_decision)


def _task_context_for_turn(turn: DemoTurn, arm: DemoArm) -> dict[str, Any]:
    if arm == "active_recall":
        return dict(turn.active_task_context)
    if arm == "hook_only":
        return dict(turn.hook_task_context)
    return {}


def _lock_for_turn(turn: DemoTurn, arm: DemoArm) -> dict[str, Any] | None:
    if arm == "active_recall":
        return turn.active_recall_lock
    return None


def _demo_task_context_contract(action: dict[str, Any]) -> dict[str, Any]:
    """Keep per-turn report rows readable while preserving the boundary proof."""

    contract = action["task_context_contract"]
    return {
        "semantic_flags_are_upstream_judgement": contract[
            "semantic_flags_are_upstream_judgement"
        ],
        "policy_parses_raw_prompt": contract["policy_parses_raw_prompt"],
        "policy_uses_static_phrase_lists": contract["policy_uses_static_phrase_lists"],
        "observed_flags": contract["observed_flags"],
        "unknown_flags": contract["unknown_flags"],
    }


def _no_memory_turn(turn: DemoTurn) -> dict[str, Any]:
    return {
        "turn_id": turn.turn_id,
        "public_prompt": turn.public_prompt,
        "packet_support_level": "none",
        "packet_suggested_action": "none",
        "agent_action": "ignore",
        "reason": "no_memory_arm_has_no_recall_surface",
        "allowed_surface": "none",
        "should_call_active_recall": False,
        "requires_source_reopen": False,
        "source_refs_allowed": False,
        "candidate_ref_count": 0,
        "manual_query_invention_expected": False,
        "manual_query_invention_count": 0,
        "lock_handling": "none",
        "activation_state": "",
        "activation_update": "none",
        "expected_note": turn.expected_note,
    }


def _run_flow_arm(flow: DemoFlow, arm: DemoArm) -> dict[str, Any]:
    if arm == "no_memory":
        return {
            "arm": arm,
            "expected_outcome": flow.expected_outcomes[arm],
            "negative_control": flow.kind == "negative_control",
            "proof_boundary": "No-memory baseline shows ordinary behavior without recall routes.",
            "turns": [_no_memory_turn(turn) for turn in flow.turns],
        }

    state: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for index, turn in enumerate(flow.turns):
        packet = _packet_for_turn(turn)
        lock = _lock_for_turn(turn, arm)
        if turn.activation_event_timing == "before_action":
            state = advance_fresh_thread_activation(
                state,
                event=turn.activation_event,
                packet=packet,
                thread_id=f"thread:{flow.flow_id}",
                workspace=_PUBLIC_WORKSPACE,
                topic_epoch=turn.topic_epoch,
                registry_fingerprint=_REGISTRY_FINGERPRINT,
                active_recall_lock=lock,
                now_unix=1_000.0 + index,
            )
        activation_context = fresh_thread_activation_context(
            state,
            topic_epoch=turn.topic_epoch,
            registry_fingerprint=_REGISTRY_FINGERPRINT,
            now_unix=1_000.0 + index,
            user_anchor=turn.user_anchor,
        )
        context = {**_task_context_for_turn(turn, arm), **activation_context}
        action = fresh_thread_action_from_packet(packet, task_context=context, active_recall_lock=lock)
        if turn.activation_event_timing == "after_action":
            state = advance_fresh_thread_activation(
                state,
                event=turn.activation_event,
                packet=packet,
                thread_id=f"thread:{flow.flow_id}",
                workspace=_PUBLIC_WORKSPACE,
                topic_epoch=turn.topic_epoch,
                registry_fingerprint=_REGISTRY_FINGERPRINT,
                active_recall_lock=lock,
                now_unix=1_000.0 + index,
            )
        rows.append(
            {
                "turn_id": turn.turn_id,
                "public_prompt": turn.public_prompt,
                "packet_support_level": packet["support_level"],
                "packet_advisory_action": packet["advisory_action"],
                "packet_suggested_action": packet["suggested_action"],
                "agent_action": action["agent_action"],
                "reason": action["reason"],
                "allowed_surface": action["allowed_surface"],
                "should_call_active_recall": action["should_call_active_recall"],
                "requires_source_reopen": action["requires_source_reopen"],
                "source_refs_allowed": action["source_refs_allowed"],
                "candidate_ref_count": len(action["candidate_refs"]),
                "manual_query_invention_expected": bool(
                    action.get("manual_query_invention_expected", False)
                ),
                "manual_query_invention_count": int(
                    action.get("manual_query_invention_count") or 0
                ),
                "lock_handling": action["lock_handling"],
                "task_context_contract": _demo_task_context_contract(action),
                "activation_state": str((state or {}).get("state") or ""),
                "activation_update": action["activation_update"],
                "expected_note": turn.expected_note,
            }
        )
    return {
        "arm": arm,
        "expected_outcome": flow.expected_outcomes[arm],
        "negative_control": flow.kind == "negative_control",
        "proof_boundary": (
            "Hook-only arm uses scent/action contracts without deeper locks."
            if arm == "hook_only"
            else "Active-recall arm may use lock handles, but source claims still reopen source."
        ),
        "turns": rows,
    }


def _flow_payload(flow: DemoFlow, arms: Sequence[DemoArm]) -> dict[str, Any]:
    return {
        "flow_id": flow.flow_id,
        "title": flow.title,
        "kind": flow.kind,
        "cue_family": flow.cue_family,
        "coverage_tags": list(flow.coverage_tags),
        "public_safe": flow.public_safe,
        "demo_goal": flow.demo_goal,
        "proof_boundary": flow.proof_boundary,
        "arms": {arm: _run_flow_arm(flow, arm) for arm in arms},
    }


def _turn_depth_distribution(flows: Sequence[DemoFlow]) -> dict[str, int]:
    depths = Counter(str(len(flow.turns)) for flow in flows)
    return dict(sorted(depths.items(), key=lambda item: int(item[0])))


def _tagged_flow_count(flows: Sequence[DemoFlow], tag: str) -> int:
    return sum(1 for flow in flows if tag in flow.coverage_tags)


def _turn_count_by_packet_field(flows: Sequence[DemoFlow], *, key: str, value: str) -> int:
    return sum(
        1
        for flow in flows
        for turn in flow.turns
        if str(turn.upstream_decision.get(key) or "") == value
    )


def _demo_metrics(flows: Sequence[DemoFlow], arm_count: int) -> dict[str, Any]:
    max_turn_depth = max((len(flow.turns) for flow in flows), default=0)
    return {
        "flow_count": len(flows),
        "positive_flow_count": sum(1 for flow in flows if flow.kind == "positive_demo"),
        "negative_control_count": sum(1 for flow in flows if flow.kind == "negative_control"),
        "arm_count": arm_count,
        "turn_depth_distribution": _turn_depth_distribution(flows),
        "max_turn_depth": max_turn_depth,
        "max_flow_turn_count": max_turn_depth,
        "multi_turn_flow_count": _tagged_flow_count(flows, "multi_turn"),
        "correction_control_count": _tagged_flow_count(flows, "correction_control"),
        "threshold_edge_control_count": _tagged_flow_count(flows, "threshold_edge"),
        "threshold_control_count": _tagged_flow_count(flows, "threshold_edge"),
        "source_required_turn_count": _turn_count_by_packet_field(
            flows,
            key="decision",
            value="evidence",
        ),
        "low_confidence_turn_count": _turn_count_by_packet_field(
            flows,
            key="confidence",
            value="low",
        ),
        "synthetic_task_context_fixture_turn_count": sum(
            1
            for flow in flows
            for turn in flow.turns
            if turn.hook_task_context or turn.active_task_context
        ),
    }


def run_fresh_thread_demo(
    *,
    flow_ids: Sequence[str] | None = None,
    arms: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the deterministic public #285/#490 demo fixture set."""

    selected_arms = _selected_arms(arms)
    selected_flows = _selected_flows(flow_ids)
    flows = [_flow_payload(flow, selected_arms) for flow in selected_flows]
    metrics = _demo_metrics(selected_flows, arm_count=len(selected_arms))
    report = {
        "kind": "aippocampus_fresh_thread_demo_report",
        "schema_version": DEMO_SCHEMA_VERSION,
        "issue": "#285/#490",
        "arms": list(selected_arms),
        "claim_boundary": {
            "issue": "#285/#490",
            "demo_proof": True,
            "benchmark_proof": False,
            "uses_private_history": False,
            "uses_live_model": False,
            "synthetic_task_context_fixtures": True,
            "semantic_classification_quality_proof": False,
            "correction_extraction_quality_proof": False,
            "real_history_sample_quality_proof": False,
            "statement": (
                "This runner demonstrates the public-safe product contract over synthetic "
                "fixtures, including multi-turn, correction, and threshold-edge controls. "
                "It does not measure real-history recall quality, live semantic "
                "classification quality, correction extraction quality, or competitor baselines."
            ),
        },
        "task_context_contract": {
            "semantic_flags_are_upstream_judgement": True,
            "policy_parses_raw_prompt": False,
            "policy_uses_static_phrase_lists": False,
            "known_flag_provenance": dict(sorted(TASK_CONTEXT_FLAG_PROVENANCE.items())),
        },
        "metrics": metrics,
        "flows": flows,
    }
    report["audit"] = validate_fresh_thread_demo_report(report)
    return report


def validate_fresh_thread_demo_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return aggregate privacy and boundary diagnostics for a demo report."""

    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    privacy_hits = [needle for needle in _DENYLIST if needle in serialized]
    unsupported_evidence = 0
    negative_active_recall = 0
    for flow in report.get("flows") or []:
        is_negative = flow.get("kind") == "negative_control"
        for arm_payload in (flow.get("arms") or {}).values():
            for turn in arm_payload.get("turns") or []:
                if turn.get("source_refs_allowed") and turn.get("agent_action") != "source_reopen":
                    unsupported_evidence += 1
                if turn.get("allowed_surface") == "source_backed" and not turn.get(
                    "requires_source_reopen"
                ):
                    unsupported_evidence += 1
                if is_negative and turn.get("should_call_active_recall"):
                    negative_active_recall += 1
    return {
        "privacy_failure_count": len(privacy_hits),
        "privacy_denied_markers": privacy_hits,
        "unsupported_evidence_count": unsupported_evidence,
        "negative_control_active_recall_count": negative_active_recall,
    }


def render_fresh_thread_demo_report(report: dict[str, Any]) -> str:
    """Render a compact text walkthrough without dumping candidate refs."""

    lines = [
        "Fresh-thread recall public demo",
        f"arms: {', '.join(report.get('arms') or [])}",
        f"claim: {report.get('claim_boundary', {}).get('statement', '')}",
    ]
    for flow in report.get("flows") or []:
        lines.append("")
        lines.append(f"{flow['flow_id']} ({flow['kind']}): {flow['title']}")
        for arm, payload in (flow.get("arms") or {}).items():
            lines.append(f"- {arm}: {payload['expected_outcome']}")
            for turn in payload.get("turns") or []:
                lines.append(
                    "  "
                    + "{turn}: scent={scent} action={action} lock={lock} source_reopen={source}".format(
                        turn=turn["turn_id"],
                        scent=turn["packet_support_level"],
                        action=turn["agent_action"],
                        lock=turn["lock_handling"],
                        source=str(bool(turn["requires_source_reopen"])).lower(),
                    )
                )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flow",
        action="append",
        dest="flows",
        help="Run only this flow id. May be passed more than once.",
    )
    parser.add_argument(
        "--arm",
        action="append",
        dest="arms",
        choices=DEMO_ARMS,
        help="Run only this arm. May be passed more than once.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = run_fresh_thread_demo(flow_ids=args.flows, arms=args.arms)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_fresh_thread_demo_report(report))
    return 0


__all__ = [
    "DEMO_ARMS",
    "DEMO_SCHEMA_VERSION",
    "DemoFlow",
    "DemoTurn",
    "fresh_thread_demo_flows",
    "main",
    "render_fresh_thread_demo_report",
    "run_fresh_thread_demo",
    "validate_fresh_thread_demo_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
