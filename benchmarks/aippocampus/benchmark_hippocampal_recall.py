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

import hippocampal_fixture_schema as schema

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
        "wrong_twin_selection_count": outcome_counts.get("wrong_twin_selection", 0),
        "overconfidence_rate": _rate(outcome_counts.get("overconfident_evidence", 0), total),
        "underconfidence_rate": _rate(outcome_counts.get("underconfident_scent", 0), total),
        "abstention_accuracy": _rate(skip_correct, skip_expected),
        "scent_precision": _rate(scent_precision_hits, scent_attempts),
        "scent_attempt_count": scent_attempts,
        "scent_precision_hit_count": scent_precision_hits,
        "outcome_counts": outcome_counts,
        "scent_layer_counts": scent_layer_counts,
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


def run_benchmark(
    fixture_path: str | Path = schema.DEFAULT_FIXTURE,
    *,
    include_private_text: bool = False,
) -> dict[str, Any]:
    rows = schema.load_fixture(fixture_path)
    validation = schema.validate_fixture(rows)
    case_results: list[dict[str, Any]] = []
    for case in rows:
        baseline_outputs = _as_mapping(case.get("baseline_outputs"))
        for arm in DEFAULT_ARMS:
            response = _as_mapping(baseline_outputs.get(arm))
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
    quality_gates = _quality_gates(validation, views)
    baseline_captured = bool(validation.get("ok")) and len(case_results) >= len(rows)
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
            "baseline_arms": list(DEFAULT_ARMS),
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
            "fixture_builder_command": "python benchmarks/aippocampus/build_hippocampal_fixture.py --json",
            "fixture": RELATIVE_FIXTURE_PATH,
            "requires_private_registry": False,
            "requires_provider_credentials": False,
            "determinism": "human_authored_fixture_with_deterministic_baseline_outputs",
        },
        "quality_gates": quality_gates,
        "outcome_weights": dict(OUTCOME_WEIGHTS),
        "views": views,
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
            "bucketed_calibration_error_without_calibrated_confidence_bins",
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
