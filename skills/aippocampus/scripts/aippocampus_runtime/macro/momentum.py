from __future__ import annotations

from typing import Mapping

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
MOMENTUM_BASIS_KEYS = (
    "support_delta",
    "counter_evidence_delta",
    "route_success_delta",
    "staleness_delta",
    "user_correction_delta",
)
PHASE_ORDER = (
    "fu",
    "lin",
    "tai",
    "dazhuang",
    "guai",
    "qian",
    "gou",
    "dun",
    "pi",
    "guan",
    "bo",
    "kun",
)

PHASES: dict[str, dict[str, object]] = {
    "fu": {
        "name": "复",
        "public_label": "revival",
        "direction": "turning",
        "route_policy": "revived_route_probe",
        "recheck_on": ("momentum_turn_recheck",),
    },
    "lin": {
        "name": "临",
        "public_label": "early_growth",
        "direction": "rising",
        "route_policy": "increase_attention_gradually",
        "recheck_on": (),
    },
    "tai": {
        "name": "泰",
        "public_label": "balanced_decision_window",
        "direction": "rising",
        "route_policy": "balanced_decision_window",
        "recheck_on": (),
    },
    "dazhuang": {
        "name": "大壮",
        "public_label": "strong_growth",
        "direction": "rising",
        "route_policy": "push_with_source_checks",
        "recheck_on": (),
    },
    "guai": {
        "name": "夬",
        "public_label": "closeout_pressure",
        "direction": "peaking",
        "route_policy": "closeout_with_overconfidence_watch",
        "recheck_on": ("momentum_overconfidence_watch",),
    },
    "qian": {
        "name": "乾",
        "public_label": "overfull_peak",
        "direction": "peaking",
        "route_policy": "closeout_with_overconfidence_watch",
        "recheck_on": ("momentum_overconfidence_watch",),
    },
    "gou": {
        "name": "姤",
        "public_label": "first_decay",
        "direction": "turning",
        "route_policy": "first_decay_recheck",
        "recheck_on": ("momentum_first_decay_recheck",),
    },
    "dun": {
        "name": "遁",
        "public_label": "withdrawal",
        "direction": "declining",
        "route_policy": "reduce_push_and_reopen_currentness",
        "recheck_on": ("momentum_first_decay_recheck",),
    },
    "pi": {
        "name": "否",
        "public_label": "blocked_decline",
        "direction": "declining",
        "route_policy": "hold_or_reassess",
        "recheck_on": ("momentum_decline_recheck",),
    },
    "guan": {
        "name": "观",
        "public_label": "observation",
        "direction": "declining",
        "route_policy": "observe_before_action",
        "recheck_on": ("momentum_decline_recheck",),
    },
    "bo": {
        "name": "剥",
        "public_label": "peeling",
        "direction": "hibernating",
        "route_policy": "peeling_or_archive_review",
        "recheck_on": ("momentum_hibernation_review",),
    },
    "kun": {
        "name": "坤",
        "public_label": "hibernating",
        "direction": "hibernating",
        "route_policy": "hibernate_until_new_source",
        "recheck_on": ("momentum_hibernation_review",),
    },
}


def default_momentum_basis() -> dict[str, float]:
    return {key: 0.0 for key in MOMENTUM_BASIS_KEYS}


def normalize_momentum_basis(basis: Mapping[str, object] | None = None) -> dict[str, float]:
    values = default_momentum_basis()
    if basis is None:
        return values
    for key, raw in basis.items():
        if key not in values:
            continue
        if not isinstance(raw, int | float) or isinstance(raw, bool):
            raise ValueError(f"momentum basis {key!r} must be numeric")
        values[key] = float(raw)
    return values


def _score_from_basis(basis: Mapping[str, float]) -> float:
    support = basis["support_delta"] + basis["route_success_delta"]
    friction = (
        basis["counter_evidence_delta"]
        + basis["staleness_delta"]
        + basis["user_correction_delta"]
    )
    return support - friction


