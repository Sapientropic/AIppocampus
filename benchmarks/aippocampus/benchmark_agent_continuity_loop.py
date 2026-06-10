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
from typing import Any

import _paths

_paths.ensure_paths()

import benchmark_maturity
from aippocampus_runtime.aippo import working_contract as aippo
from aippocampus_runtime.navigation import attention_hot_router, semantic_warm_route_producer
from aippocampus_runtime.recall import (
    agent_facade_contract,
    prompt_foreground_budget,
    source_reopen_budget,
)

SCHEMA_VERSION = 1
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
    token = semantic_warm_route_producer.project_semantic_warm_route_tokens([_semantic_row(case)])[0]
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
    report = aippo.build_aippo_working_contract_fixture_report()
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
                "red_lines": {"foreground_forbidden_key_leak": _foreground_forbidden_count([packet])},
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
        "semantic_route_used_as_truth_count": int(packet["claim_permission"] == "bounded_claim_allowed"),
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
            "source_backed_claim_without_reopen": red_lines[
                "source_backed_claim_without_reopen"
            ],
            "anti_nag_suppressed_count": anti_nag_suppressed,
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
        "cannot_claim": [
            "live_host_behavior_lift",
            "private_history_quality",
            "answer_generation_quality",
            "default_foreground_adoption",
            "public_benchmark_quality_lift",
            "external_model_quality",
        ],
    }


def run_agent_continuity_loop() -> dict[str, Any]:
    return evaluate_agent_continuity_loop_cases(fixture_agent_continuity_loop_cases())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = run_agent_continuity_loop()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"agent continuity loop: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
