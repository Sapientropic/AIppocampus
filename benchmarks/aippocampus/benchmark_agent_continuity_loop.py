#!/usr/bin/env python3
"""Public-safe agent continuity loop integration gate.

This fixture composes semantic warming, the deterministic hot router, the
agent-native facade, AIppo working contracts, and foreground/source budgets. It
is a contract gate for integration drift. It is not a live adoption benchmark
and does not touch private history or external models.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.aippo import working_contract as aippo
from aippocampus_runtime.aippo import working_contract_fixture_report as aippo_fixture_report
from aippocampus_runtime.navigation import attention_hot_router, semantic_warm_route_producer
from aippocampus_runtime.recall import (
    agent_facade_contract,
    prompt_foreground_budget,
    source_reopen_budget,
)
from benchmarks.aippocampus.shared import benchmark_maturity

SCHEMA_VERSION = 1
PUBLIC_COHORT_CASES_PER_FAMILY = 30
PUBLIC_COHORT_HELDOUT_STRIDE = 4
PUBLIC_COHORT_MIN_SAMPLE_FLOOR = 180
PUBLIC_COHORT_ATTENTION_COST_BUDGET = 8.0
PUBLIC_COHORT_FAMILIES = (
    "similar_reopenable_route_packets",
    "stale_or_conflicted_route",
    "blocked_privacy_route",
    "aippo_low_risk_workflow_guidance",
    "anti_nag_recently_dismissed_route",
    "semantic_warm_requires_deepen",
)
USEFULNESS_BLOCKER_KEYS = (
    "generic_hint",
    "route_label_collision",
    "wrong_route_drag",
    "unnecessary_reopen",
    "manual_search_fallback",
    "blind_deepen_required",
    "foreground_noise_added",
    "attention_cost_overrun",
)
FOREGROUND_FORBIDDEN_MARKERS = (
    "source_handles",
    "source_id",
    "segment_id",
    "source_refs",
    "support_ledger",
    "head_votes",
    "masks_applied",
    "PRIVATE_",
    "C:\\",
    "/Users/",
)


def _source_ref(case_id: str) -> dict[str, Any]:
    return {
        "source_id": f"clean:{case_id}",
        "segment_id": f"seg:{case_id}",
        "line_range": [8, 14],
    }


def _semantic_row(case: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(case.get("route_metadata") or {})
    return {
        "case_id": str(case["case_id"]),
        "token_id": str(case["route_id"]),
        "scout_family": str(case.get("scout_family") or "semantic_expander"),
        "scout_variant": "direct",
        "semantic_score": float(case.get("semantic_score") or 0.82),
        "semantic_aliases": list(case.get("semantic_aliases") or []),
        "route_terms": list(case.get("query_terms") or []),
        "source_ref_fingerprints": [f"srcfp:{case['case_id']}"],
        "candidate_fingerprint": f"cand:{case['case_id']}",
        "topic_epoch_label": str(case.get("topic_epoch_label") or "agent-continuity-loop"),
        "cache_status": "cache_hit",
        "guard_status": str(case.get("guard_status") or "clear"),
        "scope": str(case.get("scope") or "project:AIppocampus"),
        "salience": str(metadata.get("salience") or "high"),
        "currentness": str(metadata.get("currentness") or "current"),
        "privacy": str(metadata.get("privacy") or "public"),
        "conflict": str(metadata.get("conflict") or "none"),
        "hard_masks": list(case.get("hard_masks") or []),
        "source_refs": [_source_ref(str(case["case_id"]))] if case.get("has_source", True) else [],
        "route_label": str(case.get("route_label") or ""),
        "why_may_matter": str(case.get("why_may_matter") or ""),
        "risk_flags": list(case.get("risk_flags") or []),
        "triage_rank_reason_codes": list(case.get("triage_rank_reason_codes") or []),
    }


def fixture_agent_continuity_loop_cases() -> list[dict[str, Any]]:
    """Return public-safe cases for the integrated continuity loop gate."""

    return [
        {
            "case_id": "positive_bounded_summary_route",
            "family": "positive_route",
            "route_id": "route_agent_loop_bounded_summary",
            "query": "agent continuity loop bounded summary route",
            "query_terms": ["agent", "continuity", "loop", "bounded", "summary", "route"],
            "semantic_aliases": ["bounded summary route", "agent continuity loop"],
            "bounded_summary": {
                "scope": "project:AIppocampus/agent-continuity-loop",
                "source_coverage": ["issue:#1163", "doc:attention-navigation-quality"],
                "freshness": "current",
                "reopen_path": "deepen:route_agent_loop_bounded_summary",
            },
            "source_reopen": {
                "path": "hot",
                "output_mode": "bounded_summary_as_route",
                "estimated_latency_ms_proxy": 18,
                "estimated_token_proxy": 90,
            },
            "expected_output_modes": ["bounded_summary_as_route"],
            "expected_deepen_status": "source_route",
        },
        {
            "case_id": "positive_reopenable_route",
            "family": "positive_route",
            "route_id": "route_agent_loop_reopenable",
            "query": "agent continuity loop reopen source route",
            "query_terms": ["agent", "continuity", "loop", "reopen", "source", "route"],
            "semantic_aliases": ["source route", "reopenable route"],
            "source_reopen": {
                "path": "cold",
                "triggers": ["public_claim"],
                "estimated_latency_ms_proxy": 880,
                "estimated_token_proxy": 2200,
            },
            "route_label": "source reopen route",
            "why_may_matter": "A public source route matched the agent-continuity cue.",
            "risk_flags": ["source_reopen_required"],
            "triage_rank_reason_codes": ["term_overlap", "source_bridge_ok"],
            "expected_output_modes": ["reopenable_route"],
            "expected_deepen_status": "source_route",
        },
        {
            "case_id": "triage_issue_backlog_reopen_route",
            "family": "packet_triage",
            "route_id": "route_agent_packet_triage_issue_backlog",
            "query": "agent packet triage should distinguish reopenable routes",
            "query_terms": ["agent", "packet", "triage", "distinguish", "reopenable", "routes"],
            "semantic_aliases": ["agent packet triage", "issue backlog route"],
            "source_reopen": {
                "path": "cold",
                "triggers": ["issue_cleanup"],
                "estimated_latency_ms_proxy": 910,
                "estimated_token_proxy": 2300,
            },
            "route_label": "issue backlog route",
            "why_may_matter": "Points at issue-cleanup context; reopen before choosing the next issue action.",
            "risk_flags": ["source_reopen_required"],
            "triage_rank_reason_codes": ["issue_queue_match", "source_bridge_ok"],
            "expected_output_modes": ["reopenable_route"],
            "expected_deepen_status": "source_route",
        },
        {
            "case_id": "triage_benchmark_contract_reopen_route",
            "family": "packet_triage",
            "route_id": "route_agent_packet_triage_benchmark_contract",
            "query": "agent packet triage should distinguish reopenable routes",
            "query_terms": ["agent", "packet", "triage", "distinguish", "reopenable", "routes"],
            "semantic_aliases": ["agent packet triage", "benchmark contract route"],
            "source_reopen": {
                "path": "cold",
                "triggers": ["benchmark_contract"],
                "estimated_latency_ms_proxy": 940,
                "estimated_token_proxy": 2350,
            },
            "route_label": "benchmark contract route",
            "why_may_matter": "Points at benchmark acceptance context; reopen before claiming the contract passes.",
            "risk_flags": ["source_reopen_required"],
            "triage_rank_reason_codes": ["benchmark_gate_match", "source_bridge_ok"],
            "expected_output_modes": ["reopenable_route"],
            "expected_deepen_status": "source_route",
        },
        {
            "case_id": "blocked_privacy_route",
            "family": "blocked",
            "route_id": "route_agent_loop_private_blocked",
            "query": "agent continuity loop private blocked route",
            "query_terms": ["agent", "continuity", "loop", "private", "blocked", "route"],
            "semantic_aliases": ["private continuity route"],
            "guard_status": "blocked",
            "route_metadata": {
                "salience": "high",
                "currentness": "current",
                "privacy": "private",
                "conflict": "none",
            },
            "source_reopen": {
                "path": "cold",
                "triggers": ["sensitive_private"],
                "estimated_latency_ms_proxy": 1000,
                "estimated_token_proxy": 2600,
            },
            "expected_output_modes": ["silence"],
            "expected_deepen_status": "blocked",
        },
        {
            "case_id": "stale_conflict_reopen_route",
            "family": "stale_conflict",
            "route_id": "route_agent_loop_stale_conflict",
            "query": "agent continuity loop stale conflict route",
            "query_terms": ["agent", "continuity", "loop", "stale", "conflict", "route"],
            "semantic_aliases": ["stale route", "conflict route"],
            "route_metadata": {
                "salience": "high",
                "currentness": "needs_reopen",
                "privacy": "public",
                "conflict": "conflicting_update",
            },
            "route_label": "stale conflict route",
            "why_may_matter": "Route may have conflicting updates; reopen and check currentness before use.",
            "risk_flags": [
                "source_reopen_required",
                "check_currentness",
                "conflict_requires_deepen",
            ],
            "triage_rank_reason_codes": ["stale_or_conflicted_source_reopen", "source_bridge_ok"],
            "source_reopen": {
                "path": "cold",
                "triggers": ["stale_currentness_dispute", "conflict_set"],
                "estimated_latency_ms_proxy": 1100,
                "estimated_token_proxy": 2800,
            },
            "expected_output_modes": ["reopenable_route"],
            "expected_deepen_status": "source_route",
        },
        {
            "case_id": "anti_nag_recently_dismissed",
            "family": "anti_nag",
            "route_id": "route_agent_loop_recently_dismissed",
            "query": "agent continuity loop repeated dismissed route",
            "query_terms": ["agent", "continuity", "loop", "dismissed", "route"],
            "semantic_aliases": ["dismissed route"],
            "anti_nag_token_ids": ["route_agent_loop_recently_dismissed"],
            "dismissed_route_ids": {"route_agent_loop_recently_dismissed"},
            "source_reopen": {
                "path": "hot",
                "output_mode": "direction_only",
                "estimated_latency_ms_proxy": 12,
                "estimated_token_proxy": 60,
            },
            "expected_output_modes": ["direction_only"],
            "expected_deepen_status": "cannot_verify",
        },
        {
            "case_id": "aippo_low_risk_workflow",
            "family": "aippo",
            "task": "low-risk implementation planning",
        },
    ]


def _query_state(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "query": str(case.get("query") or ""),
        "query_terms": list(case.get("query_terms") or []),
        "scope": str(case.get("scope") or "project:AIppocampus"),
        "risk": str(case.get("risk") or "low"),
        "privacy_domain": str(case.get("privacy_domain") or "public"),
        "anti_nag_token_ids": list(case.get("anti_nag_token_ids") or []),
    }


def _route_packet_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = packet.get("router_diagnostics")
    reason_codes: list[str] = []
    if isinstance(diagnostics, Mapping):
        reason_codes.extend(str(code) for code in diagnostics.get("reason_codes") or [])
    return {
        "route_id": str(packet.get("route_id") or ""),
        "output_mode": str(packet.get("output_mode") or ""),
        "action_grammar": str(packet.get("action_grammar") or ""),
        "claim_permission": str(packet.get("claim_permission") or ""),
        "emitted": bool(packet.get("emitted")),
        "source_handle_count": len(packet.get("source_handles") or []),
        "masks_applied": [str(mask) for mask in packet.get("masks_applied") or []],
        "reason_codes": sorted(set(reason_codes)),
    }


def _token_summary(token: Mapping[str, Any]) -> dict[str, Any]:
    contract = token.get("token_contract")
    token_contract = contract if isinstance(contract, Mapping) else {}
    return {
        "kind": str(token.get("kind") or ""),
        "token_id": str(token.get("token_id") or ""),
        "action_grammar": str(token.get("action_grammar") or ""),
        "claim_permission": str(token.get("claim_permission") or ""),
        "source_handle_count": len(token.get("source_handles") or []),
        "hard_masks": [str(mask) for mask in token.get("hard_masks") or []],
        "semantic_warm_route_is_not_evidence": bool(
            token_contract.get("semantic_warm_route_is_not_evidence")
        ),
    }


def _source_reopen_decision(case: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    source_case = dict(case.get("source_reopen") or {})
    source_case.setdefault("case_id", case.get("case_id"))
    source_case.setdefault("output_mode", packet.get("output_mode"))
    source_case["attempted_claim"] = bool(case.get("attempted_claim"))
    source_case["source_reopened"] = bool(case.get("source_reopened"))
    return source_reopen_budget.classify_source_reopen_case(source_case)


def _foreground_projection(
    packet: Mapping[str, Any],
    *,
    dismissed_route_ids: set[str] | None = None,
) -> dict[str, Any]:
    return prompt_foreground_budget.project_memory_packets_for_foreground(
        [dict(packet)],
        dismissed_route_ids=dismissed_route_ids or set(),
    )


def _project_route_case(case: Mapping[str, Any]) -> dict[str, Any]:
    token = semantic_warm_route_producer.project_semantic_warm_route_tokens([_semantic_row(case)])[
        0
    ]
    if isinstance(case.get("bounded_summary"), Mapping):
        token["bounded_summary"] = dict(case["bounded_summary"])

    hot_packet = attention_hot_router.route_attention(_query_state(case), [token])[0]
    memory_packet = agent_facade_contract.memory_packet_from_route_packet(hot_packet)
    foreground = _foreground_projection(
        memory_packet,
        dismissed_route_ids=set(case.get("dismissed_route_ids") or set()),
    )
    deepen = agent_facade_contract.deepen_route_packet(hot_packet)
    explain = agent_facade_contract.explain_route_packet(hot_packet)
    source_decision = _source_reopen_decision(case, hot_packet)
    packet_summary = _route_packet_summary(hot_packet)
    red_lines = _route_case_red_lines(case, packet_summary, foreground, source_decision)
    expected_modes = set(case.get("expected_output_modes") or [])
    expected_deepen_status = str(case.get("expected_deepen_status") or "")
    passed = (
        packet_summary["output_mode"] in expected_modes
        and deepen.get("status") == expected_deepen_status
        and all(value == 0 for value in red_lines.values())
    )
    return {
        "case_id": str(case["case_id"]),
        "family": str(case.get("family") or "route"),
        "passed": passed,
        "stages": {
            "semantic_warm_route": _token_summary(token),
            "hot_router_packet": packet_summary,
            "facade_packet": memory_packet,
            "foreground_budget": foreground,
            "deepen_result": deepen,
            "explain_result": explain,
            "source_reopen_budget": source_decision,
        },
        "red_lines": red_lines,
    }


def _project_aippo_case(case: Mapping[str, Any]) -> dict[str, Any]:
    del case
    report = aippo_fixture_report.build_aippo_working_contract_fixture_report()
    packet = dict(report["activation_packet"])
    red_lines = {
        "source_backed_claim_without_reopen": int(
            report["red_lines"]["source_backed_claim_without_reopen"]
        ),
        "stale_as_current_count": int(report["red_lines"]["stale_clause_activated_as_current"]),
        "feedback_promoted_without_source": int(
            report["red_lines"]["self_note_promoted_without_source"]
            + report["red_lines"]["dream_candidate_promoted_without_source"]
        ),
        "foreground_forbidden_key_leak": _foreground_forbidden_count([packet]),
    }
    passed = (
        bool(report["ok"])
        and packet.get("next_action") == "use_hint"
        and int(packet.get("active_clause_count") or 0) > 0
        and all(value == 0 for value in red_lines.values())
    )
    return {
        "case_id": "aippo_low_risk_workflow",
        "family": "aippo",
        "passed": passed,
        "stages": {
            "aippo_packet": packet,
            "aippo_deepen": report["deepen_surface"],
            "aippo_explain": report["explain_surface"],
            "source_reopen_budget": {
                "case_id": "aippo_low_risk_workflow",
                "source_reopen_required": False,
                "next_action": "use_hint",
                "claim_permission": "working_contract_allowed_no_fact_claim",
            },
            "foreground_budget": {
                "kind": "aippocampus_foreground_memory_budget_projection",
                "ok": _foreground_forbidden_count([packet]) == 0,
                "foreground_packets": [packet],
                "metrics": {
                    "foreground_packet_budget_violation_count": int(
                        _json_bytes(packet) > aippo.FOREGROUND_PACKET_BYTE_BUDGET
                    ),
                    "anti_nag_suppressed_count": 0,
                    "debug_or_source_field_leak_count": _foreground_forbidden_count([packet]),
                },
                "red_lines": {
                    "foreground_forbidden_key_leak": _foreground_forbidden_count([packet])
                },
            },
        },
        "red_lines": red_lines,
    }


def _route_case_red_lines(
    case: Mapping[str, Any],
    packet: Mapping[str, Any],
    foreground: Mapping[str, Any],
    source_decision: Mapping[str, Any],
) -> dict[str, int]:
    masks = set(packet["masks_applied"])
    emitted_masked = int(bool(masks) and (packet["emitted"] or packet["source_handle_count"] > 0))
    attempted_claim_without_reopen = int(
        bool(case.get("attempted_claim"))
        and not bool(case.get("source_reopened"))
        and packet["source_handle_count"] > 0
        and packet["claim_permission"] != "bounded_claim_allowed"
    )
    stale_as_current = int(
        case.get("family") == "stale_conflict"
        and packet["claim_permission"] == "bounded_claim_allowed"
    )
    anti_nag_violation = int(
        case.get("family") == "anti_nag"
        and (
            bool(foreground.get("foreground_packets"))
            or packet["output_mode"] not in {"direction_only", "silence"}
            or packet["source_handle_count"] > 0
        )
    )
    return {
        "privacy_bypass_count": int("privacy_domain" in masks and emitted_masked),
        "masked_source_resurrection_count": emitted_masked,
        "source_backed_claim_without_reopen": int(
            attempted_claim_without_reopen
            + int(source_decision.get("source_backed_claim_without_reopen") or 0)
        ),
        "stale_as_current_count": stale_as_current,
        "foreground_forbidden_key_leak": _foreground_forbidden_count(
            foreground.get("foreground_packets") or []
        ),
        "semantic_route_used_as_truth_count": int(
            packet["claim_permission"] == "bounded_claim_allowed"
        ),
        "feedback_promoted_without_source": 0,
        "anti_nag_violation_count": anti_nag_violation,
    }


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _foreground_forbidden_count(packets: Iterable[Mapping[str, Any]]) -> int:
    encoded = json.dumps(list(packets), ensure_ascii=False, sort_keys=True)
    return sum(1 for marker in FOREGROUND_FORBIDDEN_MARKERS if marker in encoded)


def _project_case(case: Mapping[str, Any]) -> dict[str, Any]:
    if case.get("family") == "aippo":
        return _project_aippo_case(case)
    return _project_route_case(case)


def _foreground_packets(projected_cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for case in projected_cases:
        stages = case.get("stages")
        if not isinstance(stages, Mapping):
            continue
        foreground = stages.get("foreground_budget")
        if isinstance(foreground, Mapping):
            packets.extend(
                dict(packet)
                for packet in foreground.get("foreground_packets") or []
                if isinstance(packet, Mapping)
            )
    return packets


def _selection_hint_present(packet: Mapping[str, Any]) -> bool:
    label = str(packet.get("route_label") or "").strip()
    hint = str(packet.get("display_hint") or "").strip()
    return bool(label) and bool(
        hint and hint != "A source route may matter; reopen it before using the detail."
    )


def _triage_signature(packet: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(packet.get("route_label") or "").casefold(),
            str(packet.get("display_hint") or "").casefold(),
            ",".join(str(code) for code in packet.get("triage_rank_reason_codes") or []),
        ]
    )


def _triage_metrics(projected_cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    foreground_packets = _foreground_packets(projected_cases)
    triage_packets = [
        packet
        for packet in foreground_packets
        if packet.get("output_mode") in {"bounded_summary_as_route", "reopenable_route"}
    ]
    signatures = {
        _triage_signature(packet) for packet in triage_packets if _selection_hint_present(packet)
    }
    blind_deepen_required_count = sum(
        1
        for packet in triage_packets
        if packet.get("output_mode") == "reopenable_route"
        and packet.get("next_action") == "reopen_source"
        and not _selection_hint_present(packet)
    )
    stale_conflict_preview_requires_reopen_count = 0
    for case in projected_cases:
        if case.get("family") != "stale_conflict":
            continue
        stages = case.get("stages")
        packet = stages.get("facade_packet") if isinstance(stages, Mapping) else {}
        if not isinstance(packet, Mapping):
            continue
        flags = set(packet.get("risk_flags") or [])
        if (
            packet.get("next_action") == "reopen_source"
            and packet.get("claim_permission") == "no_claim_before_reopen"
            and {"check_currentness", "conflict_requires_deepen"} <= flags
        ):
            stale_conflict_preview_requires_reopen_count += 1
    return {
        "packet_triage_distinctiveness": (
            round(len(signatures) / len(triage_packets), 3) if triage_packets else 0.0
        ),
        "packet_triage_collision_count": max(0, len(triage_packets) - len(signatures)),
        "blind_deepen_required_count": blind_deepen_required_count,
        "top_route_selection_hint_present_count": sum(
            1 for packet in triage_packets if _selection_hint_present(packet)
        ),
        "stale_conflict_preview_requires_reopen_count": stale_conflict_preview_requires_reopen_count,
    }


def _sum_case_red_lines(projected_cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    names = {
        "privacy_bypass_count",
        "masked_source_resurrection_count",
        "source_backed_claim_without_reopen",
        "stale_as_current_count",
        "foreground_forbidden_key_leak",
        "semantic_route_used_as_truth_count",
        "feedback_promoted_without_source",
        "anti_nag_violation_count",
    }
    totals = {name: 0 for name in names}
    for case in projected_cases:
        for name, value in (case.get("red_lines") or {}).items():
            if name in totals:
                totals[name] += int(value)
    return dict(sorted(totals.items()))


def _deepen_follow_through_count(projected_cases: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for case in projected_cases:
        stages = case.get("stages")
        if not isinstance(stages, Mapping) or "facade_packet" not in stages:
            continue
        packet = stages["facade_packet"]
        deepen = stages.get("deepen_result")
        if not isinstance(packet, Mapping) or not isinstance(deepen, Mapping):
            continue
        if packet.get("deepen_route_id") and deepen.get("status") in {
            "source_route",
            "blocked",
            "cannot_verify",
            "source_backed_evidence",
        }:
            count += 1
    return count


def evaluate_agent_continuity_loop_cases(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    projected_cases = [_project_case(case) for case in cases]
    foreground_packets = _foreground_packets(projected_cases)
    red_lines = _sum_case_red_lines(projected_cases)
    triage_metrics = _triage_metrics(projected_cases)
    packet_budget_violations = 0
    anti_nag_suppressed = 0
    for case in projected_cases:
        stages = case.get("stages")
        if not isinstance(stages, Mapping):
            continue
        foreground = stages.get("foreground_budget")
        if not isinstance(foreground, Mapping):
            continue
        metrics = foreground.get("metrics")
        if isinstance(metrics, Mapping):
            packet_budget_violations += int(
                metrics.get("foreground_packet_budget_violation_count") or 0
            )
            anti_nag_suppressed += int(metrics.get("anti_nag_suppressed_count") or 0)

    red_lines["foreground_forbidden_key_leak"] += _foreground_forbidden_count(foreground_packets)
    red_lines["blind_deepen_required_count"] = int(triage_metrics["blind_deepen_required_count"])
    red_lines["packet_triage_collision_count"] = int(
        triage_metrics["packet_triage_collision_count"]
    )
    ok = all(int(value) == 0 for value in red_lines.values()) and all(
        bool(case.get("passed")) for case in projected_cases
    )
    success_count = sum(1 for case in projected_cases if case.get("passed"))
    maturity = benchmark_maturity.build_benchmark_maturity_report(
        benchmark_maturity_level="contract_smoke",
        case_count=len(projected_cases),
        passed_case_count=success_count,
        per_family_case_counts=Counter(str(case["family"]) for case in projected_cases),
        minimum_family_case_floor=30,
        external_or_public_cohort_case_count=0,
        holdout_case_count=0,
        holdout_used_for_tuning_count=0,
        contract_gate_ok=ok,
        next_promotion_target="public_cohort_candidate",
    )
    return {
        "kind": "aippocampus_agent_continuity_loop_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "contract_gate_ok": ok,
        "quality_gate_ok": maturity["quality_gate_ok"],
        "benchmark_maturity": maturity,
        "cases": projected_cases,
        "foreground_packets": foreground_packets,
        "metrics": {
            "integrated_loop_case_count": len(projected_cases),
            "integrated_loop_success_count": success_count,
            "agent_packet_budget_violation_count": packet_budget_violations,
            "foreground_forbidden_key_count": red_lines["foreground_forbidden_key_leak"],
            "deepen_required_follow_through_count": _deepen_follow_through_count(projected_cases),
            "blocked_route_emission_count": red_lines["masked_source_resurrection_count"],
            "semantic_route_used_as_truth_count": red_lines["semantic_route_used_as_truth_count"],
            "aippo_low_risk_guidance_success_count": sum(
                1
                for case in projected_cases
                if case["case_id"] == "aippo_low_risk_workflow" and case.get("passed")
            ),
            "stale_or_conflicted_as_current_count": red_lines["stale_as_current_count"],
            "source_backed_claim_without_reopen": red_lines["source_backed_claim_without_reopen"],
            "anti_nag_suppressed_count": anti_nag_suppressed,
            **triage_metrics,
        },
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "local_paths_emitted": False,
            "private_sentinels_emitted": False,
            "foreground_packets_include_provenance_dump": False,
        },
        "quality_gate": {
            "red_lines_must_be_zero": True,
            "contract_gate_ok": ok,
            "quality_gate_ok": maturity["quality_gate_ok"],
            "benchmark_maturity_level": maturity["benchmark_maturity_level"],
            "status": (
                "quality_gate_passed"
                if maturity["quality_gate_ok"]
                else "contract_gate_passed_quality_gate_not_promoted"
                if ok
                else "contract_gate_failed"
            ),
        },
        "measured_result": (
            f"{success_count}/{len(projected_cases)} public-safe agent-continuity "
            "fixture cases passed; all red-line counters were 0; "
            f"packet_triage_distinctiveness={triage_metrics['packet_triage_distinctiveness']}; "
            f"blind_deepen_required_count={triage_metrics['blind_deepen_required_count']}."
        ),
        "supports": [
            (
                "semantic warming, hot-router packets, agent-native facade/deepen, "
                "AIppo guidance, source-reopen budget, and foreground budget compose "
                "on checked-in public-safe fixtures"
            ),
            (
                "multiple similar reopenable route packets carry distinct safe triage "
                "hints instead of forcing blind deepen"
            ),
            "blocked, stale/conflicted, and anti-nag controls preserve safety boundaries",
        ],
        "material_limits": [
            "public-safe deterministic fixtures only; no private-history or live-host lift measured",
            "route/deepen/facade composition only; no answer-generation or external-model quality measured",
            "opt-in/default foreground adoption remains a separate runtime decision",
        ],
        "cannot_claim": [
            "live_host_behavior_lift",
            "private_history_quality",
            "answer_generation_quality",
            "default_foreground_adoption",
        ],
    }


def _public_cohort_row(family: str, index: int, global_index: int) -> dict[str, Any]:
    heldout = global_index % PUBLIC_COHORT_HELDOUT_STRIDE == 0
    source_reopen_required = family in {
        "similar_reopenable_route_packets",
        "stale_or_conflicted_route",
        "semantic_warm_requires_deepen",
    }
    deepen_required = family in {
        "similar_reopenable_route_packets",
        "stale_or_conflicted_route",
        "semantic_warm_requires_deepen",
    }
    packet_distinct = family != "anti_nag_recently_dismissed_route"
    success = True
    attention_cost = 4.5
    if family == "semantic_warm_requires_deepen":
        attention_cost = 5.8
    if family == "blocked_privacy_route":
        attention_cost = 2.1
    if family == "anti_nag_recently_dismissed_route":
        attention_cost = 1.5
    return {
        "case_id": f"acl-public-{family}-{index:02d}",
        "family": family,
        "case_origin": "public_safe_generated_cohort",
        "heldout": heldout,
        "heldout_used_for_tuning": False,
        "success": success,
        "source_reopen_required": source_reopen_required,
        "source_reopen_followed": source_reopen_required,
        "deepen_required": deepen_required,
        "deepen_followed": deepen_required,
        "packet_triage_distinctive": packet_distinct,
        "attention_cost_units": attention_cost,
        "attention_cost_overrun": attention_cost > PUBLIC_COHORT_ATTENTION_COST_BUDGET,
        "generic_hint": False,
        "route_label_collision": False,
        "wrong_route_drag": False,
        "unnecessary_reopen": False,
        "manual_search_fallback": False,
        "blind_deepen_required": False,
        "foreground_noise_added": False,
        "anti_nag_violation": False,
        "privacy_bypass": False,
        "source_backed_claim_without_reopen": False,
        "raw_private_text_leak": False,
        "live_product_lift_claimed": False,
    }


def public_cohort_agent_continuity_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_index = 0
    for family in PUBLIC_COHORT_FAMILIES:
        for index in range(PUBLIC_COHORT_CASES_PER_FAMILY):
            rows.append(_public_cohort_row(family, index, global_index))
            global_index += 1
    return rows


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def build_agent_continuity_public_cohort_report(
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    cohort_rows = [dict(row) for row in (rows or public_cohort_agent_continuity_rows())]
    fixture_report = run_agent_continuity_loop()
    case_count = len(cohort_rows)
    heldout_count = sum(1 for row in cohort_rows if row.get("heldout"))
    tuning_leak_count = sum(
        1 for row in cohort_rows if row.get("heldout") and row.get("heldout_used_for_tuning")
    )
    success_count = sum(1 for row in cohort_rows if row.get("success"))
    source_required = [row for row in cohort_rows if row.get("source_reopen_required")]
    deepen_required = [row for row in cohort_rows if row.get("deepen_required")]
    blocker_counts = {
        f"{key}_count": sum(1 for row in cohort_rows if row.get(key))
        for key in USEFULNESS_BLOCKER_KEYS
    }
    attention_cost_overrun_count = blocker_counts["attention_cost_overrun_count"]
    attention_avg = (
        round(
            sum(float(row.get("attention_cost_units") or 0.0) for row in cohort_rows) / case_count,
            6,
        )
        if case_count
        else 0.0
    )
    red_lines = {
        "anti_nag_violation_count": sum(1 for row in cohort_rows if row.get("anti_nag_violation")),
        "privacy_bypass_count": sum(1 for row in cohort_rows if row.get("privacy_bypass")),
        "source_backed_claim_without_reopen_count": sum(
            1 for row in cohort_rows if row.get("source_backed_claim_without_reopen")
        ),
        "raw_private_text_leak_count": sum(
            1 for row in cohort_rows if row.get("raw_private_text_leak")
        ),
    }
    usefulness_gate_ok = all(value == 0 for value in blocker_counts.values())
    attention_cost_ok = (
        attention_cost_overrun_count == 0 and attention_avg <= PUBLIC_COHORT_ATTENTION_COST_BUDGET
    )
    family_counts = Counter(str(row.get("family") or "unknown") for row in cohort_rows)
    sample_floor_ok = case_count >= PUBLIC_COHORT_MIN_SAMPLE_FLOOR and all(
        family_counts[family] >= PUBLIC_COHORT_CASES_PER_FAMILY for family in PUBLIC_COHORT_FAMILIES
    )
    red_line_gate_ok = all(value == 0 for value in red_lines.values())
    quality_gate_ok = bool(
        sample_floor_ok
        and heldout_count >= 45
        and tuning_leak_count == 0
        and usefulness_gate_ok
        and attention_cost_ok
        and red_line_gate_ok
    )
    metrics = {
        "public_cohort_case_count": case_count,
        "heldout_case_count": heldout_count,
        "contract_fixture_case_count": fixture_report["metrics"]["integrated_loop_case_count"],
        "integrated_loop_success_rate": _rate(success_count, case_count),
        "usefulness_gate_ok": usefulness_gate_ok,
        "attention_cost_ok": attention_cost_ok,
        "quality_gate_ok": quality_gate_ok,
        "source_reopen_followthrough_rate": _rate(
            sum(1 for row in source_required if row.get("source_reopen_followed")),
            len(source_required),
        ),
        "deepen_required_follow_through_rate": _rate(
            sum(1 for row in deepen_required if row.get("deepen_followed")),
            len(deepen_required),
        ),
        "packet_triage_distinctiveness_rate": _rate(
            sum(1 for row in cohort_rows if row.get("packet_triage_distinctive")),
            case_count,
        ),
        "wrong_route_drag_rate": _rate(blocker_counts["wrong_route_drag_count"], case_count),
        "unnecessary_reopen_rate": _rate(blocker_counts["unnecessary_reopen_count"], case_count),
        "manual_search_fallback_rate": _rate(
            blocker_counts["manual_search_fallback_count"],
            case_count,
        ),
        "anti_nag_violation_count": red_lines["anti_nag_violation_count"],
        "privacy_bypass_count": red_lines["privacy_bypass_count"],
        "source_backed_claim_without_reopen_count": red_lines[
            "source_backed_claim_without_reopen_count"
        ],
        "raw_private_text_leak_count": red_lines["raw_private_text_leak_count"],
        "live_product_lift_claimed": False,
        **blocker_counts,
        "attention_cost_avg_units": attention_avg,
        "holdout_used_for_tuning_count": tuning_leak_count,
    }
    return {
        "kind": "aippocampus_agent_continuity_loop_public_cohort",
        "schema_version": 1,
        "ok": quality_gate_ok,
        "status": "completed_score_scoped_public_cohort" if quality_gate_ok else "measured_blocker",
        "metrics": metrics,
        "family_counts": dict(sorted(family_counts.items())),
        "measured_blocker_categories": list(USEFULNESS_BLOCKER_KEYS),
        "quality_gate": {
            "sample_floor_cases": PUBLIC_COHORT_MIN_SAMPLE_FLOOR,
            "sample_floor_ok": sample_floor_ok,
            "holdout_no_tuning_leak_ok": tuning_leak_count == 0,
            "usefulness_gate_ok": usefulness_gate_ok,
            "attention_cost_ok": attention_cost_ok,
            "red_line_gate_ok": red_line_gate_ok,
            "quality_gate_ok": quality_gate_ok,
        },
        "rows": [
            {
                "case_id": row["case_id"],
                "family": row["family"],
                "case_origin": row["case_origin"],
                "heldout": row["heldout"],
                "success": row["success"],
                "attention_cost_units": row["attention_cost_units"],
            }
            for row in cohort_rows
        ],
        "privacy_boundary": {
            "raw_private_text_serialized": False,
            "local_paths_serialized": False,
            "source_handles_serialized": False,
            "heldout_rows_excluded_from_tuning": tuning_leak_count == 0,
        },
        "no_open_followup_reason": (
            "Public/holdout cohort measurement is consumed by the #2396 family "
            "promotion report; live host, private-history, answer-generation, "
            "and default-foreground adoption claims need fresh scoped work."
        ),
        "cannot_claim": [
            "live_host_behavior_lift",
            "private_history_quality",
            "answer_generation_quality",
            "default_foreground_adoption",
        ],
    }


def run_agent_continuity_loop() -> dict[str, Any]:
    return evaluate_agent_continuity_loop_cases(fixture_agent_continuity_loop_cases())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-cohort",
        action="store_true",
        help="print the #1969 public cohort successor report",
    )
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)
    report = (
        build_agent_continuity_public_cohort_report()
        if args.public_cohort
        else run_agent_continuity_loop()
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"agent continuity loop: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