def phase_from_momentum_basis(basis: Mapping[str, object] | None = None) -> str:
    values = normalize_momentum_basis(basis)
    if all(abs(value) < 0.000001 for value in values.values()):
        return "kun"
    score = _score_from_basis(values)
    if score >= 1.20:
        return "qian"
    if score >= 0.90:
        return "guai"
    if score >= 0.60:
        return "dazhuang"
    if score >= 0.35:
        return "tai"
    if score >= 0.15:
        return "lin"
    if score > 0.0:
        return "fu"
    if score <= -1.20:
        return "kun"
    if score <= -0.90:
        return "bo"
    if score <= -0.60:
        return "guan"
    if score <= -0.35:
        return "pi"
    if score <= -0.15:
        return "dun"
    return "gou"


def build_momentum_block(
    basis: Mapping[str, object] | None = None,
) -> dict[str, object]:
    normalized = normalize_momentum_basis(basis)
    phase = phase_from_momentum_basis(normalized)
    info = PHASES[phase]
    raw_recheck = info["recheck_on"]
    recheck_on = list(raw_recheck) if isinstance(raw_recheck, tuple) else []
    support = normalized["support_delta"] + normalized["route_success_delta"]
    friction = (
        normalized["counter_evidence_delta"]
        + normalized["staleness_delta"]
        + normalized["user_correction_delta"]
    )
    # This is a trend-compression heuristic over existing source-backed deltas,
    # not a second evidence score or a metaphysical project-state claim.
    return {
        "phase": phase,
        "phase_name": info["name"],
        "public_label": info["public_label"],
        "direction": info["direction"],
        "basis": normalized,
        "trend": {
            "supporting_delta": support,
            "friction_delta": friction,
            "net_delta": support - friction,
        },
        "route_policy": info["route_policy"],
        "recheck_on": recheck_on,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_boundary": {
            "navigation_only_not_fact": True,
            "basis_must_be_source_backed_deltas": True,
            "not_perturbation_amplitude": True,
            "no_energy_or_metaphysical_score": True,
        },
    }


def coerce_momentum_block(value: Mapping[str, object] | None = None) -> dict[str, object]:
    if value is None:
        return build_momentum_block()
    raw_basis = value.get("basis") if "basis" in value else value
    if raw_basis is not None and not isinstance(raw_basis, Mapping):
        raise ValueError("momentum basis must be a mapping")
    return build_momentum_block(raw_basis)


def validate_momentum_block(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["momentum_must_be_mapping"]
    phase = value.get("phase")
    if phase not in PHASES:
        errors.append("momentum_phase_invalid")
    info = PHASES.get(str(phase))
    if info and value.get("direction") != info["direction"]:
        errors.append("momentum_direction_mismatch")
    basis = value.get("basis")
    if not isinstance(basis, Mapping):
        errors.append("momentum_basis_invalid")
    else:
        if set(basis) != set(MOMENTUM_BASIS_KEYS):
            errors.append("momentum_basis_keys_invalid")
        try:
            normalize_momentum_basis(basis)
        except ValueError:
            errors.append("momentum_basis_values_invalid")
    if value.get("authority_level") != AUTHORITY_LEVEL:
        errors.append("momentum_authority_must_be_navigation_only")
    if value.get("action_grammar") != ACTION_GRAMMAR:
        errors.append("momentum_action_grammar_must_be_direction_only")
    if value.get("claim_permission") != CLAIM_PERMISSION:
        errors.append("momentum_claim_permission_must_require_reopen")
    if value.get("fact_claim_allowed") is not False:
        errors.append("momentum_fact_claim_must_be_false")
    return errors


def momentum_recheck_triggers(value: Mapping[str, object]) -> list[str]:
    raw = value.get("recheck_on")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def stale_after_days_for_momentum(value: Mapping[str, object], *, default: int) -> int:
    phase = value.get("phase")
    if phase in {"guai", "qian"}:
        return min(default, 21)
    if phase in {"gou", "dun", "pi", "guan"}:
        return min(default, 14)
    if phase in {"bo", "kun"}:
        return max(default, 60)
    return default


__all__ = [
    "ACTION_GRAMMAR",
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "MOMENTUM_BASIS_KEYS",
    "PHASE_ORDER",
    "PHASES",
    "build_momentum_block",
    "coerce_momentum_block",
    "default_momentum_basis",
    "momentum_recheck_triggers",
    "normalize_momentum_basis",
    "phase_from_momentum_basis",
    "stale_after_days_for_momentum",
    "validate_momentum_block",
]
