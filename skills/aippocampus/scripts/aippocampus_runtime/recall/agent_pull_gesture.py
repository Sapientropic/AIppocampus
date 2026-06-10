"""Default agent-initiated recall gesture fixture.

The gesture is the copyable product move over the smaller recall/deepen/explain
facade: detect a continuity-sensitive task, pull a compact packet, use low-risk
orientation when allowed, and deepen/reopen source before claims.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.navigation import attention_router_contract
from aippocampus_runtime.recall import agent_facade_contract

GESTURE_NAME = "source_backed_continuity_gesture_v1"
SCHEMA_VERSION = "agent-pull-gesture-v0"
FOREGROUND_PACKET_BYTE_BUDGET = agent_facade_contract.FOREGROUND_PACKET_BYTE_BUDGET


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _route_packet(
    *,
    route_id: str,
    source_handles: list[dict[str, Any]] | None = None,
    bounded_summary: dict[str, Any] | None = None,
    hard_masks: list[str] | None = None,
    source_open: bool = False,
    bounded_scope: bool = False,
) -> dict[str, Any]:
    return attention_router_contract.build_route_packet(
        {
            "case_id": route_id,
            "route_id": route_id,
            "source_handles": source_handles or [],
            "bounded_summary": bounded_summary,
            "hard_masks": hard_masks or [],
            "source_open": source_open,
            "bounded_scope": bounded_scope,
            "head_votes": [{"head": "gesture_head", "score": 0.84, "reason_code": "agent_pull_trigger"}],
        }
    )


def _summary(scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "source_coverage": ["issue:#1130", "doc:agent-native-recall-facade"],
        "freshness": "current",
        "reopen_path": f"deepen:{scope.replace(':', '_')}",
        "summary_text": "PRIVATE_SOURCE_SENTINEL",
    }


def _handle(segment_id: str) -> dict[str, Any]:
    return {
        "source_id": "clean:public-agent-pull-fixture",
        "segment_id": segment_id,
        "line_range": [10, 18],
        "reopen_required": True,
        "source_text": "PRIVATE_SOURCE_SENTINEL",
    }


def _packet_case(
    *,
    case_id: str,
    surface: str,
    trigger: str,
    route_packet: dict[str, Any],
    bounded_summary_sufficient: bool = False,
    deepen_required: bool = False,
    aippo_activation_attempted: bool = False,
    aippo_activation_succeeded: bool = False,
    hook_output_seen: bool = False,
) -> dict[str, Any]:
    memory_packet = agent_facade_contract.memory_packet_from_route_packet(route_packet)
    deepen_result = agent_facade_contract.deepen_route_packet(route_packet) if deepen_required else None
    next_safe_action = "reopen_source" if deepen_required else memory_packet["next_action"]
    return {
        "case_id": case_id,
        "surface": surface,
        "trigger": trigger,
        "should_pull": True,
        "hook_output_seen": hook_output_seen,
        "memory_packet": memory_packet,
        "foreground_packet_bytes": _json_bytes(memory_packet),
        "next_safe_action": next_safe_action,
        "bounded_summary_sufficient": bounded_summary_sufficient,
        "deepen_required": deepen_required,
        "deepen_followed": bool(deepen_required and deepen_result is not None),
        "deepen_result": deepen_result,
        "aippo_activation_attempted": aippo_activation_attempted,
        "aippo_activation_succeeded": aippo_activation_succeeded,
        "reason_codes": [trigger],
        "time_to_first_useful_packet_ms_proxy": 32,
    }


def _no_pull_case(case_id: str, *, trigger: str, reason_codes: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "surface": "agent_native_facade",
        "trigger": trigger,
        "should_pull": False,
        "hook_output_seen": False,
        "memory_packet": None,
        "foreground_packet_bytes": 0,
        "next_safe_action": "stay_silent",
        "bounded_summary_sufficient": False,
        "deepen_required": False,
        "deepen_followed": False,
        "deepen_result": None,
        "aippo_activation_attempted": False,
        "aippo_activation_succeeded": False,
        "reason_codes": reason_codes,
        "time_to_first_useful_packet_ms_proxy": 0,
    }


def fixture_agent_pull_cases() -> list[dict[str, Any]]:
    return [
        _packet_case(
            case_id="fresh_thread_magic_moment",
            surface="agent_native_facade",
            trigger="continuity_sensitive_vague_cue",
            route_packet=_route_packet(
                route_id="route_fresh_thread_magic_moment",
                source_handles=[_handle("seg-magic")],
                bounded_summary=_summary("fresh-thread/source-backed-continuity"),
            ),
            bounded_summary_sufficient=True,
        ),
        _packet_case(
            case_id="low_risk_style_hint",
            surface="human_cli",
            trigger="ordinary_collaboration_style",
            route_packet=_route_packet(
                route_id="route_low_risk_style_hint",
                source_handles=[_handle("seg-style")],
                bounded_summary=_summary("project:AIppocampus/collaboration-style"),
            ),
            bounded_summary_sufficient=True,
        ),
        _packet_case(
            case_id="project_aippo_activation",
            surface="agent_native_facade",
            trigger="known_project_aippo_named",
            route_packet=_route_packet(
                route_id="aippo_project_workflow_activation",
                source_handles=[_handle("seg-aippo")],
                bounded_summary=_summary("aippo:project-workflow"),
            ),
            aippo_activation_attempted=True,
            aippo_activation_succeeded=True,
        ),
        _packet_case(
            case_id="public_claim_requires_deepen",
            surface="hook_plus_pull",
            trigger="source_backed_public_claim",
            route_packet=_route_packet(
                route_id="route_public_claim_reopen",
                source_handles=[_handle("seg-claim")],
            ),
            deepen_required=True,
            hook_output_seen=True,
        ),
        _no_pull_case(
            "negative_small_talk_no_pull",
            trigger="low_continuity_small_talk",
            reason_codes=["no_continuity_need", "no_pull"],
        ),
        _no_pull_case(
            "anti_nag_repeated_pull_suppressed",
            trigger="recent_duplicate_pull",
            reason_codes=["anti_nag_recent_pull", "no_new_source_cue"],
        ),
    ]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def build_agent_pull_gesture_fixture_report() -> dict[str, Any]:
    cases = fixture_agent_pull_cases()
    pull_cases = [case for case in cases if case["should_pull"]]
    packet_cases = [case for case in cases if case["memory_packet"] is not None]
    deepen_required = [case for case in cases if case["deepen_required"]]
    aippo_attempted = [case for case in cases if case["aippo_activation_attempted"]]
    foreground_packet_max_bytes = max(case["foreground_packet_bytes"] for case in cases)
    unnecessary_pull_count = sum(
        1
        for case in cases
        if not case["should_pull"] and case["memory_packet"] is not None
    )
    source_backed_claim_without_reopen = sum(
        1
        for case in cases
        if case["trigger"] == "source_backed_public_claim"
        and not case["deepen_followed"]
    )
    constant_memory_fishing_count = sum(
        1
        for case in cases
        if not case["should_pull"] and "anti_nag_recent_pull" not in case["reason_codes"]
        and case["memory_packet"] is not None
    )
    red_lines = {
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
        "constant_memory_fishing_count": constant_memory_fishing_count,
        "foreground_packet_budget_violation_count": sum(
            1 for case in packet_cases if case["foreground_packet_bytes"] > FOREGROUND_PACKET_BYTE_BUDGET
        ),
    }
    metrics = {
        "agent_pull_follow_through_rate": _rate(len(packet_cases), len(pull_cases)),
        "deepen_required_follow_through_rate": _rate(
            sum(1 for case in deepen_required if case["deepen_followed"]),
            len(deepen_required),
        ),
        "aippo_activation_success_rate": _rate(
            sum(1 for case in aippo_attempted if case["aippo_activation_succeeded"]),
            len(aippo_attempted),
        ),
        "bounded_summary_sufficient_count": sum(
            1 for case in cases if case["bounded_summary_sufficient"]
        ),
        "useful_packet_rate": _rate(len(packet_cases), len(pull_cases)),
        "foreground_packet_max_bytes": foreground_packet_max_bytes,
        "time_to_first_useful_packet_ms_proxy": max(
            case["time_to_first_useful_packet_ms_proxy"] for case in cases
        ),
        "manual_query_invention_count": 0,
        "unnecessary_pull_count": unnecessary_pull_count,
        "wrong_route_drag_count": 0,
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
    }
    return {
        "kind": "aippocampus_agent_pull_gesture_fixture",
        "schema_version": SCHEMA_VERSION,
        "gesture_name": GESTURE_NAME,
        "ok": all(value == 0 for value in red_lines.values()),
        "reference_workflow": [
            "detect continuity-sensitive task",
            "recall(query, context) instead of waiting only for hook output",
            "use compact MemoryPacket or AIppo activation packet",
            "deepen(route_id) when exact, public, disputed, stale, sensitive, or high-risk claims are ahead",
            "record lightweight outcome feedback",
        ],
        "api_examples": {
            "human_cli": 'aippocampus search "distinctive old phrase"',
            "agent_native_facade": "recall(query, context) -> MemoryPacket[]",
            "hook_plus_pull": "use hook scent, then recall/deepen when task risk rises",
        },
        "surface_coverage": sorted({case["surface"] for case in cases if case["should_pull"]}),
        "foreground_packet_budget_bytes": FOREGROUND_PACKET_BYTE_BUDGET,
        "cases": cases,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_prompt_text_emitted": False,
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_in_foreground_packets": False,
        },
        "cannot_claim": [
            "agents_should_call_memory_every_turn",
            "aippos_are_claim_ready_facts",
            "bounded_summaries_replace_source_evidence",
            "broad_agent_adoption",
            "docker_like_ecosystem_position",
        ],
    }
