"""Observed phase-transition priors for Xiao Xi momentum."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"


def _phase_from_history_item(item: Any, phases: Mapping[str, object]) -> str:
    if isinstance(item, str) and item in phases:
        return item
    if isinstance(item, Mapping):
        phase = item.get("phase")
        if isinstance(phase, str) and phase in phases:
            return phase
        momentum = item.get("momentum")
        if isinstance(momentum, Mapping):
            nested = momentum.get("phase")
            if isinstance(nested, str) and nested in phases:
                return nested
    return ""


def _empty_transition_counts(phase_order: Sequence[str]) -> dict[str, dict[str, int]]:
    return {phase: {target: 0 for target in phase_order} for phase in phase_order}


def phase_transition_prior(
    history: Sequence[Any],
    *,
    phases: Mapping[str, object],
    phase_order: Sequence[str],
    current_phase: str | None = None,
    top_n: int = 3,
) -> dict[str, object]:
    observed = [_phase_from_history_item(item, phases) for item in history]
    observed = [phase for phase in observed if phase]
    counts = _empty_transition_counts(phase_order)
    for source, target in zip(observed, observed[1:], strict=False):
        counts[source][target] += 1

    target_phase = current_phase if current_phase in phases else (observed[-1] if observed else "")
    row_counts = counts.get(target_phase, {}) if target_phase else {}
    sample_count = sum(row_counts.values())
    top = [
        {
            "phase": phase,
            "sample_count": count,
            "probability": round(count / sample_count, 6) if sample_count else 0.0,
            "reason_codes": [
                "observed_phase_transition_count",
                "thin_sample_boundary" if sample_count < 3 else "observed_sample_boundary",
            ],
        }
        for phase, count in sorted(
            row_counts.items(),
            key=lambda item: (-item[1], phase_order.index(item[0])),
        )
        if count > 0
    ][: max(0, top_n)]
    confidence = "none" if sample_count == 0 else "thin_sample" if sample_count < 3 else "observed"
    reason_codes = ["observed_macro_phase_history"]
    reason_codes.append(
        "insufficient_history"
        if sample_count == 0
        else "thin_sample_boundary"
        if sample_count < 3
        else "observed_transition_distribution"
    )
    recheck_hint = (
        {
            "kind": "xiao_xi_phase_transition_recheck_hint",
            "current_phase": target_phase,
            "top_next_phase": top[0]["phase"],
            "sample_count": sample_count,
            "action_grammar": ACTION_GRAMMAR,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
            "source_reopen_required_before_claim": True,
        }
        if top
        else None
    )
    return {
        "kind": "xiao_xi_phase_transition_prior",
        "transition_matrix_kind": "xiao_xi_12x12_observed_history",
        "phase_order": list(phase_order),
        "current_phase": target_phase,
        "status": "insufficient_history" if sample_count == 0 else "observed_prior",
        "confidence": confidence,
        "sample_count": sample_count,
        "total_transition_count": sum(sum(row.values()) for row in counts.values()),
        "transition_counts": counts,
        "top_next_phase_priors": top,
        "reason_codes": reason_codes,
        "recheck_hint": recheck_hint,
        "observed_history_only": True,
        "not_prediction_authority": True,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_reopen_required_before_claim": True,
    }


__all__ = ["phase_transition_prior"]
