#!/usr/bin/env python3
"""Selected-fixture calibration for question-tracking thresholds.

This benchmark is deliberately small and local. It verifies the current
deterministic thresholds against hand-labeled public fixtures before any future
live/model confirmation adapter is trusted. It does not claim real-history
answer quality or user-visible recall improvement.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Iterable, Mapping, Sequence

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc  # noqa: E402
from aippocampus_runtime.question import tracking  # noqa: E402

SCHEMA_VERSION = 1
BENCHMARK_KIND = "aippocampus_question_tracking_calibration"
# A deliberately low fixed-similarity baseline: lowering one global threshold
# can recover weakly worded recurring questions, but it also over-merges
# surface-similar questions whose six-axis context conflicts.
FIXED_SIMILARITY_THRESHOLD = 0.52


def source_ref(suffix: str) -> dict[str, Any]:
    return {
        "thread_key": f"fixture:{suffix}",
        "message_id": f"msg_{suffix}",
        "turn_id": f"turn_{suffix}",
        "source_line": int(suffix) * 10,
        "timestamp": f"2026-05-{int(suffix):02d}T00:00:00Z",
    }


def question_row(suffix: str, **overrides: Any) -> dict[str, Any]:
    data = {
        "schema_version": 1,
        "kind": tracking.FINDING_ROW_KIND,
        "created_at": f"2026-05-{int(suffix):02d}T00:00:00Z",
        "job": "question_extraction",
        "finding_kind": tracking.QUESTION_CANDIDATE_KIND,
        "fingerprint": f"sf_calibration_{suffix}",
        "title": "Agent context continuity",
        "summary": "Selected public fixture for question tracking calibration.",
        "confidence": 0.86,
        "source_refs": [source_ref(suffix)],
        "question_text": "How do I keep agent context across compaction?",
        "question_short": "agent context continuity",
        "intent_orientation": "implementation",
        "what_features": ["agent memory", "context continuity", "compaction"],
        "where_context": ["AIppocampus"],
        "phase_context": "post_compaction",
        "collaboration_context": ["Codex"],
        "concepts": ["AIppocampus", "context continuity"],
    }
    data.update(overrides)
    return data


def selected_fixture_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "name": "obvious_recurring_context_question",
            "case_family": "recurring_context",
            "rows": [
                question_row("1", fingerprint="sf_obvious_1"),
                question_row(
                    "2",
                    fingerprint="sf_obvious_2",
                    question_text="Why does Codex forget context after compaction?",
                    question_short="Codex context loss after compaction",
                ),
            ],
            "positive_pairs": [("sf_obvious_1", "sf_obvious_2")],
            "negative_pairs": [],
        },
        {
            "name": "generic_low_information_questions",
            "case_family": "low_information",
            "rows": [
                question_row(
                    "3",
                    fingerprint="sf_generic_1",
                    confidence=0.42,
                    title="Generic process question",
                    summary="Generic wording without a source-backed axis.",
                    question_text="How should it work?",
                    question_short="how should it work",
                    intent_orientation="",
                    what_features=[],
                    where_context=[],
                    phase_context="",
                    collaboration_context=[],
                    concepts=[],
                ),
                question_row(
                    "4",
                    fingerprint="sf_generic_2",
                    confidence=0.41,
                    title="Generic process question",
                    summary="Another generic wording without a source-backed axis.",
                    question_text="How should it work?",
                    question_short="how should it work",
                    intent_orientation="",
                    what_features=[],
                    where_context=[],
                    phase_context="",
                    collaboration_context=[],
                    concepts=[],
                ),
            ],
            "positive_pairs": [],
            "negative_pairs": [("sf_generic_1", "sf_generic_2")],
        },
        {
            "name": "orientation_conflict_separation",
            "case_family": "orientation_shift",
            "rows": [
                question_row("5", fingerprint="sf_orientation_1"),
                question_row(
                    "6",
                    fingerprint="sf_orientation_2",
                    question_text="How should AI memory continuity work?",
                    question_short="AI memory continuity",
                    intent_orientation="philosophy",
                    where_context=["personal reflection"],
                    phase_context="self_reflection",
                    what_features=["identity", "AI memory"],
                    concepts=["continuity", "self-understanding"],
                ),
            ],
            "positive_pairs": [],
            "negative_pairs": [("sf_orientation_1", "sf_orientation_2")],
        },
        {
            "name": "over_split_same_frontier",
            "case_family": "over_split_same_frontier",
            "rows": [
                question_row(
                    "7",
                    fingerprint="sf_over_split_1",
                    question_text="How should the question tracker separate recurring frontiers?",
                    question_short="question tracker recurring frontiers",
                    what_features=["question tracking", "frontier calibration"],
                    where_context=["AIppocampus"],
                    phase_context="calibration",
                    intent_orientation="implementation",
                    collaboration_context=["Codex"],
                    concepts=["question tracking", "frontier calibration"],
                ),
                question_row(
                    "8",
                    fingerprint="sf_over_split_2",
                    question_text="Where do we tune the recurring-question threshold after review?",
                    question_short="recurring question threshold review",
                    what_features=["question tracking", "threshold calibration"],
                    where_context=["AIppocampus"],
                    phase_context="calibration",
                    intent_orientation="implementation",
                    collaboration_context=["Codex"],
                    concepts=["question tracking", "threshold calibration"],
                ),
            ],
            "positive_pairs": [("sf_over_split_1", "sf_over_split_2")],
            "negative_pairs": [],
        },
        {
            "name": "over_merge_orientation_scope_conflict",
            "case_family": "over_merge_orientation_scope_conflict",
            "rows": [
                question_row(
                    "9",
                    fingerprint="sf_over_merge_1",
                    question_text="How should question tracking handle memory thresholds?",
                    question_short="question tracking memory thresholds",
                    what_features=["question tracking", "memory thresholds"],
                    where_context=["AIppocampus"],
                    phase_context="implementation",
                    intent_orientation="implementation",
                    collaboration_context=["Codex"],
                    concepts=["question tracking", "memory thresholds"],
                ),
                question_row(
                    "10",
                    fingerprint="sf_over_merge_2",
                    question_text="How should question tracking handle memory thresholds?",
                    question_short="question tracking memory thresholds",
                    what_features=["identity", "AI memory"],
                    where_context=["personal reflection"],
                    phase_context="self_reflection",
                    intent_orientation="philosophy",
                    collaboration_context=["essay"],
                    concepts=["continuity", "self-understanding"],
                ),
            ],
            "positive_pairs": [],
            "negative_pairs": [("sf_over_merge_1", "sf_over_merge_2")],
        },
        {
            "name": "borderline_request_payload",
            "case_family": "borderline_confirmation",
            "strong_threshold": 0.99,
            "borderline_threshold": 0.10,
            "auto_accept_borderline": False,
            "rows": [
                question_row("11", fingerprint="sf_borderline_1"),
                question_row(
                    "12",
                    fingerprint="sf_borderline_2",
                    question_text="Where should continuity clues appear in recall?",
                    question_short="continuity clues in recall",
                    what_features=["recall continuity"],
                    phase_context="architecture_review",
                ),
            ],
            "positive_pairs": [],
            "negative_pairs": [],
            "expected_pending_request_count": 1,
        },
    ]


def _candidate_ids_by_source(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        candidate = tracking.candidate_from_row(row)
        if candidate:
            out[candidate.finding_id] = candidate.question_id
    return out


def _candidates_by_source(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        candidate = tracking.candidate_from_row(row)
        if candidate:
            out[candidate.finding_id] = candidate
    return out


def _linked_source_sets(links: Iterable[Mapping[str, Any]]) -> list[set[str]]:
    sets: list[set[str]] = []
    for link in links:
        ids = {
            str(item.get("source_finding_id") or "")
            for item in link.get("linked_questions") or []
            if isinstance(item, Mapping) and item.get("source_finding_id")
        }
        if ids:
            sets.append(ids)
    return sets


def _pair_is_linked(source_sets: list[set[str]], pair: tuple[str, str]) -> bool:
    wanted = set(pair)
    return any(wanted.issubset(source_set) for source_set in source_sets)


def _static_threshold_pair_is_linked(
    candidates_by_source: Mapping[str, Any],
    pair: tuple[str, str],
    *,
    strong_threshold: float,
) -> bool:
    left = candidates_by_source.get(pair[0])
    right = candidates_by_source.get(pair[1])
    if not left or not right:
        return False
    return tracking.pair_is_trackable(left, right) and (
        tracking.match_score(left, right) >= strong_threshold
    )


def _fixed_similarity_pair_is_linked(
    candidates_by_source: Mapping[str, Any],
    pair: tuple[str, str],
    *,
    similarity_threshold: float,
) -> bool:
    left = candidates_by_source.get(pair[0])
    right = candidates_by_source.get(pair[1])
    if not left or not right:
        return False
    return tracking.pair_is_trackable(left, right) and (
        tracking.match_score(left, right) >= similarity_threshold
    )


def _source_ids_by_question_id(candidates_by_source: Mapping[str, Any]) -> dict[str, str]:
    return {
        candidate.question_id: source_id
        for source_id, candidate in candidates_by_source.items()
        if getattr(candidate, "question_id", "")
    }


def _accepted_source_pairs(
    links: Iterable[Mapping[str, Any]],
    candidates_by_source: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_by_question_id = _source_ids_by_question_id(candidates_by_source)
    out: list[dict[str, Any]] = []
    for link in links:
        evidence = link.get("match_evidence") if isinstance(link, Mapping) else {}
        if not isinstance(evidence, Mapping):
            continue
        for pair in evidence.get("accepted_pairs") or []:
            if not isinstance(pair, Mapping):
                continue
            left_source = source_by_question_id.get(str(pair.get("left_question_id") or ""))
            right_source = source_by_question_id.get(str(pair.get("right_question_id") or ""))
            if not left_source or not right_source:
                continue
            out.append(
                {
                    "source_pair": sorted([left_source, right_source]),
                    "acceptance_source": pair.get("acceptance_source"),
                    "score": pair.get("score"),
                    "reason_codes": (pair.get("threshold_policy") or {}).get("reasons") or [],
                }
            )
    return out


def _threshold_audit(
    candidates_by_source: Mapping[str, Any],
    pairs: Iterable[tuple[str, str]],
    *,
    strong_threshold: float,
    borderline_threshold: float,
    source_sets: list[set[str]],
    positive_pairs: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    for pair in pairs:
        left = candidates_by_source.get(pair[0])
        right = candidates_by_source.get(pair[1])
        if not left or not right:
            continue
        policy = tracking.adaptive_pair_thresholds(
            left,
            right,
            strong_threshold=strong_threshold,
            borderline_threshold=borderline_threshold,
        )
        canonical_pair = tuple(sorted(pair))
        audit.append(
            {
                "pair": list(pair),
                "expected_link": canonical_pair in positive_pairs,
                "score": tracking.match_score(left, right),
                "fixed_similarity_linked": _fixed_similarity_pair_is_linked(
                    candidates_by_source,
                    pair,
                    similarity_threshold=FIXED_SIMILARITY_THRESHOLD,
                ),
                "static_strong_linked": _static_threshold_pair_is_linked(
                    candidates_by_source,
                    pair,
                    strong_threshold=strong_threshold,
                ),
                "dynamic_six_axis_linked": _pair_is_linked(source_sets, pair),
                "effective_strong_threshold": policy["strong_threshold"],
                "effective_borderline_threshold": policy["borderline_threshold"],
                "separation_pressure": policy["separation_pressure"],
                "completion_pressure": policy["completion_pressure"],
                "reason_codes": policy["reasons"],
            }
        )
    return audit


def run_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    rows = [row for row in scenario.get("rows") or [] if isinstance(row, Mapping)]
    candidates = [candidate for row in rows if (candidate := tracking.candidate_from_row(row))]
    strong_threshold = float(scenario.get("strong_threshold") or tracking.DEFAULT_STRONG_THRESHOLD)
    borderline_threshold = float(
        scenario.get("borderline_threshold") or tracking.DEFAULT_BORDERLINE_THRESHOLD
    )
    auto_accept_borderline = bool(scenario.get("auto_accept_borderline", True))
    links, diagnostics = tracking.build_question_links(
        candidates,
        [],
        strong_threshold=strong_threshold,
        borderline_threshold=borderline_threshold,
        auto_accept_borderline=auto_accept_borderline,
    )
    source_sets = _linked_source_sets(links)
    positive_pairs = [tuple(pair) for pair in scenario.get("positive_pairs") or []]
    negative_pairs = [tuple(pair) for pair in scenario.get("negative_pairs") or []]
    candidates_by_source = _candidates_by_source(rows)
    baseline_linked_positive_pairs = [
        list(pair)
        for pair in positive_pairs
        if _static_threshold_pair_is_linked(
            candidates_by_source,
            pair,
            strong_threshold=strong_threshold,
        )
    ]
    current_linked_positive_pairs = [
        list(pair) for pair in positive_pairs if _pair_is_linked(source_sets, pair)
    ]
    baseline_merged_negative_pairs = [
        list(pair)
        for pair in negative_pairs
        if _static_threshold_pair_is_linked(
            candidates_by_source,
            pair,
            strong_threshold=strong_threshold,
        )
    ]
    current_merged_negative_pairs = [
        list(pair) for pair in negative_pairs if _pair_is_linked(source_sets, pair)
    ]
    fixed_linked_positive_pairs = [
        list(pair)
        for pair in positive_pairs
        if _fixed_similarity_pair_is_linked(
            candidates_by_source,
            pair,
            similarity_threshold=FIXED_SIMILARITY_THRESHOLD,
        )
    ]
    fixed_merged_negative_pairs = [
        list(pair)
        for pair in negative_pairs
        if _fixed_similarity_pair_is_linked(
            candidates_by_source,
            pair,
            similarity_threshold=FIXED_SIMILARITY_THRESHOLD,
        )
    ]
    missed_positive_pairs = [
        list(pair) for pair in positive_pairs if list(pair) not in current_linked_positive_pairs
    ]
    merged_negative_pairs = current_merged_negative_pairs
    baseline_missed_positive_pairs = [
        list(pair)
        for pair in positive_pairs
        if list(pair) not in baseline_linked_positive_pairs
    ]
    missed_positive_delta = len(missed_positive_pairs) - len(baseline_missed_positive_pairs)
    merged_negative_delta = len(current_merged_negative_pairs) - len(baseline_merged_negative_pairs)
    expected_pending = int(scenario.get("expected_pending_request_count") or 0)
    pending_count = int(diagnostics["pending_confirmation_request_count"])
    accepted_source_pairs = _accepted_source_pairs(links, candidates_by_source)
    positive_pair_set = {tuple(sorted(pair)) for pair in positive_pairs}
    negative_pair_set = {tuple(sorted(pair)) for pair in negative_pairs}
    borderline_auto_correct_count = sum(
        1
        for pair in accepted_source_pairs
        if pair.get("acceptance_source") == "borderline_auto"
        and tuple(pair["source_pair"]) in positive_pair_set
    )
    borderline_auto_wrong_count = sum(
        1
        for pair in accepted_source_pairs
        if pair.get("acceptance_source") == "borderline_auto"
        and tuple(pair["source_pair"]) in negative_pair_set
    )
    candidate_source_ref_count = sum(1 for candidate in candidates if candidate.source_refs)
    passed = (
        not missed_positive_pairs
        and not merged_negative_pairs
        and pending_count >= expected_pending
        and missed_positive_delta <= 0
        and merged_negative_delta <= 0
    )
    return {
        "name": str(scenario.get("name") or "unnamed"),
        "case_family": str(scenario.get("case_family") or "uncategorized"),
        "passed": passed,
        "candidate_count": len(candidates),
        "candidate_source_ref_count": candidate_source_ref_count,
        "link_count": len(links),
        "positive_pair_count": len(positive_pairs),
        "missed_positive_pairs": missed_positive_pairs,
        "negative_pair_count": len(negative_pairs),
        "merged_negative_pairs": merged_negative_pairs,
        "borderline_auto_correct_count": borderline_auto_correct_count,
        "borderline_auto_wrong_count": borderline_auto_wrong_count,
        "auto_accept_borderline": auto_accept_borderline,
        "pending_confirmation_request_count": pending_count,
        "expected_pending_confirmation_request_count": expected_pending,
        "threshold_comparison": {
            "fixed_similarity_threshold": FIXED_SIMILARITY_THRESHOLD,
            "baseline": "static_strong_threshold_only",
            "current": (
                "adaptive_thresholds_with_default_borderline_auto_accept"
                if auto_accept_borderline
                else "adaptive_thresholds_with_explicit_borderline_confirmation_requests"
            ),
            "fixed_similarity_linked_positive_pairs": fixed_linked_positive_pairs,
            "fixed_similarity_missed_positive_pair_count": (
                len(positive_pairs) - len(fixed_linked_positive_pairs)
            ),
            "fixed_similarity_merged_negative_pairs": fixed_merged_negative_pairs,
            "fixed_similarity_merged_negative_pair_count": len(fixed_merged_negative_pairs),
            "baseline_linked_positive_pairs": baseline_linked_positive_pairs,
            "current_linked_positive_pairs": current_linked_positive_pairs,
            "baseline_missed_positive_pair_count": len(baseline_missed_positive_pairs),
            "current_missed_positive_pair_count": len(missed_positive_pairs),
            "missed_positive_delta": missed_positive_delta,
            "baseline_merged_negative_pair_count": len(baseline_merged_negative_pairs),
            "current_merged_negative_pair_count": len(current_merged_negative_pairs),
            "merged_negative_delta": merged_negative_delta,
        },
        "threshold_audit": _threshold_audit(
            candidates_by_source,
            [*positive_pairs, *negative_pairs],
            strong_threshold=strong_threshold,
            borderline_threshold=borderline_threshold,
            source_sets=source_sets,
            positive_pairs=positive_pair_set,
        ),
        "low_salience_pair_skipped_count": diagnostics["low_salience_pair_skipped_count"],
        "salience_tag_counts": diagnostics["salience_tag_counts"],
        "thresholds": {
            "strong": strong_threshold,
            "borderline": borderline_threshold,
        },
        "candidate_source_ids": sorted(_candidate_ids_by_source(rows).keys()),
    }


def aggregate_scenarios(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    obvious = [item for item in results if item.get("name") == "obvious_recurring_context_question"]
    generic = [item for item in results if item.get("name") == "generic_low_information_questions"]
    orientation = [item for item in results if item.get("name") == "orientation_conflict_separation"]
    missed_positive_delta = sum(
        int((item.get("threshold_comparison") or {}).get("missed_positive_delta") or 0)
        for item in results
    )
    merged_negative_delta = sum(
        int((item.get("threshold_comparison") or {}).get("merged_negative_delta") or 0)
        for item in results
    )
    positive_pair_count = sum(int(item.get("positive_pair_count") or 0) for item in results)
    negative_pair_count = sum(int(item.get("negative_pair_count") or 0) for item in results)
    candidate_count = sum(int(item.get("candidate_count") or 0) for item in results)
    candidate_source_ref_count = sum(
        int(item.get("candidate_source_ref_count") or 0) for item in results
    )
    fixed_false_split = sum(
        int((item.get("threshold_comparison") or {}).get("fixed_similarity_missed_positive_pair_count") or 0)
        for item in results
    )
    fixed_false_merge = sum(
        int((item.get("threshold_comparison") or {}).get("fixed_similarity_merged_negative_pair_count") or 0)
        for item in results
    )
    static_false_split = sum(
        int((item.get("threshold_comparison") or {}).get("baseline_missed_positive_pair_count") or 0)
        for item in results
    )
    static_false_merge = sum(
        int((item.get("threshold_comparison") or {}).get("baseline_merged_negative_pair_count") or 0)
        for item in results
    )
    dynamic_false_split = sum(len(item.get("missed_positive_pairs") or []) for item in results)
    dynamic_false_merge = sum(len(item.get("merged_negative_pairs") or []) for item in results)
    case_family_counts: dict[str, int] = {}
    for item in results:
        case_family = str(item.get("case_family") or "uncategorized")
        case_family_counts[case_family] = case_family_counts.get(case_family, 0) + 1

    def rate(count: int, total: int) -> float:
        return round(count / total, 6) if total else 0.0

    comparison_modes = {
        "fixed_similarity_threshold": {
            "threshold": FIXED_SIMILARITY_THRESHOLD,
            "false_split_count": fixed_false_split,
            "false_split_rate": rate(fixed_false_split, positive_pair_count),
            "false_merge_count": fixed_false_merge,
            "false_merge_rate": rate(fixed_false_merge, negative_pair_count),
        },
        "static_strong_threshold": {
            "threshold": tracking.DEFAULT_STRONG_THRESHOLD,
            "false_split_count": static_false_split,
            "false_split_rate": rate(static_false_split, positive_pair_count),
            "false_merge_count": static_false_merge,
            "false_merge_rate": rate(static_false_merge, negative_pair_count),
        },
        "dynamic_six_axis_threshold": {
            "threshold": "adaptive_per_pair",
            "false_split_count": dynamic_false_split,
            "false_split_rate": rate(dynamic_false_split, positive_pair_count),
            "false_merge_count": dynamic_false_merge,
            "false_merge_rate": rate(dynamic_false_merge, negative_pair_count),
        },
    }
    adaptive_improved_failure_mode_count = int(fixed_false_merge > dynamic_false_merge) + int(
        static_false_split > dynamic_false_split
    )
    return {
        "scenario_count": len(results),
        "passed_scenario_count": sum(1 for item in results if item.get("passed")),
        "failed_scenario_count": sum(1 for item in results if not item.get("passed")),
        "obvious_recurring_retained": bool(obvious and obvious[0].get("passed")),
        "generic_low_information_merge_count": sum(
            len(item.get("merged_negative_pairs") or []) for item in generic
        ),
        "orientation_conflict_merge_count": sum(
            len(item.get("merged_negative_pairs") or []) for item in orientation
        ),
        "pending_confirmation_request_count": sum(
            int(item.get("pending_confirmation_request_count") or 0) for item in results
        ),
        "threshold_missed_positive_delta": missed_positive_delta,
        "threshold_merged_negative_delta": merged_negative_delta,
        "threshold_non_regression_passed": (
            missed_positive_delta <= 0 and merged_negative_delta <= 0
        ),
        "six_axis_dynamic_thresholds": {
            "positive_pair_count": positive_pair_count,
            "negative_pair_count": negative_pair_count,
            "comparison_modes": comparison_modes,
            "adaptive_improved_failure_mode_count": adaptive_improved_failure_mode_count,
            "borderline_auto_correct_count": sum(
                int(item.get("borderline_auto_correct_count") or 0) for item in results
            ),
            "borderline_auto_wrong_count": sum(
                int(item.get("borderline_auto_wrong_count") or 0) for item in results
            ),
            "source_ref_coverage_rate": rate(candidate_source_ref_count, candidate_count),
            "source_ref_candidate_count": candidate_source_ref_count,
            "candidate_count": candidate_count,
            "case_family_counts": dict(sorted(case_family_counts.items())),
        },
    }


def run_question_tracking_calibration() -> dict[str, Any]:
    scenarios = [run_scenario(item) for item in selected_fixture_scenarios()]
    metrics = aggregate_scenarios(scenarios)
    status = (
        "selected_fixture_calibration_passed"
        if metrics["failed_scenario_count"] == 0
        else "selected_fixture_calibration_failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": BENCHMARK_KIND,
        "created_at": now_utc(),
        "status": status,
        "claim_level": "selected_fixture_calibration",
        "thresholds": {
            "default_strong": tracking.DEFAULT_STRONG_THRESHOLD,
            "default_borderline": tracking.DEFAULT_BORDERLINE_THRESHOLD,
        },
        "metrics": metrics,
        "scenarios": scenarios,
        "can_claim": [
            "selected_fixtures_keep_obvious_recurring_questions_linked",
            "selected_fixtures_keep_low_information_generic_questions_unmerged",
            "selected_fixtures_show_adaptive_thresholds_do_not_regress_static_threshold_baseline",
            "six_axis_dynamic_thresholds_are_measured_as_navigation_policy",
            "selected_fixtures_report_false_merge_and_false_split_rates_by_threshold_mode",
            "borderline_request_payloads_are_available_for_offline_or_future_live_review",
        ],
        "cannot_claim": [
            "live_external_model_confirmation",
            "real_user_calibration",
            "private_real_history_threshold_quality",
            "user_visible_recall_improvement",
            "source_truth_from_dynamic_thresholds",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = run_question_tracking_calibration()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "question tracking calibration: "
            f"{payload['metrics']['passed_scenario_count']}/"
            f"{payload['metrics']['scenario_count']} scenarios passed"
        )
    return 0 if payload["status"].endswith("_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
