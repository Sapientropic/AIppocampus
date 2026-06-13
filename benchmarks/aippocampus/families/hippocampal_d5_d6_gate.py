#!/usr/bin/env python3
"""D5/D6 source-sensitive gate for the public hippocampal recall fixture."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

D5_D6_GATE_ARM = "full_query"
D5_D6_GATE_LEVELS = ("D5", "D6")
D5_D6_GATE_MIN_CASES_PER_LEVEL = 3
D5_D6_GATE_MIN_ACCURACY = 0.8
D5_D6_GATE_MIN_SEPARATION_ACCURACY = 1.0

# Keep this taxonomy report-local so the gate can stay importable without
# pulling the full benchmark runner into tests, docs tooling, or future audits.
OUTCOME_CATEGORIES = (
    "correct_evidence",
    "correct_scent",
    "correct_skip",
    "underconfident_scent",
    "overconfident_evidence",
    "partial_miss",
    "unsupported_skip",
    "overactive_scent",
    "wrong_twin_selection",
    "source_reopen_failure",
    "wrong_evidence",
    "confabulation",
)
CORRECT_OUTCOMES = {"correct_evidence", "correct_scent", "correct_skip"}
SEPARATION_FAILURES = {
    "wrong_twin_selection",
    "partial_miss",
    "overconfident_evidence",
    "confabulation",
}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _empty_view() -> dict[str, Any]:
    return {
        "case_count": 0,
        "scored_example_count": 0,
        "correct_count": 0,
        "accuracy": 0.0,
        "separation_failure_count": 0,
        "separation_accuracy": 0.0,
        "source_reopen_failure_count": 0,
        "source_reopen_count": 0,
        "source_reopen_rate": 0.0,
        "source_reopen_success": 0.0,
        "wrong_source_or_twin_count": 0,
        "confabulation_count": 0,
        "overconfident_evidence_count": 0,
        "unsupported_skip_count": 0,
        "outcome_counts": {outcome: 0 for outcome in OUTCOME_CATEGORIES},
    }


def build_d5_d6_gate(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Gate only the AIppocampus diagnostic arm, keeping baselines comparative."""

    level_views = {level: _empty_view() for level in D5_D6_GATE_LEVELS}
    seen_cases: dict[str, set[str]] = {level: set() for level in D5_D6_GATE_LEVELS}
    for result in case_results:
        if result.get("arm") != D5_D6_GATE_ARM:
            continue
        level = str(result.get("degradation_level") or "")
        if level not in level_views:
            continue
        view = level_views[level]
        case_id = str(result.get("case_id") or "")
        if case_id:
            seen_cases[level].add(case_id)
        outcome = str(result.get("outcome") or "")
        view["scored_example_count"] += 1
        view["outcome_counts"][outcome] = int(view["outcome_counts"].get(outcome, 0)) + 1
        if outcome in CORRECT_OUTCOMES:
            view["correct_count"] += 1
        if outcome in SEPARATION_FAILURES or bool(result.get("low_separation")):
            view["separation_failure_count"] += 1
        if outcome == "source_reopen_failure":
            view["source_reopen_failure_count"] += 1
        cost = _as_mapping(result.get("cost"))
        if int(cost.get("source_reopen_count") or 0) > 0:
            view["source_reopen_count"] += 1
        if outcome in {"wrong_twin_selection", "wrong_evidence"}:
            view["wrong_source_or_twin_count"] += 1
        if outcome == "confabulation":
            view["confabulation_count"] += 1
        if outcome == "overconfident_evidence":
            view["overconfident_evidence_count"] += 1
        if outcome == "unsupported_skip":
            view["unsupported_skip_count"] += 1

    combined = _empty_view()
    for level, view in level_views.items():
        view["case_count"] = len(seen_cases[level])
        scored = int(view["scored_example_count"])
        view["accuracy"] = _rate(int(view["correct_count"]), scored)
        view["separation_accuracy"] = _rate(
            scored - int(view["separation_failure_count"]),
            scored,
        )
        view["source_reopen_success"] = _rate(
            scored - int(view["source_reopen_failure_count"]),
            scored,
        )
        view["source_reopen_rate"] = _rate(int(view["source_reopen_count"]), scored)
        for key in (
            "case_count",
            "scored_example_count",
            "correct_count",
            "separation_failure_count",
            "source_reopen_failure_count",
            "source_reopen_count",
            "wrong_source_or_twin_count",
            "confabulation_count",
            "overconfident_evidence_count",
            "unsupported_skip_count",
        ):
            combined[key] += int(view[key])
        for outcome, count in view["outcome_counts"].items():
            combined["outcome_counts"][outcome] = int(
                combined["outcome_counts"].get(outcome, 0)
            ) + int(count)

    combined_scored = int(combined["scored_example_count"])
    combined["accuracy"] = _rate(int(combined["correct_count"]), combined_scored)
    combined["separation_accuracy"] = _rate(
        combined_scored - int(combined["separation_failure_count"]),
        combined_scored,
    )
    combined["source_reopen_success"] = _rate(
        combined_scored - int(combined["source_reopen_failure_count"]),
        combined_scored,
    )
    combined["source_reopen_rate"] = _rate(
        int(combined["source_reopen_count"]),
        combined_scored,
    )
    thresholds = {
        "min_cases_per_level": D5_D6_GATE_MIN_CASES_PER_LEVEL,
        "min_accuracy_per_level": D5_D6_GATE_MIN_ACCURACY,
        "min_separation_accuracy_per_level": D5_D6_GATE_MIN_SEPARATION_ACCURACY,
        "max_wrong_source_or_twin_count": 0,
        "max_source_reopen_failure_count": 0,
        "max_confabulation_count": 0,
    }
    checks = {
        "min_cases_per_level_met": all(
            int(level_views[level]["case_count"]) >= D5_D6_GATE_MIN_CASES_PER_LEVEL
            for level in D5_D6_GATE_LEVELS
        ),
        "accuracy_floor_met": all(
            float(level_views[level]["accuracy"]) >= D5_D6_GATE_MIN_ACCURACY
            for level in D5_D6_GATE_LEVELS
        ),
        "separation_floor_met": all(
            float(level_views[level]["separation_accuracy"])
            >= D5_D6_GATE_MIN_SEPARATION_ACCURACY
            for level in D5_D6_GATE_LEVELS
        ),
        "wrong_source_or_twin_zero": int(combined["wrong_source_or_twin_count"]) == 0,
        "source_reopen_failures_zero": int(combined["source_reopen_failure_count"]) == 0,
        "confabulation_zero": int(combined["confabulation_count"]) == 0,
    }
    ok = all(checks.values())
    return {
        "version": "aippocampus.hippocampal_d5_d6_gate.v1",
        "status": "gated_diagnostic_passed" if ok else "exploratory_diagnostic",
        "ok": ok,
        "claim_level": "public_synthetic_gated_diagnostic",
        "arm": D5_D6_GATE_ARM,
        "levels": list(D5_D6_GATE_LEVELS),
        "thresholds": thresholds,
        "checks": checks,
        "by_level": level_views,
        "combined": combined,
        "cannot_claim": [
            "full_d5_d6_recall_quality",
            "full_p1_matrix_quality",
            "real_history_h1_h2_quality",
            "live_semantic_retriever_quality",
        ],
    }
