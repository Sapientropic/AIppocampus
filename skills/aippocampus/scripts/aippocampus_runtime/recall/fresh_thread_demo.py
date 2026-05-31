#!/usr/bin/env python3
"""Public-safe fresh-thread recall demo fixtures and runner.

The fixtures in this module are deliberately synthetic. They model upstream
semantic/subconscious output so the demo can exercise the real
fresh_thread_scent/action/activation contracts without classifying raw prompts
through a static phrase list. This is product-shape evidence, not a benchmark
or a claim about private-history quality.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from aippocampus_runtime.recall.fresh_thread_action import fresh_thread_action_from_packet
from aippocampus_runtime.recall.fresh_thread_activation import (
    advance_fresh_thread_activation,
    fresh_thread_activation_context,
)
from aippocampus_runtime.recall.fresh_thread_scent import fresh_thread_scent_packet_from_decision

DEMO_SCHEMA_VERSION = 1
DemoArm = Literal["no_memory", "hook_only", "active_recall"]
DemoKind = Literal["positive_demo", "negative_control"]
EventTiming = Literal["before_action", "after_action"]
DEMO_ARMS: tuple[DemoArm, ...] = ("no_memory", "hook_only", "active_recall")

_PUBLIC_WORKSPACE = "public-demo-workspace"
_REGISTRY_FINGERPRINT = {"demo_fixture": "fresh_thread_public_v1"}
_DENYLIST = (
    "raw private",
    "private source",
    "sk_test",
    "sk-test",
    "E:\\",
    "C:\\",
    "/private/",
)


@dataclass(frozen=True)
class DemoTurn:
    turn_id: str
    public_prompt: str
    upstream_decision: dict[str, Any]
    activation_event: str = "scent_emitted"
    activation_event_timing: EventTiming = "after_action"
    topic_epoch: str = "demo"
    user_anchor: bool = False
    hook_task_context: dict[str, Any] = field(default_factory=dict)
    active_task_context: dict[str, Any] = field(default_factory=dict)
    active_recall_lock: dict[str, Any] | None = None
    expected_note: str = ""


@dataclass(frozen=True)
class DemoFlow:
    flow_id: str
    title: str
    kind: DemoKind
    cue_family: str
    demo_goal: str
    proof_boundary: str
    expected_outcomes: dict[str, str]
    turns: tuple[DemoTurn, ...]
    public_safe: bool = True


def _decision(
    *,
    decision: str = "scent",
    confidence: str = "medium",
    sensitivity: str = "safe",
    freshness: str = "current",
    source_id: str = "",
    thread_key: str = "session:demo",
    line: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision": decision,
        "confidence": confidence,
        "sensitivity": sensitivity,
        "freshness": freshness,
    }
    if source_id:
        row: dict[str, Any] = {"source_id": source_id, "thread_key": thread_key}
        if line is not None:
            row["line"] = line
        key = "evidence" if decision == "evidence" else "candidates"
        payload[key] = [row]
    return payload


def fresh_thread_demo_flows() -> tuple[DemoFlow, ...]:
    """Return the synthetic public-safe #285 demo fixture set."""

    return (
        DemoFlow(
            flow_id="stress_cue",
            title="Stress cue activates only after a user anchor",
            kind="positive_demo",
            cue_family="stress",
            demo_goal="Show gentle first-turn support, then deeper recall only after the user confirms relevance.",
            proof_boundary="Demo proof: contract-level progression. Not proof of private emotional recall quality.",
            expected_outcomes={
                "no_memory": "generic_support",
                "hook_only": "private_scent_or_light_question",
                "active_recall": "gentle_support_then_confirmed_active_recall",
            },
            turns=(
                DemoTurn(
                    turn_id="stress_first_turn",
                    public_prompt="我觉得压力好大。",
                    upstream_decision=_decision(
                        confidence="low",
                        sensitivity="caution",
                        freshness="unknown",
                        source_id="clean:demo:stress-pressure",
                    ),
                    topic_epoch="stress",
                    hook_task_context={"broad_or_sensitive_prompt": True},
                    active_task_context={"broad_or_sensitive_prompt": True},
                    expected_note="First turn keeps a weak emotional scent internal.",
                ),
                DemoTurn(
                    turn_id="stress_user_anchor",
                    public_prompt="像之前开源发布前那种压力。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:stress-pressure",
                    ),
                    activation_event="user_confirmed",
                    activation_event_timing="before_action",
                    topic_epoch="stress",
                    user_anchor=True,
                    hook_task_context={},
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={"state": "ready", "lock_id": "lock_demo_stress"},
                    expected_note="The anchor lets active recall use a ready route handle.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="website_cue",
            title="Website cue can use durable taste without repo facts",
            kind="positive_demo",
            cue_family="website",
            demo_goal="Show design/workflow preference recall as a route that can change the next design decision.",
            proof_boundary="Demo proof: source-id-only preference route. Not proof of all frontend taste recall.",
            expected_outcomes={
                "no_memory": "generic_website_planning",
                "hook_only": "light_scoping_question",
                "active_recall": "preference_route_can_change_design_next_step",
            },
            turns=(
                DemoTurn(
                    turn_id="website_first_turn",
                    public_prompt="我想建个网站。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:frontend-taste",
                    ),
                    topic_epoch="website",
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={"state": "ready", "lock_id": "lock_demo_website"},
                    expected_note="Active arm can consult style/workflow memory before proposing direction.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="gift_cue",
            title="Gift cue keeps low-sensitive recall bounded by source reopen",
            kind="positive_demo",
            cue_family="gift",
            demo_goal="Show low-sensitive preference recall while keeping specific family claims source-backed.",
            proof_boundary="Demo proof: specific claims route to source_reopen. Not proof of private family-memory coverage.",
            expected_outcomes={
                "no_memory": "generic_gift_questions",
                "hook_only": "privacy_careful_light_question",
                "active_recall": "low_sensitive_preference_requires_source_before_specific_claim",
            },
            turns=(
                DemoTurn(
                    turn_id="gift_first_turn",
                    public_prompt="帮我妈妈挑个礼物。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="caution",
                        source_id="clean:demo:gift-low-sensitive",
                    ),
                    topic_epoch="gift",
                    hook_task_context={"broad_or_sensitive_prompt": True},
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={"state": "pending", "lock_id": "lock_demo_gift"},
                    expected_note="A cautious route may be probed, but not exposed as a family fact.",
                ),
                DemoTurn(
                    turn_id="gift_specific_claim",
                    public_prompt="她最近说想要安静放松一点。",
                    upstream_decision=_decision(
                        decision="evidence",
                        confidence="high",
                        sensitivity="safe",
                        source_id="clean:demo:gift-low-sensitive",
                        line=18,
                    ),
                    activation_event="source_reopened",
                    activation_event_timing="after_action",
                    topic_epoch="gift",
                    user_anchor=True,
                    hook_task_context={"specific_memory_claim": True},
                    active_task_context={"specific_memory_claim": True},
                    expected_note="Specific memory-backed wording needs source reopen.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="fresh_coding_cue",
            title="Fresh coding cue uses portable preferences, not old repo facts",
            kind="positive_demo",
            cue_family="coding",
            demo_goal="Show cross-project engineering preferences while preserving current-repo fact lookup.",
            proof_boundary="Demo proof: portable preference route only. Not proof of current repository facts.",
            expected_outcomes={
                "no_memory": "read_repo_from_scratch",
                "hook_only": "generic_repo_orientation",
                "active_recall": "portable_preferences_without_repo_fact_bleed",
            },
            turns=(
                DemoTurn(
                    turn_id="coding_first_turn",
                    public_prompt="这个新 repo 没有 AGENTS.md，先帮我开始做。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:portable-engineering-style",
                    ),
                    topic_epoch="coding",
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={"state": "ready", "lock_id": "lock_demo_coding"},
                    expected_note="Active recall may use portable working preferences; repo facts still come from files.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="negative_broad_stress",
            title="Broad stress prompt stays generic when personalization is too weak",
            kind="negative_control",
            cue_family="stress",
            demo_goal="Show that broad stress alone does not expose an old private theme.",
            proof_boundary="Negative demo control: over-personalization stays suppressed.",
            expected_outcomes={
                "no_memory": "stay_generic",
                "hook_only": "stay_generic",
                "active_recall": "stay_generic",
            },
            turns=(
                DemoTurn(
                    turn_id="broad_stress",
                    public_prompt="今天有点烦。",
                    upstream_decision=_decision(
                        confidence="low",
                        sensitivity="caution",
                        freshness="unknown",
                        source_id="clean:demo:stress-pressure",
                    ),
                    topic_epoch="negative-stress",
                    hook_task_context={"broad_or_sensitive_prompt": True},
                    active_task_context={"broad_or_sensitive_prompt": True},
                    expected_note="Weak scent remains internal; support the user normally.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="negative_irrelevant_website",
            title="Irrelevant website prompt does not force preference recall",
            kind="negative_control",
            cue_family="website",
            demo_goal="Show that a generic website prompt can simply ask for scope.",
            proof_boundary="Negative demo control: absent candidate route stays no-op.",
            expected_outcomes={
                "no_memory": "ask_normal_scoping_question",
                "hook_only": "ask_normal_scoping_question",
                "active_recall": "ask_normal_scoping_question",
            },
            turns=(
                DemoTurn(
                    turn_id="irrelevant_website",
                    public_prompt="给学校社团做个通知页。",
                    upstream_decision=_decision(decision="skip", confidence="low"),
                    activation_event="topic_shift_retired",
                    topic_epoch="negative-website",
                    expected_note="No candidate refs means no personalization route.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="negative_sensitive_gift",
            title="Sensitive gift detail is suppressed",
            kind="negative_control",
            cue_family="gift",
            demo_goal="Show that sensitive family detail remains unavailable to answer content.",
            proof_boundary="Negative demo control: suppressed packets steer nothing.",
            expected_outcomes={
                "no_memory": "suppress_sensitive_detail",
                "hook_only": "suppress_sensitive_detail",
                "active_recall": "suppress_sensitive_detail",
            },
            turns=(
                DemoTurn(
                    turn_id="sensitive_gift",
                    public_prompt="帮我挑一个很私人的家庭礼物。",
                    upstream_decision=_decision(
                        confidence="high",
                        sensitivity="suppress",
                        freshness="unknown",
                        source_id="clean:demo:sensitive-family",
                    ),
                    activation_event="suppressed",
                    topic_epoch="negative-gift",
                    active_recall_lock={"state": "ready", "lock_id": "lock_demo_sensitive"},
                    active_task_context={"memory_may_change_answer": True},
                    expected_note="Suppression wins even if a route handle exists.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="negative_project_fact_bleed",
            title="Old project facts do not answer a new repository question",
            kind="negative_control",
            cue_family="coding",
            demo_goal="Show that portable preferences are not current-repo facts.",
            proof_boundary="Negative demo control: read current files before making repo claims.",
            expected_outcomes={
                "no_memory": "read_current_repo_first",
                "hook_only": "read_current_repo_first",
                "active_recall": "read_current_repo_first",
            },
            turns=(
                DemoTurn(
                    turn_id="project_fact_bleed",
                    public_prompt="这个新 repo 的测试命令是什么？",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:portable-engineering-style",
                    ),
                    topic_epoch="negative-coding",
                    expected_note="Memory may tune habits, but repository facts must come from the current checkout.",
                ),
            ),
        ),
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
        "lock_handling": "none",
        "activation_state": "",
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
                "packet_suggested_action": packet["suggested_action"],
                "agent_action": action["agent_action"],
                "reason": action["reason"],
                "allowed_surface": action["allowed_surface"],
                "should_call_active_recall": action["should_call_active_recall"],
                "requires_source_reopen": action["requires_source_reopen"],
                "source_refs_allowed": action["source_refs_allowed"],
                "candidate_ref_count": len(action["candidate_refs"]),
                "lock_handling": action["lock_handling"],
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
        "public_safe": flow.public_safe,
        "demo_goal": flow.demo_goal,
        "proof_boundary": flow.proof_boundary,
        "arms": {arm: _run_flow_arm(flow, arm) for arm in arms},
    }


def run_fresh_thread_demo(
    *,
    flow_ids: Sequence[str] | None = None,
    arms: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the deterministic public #285 demo fixture set."""

    selected_arms = _selected_arms(arms)
    flows = [_flow_payload(flow, selected_arms) for flow in _selected_flows(flow_ids)]
    metrics = {
        "flow_count": len(flows),
        "positive_flow_count": sum(1 for flow in flows if flow["kind"] == "positive_demo"),
        "negative_control_count": sum(1 for flow in flows if flow["kind"] == "negative_control"),
        "arm_count": len(selected_arms),
    }
    report = {
        "kind": "aippocampus_fresh_thread_demo_report",
        "schema_version": DEMO_SCHEMA_VERSION,
        "issue": "#285",
        "arms": list(selected_arms),
        "claim_boundary": {
            "issue": "#285",
            "demo_proof": True,
            "benchmark_proof": False,
            "uses_private_history": False,
            "uses_live_model": False,
            "statement": (
                "This runner demonstrates the public-safe product contract over synthetic "
                "fixtures. It does not measure real-history recall quality or competitor baselines."
            ),
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
