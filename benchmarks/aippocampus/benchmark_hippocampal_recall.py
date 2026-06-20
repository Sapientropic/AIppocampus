#!/usr/bin/env python3
"""Public-safe hippocampal recall-discrimination diagnostic benchmark.

This runner executes the synthetic JSONL seed for GitHub #229/#230/#231. It is
not a live model benchmark. It validates fixture contracts, scores deterministic
example outputs, and reports D/I coverage, abstention, scent, evidence, and
source-reopen boundaries without claiming full P1 quality.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from benchmarks.aippocampus.families import hippocampal_d5_d6_gate
from benchmarks.aippocampus.families import hippocampal_fixture_schema as schema
from benchmarks.aippocampus.families.hippocampal_h5_consolidation import (
    H5_BEFORE_ARM,
    H5_CONSOLIDATION_ARMS,
    h5_consolidation_report,
)

SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = "aippocampus.hippocampal_recall_report.v1"
RELATIVE_FIXTURE_PATH = "benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl"
CLEAN_CLONE_COMMAND = "python benchmarks/aippocampus/benchmark_hippocampal_recall.py --json"
OUTCOME_CATEGORIES = (
    "correct_evidence",
    "correct_scent",
    "correct_skip",
    "underconfident_scent",
    "overconfident_evidence",
    "partial_miss",
    "unsupported_skip",
    "overactive_scent",
    "wrong_twin_selection",
    "source_reopen_failure",
    "wrong_evidence",
    "confabulation",
)
OUTCOME_WEIGHTS = {
    "correct_evidence": 1.0,
    "correct_scent": 0.7,
    "correct_skip": 0.5,
    "underconfident_scent": 0.25,
    "overconfident_evidence": -3.5,
    "partial_miss": -1.5,
    "unsupported_skip": -0.75,
    "overactive_scent": -1.0,
    "wrong_twin_selection": -4.0,
    "source_reopen_failure": -4.0,
    "wrong_evidence": -3.0,
    "confabulation": -6.0,
}
SCENT_LAYERS = (
    "scent_hit",
    "scent_distractor",
    "scent_both",
    "scent_miss",
)
CORRECT_OUTCOMES = {"correct_evidence", "correct_scent", "correct_skip"}
SEPARATION_FAILURES = {
    "wrong_twin_selection",
    "partial_miss",
    "overconfident_evidence",
    "confabulation",
}
DEFAULT_ARMS = ("full_query", "keyword_only", "random_retrieval")
LOCAL_ADAPTER_ARMS = (
    "full_query",
    "keyword_only",
    "baseline_rag",
    "closed_book",
    "overactive_all_evidence",
    "random_retrieval",
)
TRUTH_LABEL_FIELDS = (
    "expected_decision",
    "expected_source_refs",
    "acceptable_scent_refs",
    "distractor_source_refs",
    "forbidden_claims",
    "truth_source",
    "ambiguity_policy",
)
EXTERNAL_ADAPTER_CANDIDATES = ("mem0", "zep_graphiti", "letta", "langmem")
CROSS_SYSTEM_REPORT_PATH = (
    "docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md"
)
CROSS_SYSTEM_LOCAL_ROWS = tuple(
    {
        "row_id": row_id,
        "display_name": display_name,
        "h1_h2_arm": h1_h2_arm,
        "h5_arm": h5_arm,
    }
    for row_id, display_name, h1_h2_arm, h5_arm in (
        (
            "aippocampus_diagnostic",
            "AIppocampus diagnostic",
            "full_query",
            "aippocampus_dream_consolidation",
        ),
        ("baseline_rag", "Baseline RAG", "baseline_rag", None),
        ("keyword_only", "Keyword-only", "keyword_only", "no_consolidation"),
        ("closed_book", "Closed-book", "closed_book", None),
        (
            "overactive_all_evidence",
            "Overactive all-evidence",
            "overactive_all_evidence",
            None,
        ),
        ("random_retrieval", "Random retrieval", "random_retrieval", "random_consolidation"),
        (
            "simple_summary_consolidation",
            "Simple-summary consolidation",
            None,
            "simple_summary_consolidation",
        ),
    )
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _claim_hits_forbidden(case: Mapping[str, Any], response: Mapping[str, Any]) -> bool:
    forbidden = [item.casefold() for item in _as_list(case.get("forbidden_claims"))]
    claims = [item.casefold() for item in _as_list(response.get("claims"))]
    return any(forbidden_item in claim for forbidden_item in forbidden for claim in claims)


def _scent_layer(*, target_hit: bool, distractor_hit: bool, has_refs: bool) -> str:
    if target_hit and distractor_hit:
        return "scent_both"
    if target_hit:
        return "scent_hit"
    if distractor_hit:
        return "scent_distractor"
    return "scent_miss" if has_refs else "scent_miss"


def _score_payload(
    outcome: str,
    *,
    reasons: Sequence[str],
    matched_refs: set[str],
    scent_layer: str | None = None,
    low_separation: bool = False,
    calibration_category: str | None = None,
    scent_precision_contributes: bool = False,
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "score": OUTCOME_WEIGHTS[outcome],
        "reasons": list(reasons),
        "matched_ref_hashes": [schema.sha1_text(ref)[:16] for ref in sorted(matched_refs)],
        "scent_layer": scent_layer,
        "low_separation": bool(low_separation),
        "calibration_category": calibration_category or outcome,
        "scent_precision_contributes": bool(scent_precision_contributes),
    }


def adapter_case_for_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the model-facing adapter input, excluding scoring truth labels."""

    return {
        "case_id": row.get("case_id"),
        "scene_id": row.get("scene_id"),
        "query": row.get("query"),
        "degradation_level": row.get("degradation_level"),
        "interference_level": row.get("interference_level"),
        "candidate_source_refs": _as_list(row.get("candidate_source_refs")),
        "baseline_outputs": _as_mapping(row.get("baseline_outputs")),
    }


