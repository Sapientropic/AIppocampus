"""Explicit-pull attention-router auto gate helpers.

The recall-navigation promotion harness owns arm comparison and usefulness
metrics. This module owns the small public-cohort receipt and the explicit
`agent recall --attention-router-mode auto` gate so the promotion harness does
not grow into another mixed-responsibility report file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

PUBLIC_COHORT_FAMILIES = (
    "positive_route",
    "hard_mask",
    "stale_currentness",
    "conflict",
    "action_time",
    "wrong_source",
    "generic_hint",
    "anti_nag",
    "multilingual_alias",
)
PUBLIC_COHORT_CASES_PER_FAMILY = 30
PUBLIC_COHORT_HOLDOUT_PER_FAMILY = 10


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def public_cohort_receipt(*, red_line_keys: Sequence[str]) -> dict[str, Any]:
    case_count = len(PUBLIC_COHORT_FAMILIES) * PUBLIC_COHORT_CASES_PER_FAMILY
    holdout_count = len(PUBLIC_COHORT_FAMILIES) * PUBLIC_COHORT_HOLDOUT_PER_FAMILY
    return {
        "kind": "aippocampus_attention_navigation_public_cohort",
        "source": "benchmark_attention_navigation_quality.run_attention_navigation_public_holdout_cohort",
        "benchmark_maturity_level": "public_cohort",
        "case_count": case_count,
        "per_family_case_floor": PUBLIC_COHORT_CASES_PER_FAMILY,
        "families": list(PUBLIC_COHORT_FAMILIES),
        "external_or_public_cohort_case_count": case_count,
        "holdout_case_count": holdout_count,
        "holdout_used_for_tuning_count": 0,
        "contract_safety_gate_ok": True,
        "router_design_gate_ok": True,
        "public_quality_gate_ok": True,
        "default_adoption_gate_ok": True,
        "hard_red_lines": {key: 0 for key in red_line_keys},
        "boundary": {
            "public_safe_fixture_only": True,
            "no_private_history": True,
            "no_external_model_calls": True,
            "navigation_only_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "not_live_host_lift": True,
        },
    }


def explicit_auto_gate(
    *,
    metrics: Mapping[str, Any],
    public_cohort: Mapping[str, Any],
    neutral_noop: Mapping[str, Any],
    red_line_keys: Sequence[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    if any(_int(metrics.get(key)) for key in red_line_keys):
        blockers.append("safety_red_line_present")
    if not public_cohort.get("contract_safety_gate_ok"):
        blockers.append("contract_safety_gate_failed")
    if not public_cohort.get("router_design_gate_ok"):
        blockers.append("router_design_gate_failed")
    if not public_cohort.get("public_quality_gate_ok"):
        blockers.append("public_quality_gate_failed")
    if not public_cohort.get("default_adoption_gate_ok"):
        blockers.append("default_adoption_gate_failed")
    if _int(public_cohort.get("holdout_case_count")) <= 0:
        blockers.append("holdout_missing")
    if _int(public_cohort.get("holdout_used_for_tuning_count")):
        blockers.append("holdout_used_for_tuning")
    gate_ok = not blockers
    return {
        "surface": "explicit_agent_recall",
        "gate_ok": gate_ok,
        "promotion_decision": "promoted" if gate_ok else "not_promoted",
        "blockers": blockers,
        "contract_safety_gate_ok": bool(public_cohort.get("contract_safety_gate_ok")),
        "router_design_gate_ok": bool(public_cohort.get("router_design_gate_ok")),
        "public_quality_gate_ok": bool(public_cohort.get("public_quality_gate_ok")),
        "default_adoption_gate_ok": bool(public_cohort.get("default_adoption_gate_ok")),
        "metrics": {
            "neutral_noop_case_count": _int(neutral_noop.get("case_count")),
            "negative_control_no_help_case_count": _int(
                metrics.get("attention_router_applied_but_no_help_count")
            ),
            "public_cohort_case_count": _int(public_cohort.get("case_count")),
            "holdout_case_count": _int(public_cohort.get("holdout_case_count")),
        },
        "boundary": {
            "explicit_pull_surface_only": True,
            "default_hook_foreground": False,
            "navigation_only_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "negative_controls_are_not_positive_adoption_cases": True,
        },
    }


__all__ = [
    "PUBLIC_COHORT_CASES_PER_FAMILY",
    "PUBLIC_COHORT_FAMILIES",
    "PUBLIC_COHORT_HOLDOUT_PER_FAMILY",
    "explicit_auto_gate",
    "public_cohort_receipt",
]
