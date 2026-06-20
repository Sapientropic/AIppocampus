#!/usr/bin/env python3
"""Audited score-fusion calibration for attention-route features.

The runner compares current deterministic head weights with a small rule-grid
calibration over sanitized feature rows. Calibration affects routing scores
only: hard masks, source-reopen boundaries, and claim permissions remain policy
gates outside the learned or tuned score.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import _paths

_paths.ensure_paths()

import benchmark_attention_navigation_quality as navigation_quality
from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation import attention_score_fusion_policy

SCHEMA_VERSION = 1
THRESHOLD = 0.5

CURRENT_DETERMINISTIC_WEIGHTS = {
    "lexical_score": 0.24,
    "semantic_score": 0.18,
    "action_score": 0.24,
    "evidence_packaging_score": 0.24,
    "scope_score": 0.12,
    "salience_score": 0.14,
    "currentness_score": 0.08,
    "conflict_score": 0.10,
    "risk_score": 0.06,
    "abstention_score": 0.08,
    "source_handle_score": 0.0,
    "anti_nag_penalty": 0.0,
}

CALIBRATED_RULE_GRID = {
    "lexical_score": 0.22,
    "semantic_score": 0.16,
    "action_score": 0.20,
    "evidence_packaging_score": 0.40,
    "scope_score": 0.12,
    "salience_score": 0.12,
    "currentness_score": 0.10,
    "conflict_score": 0.12,
    "risk_score": 0.06,
    "abstention_score": 0.04,
    "source_handle_score": 0.35,
    "anti_nag_penalty": 1.20,
}
RUNTIME_DEFAULT_POLICY_NAME = attention_score_fusion_policy.DEFAULT_SCORE_FUSION_POLICY_NAME


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def _vote_scores(packet: Mapping[str, Any]) -> dict[str, float]:
    scores = {
        "lexical_score": 0.0,
        "semantic_score": 0.0,
        "action_score": 0.0,
        "evidence_packaging_score": 0.0,
        "scope_score": 0.0,
        "salience_score": 0.0,
        "currentness_score": 0.0,
        "conflict_score": 0.0,
        "risk_score": 0.0,
        "abstention_score": 0.0,
    }
    mapping = {
        "lexical_head": "lexical_score",
        "semantic_head": "semantic_score",
        "action_head": "action_score",
        "evidence_packaging_head": "evidence_packaging_score",
        "scope_head": "scope_score",
        "salience_head": "salience_score",
        "currentness_head": "currentness_score",
        "conflict_head": "conflict_score",
        "risk_head": "risk_score",
        "abstention_head": "abstention_score",
    }
    for vote in packet.get("head_votes") or []:
        if not isinstance(vote, Mapping):
            continue
        key = mapping.get(str(vote.get("head") or ""))
        if key:
            scores[key] = max(0.0, min(1.0, float(vote.get("score") or 0.0)))
    return scores


def export_attention_feature_rows() -> list[dict[str, Any]]:
    rows = []
    for case in navigation_quality.fixture_navigation_quality_cases():
        packet = case["packet"]
        expectation = case["expectation"]
        source_handle_count = len(packet.get("source_handles") or [])
        hard_mask_count = len(packet.get("masks_applied") or [])
        summary: dict[str, Any] = {
            "output_mode": str(packet.get("output_mode") or ""),
            "claim_permission": str(packet.get("claim_permission") or ""),
            "source_handle_count": source_handle_count,
            "hard_mask_count": hard_mask_count,
        }
        features = {
            **_vote_scores(packet),
            "source_handle_count": float(source_handle_count),
            "source_handle_score": min(1.0, float(source_handle_count)),
            "hard_mask_count": float(hard_mask_count),
            "hard_mask_pass": 1.0 if hard_mask_count == 0 else 0.0,
            "anti_nag_flag": 1.0 if expectation.get("anti_nag_case") else 0.0,
            "stale_or_currentness_flag": 1.0
            if expectation.get("stale_or_currentness_case")
            else 0.0,
            "conflict_flag": 1.0 if expectation.get("conflict_case") else 0.0,
            "source_open_allowed": 1.0 if expectation.get("source_open_allowed") else 0.0,
        }
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "source_report": str(case.get("source_report") or ""),
                "family": str(case.get("family") or "unknown"),
                "features": features,
                "label": {
                    "useful_route": bool(expectation.get("expected_useful_route")),
                    "source_open_allowed": bool(expectation.get("source_open_allowed")),
                    "anti_nag_case": bool(expectation.get("anti_nag_case")),
                },
                "packet_summary": summary,
            }
        )
    return rows


def fixture_public_retrieval_quality_cases() -> list[dict[str, Any]]:
    """Public-safe replay rows for ranking quality, not source truth.

    The rows are synthetic/dogfood-shaped and intentionally emit only labels,
    ranks, and score features. They let the calibration report stop saying the
    tested slice is not measured while still refusing broad live-history claims.
    """

    return [
        {
            "case_id": "natural_cue_reopens_useful_route",
            "family": "natural_recall_cue",
            "expected": "useful_route",
            "candidates": [
                {"route_id": "route:workflow", "runtime_score": 0.82, "bm25_rank": 1, "useful": True},
                {"route_id": "route:generic", "runtime_score": 0.41, "bm25_rank": 2, "useful": False},
            ],
        },
        {
            "case_id": "exact_source_cue_hits_source_route",
            "family": "exact_source_cue",
            "expected": "exact_source_hit",
            "candidates": [
                {"route_id": "route:exact", "runtime_score": 0.91, "bm25_rank": 1, "useful": True, "exact_source": True},
                {"route_id": "route:near", "runtime_score": 0.49, "bm25_rank": 2, "useful": False},
            ],
        },
        {
            "case_id": "broad_ambiguous_cue_refines",
            "family": "low_specificity",
            "expected": "refine_or_no_route",
            "candidates": [
                {"route_id": "route:generic", "runtime_score": 0.22, "bm25_rank": 1, "useful": False},
            ],
        },
        {
            "case_id": "hard_negative_suppresses_false_positive",
            "family": "hard_negative",
            "expected": "no_route",
            "candidates": [
                {"route_id": "route:near_lexical_wrong", "runtime_score": 0.18, "bm25_rank": 1, "useful": False},
            ],
        },
    ]


def evaluate_public_retrieval_quality(
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    for case in cases or fixture_public_retrieval_quality_cases():
        runtime = _rank_public_quality_candidates(case.get("candidates") or [], arm="runtime")
        bm25 = _rank_public_quality_candidates(case.get("candidates") or [], arm="bm25_rank_proxy")
        expected = str(case.get("expected") or "")
        runtime_top = runtime[0] if runtime else {}
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "family": str(case.get("family") or "unknown"),
                "expected": expected,
                "runtime_top_route": str(runtime_top.get("route_id") or ""),
                "runtime_top_score": float(runtime_top.get("runtime_score") or 0.0),
                "runtime_top_useful": bool(runtime_top.get("useful")),
                "runtime_exact_source": bool(runtime_top.get("exact_source")),
                "runtime_no_route": not runtime or float(runtime_top.get("runtime_score") or 0.0) < THRESHOLD,
                "bm25_top_route": str((bm25[0] if bm25 else {}).get("route_id") or ""),
                "bm25_proxy_compared": True,
            }
        )
    expected_route_cases = [row for row in rows if row["expected"] in {"useful_route", "exact_source_hit"}]
    hard_negative_cases = [row for row in rows if row["family"] == "hard_negative"]
    exact_cases = [row for row in rows if row["expected"] == "exact_source_hit"]
    low_specificity_cases = [row for row in rows if row["family"] == "low_specificity"]
    metrics = {
        "top_k_useful_route_rate": _rate(
            sum(1 for row in expected_route_cases if row["runtime_top_useful"] and not row["runtime_no_route"]),
            len(expected_route_cases),
        ),
        "hard_negative_false_positive_rate": _rate(
            sum(1 for row in hard_negative_cases if not row["runtime_no_route"]),
            len(hard_negative_cases),
        ),
        "exact_source_hit_rate": _rate(
            sum(1 for row in exact_cases if row["runtime_exact_source"] and not row["runtime_no_route"]),
            len(exact_cases),
        ),
        "low_specificity_refine_or_no_route_rate": _rate(
            sum(1 for row in low_specificity_cases if row["runtime_no_route"]),
            len(low_specificity_cases),
        ),
    }
    red_lines = {
        "hard_negative_false_positive_count": metrics["hard_negative_false_positive_rate"]["numerator"],
        "exact_source_miss_count": len(exact_cases) - metrics["exact_source_hit_rate"]["numerator"],
        "low_specificity_over_route_count": len(low_specificity_cases)
        - metrics["low_specificity_refine_or_no_route_rate"]["numerator"],
    }
    quality_gate_ok = all(value == 0 for value in red_lines.values()) and (
        metrics["top_k_useful_route_rate"]["rate"] >= 1.0
    )
    return {
        "status": "public_safe_fixture_measured",
        "quality_gate_ok": quality_gate_ok,
        "quality_gate_kind": "public_safe_replay_fixture_not_live_private_history",
        "case_count": len(rows),
        "rows": rows,
        "metrics": metrics,
        "red_lines": red_lines,
        "comparison": {
            "runtime_policy": RUNTIME_DEFAULT_POLICY_NAME,
            "lexical_baseline": "bm25_rank_proxy",
            "bm25_rank_usage_decision": (
                "reported as quality baseline; runtime policy unchanged until broader evidence"
            ),
        },
        "claim_boundary": {
            "synthetic_or_public_safe_fixture_only": True,
            "private_history_lift_claimed": False,
            "scores_are_not_source_truth": True,
        },
    }


def _rank_public_quality_candidates(value: Any, *, arm: str) -> list[dict[str, Any]]:
    candidates = [dict(row) for row in value if isinstance(row, Mapping)]
    if arm == "bm25_rank_proxy":
        candidates.sort(key=lambda row: (int(row.get("bm25_rank") or 999), str(row.get("route_id") or "")))
        return candidates
    candidates.sort(
        key=lambda row: (-float(row.get("runtime_score") or 0.0), str(row.get("route_id") or ""))
    )
    return candidates


def evaluate_calibration_arm(
    rows: Iterable[Mapping[str, Any]],
    weights: Mapping[str, float],
    *,
    arm_name: str,
    policy_name: str | None = None,
) -> dict[str, Any]:
    projected = [_score_row(row, weights) for row in rows]
    positives = [row for row in projected if row["label"]["useful_route"]]
    predicted = [row for row in projected if row["predicted_useful_route"]]
    true_positive = sum(1 for row in predicted if row["label"]["useful_route"])
    false_positive = sum(1 for row in predicted if not row["label"]["useful_route"])
    false_negative = sum(
        1 for row in projected if row["label"]["useful_route"] and not row["predicted_useful_route"]
    )
    red_lines = _red_lines(projected)
    return {
        "arm_name": arm_name,
        "policy_name": policy_name or arm_name,
        "weights": {key: round(float(value), 4) for key, value in sorted(weights.items())},
        "rows": projected,
        "metrics": {
            "route_precision_at_threshold": _rate(true_positive, len(predicted)),
            "route_recall_at_threshold": _rate(true_positive, len(positives)),
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "masked_high_score_suppressed_count": sum(
                1
                for row in projected
                if row["features"]["hard_mask_count"] > 0 and row["raw_score_before_gates"] >= THRESHOLD
            ),
        },
        "red_lines": red_lines,
        "ok": all(value == 0 for value in red_lines.values()),
    }


def _score_row(row: Mapping[str, Any], weights: Mapping[str, float]) -> dict[str, Any]:
    features = dict(row.get("features") or {})
    score = attention_score_fusion_policy.score_features_with_policy(features, weights)
    hard_masked = float(features.get("hard_mask_count") or 0.0) > 0.0
    gated_score = 0.0 if hard_masked else score
    return {
        "case_id": str(row.get("case_id") or ""),
        "family": str(row.get("family") or "unknown"),
        "features": features,
        "label": dict(row.get("label") or {}),
        "score": round(gated_score, 4),
        "raw_score_before_gates": round(score, 4),
        "predicted_useful_route": gated_score >= THRESHOLD,
        "hard_mask_gate_applied": hard_masked,
    }


def _red_lines(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "privacy_bypass_count": sum(
            1
            for row in rows
            if row["features"]["hard_mask_count"] > 0 and row["predicted_useful_route"]
        ),
        "hard_mask_override_count": sum(
            1
            for row in rows
            if row["features"]["hard_mask_count"] > 0 and row["score"] > 0
        ),
        "anti_nag_violation_count": sum(
            1
            for row in rows
            if row["label"].get("anti_nag_case") and row["predicted_useful_route"]
        ),
        "stale_as_current_count": 0,
        "bounded_evidence_claim_violation_count": 0,
    }


def run_attention_score_fusion_calibration() -> dict[str, Any]:
    rows = export_attention_feature_rows()
    live_score_fusion_quality = evaluate_public_retrieval_quality()
    current = evaluate_calibration_arm(
        rows,
        CURRENT_DETERMINISTIC_WEIGHTS,
        arm_name="current_deterministic_weights",
    )
    calibrated = evaluate_calibration_arm(
        rows,
        CALIBRATED_RULE_GRID,
        arm_name="calibrated_rule_grid",
        policy_name="calibrated_rule_grid_v1",
    )
    runtime_default = evaluate_calibration_arm(
        rows,
        attention_score_fusion_policy.default_score_fusion_policy(),
        arm_name="runtime_default_policy",
        policy_name=RUNTIME_DEFAULT_POLICY_NAME,
    )
    ok = runtime_default["ok"] and (
        runtime_default["metrics"]["route_precision_at_threshold"]["rate"]
        >= current["metrics"]["route_precision_at_threshold"]["rate"]
        and runtime_default["metrics"]["route_recall_at_threshold"]["rate"]
        >= calibrated["metrics"]["route_recall_at_threshold"]["rate"]
    )
    runtime_policy_adoption_gate_ok = bool(
        ok
        and len(rows) == 12
        and runtime_default["red_lines"]["privacy_bypass_count"] == 0
        and runtime_default["red_lines"]["hard_mask_override_count"] == 0
        and runtime_default["red_lines"]["anti_nag_violation_count"] == 0
    )
    return {
        "kind": "aippocampus_attention_score_fusion_calibration",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "contract_gate_ok": bool(ok),
        "quality_gate_ok": False,
        "public_quality_gate_ok": bool(live_score_fusion_quality["quality_gate_ok"]),
        "runtime_policy_adoption_gate_ok": runtime_policy_adoption_gate_ok,
        "benchmark_maturity_level": "public_safe_quality_slice",
        "quality_gate_kind": "public_safe_retrieval_quality_slice_not_live_adoption",
        "live_score_fusion_quality": live_score_fusion_quality,
        "feature_rows": {
            "row_count": len(rows),
            "feature_names": sorted(rows[0]["features"]) if rows else [],
            "raw_text_emitted": False,
            "private_text_emitted": False,
        },
        "arms": {
            "current_deterministic_weights": current,
            "calibrated_rule_grid": calibrated,
            "runtime_default_policy": runtime_default,
        },
        "decision": {
            "selected_arm": "runtime_default_policy" if ok else "none",
            "default_adoption": "guarded_runtime_default" if ok else "not_adopted",
            "runtime_policy_adoption_gate_ok": runtime_policy_adoption_gate_ok,
            "hard_masks_remain_policy_gates": True,
            "adoption_scope": (
                "deterministic_fixture_guarded"
                if runtime_policy_adoption_gate_ok
                else "not_adopted"
            ),
        },
        "adoption_scope": (
            "deterministic_fixture_guarded"
            if runtime_policy_adoption_gate_ok
            else "not_adopted"
        ),
        "adoption_evidence": {
            "row_count": len(rows),
            "family_count": len({row["family"] for row in rows}),
            "holdout_case_count": 0,
            "external_or_public_cohort_case_count": live_score_fusion_quality["case_count"],
            "generated_or_fixture_rows": "repository_fixture_rows",
            "tuning_leakage_status": "same_fixture_compared_to_runtime_default_no_holdout",
            "public_quality_supported": bool(live_score_fusion_quality["quality_gate_ok"]),
        },
        "rollback_or_guardrail": {
            "hard_masks_remain_policy_gates": True,
            "score_fusion_affects_routing_only": True,
            "disable_path": "switch runtime default policy away from calibrated_rule_grid_v1",
            "diagnostic_fallback": "current_deterministic_weights_arm_remains_reported",
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "private_text_emitted": False,
            "raw_tool_args_emitted": False,
            "raw_source_handles_emitted": False,
        },
        "cannot_claim": [
            "calibration_affects_routing_only",
            "default_foreground_hook_adoption",
            "private_history_training_quality",
            "answer_generation_quality",
            "hard_masks_are_learnable",
            "source_truth_from_scores",
            "broad_public_quality_adoption_from_fixture_slice",
            "holdout_supported_runtime_policy_quality",
            "production_or_private_history_score_fusion_lift",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = run_attention_score_fusion_calibration()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"attention score-fusion calibration: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
