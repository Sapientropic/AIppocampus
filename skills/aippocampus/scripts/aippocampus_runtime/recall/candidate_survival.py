"""Candidate-survival calibration for safe-but-useless recall failures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.recall import authority


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    return bool(value)


def _candidate_survival_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    useful_total = sum(1 for case in cases if _bool(case.get("later_useful")))
    survived = sum(
        1
        for case in cases
        if _bool(case.get("later_useful"))
        and str(case.get("candidate_state") or "") in {"delivered", "preserved"}
    )
    dropped_later_useful = sum(
        1
        for case in cases
        if case.get("candidate_state") == "dropped" and _bool(case.get("later_useful"))
    )
    parked_later_useful = sum(
        1
        for case in cases
        if case.get("candidate_state") == "parked" and _bool(case.get("later_useful"))
    )
    useful_suppressed = dropped_later_useful + parked_later_useful
    direction_false_positive = sum(
        1
        for case in cases
        if case.get("action_grammar") == authority.ACTION_DIRECTION_ONLY
        and _bool(case.get("wrong_direction"))
    )
    direction_false_negative = sum(
        1
        for case in cases
        if case.get("action_grammar") == authority.ACTION_DIRECTION_ONLY
        and case.get("candidate_state") in {"dropped", "parked"}
        and _bool(case.get("later_useful"))
    )
    visible = sum(1 for case in cases if _bool(case.get("foreground_visible")))
    return {
        "candidate_dropped_later_useful_count": dropped_later_useful,
        "candidate_parked_later_useful_count": parked_later_useful,
        "direction_only_false_positive_count": direction_false_positive,
        "direction_only_false_negative_count": direction_false_negative,
        "silent_nudge_drift_count": sum(1 for case in cases if _bool(case.get("silent_drift"))),
        "useful_candidate_suppressed_count": useful_suppressed,
        "candidate_survival_rate": round(survived / max(1, useful_total), 4),
        "candidate_delivery_latency_turns": round(
            sum(_int(case.get("delivery_latency_turns")) for case in cases)
            / max(1, len(cases)),
            4,
        ),
        "foreground_candidate_visibility_rate": round(visible / max(1, len(cases)), 4),
        "emergent_bridge_preserved_count": sum(
            1 for case in cases if _bool(case.get("emergent_bridge_preserved"))
        ),
        "overconservative_filter_stack_score": sum(
            _int(case.get("filter_stack_depth"))
            for case in cases
            if case.get("candidate_state") in {"dropped", "parked"}
            and _bool(case.get("later_useful"))
        ),
    }


def build_candidate_survival_report(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    clean_cases = [dict(case) for case in cases]
    metrics = _candidate_survival_metrics(clean_cases)
    red_lines = {
        "dream_candidate_promoted_to_fact_count": sum(
            1 for case in clean_cases if _bool(case.get("fact_claim_allowed"))
        ),
        "masked_candidate_foreground_count": sum(
            1
            for case in clean_cases
            if _bool(case.get("hard_masked")) and _bool(case.get("foreground_visible"))
        ),
        "source_claim_without_reopen_count": sum(
            1
            for case in clean_cases
            if _bool(case.get("claim_ready")) and not _bool(case.get("source_open"))
        ),
    }
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    usefulness_gate_ok = (
        metrics["useful_candidate_suppressed_count"] == 0
        and metrics["direction_only_false_positive_count"] == 0
    )
    return {
        "kind": "aippocampus_candidate_survival_report",
        "schema_version": 1,
        "cases": clean_cases,
        "metrics": metrics,
        "red_lines": red_lines,
        "safety_gate_ok": safety_gate_ok,
        "usefulness_gate_ok": usefulness_gate_ok,
        "quality_gate_ok": safety_gate_ok and usefulness_gate_ok,
        "source_boundary": {
            "candidate_survival_is_calibration_evidence": True,
            "candidate_survival_is_not_source_truth": True,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
        },
    }


def build_candidate_survival_fixture_report() -> dict[str, Any]:
    cases = [
        {
            "case_id": "adjudication_stack_false_negative",
            "surface_family": "working_memory",
            "candidate_state": "dropped",
            "later_useful": True,
            "foreground_visible": False,
            "source_safe_navigation_boundary": True,
            "filter_stack_depth": 5,
            "delivery_latency_turns": 4,
            "action_grammar": authority.ACTION_DIRECTION_ONLY,
            "fact_claim_allowed": False,
        },
        {
            "case_id": "parked_later_useful_route",
            "surface_family": "dream",
            "candidate_state": "parked",
            "later_useful": True,
            "foreground_visible": False,
            "source_safe_navigation_boundary": True,
            "filter_stack_depth": 3,
            "delivery_latency_turns": 3,
            "action_grammar": authority.ACTION_DIRECTION_WITH_REF,
            "fact_claim_allowed": False,
        },
        {
            "case_id": "direction_only_silent_error",
            "surface_family": "direction_only",
            "candidate_state": "delivered",
            "later_useful": False,
            "foreground_visible": True,
            "wrong_direction": True,
            "silent_drift": True,
            "delivery_latency_turns": 1,
            "action_grammar": authority.ACTION_DIRECTION_ONLY,
            "fact_claim_allowed": False,
        },
        {
            "case_id": "weak_source_emergence_preserved",
            "surface_family": "dream",
            "candidate_state": "preserved",
            "later_useful": True,
            "foreground_visible": True,
            "foreground_projection": authority.AUTHORITY_NAVIGATION_ONLY,
            "action_grammar": authority.ACTION_DIRECTION_ONLY,
            "emergent_bridge_preserved": True,
            "delivery_latency_turns": 1,
            "fact_claim_allowed": False,
        },
        {
            "case_id": "correct_but_creatively_starved",
            "surface_family": "foreground_packet_set",
            "candidate_state": "dropped",
            "later_useful": False,
            "foreground_visible": False,
            "safety_gate_ok": True,
            "usefulness_gate_ok": False,
            "only_verified_low_ambiguity_material_visible": True,
            "delivery_latency_turns": 2,
            "action_grammar": authority.ACTION_IGNORE_OR_BLOCKED,
            "fact_claim_allowed": False,
        },
    ]
    return build_candidate_survival_report(cases)


__all__ = [
    "build_candidate_survival_fixture_report",
    "build_candidate_survival_report",
]
