from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
ROLLOUT_DATASET = (
    REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "rollout_behavior_events_v1.jsonl"
)
sys.path.insert(0, str(BENCHMARKS))

import benchmark_vcs_future_event_recall as benchmark  # noqa: E402


class VcsFutureEventRecallBenchmarkTests(unittest.TestCase):
    def test_checked_in_dataset_has_hard_future_events_and_negatives(self) -> None:
        dataset = benchmark.load_dataset()
        families = {str(event.get("family")) for event in dataset.events_by_id.values()}
        hard_kinds = {str(event.get("hard_event_kind")) for event in dataset.events_by_id.values()}

        self.assertEqual(dataset.dataset_id, "aippocampus_vcs_future_events_v1")
        self.assertGreaterEqual(len(dataset.rows), 3)
        self.assertGreaterEqual(len(dataset.flag_worthy_event_ids), 5)
        self.assertGreaterEqual(len(dataset.non_flag_event_ids), 3)
        self.assertLessEqual(
            {
                "reopen_condition",
                "workaround_rationale",
                "tacit_constraint",
                "rejected_route",
                "anti_drift_negative",
            },
            families,
        )
        self.assertLessEqual(
            {"pull_request_merged", "pull_request_rejected", "commit_reverted", "patchset_superseded"},
            hard_kinds,
        )

    def test_gold_baseline_scores_full_recall_and_precision_without_raw_text(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_vcs_future_event_recall_benchmark")
        self.assertEqual(payload["status"], "future_event_recall_scored")
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["dataset"]["future_event_gold_available"])
        self.assertEqual(payload["metrics"]["future_event_flag_recall_rate"], 1.0)
        self.assertEqual(payload["metrics"]["future_event_flag_precision"], 1.0)
        self.assertEqual(
            payload["metrics"]["rate_estimates"]["future_event_flag_recall"][
                "confidence_interval"
            ]["method"],
            "wilson_score",
        )
        anti_drift_violation_rate = payload["metrics"]["rate_estimates"][
            "anti_drift_violation_rate"
        ]
        self.assertEqual(anti_drift_violation_rate["numerator"], 0)
        self.assertEqual(
            anti_drift_violation_rate["denominator"],
            payload["metrics"]["anti_drift_negative_count"],
        )
        self.assertGreater(anti_drift_violation_rate["confidence_interval"]["upper"], 0)
        self.assertIn("future_event_flag_recall", payload["lower_bound_gates"])
        self.assertEqual(payload["metrics"]["false_negative_count"], 0)
        self.assertEqual(payload["metrics"]["false_positive_count"], 0)
        self.assertTrue(payload["metrics"]["silent_dream_penalty_applies"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Reject this Redis", dumped)
        self.assertNotIn("Merged PR 207", dumped)
        self.assertNotIn(str(REPO_ROOT), dumped)

    def test_lower_bound_gate_mode_does_not_promote_small_perfect_fixture(self) -> None:
        payload = benchmark.run_benchmark(gate_statistic="lower_bound")

        self.assertFalse(payload["ok"])
        recall_gate = payload["lower_bound_gates"]["future_event_flag_recall"]
        self.assertTrue(recall_gate["passes_point_estimate"])
        self.assertFalse(recall_gate["passes_lower_bound"])
        self.assertTrue(recall_gate["applied_to_status"])

    def test_empty_baseline_is_penalized_for_false_negatives(self) -> None:
        payload = benchmark.run_benchmark(baseline="empty")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["metrics"]["predicted_flag_count"], 0)
        self.assertEqual(payload["metrics"]["future_event_flag_recall_rate"], 0.0)
        self.assertEqual(
            payload["metrics"]["false_negative_count"],
            payload["metrics"]["future_event_gold_count"],
        )
        self.assertEqual(payload["metrics"]["false_positive_count"], 0)
        self.assertEqual(payload["metrics"]["anti_drift_pass_rate"], 1.0)

    def test_closed_book_ablation_reports_source_lift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            closed_book = Path(tmp) / "closed-book.jsonl"
            closed_book.write_text("", encoding="utf-8")

            payload = benchmark.run_benchmark(closed_book_predictions_file=closed_book)

        control = payload["contamination_control"]
        self.assertTrue(control["closed_book_ablation_available"])
        self.assertTrue(control["time_split_required_for_public_claims"])
        self.assertTrue(control["counterfactual_perturbation_required_for_public_claims"])
        self.assertEqual(
            control["closed_book"]["metrics"]["future_event_flag_recall_rate"],
            0.0,
        )
        self.assertEqual(control["closed_book"]["source_over_closed_book_lift"]["recall"], 1.0)
        self.assertEqual(
            control["closed_book"]["source_over_closed_book_lift"]["false_negative_reduction"],
            payload["metrics"]["future_event_gold_count"],
        )

    def test_rollout_behavior_dataset_uses_behavior_not_narrative_as_gold(self) -> None:
        dataset = benchmark.load_dataset(ROLLOUT_DATASET)
        hard_kinds = {str(event.get("hard_event_kind")) for event in dataset.events_by_id.values()}
        narrative_source_ids = {
            str(source.get("source_id"))
            for row in dataset.rows
            for source in row.get("past_window", [])
            if source.get("behavior_backed") is False
        }
        required_source_ids = {
            source_id
            for event in dataset.events_by_id.values()
            for source_id in benchmark.as_string_list(event.get("required_past_source_ids"))
        }

        self.assertEqual(dataset.dataset_id, "aippocampus_rollout_behavior_events_v1")
        self.assertGreaterEqual(len(dataset.flag_worthy_event_ids), 3)
        self.assertIn("tool_call_failed", hard_kinds)
        self.assertIn("test_failed", hard_kinds)
        self.assertIn("tool_call_succeeded", hard_kinds)
        self.assertTrue(narrative_source_ids)
        self.assertTrue(narrative_source_ids.isdisjoint(required_source_ids))

    def test_narrative_only_rollout_source_cannot_support_gold_event(self) -> None:
        row = {
            "dataset_id": "bad_rollout_fixture",
            "schema_version": 1,
            "license": "CC0-1.0",
            "project_id": "bad-rollout",
            "source_family": "agent_rollout_behavior_contract",
            "past_window": [
                {
                    "source_id": "assistant-said-no",
                    "kind": "assistant_message",
                    "behavior_backed": False,
                    "text": "The assistant said this route was rejected.",
                }
            ],
            "future_window": [
                {
                    "event_id": "repeat-failed",
                    "family": "rejected_route",
                    "hard_event_kind": "test_failed",
                    "flag_worthy": True,
                    "text": "A later attempt failed.",
                    "required_past_source_ids": ["assistant-said-no"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "bad.jsonl"
            fixture.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "narrative-only source"):
                benchmark.load_dataset(fixture)

    def test_predictions_catch_non_flag_unknown_and_source_support_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions.jsonl"
            rows = [
                {
                    "prediction_id": "tp-good",
                    "event_id": "cache-pr-207-merged",
                    "decision": "flag",
                    "past_source_ids": ["cache-pr-101-review"],
                },
                {
                    "prediction_id": "non-flag-fp",
                    "event_id": "cache-pr-208-merged",
                    "decision": "flag",
                    "past_source_ids": ["cache-pr-102-review"],
                },
                {
                    "prediction_id": "unknown-fp",
                    "event_id": "missing-event",
                    "decision": "flag",
                    "past_source_ids": [],
                },
                {
                    "prediction_id": "bad-source",
                    "event_id": "renderer-change-90-merged",
                    "decision": "flag",
                    "past_source_ids": [],
                },
            ]
            predictions.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(predictions_file=predictions)

        by_event = {row["event_id"]: row for row in payload["events"]}
        self.assertFalse(payload["ok"])
        self.assertTrue(by_event["cache-pr-207-merged"]["true_positive"])
        self.assertTrue(by_event["cache-pr-208-merged"]["false_positive"])
        self.assertTrue(by_event["renderer-change-90-merged"]["false_negative"])
        self.assertGreaterEqual(payload["metrics"]["false_positive_count"], 2)
        self.assertGreaterEqual(payload["metrics"]["source_support_failure_count"], 1)
        self.assertEqual(payload["metrics"]["unknown_event_false_positive_count"], 1)
        self.assertEqual(payload["metrics"]["future_event_flag_precision"], 0.25)
        self.assertEqual(payload["metrics"]["diagnostic_event_identity_precision"], 0.5)
        self.assertEqual(
            payload["precision_contract"]["primary_metric"],
            "future_event_flag_precision",
        )
        self.assertEqual(
            payload["precision_contract"]["diagnostic_metric"],
            "diagnostic_event_identity_precision",
        )

    def test_adversarial_controls_catch_stale_behavior_and_abstention_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "adversarial.jsonl"
            predictions = root / "bad-predictions.jsonl"
            rows = [
                {
                    "dataset_id": "unit_adversarial_vcs",
                    "schema_version": 1,
                    "license": "CC0-1.0",
                    "project_id": "dual-source",
                    "source_family": "unit_adversarial",
                    "past_window": [
                        {
                            "source_id": "old-public-source",
                            "kind": "pull_request_metadata",
                            "text": "Old public rationale that has been superseded.",
                        },
                        {
                            "source_id": "current-local-source",
                            "kind": "current_decision_source",
                            "text": "Current local rationale that overrides the old public source.",
                        },
                    ],
                    "future_window": [
                        {
                            "event_id": "current-route-reopened",
                            "family": "reopen_condition",
                            "hard_event_kind": "pull_request_merged",
                            "flag_worthy": True,
                            "text": "The route was reopened under the current source.",
                            "required_past_source_ids": ["current-local-source"],
                        },
                        {
                            "event_id": "near-miss-revert",
                            "family": "reopen_condition",
                            "hard_event_kind": "commit_reverted",
                            "flag_worthy": False,
                            "text": "Similar vocabulary, unrelated route.",
                            "required_past_source_ids": [],
                            "anti_drift_family_under_test": "reopen_condition",
                            "anti_drift_contrast_family": "rejected_route",
                        },
                        {
                            "event_id": "cross-family-route",
                            "family": "anti_drift_negative",
                            "hard_event_kind": "pull_request_merged",
                            "flag_worthy": False,
                            "text": "A merge event should not activate rejected-route memory.",
                            "required_past_source_ids": [],
                            "anti_drift_family_under_test": "rejected_route",
                            "anti_drift_contrast_family": "reopen_condition",
                        },
                    ],
                },
                {
                    "dataset_id": "unit_adversarial_vcs",
                    "schema_version": 1,
                    "license": "CC0-1.0",
                    "project_id": "behavior-only",
                    "source_family": "unit_adversarial",
                    "past_window": [
                        {
                            "source_id": "failed-test-trace",
                            "kind": "test_failed",
                            "behavior_backed": True,
                            "text": "A deterministic test failure rejected this route.",
                        },
                        {
                            "source_id": "assistant-narrative",
                            "kind": "assistant_message",
                            "behavior_backed": False,
                            "text": "Narrative-only claim that the route is risky.",
                        },
                    ],
                    "future_window": [
                        {
                            "event_id": "route-failed-again",
                            "family": "rejected_route",
                            "hard_event_kind": "test_failed",
                            "flag_worthy": True,
                            "text": "The route failed tests again.",
                            "required_past_source_ids": ["failed-test-trace"],
                        }
                    ],
                },
            ]
            bad_predictions = [
                {
                    "prediction_id": "stale-source",
                    "event_id": "current-route-reopened",
                    "decision": "flag",
                    "past_source_ids": ["old-public-source"],
                },
                {
                    "prediction_id": "near-miss-fp",
                    "event_id": "near-miss-revert",
                    "decision": "flag",
                    "past_source_ids": [],
                },
                {
                    "prediction_id": "cross-family-fp",
                    "event_id": "cross-family-route",
                    "decision": "flag",
                    "past_source_ids": [],
                },
                {
                    "prediction_id": "narrative-source",
                    "event_id": "route-failed-again",
                    "decision": "flag",
                    "past_source_ids": ["assistant-narrative"],
                },
            ]
            fixture.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            predictions.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bad_predictions),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=fixture,
                predictions_file=predictions,
            )

        by_event = {row["event_id"]: row for row in payload["events"]}
        self.assertFalse(payload["ok"])
        self.assertTrue(by_event["current-route-reopened"]["false_negative"])
        self.assertTrue(by_event["route-failed-again"]["false_negative"])
        self.assertTrue(by_event["near-miss-revert"]["false_positive"])
        self.assertTrue(by_event["cross-family-route"]["false_positive"])
        self.assertEqual(payload["metrics"]["source_support_failure_count"], 2)
        self.assertEqual(payload["metrics"]["false_positive_count"], 2)
        self.assertEqual(payload["metrics"]["anti_drift_pass_rate"], 0.0)
        self.assertEqual(payload["anti_drift_controls"]["negative_cross_family_count"], 2)
        self.assertEqual(
            payload["anti_drift_controls"]["negative_cross_family_violation_count"], 2
        )

    def test_candidate_discovery_bias_and_source_degradation_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "validity-controls.jsonl"
            row = {
                "dataset_id": "unit_validity_controls",
                "schema_version": 1,
                "license": "CC0-1.0",
                "project_id": "validity",
                "source_family": "unit_validity",
                "candidate_discovery_bias": {
                    "available": True,
                    "source_surface_mix": {"title": {"count": 1, "proportion": 1.0}},
                    "query_term_hit_mix_by_family": {"revert": 1},
                    "manual_decision_counts": {"included": 1},
                    "sampled_miss_rate": {"available": True, "sample_count": 1, "miss_count": 0, "rate": 0.0},
                },
                "past_window": [
                    {
                        "source_id": "redacted-source",
                        "kind": "pull_request_review",
                        "text": "[redacted but source id retained]",
                    },
                    {
                        "source_id": "partial-source",
                        "kind": "pull_request_review",
                        "text": "Only partial support survived.",
                    },
                ],
                "future_window": [
                    {
                        "event_id": "redacted-event",
                        "family": "reopen_condition",
                        "hard_event_kind": "pull_request_merged",
                        "flag_worthy": True,
                        "text": "Redacted source still has a source id.",
                        "required_past_source_ids": ["redacted-source"],
                        "source_degradation": "redacted_source",
                    },
                    {
                        "event_id": "partial-event",
                        "family": "workaround_rationale",
                        "hard_event_kind": "commit_reverted",
                        "flag_worthy": True,
                        "text": "Partial source should not count as full support.",
                        "required_past_source_ids": ["partial-source"],
                        "source_degradation": "partial_support",
                    },
                    {
                        "event_id": "missing-source-event",
                        "family": "tacit_constraint",
                        "hard_event_kind": "issue_reopened",
                        "flag_worthy": True,
                        "text": "The candidate mentions a source id that is not redistributable.",
                        "required_past_source_ids": ["missing-public-source"],
                        "source_degradation": "missing_source_id",
                    },
                ],
            }
            fixture.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            payload = benchmark.run_benchmark(dataset_path=fixture)

        self.assertTrue(payload["candidate_discovery_bias"]["available"])
        degradation = payload["source_degradation_controls"]
        self.assertEqual(degradation["counts_by_state"]["redacted_source"], 1)
        self.assertEqual(degradation["counts_by_state"]["partial_support"], 1)
        self.assertEqual(degradation["counts_by_state"]["missing_source_id"], 1)
        self.assertEqual(degradation["full_support_blocked_count"], 2)
        by_event = {row["event_id"]: row for row in payload["events"]}
        self.assertTrue(by_event["redacted-event"]["true_positive"])
        self.assertFalse(by_event["partial-event"]["source_supported"])
        self.assertFalse(by_event["missing-source-event"]["source_supported"])


if __name__ == "__main__":
    unittest.main()
