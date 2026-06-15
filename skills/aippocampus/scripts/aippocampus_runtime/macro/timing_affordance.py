"""Navigation-only macro timing affordance reducer.

This reducer keeps timing as an attention decision. It can say "act now",
"probe gently", or "reopen first", but it never turns macro posture into source
evidence or mutates foreground recall budgets.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeAlias

from aippocampus_runtime.recall import prompt_recall_budget

TimingPosture: TypeAlias = Literal[
    "act_now_bounded",
    "probe_gently",
    "hold_recheck",
    "narrow_before_widening",
    "conflict_reopen_first",
    "hibernate_until_source",
]
AttentionBandwidth: TypeAlias = Literal[
    "silent",
    "backstage",
    "narrow",
    "normal",
    "wide",
    "reopen_first",
]

AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(mapping: Mapping[str, Any], *keys: str) -> bool:
    return any(bool(mapping.get(key)) for key in keys)


def _status(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(mapping.get(key))
        if value:
            return value
    return "unknown"


def _reason(*items: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def macro_timing_affordance(
    *,
    momentum: Mapping[str, Any] | None = None,
    perturbation: Mapping[str, Any] | None = None,
    topology: Mapping[str, Any] | None = None,
    source_shape: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reduce macro runtime signals into an action timing posture."""

    mom = momentum or {}
    pert = perturbation or {}
    topo = topology or {}
    shape = source_shape or {}
    phase = _status(mom, "phase", "momentum_phase", "status")
    freshness = _status(shape, "freshness", "freshness_status", "currentness_status")
    source_coverage = _status(shape, "source_coverage", "source_coverage_status", "coverage")
    band = _status(pert, "band", "amplitude_band", "perturbation_band")
    conflict = _bool(shape, "conflict", "contested", "stale_conflict_checks_required") or _bool(
        pert,
        "conflict_review_required",
        "stale_conflict_checks_required",
    )
    broken = _bool(topo, "broken_coupling", "invariant_break", "obstruction")
    hibernating = phase in {"hibernating", "sleeping", "dormant"}
    closeout = phase in {"closeout", "closeout_pressure", "verification", "release"}
    revival = phase in {"revival", "seed", "seed_probe", "thin_revival"}
    thin_source = source_coverage in {"thin", "low", "missing", "unknown"}
    current = freshness in {"current", "fresh", "ready"}

    if hibernating and not current:
        posture: TimingPosture = "hibernate_until_source"
        bandwidth: AttentionBandwidth = "silent"
        next_action = "stay_silent_until_new_source"
        reasons = _reason("hibernating_phase", "no_new_source")
    elif conflict or broken or freshness in {"stale", "expired", "conflicted"}:
        posture = "conflict_reopen_first"
        bandwidth = "reopen_first"
        next_action = "reopen_source_before_ranking"
        reasons = _reason("source_conflict_or_staleness", "local_global_guard_before_ranking")
    elif closeout and current and band in {"local", "small", "bounded", "one_line"}:
        posture = "act_now_bounded"
        bandwidth = "normal"
        next_action = "run_bounded_verification_then_close"
        reasons = _reason("closeout_pressure", "current_source", "local_perturbation")
    elif revival and thin_source:
        posture = "probe_gently"
        bandwidth = "backstage"
        next_action = "prepare_background_probe_with_source_reopen"
        reasons = _reason("revival_phase", "thin_source")
    elif band in {"wide", "large", "global"}:
        posture = "narrow_before_widening"
        bandwidth = "narrow"
        next_action = "narrow_scope_before_wide_search"
        reasons = _reason("wide_perturbation", "avoid_premature_foreground_fanout")
    else:
        posture = "hold_recheck"
        bandwidth = "narrow"
        next_action = "hold_for_recheck_or_more_source"
        reasons = _reason("insufficient_timing_signal")

    return {
        "kind": "macro_timing_affordance",
        "timing_posture": posture,
        "attention_bandwidth": bandwidth,
        "recommended_next": next_action,
        "reason_codes": reasons,
        "inputs": {
            "phase": phase,
            "freshness": freshness,
            "source_coverage": source_coverage,
            "perturbation_band": band,
            "conflict": conflict,
            "broken_coupling": broken,
        },
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_reopen_required_before_claim": True,
        "boundary": {
            "timing_is_navigation_only": True,
            "does_not_mutate_recall_budget": True,
            "does_not_transfer_fact": True,
        },
    }


def timing_affordance_feedback_gate(
    foreground_outcomes: Sequence[Mapping[str, Any]],
    *,
    scope: str = "macro_timing",
    window: int = 5,
    min_repeated_misses: int = 2,
) -> dict[str, Any]:
    """Detect repeated foreground misses and recommend a recheck budget posture."""

    rows = [row for row in foreground_outcomes if isinstance(row, Mapping)][-max(1, window):]
    bad_signals = {
        "source_miss",
        "source_reopen_miss",
        "read_timeout",
        "timeout",
        "wrong_route_drag",
        "insufficient_source",
    }
    counts = Counter(_text(row.get("outcome") or row.get("signal")) for row in rows)
    miss_count = sum(counts.get(signal, 0) for signal in bad_signals)
    triggered = miss_count >= min_repeated_misses
    budget = prompt_recall_budget.semantic_budget_result(
        "timing_affordance_falsified" if triggered else "timing_affordance_feedback_observed",
        requested_timeout=None,
        effective_timeout=None,
        max_elapsed_ms=None,
    )
    if not triggered:
        budget["decision"] = "keep"
        budget["available"] = True
        budget["budget"]["agent_next_action"] = "no_budget_change_needed"
    return {
        "kind": "timing_affordance_feedback_gate",
        "scope": str(scope or "macro_timing")[:120],
        "window_size": len(rows),
        "miss_count": miss_count,
        "signal_counts": dict(sorted(counts.items())),
        "timing_affordance_falsified": triggered,
        "runtime_recheck_reason": "timing_affordance_falsified" if triggered else "",
        "budget_recommendation": budget["budget"],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "boundary": {
            "feedback_gate_is_no_write": True,
            "budget_recommendation_is_not_policy_mutation": True,
            "single_timeout_does_not_falsify": min_repeated_misses > 1,
        },
    }


__all__ = [
    "AttentionBandwidth",
    "TimingPosture",
    "macro_timing_affordance",
    "timing_affordance_feedback_gate",
]
