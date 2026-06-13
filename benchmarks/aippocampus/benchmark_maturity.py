#!/usr/bin/env python3
"""Benchmark maturity and sample-size promotion helpers.

Small deterministic fixtures are useful contract gates. This helper keeps that
green signal separate from public-quality cohort claims by making maturity,
sample floors, uncertainty, holdout status, and next promotion targets explicit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import benchmark_statistics

MATURITY_LEVELS = (
    "contract_smoke",
    "diagnostic_proxy",
    "public_cohort_candidate",
    "public_cohort",
    "holdout_quality",
)
PUBLIC_QUALITY_LEVELS = {"public_cohort", "holdout_quality"}


def _normalized_counts(value: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(key): max(0, int(count or 0))
        for key, count in sorted(value.items(), key=lambda item: str(item[0]))
    }


def _sample_floor_met(per_family_case_counts: Mapping[str, int], floor: int) -> bool:
    if not per_family_case_counts:
        return False
    return all(int(count) >= int(floor) for count in per_family_case_counts.values())


def _quality_gate_blockers(
    *,
    benchmark_maturity_level: str,
    contract_gate_ok: bool,
    usefulness_gate_ok: bool,
    attention_cost_ok: bool,
    sample_floor_met: bool,
    external_or_public_cohort_case_count: int,
    holdout_case_count: int,
    holdout_used_for_tuning_count: int,
) -> list[str]:
    blockers: list[str] = []
    if not contract_gate_ok:
        blockers.append("contract_gate_failed")
    if not usefulness_gate_ok:
        blockers.append("usefulness_gate_failed")
    if not attention_cost_ok:
        blockers.append("attention_cost_gate_failed")
    if benchmark_maturity_level not in PUBLIC_QUALITY_LEVELS:
        blockers.append("maturity_level_below_public_quality")
    if not sample_floor_met:
        blockers.append("sample_floor_not_met")
    if external_or_public_cohort_case_count <= 0:
        blockers.append("public_or_external_cohort_missing")
    if holdout_case_count <= 0:
        blockers.append("holdout_missing")
    if holdout_used_for_tuning_count > 0:
        blockers.append("holdout_used_for_tuning")
    return blockers


def build_benchmark_maturity_report(
    *,
    benchmark_maturity_level: str,
    case_count: int,
    passed_case_count: int,
    per_family_case_counts: Mapping[str, int],
    minimum_family_case_floor: int,
    external_or_public_cohort_case_count: int,
    holdout_case_count: int,
    holdout_used_for_tuning_count: int,
    contract_gate_ok: bool,
    usefulness_gate_ok: bool = True,
    attention_cost_ok: bool = True,
    next_promotion_target: str = "",
) -> dict[str, Any]:
    """Return reusable maturity metadata for benchmark reports.

    `contract_gate_ok` says the local fixture or contract passed. It does not
    imply public-quality evidence. Public-quality promotion requires the
    maturity level, sample floor, public/external cohort, holdout, and no tuning
    leakage checks to pass at the same time.
    """

    level = str(benchmark_maturity_level)
    if level not in MATURITY_LEVELS:
        raise ValueError(f"unsupported benchmark_maturity_level: {level}")
    family_counts = _normalized_counts(per_family_case_counts)
    family_floor_met = _sample_floor_met(family_counts, int(minimum_family_case_floor))
    success_rate = benchmark_statistics.binomial_rate_report(
        "contract_case_success_rate",
        numerator=int(passed_case_count),
        denominator=int(case_count),
    )
    blockers = _quality_gate_blockers(
        benchmark_maturity_level=level,
        contract_gate_ok=bool(contract_gate_ok),
        usefulness_gate_ok=bool(usefulness_gate_ok),
        attention_cost_ok=bool(attention_cost_ok),
        sample_floor_met=family_floor_met,
        external_or_public_cohort_case_count=int(external_or_public_cohort_case_count),
        holdout_case_count=int(holdout_case_count),
        holdout_used_for_tuning_count=int(holdout_used_for_tuning_count),
    )
    quality_gate_ok = not blockers
    return {
        "benchmark_maturity_level": level,
        "case_count": int(case_count),
        "failure_family_count": len(family_counts),
        "per_family_case_counts": family_counts,
        "minimum_family_case_floor": int(minimum_family_case_floor),
        "sample_floor_met": family_floor_met,
        "external_or_public_cohort_case_count": int(external_or_public_cohort_case_count),
        "holdout_case_count": int(holdout_case_count),
        "holdout_used_for_tuning_count": int(holdout_used_for_tuning_count),
        "wilson_or_uncertainty_reported": bool(success_rate["defined"]),
        "success_rate": success_rate,
        "contract_gate_ok": bool(contract_gate_ok),
        "usefulness_gate_ok": bool(usefulness_gate_ok),
        "attention_cost_ok": bool(attention_cost_ok),
        "public_quality_gate_ok": quality_gate_ok,
        "default_adoption_gate_ok": quality_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "quality_gate_ok_means": "public_quality_gate_ok",
        "quality_gate_blockers": blockers,
        "cannot_claim_due_to_sample_size": not family_floor_met,
        "next_promotion_target": str(next_promotion_target),
        "cannot_claim": [
            "representative_public_quality",
            "holdout_quality",
            "live_user_visible_lift",
            "competitor_superiority",
        ]
        if not quality_gate_ok
        else [],
    }