def _cost_payload(
    response: Mapping[str, Any],
    *,
    candidate_count: int,
) -> dict[str, Any]:
    source_reopen_count = len(_as_list(response.get("evidence_refs"))) if response.get("source_reopened") else 0
    return {
        "candidate_count": candidate_count,
        "source_reopen_count": source_reopen_count,
        "model_calls": 0,
        "tokens": 0,
        "latency_ms": 0.0,
    }


def _with_adapter_metadata(
    response: Mapping[str, Any],
    *,
    arm: str,
    candidate_count: int,
) -> dict[str, Any]:
    payload = dict(response)
    payload.setdefault("adapter_status", "ok")
    payload.setdefault("adapter_arm", arm)
    payload.setdefault("cost", _cost_payload(payload, candidate_count=candidate_count))
    return payload


def _closed_book_response() -> dict[str, Any]:
    return {
        "decision": "evidence",
        "confidence": 0.5,
        "evidence_refs": [],
        "scent_refs": [],
        "source_reopened": False,
        "claims": ["closed-book memory answer without reopened source"],
    }


def _overactive_response(adapter_case: Mapping[str, Any]) -> dict[str, Any]:
    refs = _as_list(adapter_case.get("candidate_source_refs"))
    return {
        "decision": "evidence" if refs else "skip",
        "confidence": 0.99 if refs else 0.05,
        "evidence_refs": refs,
        "scent_refs": [],
        "source_reopened": bool(refs),
        "claims": [],
    }


def _baseline_rag_response(adapter_case: Mapping[str, Any]) -> dict[str, Any]:
    refs = _as_list(adapter_case.get("candidate_source_refs"))
    if not refs:
        return {
            "decision": "skip",
            "confidence": 0.05,
            "evidence_refs": [],
            "scent_refs": [],
            "source_reopened": False,
            "claims": [],
        }
    return {
        "decision": "evidence",
        "confidence": 0.62,
        "evidence_refs": [refs[0]],
        "scent_refs": [],
        "source_reopened": True,
        "claims": [],
    }


def run_adapter_arm(case: Mapping[str, Any], arm: str) -> dict[str, Any]:
    adapter_case = adapter_case_for_row(case)
    candidate_count = len(_as_list(adapter_case.get("candidate_source_refs")))
    baseline_outputs = _as_mapping(adapter_case.get("baseline_outputs"))
    if arm in baseline_outputs:
        response = _as_mapping(baseline_outputs.get(arm))
    elif arm == "baseline_rag":
        response = _baseline_rag_response(adapter_case)
    elif arm == "closed_book":
        response = _closed_book_response()
    elif arm == "overactive_all_evidence":
        response = _overactive_response(adapter_case)
    else:
        response = {
            "decision": "skip",
            "confidence": 0.0,
            "evidence_refs": [],
            "scent_refs": [],
            "source_reopened": False,
            "claims": [],
            "adapter_status": "unsupported_arm",
        }
    return _with_adapter_metadata(
        response,
        arm=arm,
        candidate_count=candidate_count,
    )


