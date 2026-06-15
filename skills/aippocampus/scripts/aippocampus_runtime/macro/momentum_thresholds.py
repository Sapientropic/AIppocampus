"""Named Xiao Xi momentum threshold metadata."""

from __future__ import annotations

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
MOMENTUM_THRESHOLD_SET_ID = "xiaoxi_initial_heuristic_v0"
MOMENTUM_THRESHOLD_METADATA = {
    "threshold_set_id": MOMENTUM_THRESHOLD_SET_ID,
    "calibration_state": "initial_heuristic",
    "basis": "source_backed_delta_net_score_bands",
    "last_reviewed": "2026-06-15",
    "thresholds_are_evidence_scores": False,
    "future_calibration_requires": "observed_source_backed_delta_history_with_stable_outcomes",
}
POSITIVE_PHASE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (1.20, "qian"),
    (0.90, "guai"),
    (0.60, "dazhuang"),
    (0.35, "tai"),
    (0.15, "lin"),
)
NEGATIVE_PHASE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (-1.20, "kun"),
    (-0.90, "bo"),
    (-0.60, "guan"),
    (-0.35, "pi"),
    (-0.15, "dun"),
)


def momentum_threshold_report() -> dict[str, object]:
    return {
        **MOMENTUM_THRESHOLD_METADATA,
        "positive_phase_thresholds": [
            {"minimum_net_delta": threshold, "phase": phase}
            for threshold, phase in POSITIVE_PHASE_THRESHOLDS
        ],
        "negative_phase_thresholds": [
            {"maximum_net_delta": threshold, "phase": phase}
            for threshold, phase in NEGATIVE_PHASE_THRESHOLDS
        ],
        "zero_delta_phase": "kun",
        "small_positive_phase": "fu",
        "small_nonpositive_nonzero_phase": "gou",
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
    }


__all__ = [
    "MOMENTUM_THRESHOLD_METADATA",
    "MOMENTUM_THRESHOLD_SET_ID",
    "NEGATIVE_PHASE_THRESHOLDS",
    "POSITIVE_PHASE_THRESHOLDS",
    "momentum_threshold_report",
]
