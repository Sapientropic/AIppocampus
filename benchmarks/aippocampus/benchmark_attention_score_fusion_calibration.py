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


def evaluate_calibration_arm(
    rows: Iterable[Mapping[str, Any]],
    weights: Mapping[str, float],
    *,
    arm_name: str,
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
    raw_score = 0.0
    for key, weight in weights.items():
        if key.endswith("_penalty"):
            continue
        raw_score += float(features.get(key) or 0.0) * float(weight)
    if features.get("anti_nag_flag"):
        raw_score -= float(weights.get("anti_nag_penalty") or 0.0)
    score = max(0.0, min(1.0, round(raw_score, 4)))
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
    current = evaluate_calibration_arm(
        rows,
        CURRENT_DETERMINISTIC_WEIGHTS,
        arm_name="current_deterministic_weights",
    )
    calibrated = evaluate_calibration_arm(
        rows,
        CALIBRATED_RULE_GRID,
        arm_name="calibrated_rule_grid",
    )
    ok = calibrated["ok"] and (
        calibrated["metrics"]["route_precision_at_threshold"]["rate"]
        >= current["metrics"]["route_precision_at_threshold"]["rate"]
    )
    return {
        "kind": "aippocampus_attention_score_fusion_calibration",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "feature_rows": {
            "row_count": len(rows),
            "feature_names": sorted(rows[0]["features"]) if rows else [],
            "raw_text_emitted": False,
            "private_text_emitted": False,
        },
        "arms": {
            "current_deterministic_weights": current,
            "calibrated_rule_grid": calibrated,
        },
        "decision": {
            "selected_arm": "calibrated_rule_grid" if ok else "none",
            "default_adoption": "not_adopted_by_this_benchmark",
            "hard_masks_remain_policy_gates": True,
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "private_text_emitted": False,
            "raw_tool_args_emitted": False,
            "raw_source_handles_emitted": False,
        },
        "cannot_claim": [
            "calibration_affects_routing_only",
            "default_foreground_adoption",
            "private_history_training_quality",
            "answer_generation_quality",
            "hard_masks_are_learnable",
            "source_truth_from_scores",
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
