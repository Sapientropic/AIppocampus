from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLLOUT_DATASET = (
    REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "rollout_behavior_events_v1.jsonl"
)
ROLLOUT_V2_DATASET = (
    REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "rollout_behavior_events_v2.json"
)

benchmark = import_benchmark_module("benchmark_vcs_future_event_recall")

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

    def test_rollout_v2_dataset_is_public_hard_event_cohort(self) -> None:
        dataset = benchmark.load_dataset(ROLLOUT_V2_DATASET)
        tracks = {str(event.get("track")) for event in dataset.events_by_id.values()}
        positive_families = {
            str(event.get("family"))
            for event_id, event in dataset.events_by_id.items()
            if event_id in dataset.flag_worthy_event_ids
        }
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

        self.assertEqual(dataset.dataset_id, "aippocampus_rollout_behavior_events_v2")
        self.assertEqual(len(dataset.rows), 17)
        self.assertEqual(len(dataset.flag_worthy_event_ids), 17)
        self.assertEqual(len(dataset.non_flag_event_ids), 17)
        self.assertLessEqual(
            {
                "temporal_override",
                "cross_project_contamination",
                "cross_scope_drift",
                "post_compaction_gap",
                "intentional_forget_boundary",
                "dream_candidate_boundary",
                "route_topic_specificity",
            },
            tracks,
        )
        self.assertLessEqual(
            {"rejected_route", "tacit_constraint", "workaround_rationale"},
            positive_families,
        )
        self.assertTrue(narrative_source_ids)
        self.assertTrue(narrative_source_ids.isdisjoint(required_source_ids))

    def test_rollout_v2_production_like_topk2_recovers_cohort_chains(self) -> None:
        payload = benchmark.run_benchmark(
            dataset_path=ROLLOUT_V2_DATASET,
            production_like_retrieval=True,
            source_disambiguation_top_k=2,
        )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["dataset"]["project_count"], 17)
        self.assertNotIn("V1", payload["dataset"]["claim_boundary"])
        self.assertEqual(payload["metrics"]["future_event_gold_count"], 17)
        self.assertEqual(payload["metrics"]["non_flag_future_event_count"], 17)
        self.assertEqual(payload["metrics"]["future_event_flag_recall_rate"], 1.0)
        self.assertEqual(payload["metrics"]["future_event_flag_precision"], 1.0)
        self.assertEqual(payload["metrics"]["anti_drift_violation_count"], 0)

        source_metrics = payload["source_disambiguation"]["metrics"]
        self.assertEqual(source_metrics["required_chain_candidate_count"], 17)
        self.assertEqual(source_metrics["multi_source_chain_recovered_count"], 17)
        self.assertEqual(source_metrics["positive_chain_complete_rate"], 1.0)
        self.assertEqual(source_metrics["wrong_source_evidence_rate"], 0.0)
        self.assertEqual(source_metrics["foreground_action_false_positive_count"], 0)
        self.assertGreaterEqual(
            len(payload["source_disambiguation"]["by_track"]),
            10,
        )

        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Assistant speculated", dumped)
        self.assertNotIn(str(REPO_ROOT), dumped)

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

    def test_production_like_retrieval_disambiguates_current_from_stale_sources(self) -> None:
        rows = [
            {
                "dataset_id": "unit_source_disambiguation",
                "schema_version": 1,
                "license": "CC0-1.0",
                "project_id": "dual-source",
                "source_family": "unit_adversarial",
                "past_window": [
                    {
                        "source_id": "plain-correct-source",
                        "kind": "counterfactual_current_source",
                        "text": "Current local override: this is the active rationale for the route.",
                    },
                    {
                        "source_id": "current-looking-stale-source-id",
                        "kind": "pull_request_metadata",
                        "text": "Original public source with stale rationale for the route.",
                    },
                ],
                "future_window": [
                    {
                        "event_id": "dual-current-event",
                        "track": "dual_source_counterfactual",
                        "family": "rejected_route",
                        "hard_event_kind": "commit_reverted",
                        "flag_worthy": True,
                        "text": "The current local source overrides the original public rationale.",
                        "required_past_source_ids": ["plain-correct-source"],
                    }
                ],
            },
            {
                "dataset_id": "unit_source_disambiguation",
                "schema_version": 1,
                "license": "CC0-1.0",
                "project_id": "temporal-override",
                "source_family": "unit_adversarial",
                "past_window": [
                    {
                        "source_id": "old-source",
                        "kind": "old_decision_source",
                        "text": "Old source: the route looked rejected under the earlier constraint.",
                    },
                    {
                        "source_id": "effective-source",
                        "kind": "current_decision_source",
                        "text": "Current source: the earlier constraint was overridden; this is the effective rule.",
                    },
                ],
                "future_window": [
                    {
                        "event_id": "temporal-current-event",
                        "track": "temporal_override_chain",
                        "family": "reopen_condition",
                        "hard_event_kind": "pull_request_merged",
                        "flag_worthy": True,
                        "text": "The newer source is the current effective rule after the override chain.",
                        "required_past_source_ids": ["effective-source"],
                    }
                ],
            },
            {
                "dataset_id": "unit_source_disambiguation",
                "schema_version": 1,
                "license": "CC0-1.0",
                "project_id": "unsupported-negative",
                "source_family": "unit_adversarial",
                "past_window": [
                    {
                        "source_id": "weak-related-source",
                        "kind": "weak_related_source",
                        "text": "Weak related source: vocabulary overlaps but no hard source-backed condition exists.",
                    }
                ],
                "future_window": [
                    {
                        "event_id": "unsupported-event",
                        "track": "abstention_unsupported",
                        "family": "rejected_route",
                        "hard_event_kind": "commit_reverted",
                        "flag_worthy": False,
                        "text": "Unsupported abstention case: similar surface form but no source-backed condition.",
                        "required_past_source_ids": [],
                    }
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "source-disambiguation.jsonl"
            fixture.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=fixture,
                production_like_retrieval=True,
                source_disambiguation_top_k=1,
            )

        self.assertEqual(payload["config"]["prediction_source"], "production_like_retrieval")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(
            payload["claim_levels"]["source_window_oracle_contract"][
                "uses_required_past_source_ids_as_prediction_input"
            ],
            False,
        )
        self.assertTrue(payload["claim_levels"]["production_like_retrieval"]["available"])
        self.assertFalse(
            payload["source_disambiguation"]["input_contract"][
                "uses_required_past_source_ids_for_ranking"
            ]
        )
        self.assertEqual(
            payload["source_disambiguation"]["metrics"]["current_source_top_k_hit_rate"],
            1.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["metrics"][
                "current_vs_stale_pairwise_win_rate"
            ],
            1.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["metrics"]["stale_source_top_k_rate"],
            0.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["metrics"]["wrong_source_evidence_rate"],
            0.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["metrics"]["negative_false_positive_rate"],
            0.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["by_track"]["dual_source_counterfactual"][
                "current_source_top_k_hit_rate"
            ],
            1.0,
        )
        self.assertEqual(
            payload["source_disambiguation"]["by_track"]["temporal_override_chain"][
                "current_vs_stale_pairwise_win_rate"
            ],
            1.0,
        )
        prediction_by_event = {row["event_id"]: row for row in payload["events"]}
        self.assertEqual(
            prediction_by_event["dual-current-event"]["predicted_past_source_ids"],
            ["plain-correct-source"],
        )

    def test_source_disambiguation_uses_metadata_file_for_track_slices(self) -> None:
        row = {
            "dataset_id": "unit_source_disambiguation_metadata",
            "schema_version": 1,
            "license": "CC0-1.0",
            "project_id": "metadata-track",
            "source_family": "unit_adversarial",
            "past_window": [
                {
                    "source_id": "old-source",
                    "kind": "old_decision_source",
                    "text": "Old source: the route looked rejected under the earlier constraint.",
                },
                {
                    "source_id": "effective-source",
                    "kind": "current_decision_source",
                    "text": "Current source: the earlier constraint was overridden; this is the effective rule.",
                },
            ],
            "future_window": [
                {
                    "event_id": "metadata-temporal-event",
                    "family": "reopen_condition",
                    "hard_event_kind": "pull_request_merged",
                    "flag_worthy": True,
                    "text": "The newer source is the current effective rule after the override chain.",
                    "required_past_source_ids": ["effective-source"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "source-disambiguation.jsonl"
            metadata = root / "event-meta.json"
            fixture.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            metadata.write_text(
                json.dumps(
                    {
                        "metadata-temporal-event": {
                            "track": "temporal_override_chain",
                        }
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=fixture,
                event_metadata_file=metadata,
                production_like_retrieval=True,
            )

        self.assertIn("temporal_override_chain", payload["source_disambiguation"]["by_track"])

    def test_source_disambiguation_suppresses_lexical_near_miss_subtypes(self) -> None:
        rows = [
            {
                "dataset_id": "unit_source_disambiguation_near_miss",
                "schema_version": 1,
                "license": "CC0-1.0",
                "project_id": "near-miss-subtypes",
                "source_family": "unit_adversarial",
                "past_window": [
                    {
                        "source_id": "stale-current-source",
                        "kind": "old_decision_source",
                        "text": "Old source says the current override was rejected earlier.",
                    },
                    {
                        "source_id": "wrong-stance-source",
                        "kind": "pull_request_metadata",
                        "text": "Merged PR vocabulary says the route is supported.",
                    },
                    {
                        "source_id": "lexical-recap-source",
                        "kind": "assistant_message",
                        "text": "Recap of similar route words without source-backed evidence.",
                    },
                ],
                "future_window": [
                    {
                        "event_id": "near-miss-stale-current",
                        "family": "reopen_condition",
                        "hard_event_kind": "pull_request_merged",
                        "flag_worthy": False,
                        "text": "Stale-current near-miss: old source vocabulary is not support for a current rule.",
                        "required_past_source_ids": [],
                    },
                    {
                        "event_id": "near-miss-wrong-stance",
                        "family": "workaround_rationale",
                        "hard_event_kind": "pull_request_rejected",
                        "flag_worthy": False,
                        "text": "Wrong-stance near-miss: same token vocabulary but opposite stance, not support.",
                        "required_past_source_ids": [],
                    },
                    {
                        "event_id": "near-miss-lexical-recap",
                        "family": "rejected_route",
                        "hard_event_kind": "commit_reverted",
                        "flag_worthy": False,
                        "text": "Lexical recap near-miss: summary-like wording without source-backed condition.",
                        "required_past_source_ids": [],
                    },
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "source-disambiguation-near-miss.jsonl"
            fixture.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=fixture,
                production_like_retrieval=True,
                source_disambiguation_top_k=1,
            )

        metrics = payload["source_disambiguation"]["metrics"]
        self.assertEqual(metrics["negative_false_positive_rate"], 0.0)
        self.assertEqual(metrics["hard_negative_suppression_rate"], 1.0)
        self.assertEqual(
            payload["source_disambiguation"]["negative_subtypes"],
            {
                "lexical_recap_lure": {
                    "event_count": 1,
                    "false_positive_count": 0,
                    "suppressed_count": 1,
                    "suppression_rate": 1.0,
                },
                "stale_current_lure": {
                    "event_count": 1,
                    "false_positive_count": 0,
                    "suppressed_count": 1,
                    "suppression_rate": 1.0,
                },
                "wrong_stance_lure": {
                    "event_count": 1,
                    "false_positive_count": 0,
                    "suppressed_count": 1,
                    "suppression_rate": 1.0,
                },
            },
        )
        by_event = {
            row["event_id"]: row for row in payload["source_disambiguation"]["events"]
        }
        self.assertEqual(by_event["near-miss-stale-current"]["hard_negative_subtype"], "stale_current_lure")
        self.assertEqual(by_event["near-miss-wrong-stance"]["hard_negative_subtype"], "wrong_stance_lure")
        self.assertEqual(by_event["near-miss-lexical-recap"]["hard_negative_subtype"], "lexical_recap_lure")
        for row in by_event.values():
            self.assertEqual(row["route_actionability"]["decision"], "suppress")
            self.assertFalse(row["negative_false_positive"])

    def test_hard_negative_subtype_ignores_grader_fields(self) -> None:
        event = {
            "event_id": "near-miss-grader-boundary",
            "family": "reopen_condition",
            "hard_event_kind": "pull_request_merged",
            "flag_worthy": False,
            "expected_signal": "ignore_me",
            "text": "Wrong-stance near-miss: same token vocabulary but opposite stance, not support.",
            "required_past_source_ids": [],
        }
        altered = {
            **event,
            "flag_worthy": True,
            "expected_signal": "different_grader_label",
            "required_past_source_ids": ["current-source"],
        }

        self.assertEqual(
            benchmark.hard_negative_subtype_for_event(event),
            benchmark.hard_negative_subtype_for_event(altered),
        )

    def test_source_disambiguation_keeps_positive_near_miss_without_lure_cue(self) -> None:
        row = {
            "dataset_id": "unit_source_disambiguation_positive_near_miss",
            "schema_version": 1,
            "license": "CC0-1.0",
            "project_id": "positive-near-miss",
            "source_family": "unit_adversarial",
            "past_window": [
                {
                    "source_id": "current-source",
                    "kind": "current_decision",
                    "text": "The current effective route records a near-miss follow-up as active.",
                }
            ],
            "future_window": [
                {
                    "event_id": "positive-near-miss",
                    "family": "reopen_condition",
                    "hard_event_kind": "pull_request_merged",
                    "flag_worthy": True,
                    "text": "Near-miss follow-up keeps the current effective route active.",
                    "required_past_source_ids": ["current-source"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "positive-near-miss.jsonl"
            fixture.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            payload = benchmark.run_benchmark(
                dataset_path=fixture,
                production_like_retrieval=True,
            )

        self.assertTrue(payload["ok"], payload)
        event = payload["source_disambiguation"]["events"][0]
        self.assertEqual(event["hard_negative_subtype"], "")
        self.assertEqual(event["route_candidate_reason"], "route_candidate")
        self.assertEqual(event["route_actionability"]["decision"], "flag")

    def test_rollout_route_chain_readout_separates_retrieval_from_actionability(self) -> None:
        payload = benchmark.run_benchmark(
            dataset_path=ROLLOUT_DATASET,
            production_like_retrieval=True,
            source_disambiguation_top_k=2,
        )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["metrics"]["future_event_flag_recall_rate"], 1.0)
        self.assertEqual(payload["metrics"]["future_event_flag_precision"], 1.0)
        self.assertEqual(payload["metrics"]["anti_drift_violation_count"], 0)

        source_metrics = payload["source_disambiguation"]["metrics"]
        self.assertEqual(source_metrics["required_chain_candidate_count"], 3)
        self.assertEqual(source_metrics["multi_source_chain_recovered_count"], 3)
        self.assertEqual(source_metrics["positive_chain_complete_rate"], 1.0)
        self.assertEqual(source_metrics["negative_route_drag_count"], 2)
        self.assertEqual(source_metrics["anti_drift_route_suppression_count"], 2)
        self.assertEqual(source_metrics["anti_drift_route_suppression_rate"], 1.0)
        self.assertEqual(source_metrics["foreground_action_false_positive_count"], 0)

        source_events = {
            row["event_id"]: row for row in payload["source_disambiguation"]["events"]
        }
        refactor_passed = source_events["background-refactor-tests-passed"]
        self.assertEqual(
            refactor_passed["top_source_ids"],
            ["foreground-smoke-failed", "foreground-route-abandoned"],
        )
        self.assertEqual(refactor_passed["selected_past_source_ids"], [])
        self.assertTrue(refactor_passed["negative_route_drag"])
        self.assertTrue(refactor_passed["anti_drift_route_suppressed"])
        self.assertEqual(refactor_passed["route_actionability"]["decision"], "suppress")
        self.assertEqual(
            refactor_passed["route_actionability"]["reason"],
            "successful_current_event",
        )

if __name__ == "__main__":
    unittest.main()
