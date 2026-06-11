"""Deterministic attention-router score-fusion policies.

Scores are routing diagnostics only. Hard masks, source-reopen requirements,
and claim permissions stay outside score fusion so a high score cannot turn a
blocked route into usable evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_SCORE_FUSION_POLICY_NAME = "calibrated_rule_grid_v1"

LEGACY_DETERMINISTIC_SCORE_FUSION_POLICY = {
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

CALIBRATED_SCORE_FUSION_POLICY = {
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

DEFAULT_SCORE_FUSION_POLICY = CALIBRATED_SCORE_FUSION_POLICY


def default_score_fusion_policy() -> dict[str, float]:
    return dict(DEFAULT_SCORE_FUSION_POLICY)


def score_features_with_policy(
    features: Mapping[str, Any],
    weights: Mapping[str, float] | None = None,
) -> float:
    policy = weights or DEFAULT_SCORE_FUSION_POLICY
    raw_score = 0.0
    for key, weight in policy.items():
        if key.endswith("_penalty"):
            continue
        raw_score += float(features.get(key) or 0.0) * float(weight)
    if features.get("anti_nag_flag"):
        raw_score -= float(policy.get("anti_nag_penalty") or 0.0)
    return max(0.0, min(1.0, round(raw_score, 4)))
