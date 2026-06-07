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
            "name": "borderline_request_payload",
            "strong_threshold": 0.99,
            "borderline_threshold": 0.10,
            "auto_accept_borderline": False,
            "rows": [
                question_row("7", fingerprint="sf_borderline_1"),
                question_row(
                    "8",
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
    passed = (
        not missed_positive_pairs
        and not merged_negative_pairs
        and pending_count >= expected_pending
        and missed_positive_delta <= 0
        and merged_negative_delta <= 0
    )
    return {
        "name": str(scenario.get("name") or "unnamed"),
        "passed": passed,
        "candidate_count": len(candidates),
        "link_count": len(links),
        "positive_pair_count": len(positive_pairs),
        "missed_positive_pairs": missed_positive_pairs,
        "negative_pair_count": len(negative_pairs),
        "merged_negative_pairs": merged_negative_pairs,
        "auto_accept_borderline": auto_accept_borderline,
        "pending_confirmation_request_count": pending_count,
        "expected_pending_confirmation_request_count": expected_pending,
        "threshold_comparison": {
            "baseline": "static_strong_threshold_only",
            "current": (
                "adaptive_thresholds_with_default_borderline_auto_accept"
                if auto_accept_borderline
                else "adaptive_thresholds_with_explicit_borderline_confirmation_requests"
            ),
            "baseline_linked_positive_pairs": baseline_linked_positive_pairs,
            "current_linked_positive_pairs": current_linked_positive_pairs,
            "baseline_missed_positive_pair_count": len(baseline_missed_positive_pairs),
            "current_missed_positive_pair_count": len(missed_positive_pairs),
            "missed_positive_delta": missed_positive_delta,
            "baseline_merged_negative_pair_count": len(baseline_merged_negative_pairs),
            "current_merged_negative_pair_count": len(current_merged_negative_pairs),
            "merged_negative_delta": merged_negative_delta,
        },
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
            "borderline_request_payloads_are_available_for_offline_or_future_live_review",
        ],
        "cannot_claim": [
            "live_external_model_confirmation",
            "real_user_calibration",
            "private_real_history_threshold_quality",
            "user_visible_recall_improvement",
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
