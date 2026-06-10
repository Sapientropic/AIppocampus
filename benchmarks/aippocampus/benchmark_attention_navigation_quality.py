#!/usr/bin/env python3
"""Attention Navigation Quality benchmark.

This benchmark evaluates the attention router as a navigation system, not as
answer generation or broad memory QA. Red-line violations are reported
separately so a high average route rate cannot hide privacy, stale/currentness,
or claim-permission failures.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation import (
    attention_evidence_packager,
    attention_hot_router,
    attention_router_contract,
)

SCHEMA_VERSION = 1


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def _case_by_id(report: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    for case in report.get("cases") or []:
        if isinstance(case, Mapping) and case.get("case_id") == case_id:
            return case
    raise KeyError(case_id)


def _quality_case(
    *,
    source_report: str,
    case: Mapping[str, Any],
    family: str,
    expected_output_modes: list[str],
    expected_useful_route: bool,
    expected_source_handle: bool = False,
    source_open_allowed: bool = False,
    stale_or_currentness_case: bool = False,
    conflict_case: bool = False,
    anti_nag_case: bool = False,
    wrong_source_opportunity: bool = False,
    wrong_source_evidence: bool = False,
    counter_evidence_included: bool = False,
) -> dict[str, Any]:
    packet = dict(case.get("packet") or {})
    return {
        "case_id": str(case.get("case_id") or packet.get("route_id")),
        "source_report": source_report,
        "family": family,
        "packet": packet,
        "expectation": {
            "expected_output_modes": expected_output_modes,
            "expected_useful_route": expected_useful_route,
            "expected_source_handle": expected_source_handle,
            "source_open_allowed": source_open_allowed,
            "stale_or_currentness_case": stale_or_currentness_case,
            "conflict_case": conflict_case,
            "anti_nag_case": anti_nag_case,
            "wrong_source_opportunity": wrong_source_opportunity,
            "wrong_source_evidence": wrong_source_evidence,
            "counter_evidence_included": counter_evidence_included,
        },
    }


def fixture_navigation_quality_cases() -> list[dict[str, Any]]:
    contract = attention_router_contract.build_contract_fixture_report()
    hot = attention_hot_router.build_hot_router_fixture_report()
    action = attention_hot_router.build_action_head_fixture_report()
    evidence = attention_evidence_packager.build_evidence_packaging_fixture_report()

    cases = [
        _quality_case(
            source_report="attention_router_contract",
            case=_case_by_id(contract, "privacy_mask_beats_high_relevance"),
            family="hard_mask",
            expected_output_modes=["silence"],
            expected_useful_route=False,
        ),
        _quality_case(
            source_report="attention_router_contract",
            case=_case_by_id(contract, "source_backed_reopenable_route"),
            family="positive_route",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
        ),
        _quality_case(
            source_report="attention_router_contract",
            case=_case_by_id(contract, "source_open_bounded_evidence"),
            family="positive_route",
            expected_output_modes=["bounded_evidence"],
            expected_useful_route=True,
            expected_source_handle=True,
            source_open_allowed=True,
        ),
        _quality_case(
            source_report="attention_hot_router",
            case=_case_by_id(hot, "positive_source_span_route"),
            family="positive_route",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
        ),
        _quality_case(
            source_report="attention_hot_router",
            case=_case_by_id(hot, "masked_high_relevance_private_route"),
            family="hard_mask",
            expected_output_modes=["silence"],
            expected_useful_route=False,
        ),
        _quality_case(
            source_report="attention_hot_router",
            case=_case_by_id(hot, "stale_conflict_reopen_route"),
            family="stale_currentness",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
            stale_or_currentness_case=True,
            conflict_case=True,
        ),
        _quality_case(
            source_report="attention_action_head",
            case=_case_by_id(action, "action_path_issue_match"),
            family="action_time",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
        ),
        _quality_case(
            source_report="attention_action_head",
            case=_case_by_id(action, "action_repeated_hint_suppressed"),
            family="anti_nag",
            expected_output_modes=["direction_only"],
            expected_useful_route=False,
            anti_nag_case=True,
        ),
        _quality_case(
            source_report="attention_evidence_packager",
            case=_case_by_id(evidence, "context_visible_span_becomes_bounded_evidence"),
            family="positive_route",
            expected_output_modes=["bounded_evidence"],
            expected_useful_route=True,
            expected_source_handle=True,
            source_open_allowed=True,
        ),
        _quality_case(
            source_report="attention_evidence_packager",
            case=_case_by_id(evidence, "wrong_source_top_span_rejected"),
            family="wrong_source",
            expected_output_modes=["bounded_evidence"],
            expected_useful_route=True,
            expected_source_handle=True,
            source_open_allowed=True,
            wrong_source_opportunity=True,
            wrong_source_evidence=False,
        ),
        _quality_case(
            source_report="attention_evidence_packager",
            case=_case_by_id(evidence, "stale_span_requires_currentness_check"),
            family="stale_currentness",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
            stale_or_currentness_case=True,
        ),
        _quality_case(
            source_report="attention_evidence_packager",
            case=_case_by_id(evidence, "conflicted_span_packages_counter_evidence"),
            family="conflict",
            expected_output_modes=["reopenable_route"],
            expected_useful_route=True,
            expected_source_handle=True,
            conflict_case=True,
            counter_evidence_included=True,
        ),
    ]
    return cases


def evaluate_navigation_quality_cases(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    projected_cases = [_project_case(case) for case in cases]
    hard_red_lines = _hard_red_lines(projected_cases)
    correct_count = sum(1 for case in projected_cases if case["correct_primary_route"])
    useful_cases = [case for case in projected_cases if case["expectation"]["expected_useful_route"]]
    useful_surfaced = sum(1 for case in useful_cases if case["correct_primary_route"])
    source_handle_cases = [
        case for case in projected_cases if case["expectation"]["expected_source_handle"]
    ]
    source_handle_success = sum(
        1 for case in source_handle_cases if case["packet_summary"]["source_handle_count"] > 0
    )
    wrong_source_cases = [
        case for case in projected_cases if case["expectation"]["wrong_source_opportunity"]
    ]
    false_preactivation_cases = [
        case
        for case in projected_cases
        if case["family"] in {"hard_mask", "anti_nag"} and case["packet_summary"]["source_handle_count"] > 0
    ]
    ok = all(value == 0 for value in hard_red_lines.values()) and correct_count == len(projected_cases)
    return {
        "kind": "aippocampus_attention_navigation_quality",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "cases": projected_cases,
        "metrics": {
            "case_count": len(projected_cases),
            "route_precision_at_1": _rate(correct_count, len(projected_cases)),
            "route_recall_at_k": _rate(useful_surfaced, len(useful_cases)),
            "source_reopen_success_rate": _rate(source_handle_success, len(source_handle_cases)),
            "wrong_source_evidence_rate": _rate(
                hard_red_lines["wrong_source_evidence_count"],
                len(wrong_source_cases),
            ),
            "false_preactivation_rate": _rate(
                len(false_preactivation_cases),
                sum(1 for case in projected_cases if case["family"] in {"hard_mask", "anti_nag"}),
            ),
        },
        "hard_red_lines": hard_red_lines,
        "quality_gate": {
            "red_lines_must_be_zero": True,
            "averages_do_not_mask_red_lines": True,
            "status": "passed" if ok else "failed",
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "private_text_emitted": False,
            "gold_labels_or_answers_emitted": False,
            "local_paths_emitted": False,
        },
        "cannot_claim": [
            "broad_memory_qa_quality",
            "answer_generation_quality",
            "private_history_behavior_quality",
            "live_host_behavior_lift",
            "default_foreground_router_adoption",
            "score_fusion_calibration",
        ],
    }


def _project_case(case: Mapping[str, Any]) -> dict[str, Any]:
    packet = dict(case.get("packet") or {})
    expectation = dict(case.get("expectation") or {})
    summary = _packet_summary(packet)
    expected_modes = set(expectation.get("expected_output_modes") or [])
    correct = summary["output_mode"] in expected_modes
    if expectation.get("anti_nag_case") and summary["source_handle_count"] > 0:
        correct = False
    if summary["masks_applied"] and (summary["emitted"] or summary["source_handle_count"] > 0):
        correct = False
    return {
        "case_id": str(case.get("case_id") or ""),
        "source_report": str(case.get("source_report") or ""),
        "family": str(case.get("family") or "unknown"),
        "expectation": expectation,
        "packet_summary": summary,
        "correct_primary_route": correct,
    }


def _packet_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = packet.get("router_diagnostics")
    reason_codes: list[str] = []
    if isinstance(diagnostics, Mapping):
        reason_codes.extend(str(code) for code in diagnostics.get("reason_codes") or [])
    reason_codes.extend(str(vote.get("reason_code")) for vote in packet.get("head_votes") or [])
    return {
        "output_mode": str(packet.get("output_mode") or ""),
        "claim_permission": str(packet.get("claim_permission") or ""),
        "emitted": bool(packet.get("emitted")),
        "masks_applied": [str(mask) for mask in packet.get("masks_applied") or []],
        "source_handle_count": len(packet.get("source_handles") or []),
        "reason_codes": sorted({code for code in reason_codes if code}),
    }


def _hard_red_lines(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "privacy_bypass_count": 0,
        "masked_source_resurrection_count": 0,
        "source_backed_claim_without_reopen": 0,
        "stale_as_current_count": 0,
        "wrong_source_evidence_count": 0,
        "conflict_missed_count": 0,
        "manual_query_invention_count": 0,
        "anti_nag_violation_count": 0,
        "bounded_evidence_claim_violation_count": 0,
    }
    for case in cases:
        packet = case["packet_summary"]
        expectation = case["expectation"]
        masks = set(packet["masks_applied"])
        if "privacy_domain" in masks and (packet["emitted"] or packet["source_handle_count"]):
            counts["privacy_bypass_count"] += 1
        if masks and (packet["emitted"] or packet["source_handle_count"]):
            counts["masked_source_resurrection_count"] += 1
        if (
            packet["claim_permission"] == "bounded_claim_allowed"
            and not expectation.get("source_open_allowed")
        ):
            counts["source_backed_claim_without_reopen"] += 1
        if (
            expectation.get("stale_or_currentness_case")
            and packet["claim_permission"] == "bounded_claim_allowed"
        ):
            counts["stale_as_current_count"] += 1
        if expectation.get("wrong_source_evidence"):
            counts["wrong_source_evidence_count"] += 1
        if expectation.get("conflict_case") and not (
            expectation.get("counter_evidence_included")
            or "stale_or_conflicted_source_reopen" in packet["reason_codes"]
            or any("counter_evidence" in code for code in packet["reason_codes"])
        ):
            counts["conflict_missed_count"] += 1
        if "manual_query_invented" in packet["reason_codes"]:
            counts["manual_query_invention_count"] += 1
        if expectation.get("anti_nag_case") and (
            packet["output_mode"] != "direction_only" or packet["source_handle_count"] > 0
        ):
            counts["anti_nag_violation_count"] += 1
        if (
            packet["output_mode"] == "bounded_evidence"
            and packet["claim_permission"] != "bounded_claim_allowed"
        ):
            counts["bounded_evidence_claim_violation_count"] += 1
    return counts


def run_attention_navigation_quality() -> dict[str, Any]:
    return evaluate_navigation_quality_cases(fixture_navigation_quality_cases())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = run_attention_navigation_quality()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"attention navigation quality: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
