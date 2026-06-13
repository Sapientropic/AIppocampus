"""Navigation-only Macro/Yi guidance for Dream queue and workers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"
PROTECTED_TRIGGER_FAMILIES = {
    "explicit_operator_request",
    "correction_outcome",
    "recall_miss_feedback",
}

_DECLINING_TERMS = {
    "blocked",
    "blocked_decline",
    "decline",
    "declining",
    "decay",
    "first_decay",
    "hibernating",
    "hibernation",
    "stale",
    "superseded",
}
_RISING_OR_BALANCED_TERMS = {
    "active",
    "balanced",
    "equilibrium",
    "neutral",
    "rising",
    "stable",
    "steady",
}
_DREAM_RECHECK_TERMS = {
    "dream",
    "dream_seed",
    "macro_recheck",
    "momentum_first_decay_recheck",
    "runtime_recheck",
}


def _stable_digest(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return [str(item) for item in value if item not in {None, ""}]
    return []


def _tokens_from_context(context: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(context, Mapping):
        return set()
    values: list[str] = []
    for key in (
        "direction",
        "phase",
        "phase_hint",
        "momentum_phase",
        "status",
        "lifecycle_status",
        "state",
    ):
        values.extend(_string_values(context.get(key)))
    values.extend(_string_values(context.get("recheck_on")))
    values.extend(_string_values(context.get("reason_codes")))
    values.extend(_string_values(context.get("diagnostics")))
    return {value.strip().casefold() for value in values if value.strip()}


def macro_momentum_priority_adjustment(
    context: Mapping[str, Any] | None,
    *,
    trigger_family: str,
    dream_function: str,
    cap: int = 10,
) -> dict[str, Any]:
    """Return a bounded Dream queue adjustment from macro momentum.

    Momentum is only a navigation hint. Source-backed trigger family remains
    primary because corrections, recall misses, and explicit operator requests
    already carry stronger reopen intent than symbolic phase shape.
    """

    tokens = _tokens_from_context(context)
    base = {
        "kind": "macro_momentum_priority_adjustment",
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "navigation_only": True,
        "may_create_dream_work": False,
        "may_emit_foreground_instruction": False,
        "may_be_used_as_source_evidence": False,
    }
    if not tokens:
        return {
            **base,
            "adjustment": 0,
            "reason_code": "macro_momentum_context_absent",
            "matched_terms": [],
        }
    if trigger_family in PROTECTED_TRIGGER_FAMILIES:
        return {
            **base,
            "adjustment": 0,
            "reason_code": "macro_momentum_does_not_override_source_backed_trigger",
            "matched_terms": sorted(tokens & (_DECLINING_TERMS | _DREAM_RECHECK_TERMS))[:8],
        }

    declining = bool(tokens & _DECLINING_TERMS)
    dream_recheck = bool(tokens & _DREAM_RECHECK_TERMS)
    rising_or_balanced = bool(tokens & _RISING_OR_BALANCED_TERMS)
    if declining or dream_recheck:
        raw = 8 if dream_function == "compensatory" else 3
        reason = (
            "macro_momentum_declining_compensatory_bump"
            if dream_function == "compensatory"
            else "macro_momentum_recheck_secondary_bump"
        )
    elif rising_or_balanced:
        raw = 0
        reason = "macro_momentum_rising_or_balanced_no_bump"
    else:
        raw = 0
        reason = "macro_momentum_no_priority_bump"
    return {
        **base,
        "adjustment": max(0, min(int(cap), raw)),
        "reason_code": reason,
        "matched_terms": sorted(tokens & (_DECLINING_TERMS | _RISING_OR_BALANCED_TERMS | _DREAM_RECHECK_TERMS))[:8],
    }


def priority_with_macro_momentum(
    *,
    base_priority: int,
    trigger_family: str,
    dream_function: str,
    context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    adjustment = macro_momentum_priority_adjustment(
        context,
        trigger_family=trigger_family,
        dream_function=dream_function,
    )
    value = int(base_priority) + int(adjustment["adjustment"])
    return {
        "priority": value,
        "base_priority": int(base_priority),
        "macro_momentum": adjustment,
    }


def _nested_mapping(context: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = context.get(key)
    return value if isinstance(value, Mapping) else {}


def _band_from_perturbation(context: Mapping[str, Any] | None) -> str:
    if not isinstance(context, Mapping):
        return "none"
    fanout = _nested_mapping(context, "fanout_hint")
    return compact_text(
        str(
            context.get("band")
            or context.get("perturbation_band")
            or context.get("amplitude")
            or fanout.get("band")
            or "none"
        ),
        40,
    ).casefold()


def _int_value(value: object, fallback: int = 0) -> int:
    if type(value) is int:
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def dream_worker_strategy_from_perturbation(
    context: Mapping[str, Any] | None,
    *,
    default_max_samples: int = 1,
    hard_cap: int = 3,
) -> dict[str, Any]:
    """Map macro perturbation width to a small Dream worker strategy.

    The foreground route fanout can be wider than Dream's model sample budget.
    Dream only receives a capped scan strategy, and inversion always pauses at
    source reopen/conflict review before any expanded generation.
    """

    safe_default = max(1, int(default_max_samples))
    safe_cap = max(1, int(hard_cap))
    band = _band_from_perturbation(context)
    fanout = _nested_mapping(context or {}, "fanout_hint") if isinstance(context, Mapping) else {}
    route_policy = compact_text(str((context or {}).get("route_policy") or ""), 80) if isinstance(context, Mapping) else ""
    conflict_review = (
        bool((context or {}).get("conflict_review_required")) if isinstance(context, Mapping) else False
    ) or band == "inversion" or "conflict_review" in route_policy

    if conflict_review:
        strategy = {
            "strategy": "conflict_review_first",
            "max_samples": safe_default,
            "dream_candidate_budget": safe_default,
            "candidate_limit_after_review": min(
                safe_cap,
                max(safe_default, _int_value(fanout.get("candidate_limit_after_review"), safe_default)),
            ),
            "requires_conflict_review_before_expand": True,
            "reason_code": "inversion_requires_source_reopen_before_dream_expand",
        }
    elif band in {"large", "wide", "large_shift", "broad"}:
        budget = min(
            safe_cap,
            max(safe_default, min(safe_cap, _int_value(fanout.get("recommended_candidate_limit"), 2))),
        )
        strategy = {
            "strategy": "expanded_bounded",
            "max_samples": budget,
            "dream_candidate_budget": budget,
            "candidate_limit_after_review": budget,
            "requires_conflict_review_before_expand": False,
            "reason_code": "large_perturbation_bounded_dream_scan",
        }
    elif band in {"medium", "perspective_shift"}:
        budget = min(safe_cap, max(safe_default, 2))
        strategy = {
            "strategy": "medium_bounded_scan",
            "max_samples": budget,
            "dream_candidate_budget": budget,
            "candidate_limit_after_review": budget,
            "requires_conflict_review_before_expand": False,
            "reason_code": "medium_perturbation_bounded_dream_scan",
        }
    else:
        strategy = {
            "strategy": "conservative_check",
            "max_samples": safe_default,
            "dream_candidate_budget": safe_default,
            "candidate_limit_after_review": safe_default,
            "requires_conflict_review_before_expand": False,
            "reason_code": "none_or_local_perturbation_conservative_dream_check",
        }

    payload = {
        "kind": "macro_perturbation_dream_worker_strategy",
        "band": band,
        "route_policy": route_policy,
        "recommended_candidate_limit_seen": _int_value(fanout.get("recommended_candidate_limit"), 0),
        "raw_foreground_fanout_copied": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "navigation_only": True,
        "may_create_source_claim": False,
        "foreground_eligible": False,
        **strategy,
    }
    redacted = redact_sensitive_values(redact_private_paths(payload))
    return redacted if isinstance(redacted, dict) else payload


def line_topology_dream_seed_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if row.get("kind") != "macro_line_topology_diagnostics":
        return None
    broken = [
        item
        for item in row.get("broken_couplings") or []
        if isinstance(item, Mapping) and str(item.get("status") or "") == "missing_lower_support"
    ]
    if not broken:
        return None
    refs = safe_source_refs(
        row.get("source_refs")
        or row.get("snapshot_refs")
        or (_nested_mapping(row, "source_shape_descriptor").get("source_refs"))
    )
    if not refs:
        return None
    adjacent_pressure = [
        item
        for item in row.get("adjacent_relations") or []
        if isinstance(item, Mapping)
        and str(item.get("diagnostic") or "") == "adjacent_pressure_without_lower_support"
    ]
    reason_codes = [
        compact_text(str(item.get("diagnostic") or ""), 100)
        for item in [*broken, *adjacent_pressure]
    ]
    reason_codes.extend(_string_values(row.get("reason_codes")))
    reason_codes = [
        code
        for code in dict.fromkeys(reason_codes)
        if code and code != "topology_no_broken_cross_layer_coupling"
    ][:10]
    source_shape_id = compact_text(str(row.get("source_shape_id") or row.get("descriptor_id") or ""), 140)
    pair_ids = [
        compact_text(str(item.get("pair_id") or ""), 80)
        for item in broken
        if compact_text(str(item.get("pair_id") or ""), 80)
    ]
    payload = {
        "seed_id": _stable_digest(source_shape_id, pair_ids, reason_codes, refs, prefix="ltopo_seed"),
        "seed_kind": "line_topology_dream_seed",
        "title": "Line topology broken coupling seed",
        "summary": (
            "Broken cross-layer coupling can route a compensatory Dream probe; "
            "topology is diagnostic-only and source must be reopened before claims."
        ),
        "source_refs": refs,
        "source_finding_ids": [source_shape_id] if source_shape_id else [],
        "frontiers": reason_codes,
        "themes": [*pair_ids, *reason_codes, source_shape_id],
        "concepts": [*pair_ids, *reason_codes],
        "negative_contexts": [
            "line topology is navigation context, not evidence",
            "broken coupling may seed compensatory Dream review only after source-pack eligibility",
            "do not change route ranking or macro state from topology alone",
        ],
        "preferred_dream_functions": ["compensatory"],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "ranking_weight_changes": False,
    }
    redacted = redact_sensitive_values(redact_private_paths(payload))
    return redacted if isinstance(redacted, dict) else payload


__all__ = [
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "PROTECTED_TRIGGER_FAMILIES",
    "dream_worker_strategy_from_perturbation",
    "line_topology_dream_seed_payload",
    "macro_momentum_priority_adjustment",
    "priority_with_macro_momentum",
]
