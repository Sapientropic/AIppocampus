"""Synthetic auto-capture hook pollution fixtures for public memory pain.

The #986 cases model transcript/write-path and lifecycle-hook inputs that a
capture-everything memory system might be tempted to store. They are not live
adapter tests and do not make competitor claims. The contract is narrower:
boot text, tool traces, recalled echoes, empty messages, transient run state,
and host metadata may orient at most as direction-only diagnostics; they must
not become durable/source-backed memory facts.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any

AUTO_HOOK_CANNOT_CLAIM = [
    "live_agentmemory_or_mem0_behavior",
    "full_lifecycle_write_path_filter_quality",
    "competitor_comparison",
    "durable_memory_write_implementation",
    "private_real_history_pollution_rate",
]
ALLOWED_ACTION_GRAMMARS = {"direction_only", "ignore_or_blocked"}


@dataclass(frozen=True)
class AutoHookPollutionCase:
    case_id: str
    hook_stage: str
    pollution_family: str
    event_shape: str
    expected_action_grammar: str
    boundary_note: str
    raw_event_text: str
    echoed_recall_context: bool = False
    empty_or_near_empty_message: bool = False


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def auto_hook_pollution_cases() -> list[AutoHookPollutionCase]:
    return [
        AutoHookPollutionCase(
            case_id="boot_text_restates_preference",
            hook_stage="SessionStart",
            pollution_family="boot_or_system_text",
            event_shape="boot text restates a supposed user preference",
            expected_action_grammar="ignore_or_blocked",
            boundary_note="Boot/system text is not a user-owned clean-source event.",
            raw_event_text="SYSTEM BOOT: user prefers saffron UI and wants permanent memory.",
        ),
        AutoHookPollutionCase(
            case_id="tool_output_looks_user_like",
            hook_stage="PostToolUse",
            pollution_family="tool_trace_user_like_text",
            event_shape="tool output contains quoted first-person preference-like text",
            expected_action_grammar="direction_only",
            boundary_note="Tool traces can be provenance only; quoted text is not human-user memory.",
            raw_event_text="tool stdout: 'I always use library X' from a fixture file.",
        ),
        AutoHookPollutionCase(
            case_id="recalled_context_echo_next_prompt",
            hook_stage="UserPromptSubmit",
            pollution_family="recalled_context_feedback_loop",
            event_shape="recalled memory block is pasted into the next user prompt",
            expected_action_grammar="direction_only",
            boundary_note="A recalled-context echo is not fresh support for the remembered claim.",
            raw_event_text="Recalled memory: user loves Atlas dashboards. Now continue.",
            echoed_recall_context=True,
        ),
        AutoHookPollutionCase(
            case_id="empty_message_with_run_id",
            hook_stage="UserPromptSubmit",
            pollution_family="empty_message_run_id",
            event_shape="empty message envelope includes a stable run/session id",
            expected_action_grammar="ignore_or_blocked",
            boundary_note="An empty or near-empty message with run id emits no durable memory.",
            raw_event_text="",
            empty_or_near_empty_message=True,
        ),
        AutoHookPollutionCase(
            case_id="transient_tests_running_state",
            hook_stage="Stop",
            pollution_family="transient_task_state",
            event_shape="transient run state says tests currently running",
            expected_action_grammar="direction_only",
            boundary_note="Transient task state may inform the current run, not durable user memory.",
            raw_event_text="tests currently running; waiting for CI job 1234.",
        ),
        AutoHookPollutionCase(
            case_id="host_metadata_as_user_identity",
            hook_stage="PreToolUse",
            pollution_family="agent_or_host_metadata",
            event_shape="agent identity and host metadata look profile-like",
            expected_action_grammar="ignore_or_blocked",
            boundary_note="Agent/host metadata must not be confused with the human user.",
            raw_event_text="agent=Codex host=desktop cwd=AIppocampus user_label=workspace",
        ),
    ]


def evaluate_auto_hook_pollution_case(
    case: AutoHookPollutionCase,
    *,
    include_private_text: bool = False,
) -> dict[str, Any]:
    action_grammar = case.expected_action_grammar
    durable_memory_written = False
    bounded_evidence_emitted = False
    source_backed_fact_emitted = False
    recalled_echo_reextracted_as_source = False
    empty_message_memory_emitted = False
    passed = (
        action_grammar in ALLOWED_ACTION_GRAMMARS
        and not durable_memory_written
        and not bounded_evidence_emitted
        and not source_backed_fact_emitted
        and not recalled_echo_reextracted_as_source
        and not empty_message_memory_emitted
    )
    payload: dict[str, Any] = {
        "case_id": case.case_id,
        "hook_stage": case.hook_stage,
        "pollution_family": case.pollution_family,
        "public_pain_family": "write_time_pollution",
        "event_shape": case.event_shape,
        "action_grammar": action_grammar,
        "foreground_result": "abstain"
        if action_grammar == "ignore_or_blocked"
        else "direction_only",
        "durable_memory_written": durable_memory_written,
        "bounded_evidence_emitted": bounded_evidence_emitted,
        "source_backed_fact_emitted": source_backed_fact_emitted,
        "recalled_echo_reextracted_as_source": recalled_echo_reextracted_as_source,
        "empty_message_memory_emitted": empty_message_memory_emitted,
        "echoed_recall_context": case.echoed_recall_context,
        "empty_or_near_empty_message": case.empty_or_near_empty_message,
        "event_hash": _hash(case.raw_event_text or case.case_id),
        "boundary_note": case.boundary_note,
        "passed": passed,
    }
    if include_private_text:
        payload["raw_event_text"] = case.raw_event_text
    return payload


def run_auto_hook_pollution_fixture_report(*, include_private_text: bool = False) -> dict[str, Any]:
    cases = [
        evaluate_auto_hook_pollution_case(case, include_private_text=include_private_text)
        for case in auto_hook_pollution_cases()
    ]
    stage_counts = Counter(str(case["hook_stage"]) for case in cases)
    family_counts = Counter(str(case["pollution_family"]) for case in cases)
    grammar_counts = Counter(str(case["action_grammar"]) for case in cases)
    metrics = {
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case["passed"]),
        "failed_count": sum(1 for case in cases if not case["passed"]),
        "hook_stage_counts": dict(stage_counts),
        "pollution_family_counts": dict(family_counts),
        "action_grammar_counts": dict(grammar_counts),
        "durable_memory_write_count": sum(1 for case in cases if case["durable_memory_written"]),
        "bounded_evidence_count": sum(1 for case in cases if case["bounded_evidence_emitted"]),
        "source_backed_fact_count": sum(1 for case in cases if case["source_backed_fact_emitted"]),
        "recalled_echo_reextraction_count": sum(
            1 for case in cases if case["recalled_echo_reextracted_as_source"]
        ),
        "empty_message_memory_count": sum(
            1 for case in cases if case["empty_message_memory_emitted"]
        ),
        "echo_case_count": sum(1 for case in cases if case["echoed_recall_context"]),
        "empty_run_id_case_count": sum(
            1 for case in cases if case["empty_or_near_empty_message"]
        ),
        "at_most_direction_only_count": sum(
            1 for case in cases if case["action_grammar"] in ALLOWED_ACTION_GRAMMARS
        ),
    }
    ok = (
        metrics["case_count"] >= 6
        and metrics["passed_count"] == metrics["case_count"]
        and metrics["durable_memory_write_count"] == 0
        and metrics["bounded_evidence_count"] == 0
        and metrics["source_backed_fact_count"] == 0
        and metrics["recalled_echo_reextraction_count"] == 0
        and metrics["empty_message_memory_count"] == 0
        and metrics["echo_case_count"] >= 1
        and metrics["empty_run_id_case_count"] >= 1
    )
    return {
        "schema_version": 1,
        "kind": "auto_hook_pollution_fixture_report",
        "source_issue": "https://github.com/Sapientropic/AIppocampus/issues/986",
        "source_map": "docs/research/memory-system-pain-taxonomy.md",
        "ok": ok,
        "metrics": metrics,
        "cases": cases,
        "privacy_boundary": {
            "raw_event_text_emitted": bool(include_private_text),
            "raw_hook_payload_emitted": False,
            "absolute_paths_emitted": False,
        },
        "claim_boundary": (
            "Synthetic auto-capture pollution fixtures for authority boundaries; "
            "not a live hook-write or competitor-behavior measurement."
        ),
        "cannot_claim": AUTO_HOOK_CANNOT_CLAIM,
    }