def score_response(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    decision = str(response.get("decision") or "skip")
    evidence_refs = set(_as_list(response.get("evidence_refs")))
    scent_refs = set(_as_list(response.get("scent_refs")))
    response_refs = evidence_refs | scent_refs
    expected_refs = set(_as_list(case.get("expected_source_refs")))
    acceptable_scent_refs = set(_as_list(case.get("acceptable_scent_refs"))) | expected_refs
    distractor_refs = set(_as_list(case.get("distractor_source_refs")))
    expected_decision = str(case.get("expected_decision") or "skip")
    ambiguity_policy = str(case.get("ambiguity_policy") or "")
    source_reopened = bool(response.get("source_reopened"))

    if _claim_hits_forbidden(case, response):
        return _score_payload(
            "confabulation",
            reasons=["claim_matches_forbidden_fixture_claim"],
            matched_refs=response_refs,
        )

    if decision == "evidence":
        if expected_decision != "evidence" or ambiguity_policy in {
            "multi_candidate_scent",
            "unsupported_skip",
        }:
            return _score_payload(
                "overconfident_evidence",
                reasons=["evidence_escalates_above_expected_decision"],
                matched_refs=evidence_refs,
                calibration_category="overconfident_evidence",
            )
        if not evidence_refs or not source_reopened:
            return _score_payload(
                "source_reopen_failure",
                reasons=["evidence_requires_successful_source_reopen"],
                matched_refs=evidence_refs,
            )
        if evidence_refs & distractor_refs and not evidence_refs & expected_refs:
            return _score_payload(
                "wrong_twin_selection",
                reasons=["evidence_selects_distractor_without_target_ref"],
                matched_refs=evidence_refs & distractor_refs,
            )
        if evidence_refs & expected_refs:
            return _score_payload(
                "correct_evidence",
                reasons=["evidence_reopens_expected_target_ref"],
                matched_refs=evidence_refs & expected_refs,
            )
        return _score_payload(
            "wrong_evidence",
            reasons=["evidence_refs_do_not_match_expected_source_refs"],
            matched_refs=evidence_refs,
        )

    if decision == "scent":
        target_hit = bool(response_refs & acceptable_scent_refs)
        distractor_hit = bool(response_refs & distractor_refs)
        layer = _scent_layer(
            target_hit=target_hit,
            distractor_hit=distractor_hit,
            has_refs=bool(response_refs),
        )
        low_separation = layer == "scent_both"
        if layer == "scent_distractor":
            return _score_payload(
                "partial_miss",
                reasons=["scent_selects_only_distractor_refs"],
                matched_refs=response_refs & distractor_refs,
                scent_layer=layer,
                low_separation=True,
                calibration_category="partial_miss",
            )
        if expected_decision == "evidence":
            if target_hit:
                return _score_payload(
                    "underconfident_scent",
                    reasons=["target_found_but_answer_stays_below_evidence"],
                    matched_refs=response_refs & acceptable_scent_refs,
                    scent_layer=layer,
                    low_separation=low_separation,
                    calibration_category="underconfident_scent",
                )
            return _score_payload(
                "partial_miss",
                reasons=["scent_misses_expected_evidence_ref"],
                matched_refs=response_refs,
                scent_layer=layer,
                calibration_category="partial_miss",
            )
        if expected_decision == "scent":
            if target_hit:
                return _score_payload(
                    "correct_scent",
                    reasons=["scent_identifies_expected_ref_without_evidence_escalation"],
                    matched_refs=response_refs & acceptable_scent_refs,
                    scent_layer=layer,
                    low_separation=low_separation,
                    calibration_category="correct_scent",
                    scent_precision_contributes=layer == "scent_hit",
                )
            return _score_payload(
                "partial_miss",
                reasons=["scent_does_not_include_expected_ref"],
                matched_refs=response_refs,
                scent_layer=layer,
                calibration_category="partial_miss",
            )
        return _score_payload(
            "overactive_scent",
            reasons=["scent_returned_when_fixture_expects_skip"],
            matched_refs=response_refs,
            scent_layer=layer,
            calibration_category="overactive_scent",
        )

    if decision == "skip":
        if expected_decision == "skip":
            return _score_payload(
                "correct_skip",
                reasons=["unsupported_or_ambiguous_case_abstains"],
                matched_refs=set(),
            )
        return _score_payload(
            "unsupported_skip",
            reasons=["skip_misses_expected_recall_or_scent"],
            matched_refs=set(),
            calibration_category="unsupported_skip",
        )

    return _score_payload(
        "wrong_evidence",
        reasons=["unsupported_decision_label"],
        matched_refs=response_refs,
    )


def _sanitized_case_result(
    *,
    arm: str,
    case: Mapping[str, Any],
    response: Mapping[str, Any],
    score: Mapping[str, Any],
    include_private_text: bool,
) -> dict[str, Any]:
    payload = {
        "arm": arm,
        "case_id": case.get("case_id"),
        "scene_id": case.get("scene_id"),
        "degradation_level": case.get("degradation_level"),
        "interference_level": case.get("interference_level"),
        "expected_decision": case.get("expected_decision"),
        "actual_decision": response.get("decision"),
        "confidence": response.get("confidence"),
        "outcome": score.get("outcome"),
        "score": score.get("score"),
        "scent_layer": score.get("scent_layer"),
        "low_separation": bool(score.get("low_separation")),
        "calibration_category": score.get("calibration_category"),
        "query_sha1": schema.sha1_text(str(case.get("query") or ""))[:16],
        "matched_ref_hashes": score.get("matched_ref_hashes") or [],
        "adapter_status": response.get("adapter_status"),
        "cost": response.get("cost") or {},
    }
    if include_private_text:
        payload["query"] = str(case.get("query") or "")
        payload["claims"] = _as_list(response.get("claims"))
    return payload


def _blank_view() -> dict[str, Any]:
    return {
        "case_count": 0,
        "scored_example_count": 0,
        "correct_count": 0,
        "accuracy": 0.0,
        "separation_failure_count": 0,
        "source_reopen_failure_count": 0,
    }


def _views(
    rows: Sequence[Mapping[str, Any]],
    validation: Mapping[str, Any],
    case_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_degradation = {level: _blank_view() for level in schema.DEGRADATION_LEVELS}
    by_interference = {level: _blank_view() for level in schema.INTERFERENCE_LEVELS}
    matrix: dict[str, dict[str, Any]] = {
        key: {
            "case_count": payload["case_count"],
            "density_floor": payload["density_floor"],
            "coverage_status": payload["coverage_status"],
            "phase": payload["phase"],
            "scored_example_count": 0,
            "correct_count": 0,
            "accuracy": 0.0,
            "separation_failure_count": 0,
            "source_reopen_failure_count": 0,
        }
        for key, payload in _as_mapping(validation.get("cell_density")).items()
    }

    for row in rows:
        degradation = str(row.get("degradation_level") or "")
        interference = str(row.get("interference_level") or "")
        key = f"{degradation}/{interference}"
        if degradation in by_degradation:
            by_degradation[degradation]["case_count"] += 1
        if interference in by_interference:
            by_interference[interference]["case_count"] += 1
        if key in matrix:
            matrix[key]["case_count"] = int(matrix[key]["case_count"])

    outcome_counts = {outcome: 0 for outcome in OUTCOME_CATEGORIES}
    calibration_counts: dict[str, int] = {}
    scent_layer_counts = {layer: 0 for layer in SCENT_LAYERS}
    scent_attempts = 0
    scent_precision_hits = 0
    confidence_present = 0
    skip_expected = 0
    skip_correct = 0
    score_total = 0.0
    cost_totals = {
        "source_reopen_count": 0,
        "model_calls": 0,
        "tokens": 0,
        "latency_ms": 0.0,
    }

    for result in case_results:
        degradation = str(result.get("degradation_level") or "")
        interference = str(result.get("interference_level") or "")
        key = f"{degradation}/{interference}"
        outcome = str(result.get("outcome") or "")
        calibration = str(result.get("calibration_category") or outcome)
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        calibration_counts[calibration] = calibration_counts.get(calibration, 0) + 1
        if isinstance(result.get("confidence"), (int, float)):
            confidence_present += 1
        if isinstance(result.get("score"), (int, float)):
            score_total += float(result["score"])
        cost = _as_mapping(result.get("cost"))
        cost_totals["source_reopen_count"] += int(cost.get("source_reopen_count") or 0)
        cost_totals["model_calls"] += int(cost.get("model_calls") or 0)
        cost_totals["tokens"] += int(cost.get("tokens") or 0)
        if isinstance(cost.get("latency_ms"), (int, float)):
            cost_totals["latency_ms"] += float(cost["latency_ms"])
        if result.get("expected_decision") == "skip":
            skip_expected += 1
            if outcome == "correct_skip":
                skip_correct += 1

        for view in (
            by_degradation.get(degradation),
            by_interference.get(interference),
            matrix.get(key),
        ):
            if view is None:
                continue
            view["scored_example_count"] += 1
            if outcome in CORRECT_OUTCOMES:
                view["correct_count"] += 1
            if outcome in SEPARATION_FAILURES or bool(result.get("low_separation")):
                view["separation_failure_count"] += 1
            if outcome == "source_reopen_failure":
                view["source_reopen_failure_count"] += 1

        layer = result.get("scent_layer")
        if isinstance(layer, str) and layer:
            scent_attempts += 1
            if layer in scent_layer_counts:
                scent_layer_counts[layer] += 1
            if bool(result.get("scent_precision_contributes")):
                scent_precision_hits += 1

    for view in list(by_degradation.values()) + list(by_interference.values()) + list(matrix.values()):
        view["accuracy"] = _rate(int(view["correct_count"]), int(view["scored_example_count"]))
        view["separation_accuracy"] = _rate(
            int(view["scored_example_count"]) - int(view["separation_failure_count"]),
            int(view["scored_example_count"]),
        )
        view["source_reopen_success"] = _rate(
            int(view["scored_example_count"]) - int(view["source_reopen_failure_count"]),
            int(view["scored_example_count"]),
        )

    total = len(case_results)
    aggregate = {
        "case_count": len(rows),
        "scored_example_count": total,
        "score_total": round(score_total, 6),
        "correct_count": sum(outcome_counts.get(item, 0) for item in CORRECT_OUTCOMES),
        "confabulation_count": outcome_counts.get("confabulation", 0),
        "confabulation_rate": _rate(outcome_counts.get("confabulation", 0), total),
        "source_reopen_failure_count": outcome_counts.get("source_reopen_failure", 0),
        "source_reopen_success": _rate(
            total - outcome_counts.get("source_reopen_failure", 0),
            total,
        ),
        "wrong_twin_selection_count": outcome_counts.get("wrong_twin_selection", 0),
        "overconfidence_rate": _rate(outcome_counts.get("overconfident_evidence", 0), total),
        "underconfidence_rate": _rate(outcome_counts.get("underconfident_scent", 0), total),
        "abstention_accuracy": _rate(skip_correct, skip_expected),
        "scent_precision": _rate(scent_precision_hits, scent_attempts),
        "scent_attempt_count": scent_attempts,
        "scent_precision_hit_count": scent_precision_hits,
        "outcome_counts": outcome_counts,
        "scent_layer_counts": scent_layer_counts,
        "cost": {
            **cost_totals,
            "latency_ms": round(cost_totals["latency_ms"], 6),
            "available": total > 0,
        },
    }
    return {
        "by_degradation": by_degradation,
        "by_interference": by_interference,
        "matrix": matrix,
        "aggregate": aggregate,
        "calibration": {
            "category_counts": dict(sorted(calibration_counts.items())),
            "confidence_available": confidence_present > 0,
            "confidence_example_count": confidence_present,
            "bucketed_calibration_available": False,
            "cannot_claim": [
                "bucketed_expected_calibration_error_without_calibrated_confidence_bins",
            ],
        },
    }


def _quality_gates(validation: Mapping[str, Any], views: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = _as_mapping(views.get("aggregate"))
    matrix = _as_mapping(views.get("matrix"))
    d4_d6_marked = all(
        _as_mapping(payload).get("coverage_status") != "release_gate"
        for key, payload in matrix.items()
        if str(key).startswith(("D4/", "D5/", "D6/"))
    )
    gate_items = {
        "fixture_valid": bool(validation.get("ok")),
        "must_pass_gates_represented": True,
        "source_reopen_required": True,
        "confabulation_rate_zero": aggregate.get("confabulation_count") == 0,
        "full_p1_coverage_sufficient": bool(
            _as_mapping(validation.get("coverage")).get("full_p1_matrix_claim")
        ),
        "d4_d6_exploratory_marked": d4_d6_marked,
    }
    return {**gate_items, "ok": all(gate_items.values())}


def _views_by_arm(
    rows: Sequence[Mapping[str, Any]],
    validation: Mapping[str, Any],
    case_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    views: dict[str, Any] = {}
    for arm in LOCAL_ADAPTER_ARMS:
        arm_results = [result for result in case_results if result.get("arm") == arm]
        views[arm] = _views(rows, validation, arm_results)
    return views


def _external_adapter_diagnostics() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "status": "diagnostic_missing_configuration",
            "requires_opt_in": True,
            "quality_gate_participation": "none",
            "cannot_claim": [
                "adapter_score",
                "product_comparison",
                "api_compatibility",
            ],
        }
        for name in EXTERNAL_ADAPTER_CANDIDATES
    }


def _adapter_contract() -> dict[str, Any]:
    return {
        "version": "aippocampus.hippocampal_adapter_contract.v1",
        "local_arms": list(LOCAL_ADAPTER_ARMS),
        "arm_count": len(LOCAL_ADAPTER_ARMS),
        "requires_external_credentials": False,
        "truth_label_fields_hidden_from_adapters": list(TRUTH_LABEL_FIELDS),
        "adapter_input_fields": [
            "case_id",
            "scene_id",
            "query",
            "degradation_level",
            "interference_level",
            "candidate_source_refs",
        ],
        "external_adapters": _external_adapter_diagnostics(),
        "cannot_claim": [
            "external_memory_system_score",
            "cross_system_superiority",
            "live_provider_quality",
        ],
    }


def _comparison_rate_for_levels(
    by_degradation: Mapping[str, Any],
    levels: Sequence[str],
) -> tuple[float | None, int]:
    scored = 0
    correct = 0
    for level in levels:
        view = _as_mapping(by_degradation.get(level))
        scored += int(view.get("scored_example_count") or 0)
        correct += int(view.get("correct_count") or 0)
    if scored <= 0:
        return None, 0
    return _rate(correct, scored), scored


def _comparison_separation_accuracy(
    by_degradation: Mapping[str, Any],
    levels: Sequence[str],
) -> float | None:
    scored = 0
    failures = 0
    for level in levels:
        view = _as_mapping(by_degradation.get(level))
        scored += int(view.get("scored_example_count") or 0)
        failures += int(view.get("separation_failure_count") or 0)
    if scored <= 0:
        return None
    return _rate(scored - failures, scored)


def _comparison_round_delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(before - after, 6)


def _comparison_row_from_arm(
    row_spec: Mapping[str, Any],
    *,
    arm_views: Mapping[str, Any],
    h5_report: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    h1_h2_arm = row_spec.get("h1_h2_arm")
    h5_arm = row_spec.get("h5_arm")
    h1_h2_view = _as_mapping(arm_views.get(str(h1_h2_arm))) if h1_h2_arm else {}
    aggregate = _as_mapping(h1_h2_view.get("aggregate"))
    by_degradation = _as_mapping(h1_h2_view.get("by_degradation"))
    d0_accuracy, d0_sample_size = _comparison_rate_for_levels(by_degradation, ("D0",))
    degraded_accuracy, degraded_sample_size = _comparison_rate_for_levels(
        by_degradation,
        ("D1", "D2", "D3", "D4", "D5", "D6"),
    )
    d5_d6_accuracy, d5_d6_sample_size = _comparison_rate_for_levels(
        by_degradation,
        ("D5", "D6"),
    )
    d5_accuracy, d5_sample_size = _comparison_rate_for_levels(by_degradation, ("D5",))
    d6_accuracy, d6_sample_size = _comparison_rate_for_levels(by_degradation, ("D6",))
    h5_aggregate = (
        _as_mapping(
            _as_mapping(_as_mapping(h5_report.get("views_by_arm")).get(str(h5_arm))).get(
                "aggregate"
            )
        )
        if h5_arm
        else {}
    )
    return {
        "row_id": row_spec["row_id"],
        "display_name": row_spec["display_name"],
        "availability": "observed_public_synthetic",
        "comparable": bool(h1_h2_arm or h5_arm),
        "claim_level": "synthetic_public_result",
        "h1_h2_arm": h1_h2_arm,
        "h5_arm": h5_arm,
        "h1_h2_sample_size": int(aggregate.get("scored_example_count") or 0),
        "cell_density_floor": validation.get("density_floor"),
        "full_p1_matrix_claim": bool(
            _as_mapping(validation.get("coverage")).get("full_p1_matrix_claim")
        ),
        "d0_accuracy": d0_accuracy,
        "d0_sample_size": d0_sample_size,
        "h1_degraded_accuracy": degraded_accuracy,
        "h1_degraded_sample_size": degraded_sample_size,
        "h1_degraded_drop_from_d0": _comparison_round_delta(
            d0_accuracy,
            degraded_accuracy,
        ),
        "d5_d6_accuracy": d5_d6_accuracy,
        "d5_d6_sample_size": d5_d6_sample_size,
        "d5_d6_drop_from_d0": _comparison_round_delta(d0_accuracy, d5_d6_accuracy),
        "d5_accuracy": d5_accuracy,
        "d5_sample_size": d5_sample_size,
        "d6_accuracy": d6_accuracy,
        "d6_sample_size": d6_sample_size,
        "h2_separation_accuracy": _comparison_separation_accuracy(
            by_degradation,
            schema.DEGRADATION_LEVELS,
        ),
        "source_reopen_success": aggregate.get("source_reopen_success"),
        "confabulation_rate": aggregate.get("confabulation_rate"),
        "overconfidence_rate": aggregate.get("overconfidence_rate"),
        "underconfidence_rate": aggregate.get("underconfidence_rate"),
        "h5_score_delta_total": h5_aggregate.get("score_delta_total"),
        "h5_false_forgetting_count": h5_aggregate.get("false_forgetting_count"),
        "h5_overgeneralization_count": h5_aggregate.get("overgeneralization_count"),
        "h5_stale_as_current_delta": h5_aggregate.get("stale_as_current_delta"),
        "h5_wrong_twin_delta": h5_aggregate.get("wrong_twin_delta"),
        "h5_cost_per_improvement": h5_aggregate.get("cost_per_improvement"),
        "comparison_status": (
            "diagnostic_h5_only"
            if h5_arm and not h1_h2_arm
            else "public_synthetic_comparable"
        ),
    }


def _comparison_missing_row(
    *,
    row_id: str,
    display_name: str,
    availability: str,
    claim_level: str,
) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "display_name": display_name,
        "availability": availability,
        "comparable": False,
        "claim_level": claim_level,
        "h1_h2_arm": None,
        "h5_arm": None,
        "h1_h2_sample_size": 0,
        "cell_density_floor": None,
        "full_p1_matrix_claim": False,
        "d0_accuracy": None,
        "d0_sample_size": 0,
        "h1_degraded_accuracy": None,
        "h1_degraded_sample_size": 0,
        "h1_degraded_drop_from_d0": None,
        "d5_d6_accuracy": None,
        "d5_d6_sample_size": 0,
        "d5_d6_drop_from_d0": None,
        "d5_accuracy": None,
        "d5_sample_size": 0,
        "d6_accuracy": None,
        "d6_sample_size": 0,
        "h2_separation_accuracy": None,
        "source_reopen_success": None,
        "confabulation_rate": None,
        "overconfidence_rate": None,
        "underconfidence_rate": None,
        "h5_score_delta_total": None,
        "h5_false_forgetting_count": None,
        "h5_overgeneralization_count": None,
        "h5_stale_as_current_delta": None,
        "h5_wrong_twin_delta": None,
        "h5_cost_per_improvement": None,
        "comparison_status": "not_scored",
    }


def _cross_system_comparison_report(
    *,
    validation: Mapping[str, Any],
    arm_views: Mapping[str, Any],
    h5_report: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [
        _comparison_row_from_arm(
            row_spec,
            arm_views=arm_views,
            h5_report=h5_report,
            validation=validation,
        )
        for row_spec in CROSS_SYSTEM_LOCAL_ROWS
    ]
    rows.append(
        _comparison_missing_row(
            row_id="semantic_only",
            display_name="Semantic-only",
            availability="adapter_not_implemented",
            claim_level="diagnostic_not_available",
        )
    )
    for adapter_name, adapter in _external_adapter_diagnostics().items():
        rows.append(
            _comparison_missing_row(
                row_id=adapter_name,
                display_name=adapter_name.replace("_", " / ").title(),
                availability=str(adapter.get("status") or "diagnostic_missing_configuration"),
                claim_level="diagnostic_missing_configuration",
            )
        )
    return {
        "version": "aippocampus.hippocampal_cross_system_comparison.v1",
        "dated_report_path": CROSS_SYSTEM_REPORT_PATH,
        "source_issue": "https://github.com/Sapientropic/AIppocampus/issues/238",
        "parent_issue": "https://github.com/Sapientropic/AIppocampus/issues/228",
        "comparison_boundary": {
            "public_synthetic_fixture_only": True,
            "private_real_history_included": False,
            "external_adapters_scored": False,
            "missing_adapters_visible": True,
            "sparse_cells_visible": True,
        },
        "rows": rows,
        "cannot_claim": [
            "cross_system_superiority",
            "external_memory_system_score",
            "industry_hardest_benchmark",
            "user_visible_dream_benefit",
            "publication_grade_comparison",
        ],
    }


def run_benchmark(
    fixture_path: str | Path = schema.DEFAULT_FIXTURE,
    *,
    include_private_text: bool = False,
) -> dict[str, Any]:
    rows = schema.load_fixture(fixture_path)
    validation = schema.validate_fixture(rows)
    case_results: list[dict[str, Any]] = []
    for case in rows:
        for arm in LOCAL_ADAPTER_ARMS:
            response = run_adapter_arm(case, arm)
            if not response:
                continue
            score = score_response(case, response)
            result = _sanitized_case_result(
                arm=arm,
                case=case,
                response=response,
                score=score,
                include_private_text=include_private_text,
            )
            result["scent_precision_contributes"] = bool(
                score.get("scent_precision_contributes")
            )
            case_results.append(result)

    views = _views(rows, validation, case_results)
    arm_views = _views_by_arm(rows, validation, case_results)
    d5_d6_gate = hippocampal_d5_d6_gate.build_d5_d6_gate(case_results)
    h5_consolidation = h5_consolidation_report(
        rows,
        run_adapter_arm=run_adapter_arm,
        score_response=score_response,
        with_adapter_metadata=_with_adapter_metadata,
    )
    cross_system_comparison = _cross_system_comparison_report(
        validation=validation,
        arm_views=arm_views,
        h5_report=h5_consolidation,
    )
    quality_gates = _quality_gates(validation, views)
    baseline_captured = bool(validation.get("ok")) and len(case_results) >= (
        len(rows) * len(LOCAL_ADAPTER_ARMS)
    )
    status = (
        "quality_gate_passed"
        if baseline_captured and quality_gates["ok"]
        else "baseline_captured_with_known_gaps"
        if baseline_captured
        else "baseline_capture_failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "kind": "aippocampus_hippocampal_recall_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": baseline_captured,
        "quality_gate_ok": bool(quality_gates["ok"]),
        "config": {
            "fixture": RELATIVE_FIXTURE_PATH,
            "fixture_dataset_id": validation.get("dataset_id"),
            "fixture_schema_version": validation.get("schema_version"),
            "fixture_version": schema.FIXTURE_VERSION,
            "fixture_seed": schema.FIXTURE_SEED,
            "uses_live_model": False,
            "uses_model_judge": False,
            "uses_private_history": False,
            "baseline_arms": list(LOCAL_ADAPTER_ARMS),
            "h5_before_arm": H5_BEFORE_ARM,
            "h5_consolidation_arms": list(H5_CONSOLIDATION_ARMS),
            "include_private_text": include_private_text,
        },
        "fixture_validation": {
            "ok": bool(validation.get("ok")),
            "case_count": validation.get("case_count"),
            "scene_count": validation.get("scene_count"),
            "density_floor": validation.get("density_floor"),
            "dataset_id": validation.get("dataset_id"),
            "schema_version": validation.get("schema_version"),
            "fixture_version": schema.FIXTURE_VERSION,
            "fixture_seed": schema.FIXTURE_SEED,
            "blocker_codes": validation.get("blocker_codes") or [],
            "coverage": validation.get("coverage"),
            "public_safety": validation.get("public_safety"),
        },
        "reproducibility": {
            "clean_clone_command": CLEAN_CLONE_COMMAND,
            "fixture_builder_command": "python benchmarks/aippocampus/builders/build_hippocampal_fixture.py --json",
            "fixture": RELATIVE_FIXTURE_PATH,
            "requires_private_registry": False,
            "requires_provider_credentials": False,
            "determinism": "human_authored_fixture_with_deterministic_baseline_outputs",
        },
        "quality_gates": quality_gates,
        "adapter_contract": _adapter_contract(),
        "outcome_weights": dict(OUTCOME_WEIGHTS),
        "views": views,
        "views_by_arm": arm_views,
        "d5_d6_gate": d5_d6_gate,
        "h5_consolidation": h5_consolidation,
        "cross_system_comparison": cross_system_comparison,
        "cases": case_results,
        "privacy_boundary": {
            "public_safe_synthetic_fixture": True,
            "raw_query_text_emitted": include_private_text,
            "raw_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "internal_inputs_emitted": False,
            "source_ref_hashes_only": not include_private_text,
        },
        "cannot_claim": [
            "full_50_scene_350_case_p1_quality",
            "real_history_h1_h2_recall_quality",
            "live_model_or_semantic_retriever_quality",
            "d4_d6_quality_gate_until_dense_reviewed_cells_exist",
            "full_d5_d6_recall_quality_from_the_public_synthetic_gate",
            "bucketed_calibration_error_without_calibrated_confidence_bins",
            "user_visible_dream_benefit_from_synthetic_h5_deltas",
            "cross_system_superiority_from_diagnostic_comparison_table",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(schema.DEFAULT_FIXTURE))
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = run_benchmark(
        args.fixture,
        include_private_text=bool(args.include_private_text),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output or args.output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"cases: {payload['fixture_validation']['case_count']}")
        print(f"quality gates ok: {payload['quality_gate_ok']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
