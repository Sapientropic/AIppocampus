#!/usr/bin/env python3
"""Public-safe synthetic fixture catalog for the fresh-thread demo runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DemoKind = Literal["positive_demo", "negative_control"]
EventTiming = Literal["before_action", "after_action"]


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
    coverage_tags: tuple[str, ...] = ()
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
    """Return the synthetic public-safe #285/#490 demo fixture set.

    These fixtures model upstream semantic/subconscious output. The runner and
    action policy must not turn this catalog into a prompt phrase classifier or
    private-history benchmark.
    """

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
                    hook_task_context={"low_specificity_prompt": True},
                    active_task_context={"low_specificity_prompt": True},
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
                    hook_task_context={"low_specificity_prompt": True},
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
            flow_id="multi_turn_threshold_cue",
            title="Threshold edges progress from light question to source reopen",
            kind="positive_demo",
            cue_family="planning",
            demo_goal=(
                "Show a longer fresh-thread route where low-confidence scent asks for an "
                "anchor, confirmed memory can trigger active recall, and specific public "
                "wording still requires source reopen."
            ),
            proof_boundary=(
                "Demo proof: threshold/action boundary over synthetic upstream packets. "
                "Not proof of live threshold calibration or private-history quality."
            ),
            expected_outcomes={
                "no_memory": "ordinary_planning_without_recall",
                "hook_only": "low_confidence_scent_stays_as_light_question",
                "active_recall": "light_question_then_confirmed_active_recall_then_source_reopen",
            },
            turns=(
                DemoTurn(
                    turn_id="threshold_low_confidence",
                    public_prompt="我想延续上次那个公开演示的写法。",
                    upstream_decision=_decision(
                        confidence="low",
                        sensitivity="safe",
                        source_id="clean:demo:demo-writing-style",
                    ),
                    activation_event="scent_emitted",
                    topic_epoch="threshold",
                    expected_note="Low confidence with a candidate asks for an anchor, not active recall.",
                ),
                DemoTurn(
                    turn_id="threshold_user_anchor",
                    public_prompt="对，就是那种先讲边界再给下一步的风格。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:demo-writing-style",
                    ),
                    activation_event="user_confirmed",
                    activation_event_timing="before_action",
                    topic_epoch="threshold",
                    user_anchor=True,
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={"state": "ready", "lock_id": "lock_demo_threshold"},
                    expected_note="The explicit anchor lets the active arm use a ready route handle.",
                ),
                DemoTurn(
                    turn_id="threshold_source_boundary",
                    public_prompt="现在把这句写成可以公开引用的版本。",
                    upstream_decision=_decision(
                        decision="evidence",
                        confidence="high",
                        sensitivity="safe",
                        source_id="clean:demo:demo-writing-style",
                        line=12,
                    ),
                    activation_event="source_reopened",
                    activation_event_timing="after_action",
                    topic_epoch="threshold",
                    user_anchor=True,
                    active_task_context={"specific_memory_claim": True},
                    expected_note="Specific wording is gated through source reopen even after confirmation.",
                ),
            ),
            coverage_tags=("multi_turn", "threshold_edge"),
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
                    hook_task_context={"low_specificity_prompt": True},
                    active_task_context={"low_specificity_prompt": True},
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
            flow_id="personal_family_gift_continuity",
            title="Personal family gift can use same-user continuity",
            kind="positive_demo",
            cue_family="gift",
            demo_goal=(
                "Show that ordinary personal/family gift context can use a relevant "
                "same-user route without turning the route into unsupported facts."
            ),
            proof_boundary=(
                "Demo proof: same-user route handle can affect planning; specific "
                "family claims still require source reopen."
            ),
            expected_outcomes={
                "no_memory": "generic_gift_questions",
                "hook_only": "light_source_safe_continuity_question",
                "active_recall": "same_user_family_preference_route_can_change_next_step",
            },
            turns=(
                DemoTurn(
                    turn_id="personal_family_gift",
                    public_prompt="帮我挑一个很私人的家庭礼物。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="caution",
                        source_id="clean:demo:family-gift-continuity",
                    ),
                    topic_epoch="gift-continuity",
                    hook_task_context={"low_specificity_prompt": True},
                    active_task_context={"memory_may_change_answer": True},
                    active_recall_lock={
                        "state": "ready",
                        "lock_id": "lock_demo_family_gift",
                        "reopenable_ref_count": 1,
                    },
                    expected_note=(
                        "Personal/family context is not a hard privacy block; use the "
                        "route only as navigation until source is reopened."
                    ),
                ),
            ),
            coverage_tags=("personal_continuity_boundary",),
        ),
        DemoFlow(
            flow_id="negative_hard_risk_secret",
            title="Credential or payment-like gift route stays blocked",
            kind="negative_control",
            cue_family="security",
            demo_goal="Show that concrete property-risk material remains unavailable to answer content.",
            proof_boundary="Negative demo control: hard-risk routes steer nothing unless safely redacted.",
            expected_outcomes={
                "no_memory": "hard_risk_detail_blocked_or_redacted",
                "hook_only": "hard_risk_detail_blocked_or_redacted",
                "active_recall": "hard_risk_detail_blocked_or_redacted",
            },
            turns=(
                DemoTurn(
                    turn_id="hard_risk_gift_payment",
                    public_prompt="帮我用之前那个 API key 处理礼物支付。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:gift-hard-risk",
                    ),
                    activation_event="suppressed",
                    topic_epoch="negative-hard-risk",
                    hook_task_context={"hard_risk_prompt": True},
                    active_task_context={
                        "memory_may_change_answer": True,
                        "hard_risk_prompt": True,
                    },
                    active_recall_lock={
                        "state": "ready",
                        "lock_id": "lock_demo_hard_risk",
                        "reopenable_ref_count": 1,
                    },
                    expected_note="Hard-risk material remains blocked even if a route handle exists.",
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
                    hook_task_context={"current_checkout_required": True},
                    active_task_context={"current_checkout_required": True},
                    expected_note="Memory may tune habits, but repository facts must come from the current checkout.",
                ),
            ),
        ),
        DemoFlow(
            flow_id="negative_wrong_recall_correction",
            title="Plausible but wrong recall is rejected and suppressed",
            kind="negative_control",
            cue_family="correction",
            demo_goal=(
                "Show that a plausible old preference must be corrected or suppressed "
                "after the user rejects it, rather than becoming personalized answer content."
            ),
            proof_boundary=(
                "Negative demo control: correction handling over synthetic activation state. "
                "Not proof of live correction extraction quality."
            ),
            expected_outcomes={
                "no_memory": "follow_current_user_correction",
                "hook_only": "wrong_recall_rejected_and_suppressed",
                "active_recall": "wrong_recall_rejected_and_suppressed",
            },
            turns=(
                DemoTurn(
                    turn_id="wrong_recall_plausible",
                    public_prompt="是不是应该按以前那个暗色控制台风格来？",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        source_id="clean:demo:stale-dark-console",
                    ),
                    activation_event="soft_hypothesis_shown",
                    topic_epoch="wrong-recall",
                    expected_note="A plausible route can only ask lightly without a current anchor.",
                ),
                DemoTurn(
                    turn_id="wrong_recall_user_rejected",
                    public_prompt="不对，这次客户明确要浅色医疗风格，别套旧偏好。",
                    upstream_decision=_decision(
                        confidence="medium",
                        sensitivity="safe",
                        freshness="possibly_stale",
                        source_id="clean:demo:stale-dark-console",
                    ),
                    activation_event="user_rejected",
                    activation_event_timing="before_action",
                    topic_epoch="wrong-recall",
                    expected_note="User rejection suppresses the route before answer planning.",
                ),
                DemoTurn(
                    turn_id="wrong_recall_follow_current",
                    public_prompt="继续浅色医疗风格。",
                    upstream_decision=_decision(
                        confidence="high",
                        sensitivity="safe",
                        freshness="superseded",
                        source_id="clean:demo:stale-dark-console",
                    ),
                    activation_event="topic_shift_retired",
                    topic_epoch="wrong-recall",
                    expected_note="The superseded route stays unavailable; current user correction wins.",
                ),
            ),
            coverage_tags=("multi_turn", "correction_control"),
        ),
    )


__all__ = [
    "DemoFlow",
    "DemoKind",
    "DemoTurn",
    "EventTiming",
    "fresh_thread_demo_flows",
]
