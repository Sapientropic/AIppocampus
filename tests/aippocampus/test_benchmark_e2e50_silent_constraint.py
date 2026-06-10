from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_e2e50_silent_constraint as benchmark  # noqa: E402


class E2E50SilentConstraintBenchmarkTests(unittest.TestCase):
    def test_default_fixture_scores_behavior_metrics_without_private_payloads(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["kind"], "aippocampus_e2e50_silent_constraint_case_pack")
        self.assertEqual(payload["claim_level"], "public_synthetic_case_pack_scaffold_only")
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["raw_source_refs_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["private_thread_ids_emitted"], False)

        metrics = payload["metrics"]
        self.assertGreaterEqual(metrics["total_cases"], 20)
        self.assertEqual(metrics["silent_constraint_respected_rate"], 1.0)
        self.assertEqual(metrics["known_bad_route_avoided_rate"], 1.0)
        self.assertEqual(metrics["transient_concern_extinguished_rate"], 1.0)
        self.assertEqual(metrics["current_rule_selected_rate"], 1.0)
        self.assertEqual(metrics["source_reopen_before_risky_action_rate"], 1.0)
        self.assertEqual(metrics["unprompted_overhang_count"], 0)
        self.assertEqual(metrics["stale_revival_count"], 0)
        self.assertEqual(metrics["confabulation_count"], 0)
        self.assertGreaterEqual(metrics["sequence_packet_case_count"], 6)
        self.assertEqual(metrics["order_sensitivity_accuracy"], 1.0)
        self.assertEqual(metrics["middle_event_gap_detection_rate"], 1.0)
        self.assertEqual(metrics["single_point_overclaim_rate"], 0.0)
        self.assertEqual(metrics["supersession_chain_accuracy"], 1.0)
        self.assertEqual(metrics["source_ref_chain_coverage"], 1.0)
        self.assertEqual(metrics["behavior_only_rejection_recall"], 1.0)
        self.assertGreaterEqual(metrics["cognitive_load_sidecar_case_count"], 3)
        self.assertEqual(metrics["load_weight_false_positive_rate"], 0.0)
        self.assertEqual(metrics["load_weight_decay_coverage"], 1.0)
        self.assertEqual(metrics["overpersonalization_from_load_signal_count"], 0)
        self.assertEqual(metrics["load_source_truth_override_count"], 0)

        self.assertLessEqual(
            {
                "binding_constraint_survival",
                "behavior_backed_rejected_route",
                "transient_concern_extinction",
                "superseded_currentness",
                "same_topic_drift_trap",
                "benign_non_action_cue",
                "source_reopen_before_risky_action",
            },
            set(payload["coverage"]["case_families"]),
        )
        self.assertEqual(
            payload["coverage"]["annotation_status_counts"],
            {
                "calibration_seed": 3,
                "duplicate_candidate": 2,
                "gold_seed": 10,
                "negative_control": 2,
                "rejected_candidate": 2,
                "source_visible_candidate": 1,
            },
        )
        self.assertEqual(
            payload["coverage"]["source_family_counts"],
            {"synthetic_public_safe": 20},
        )
        self.assertIn(
            "public_safe_20_case_seed_pack_contract_scored",
            payload["can_claim"],
        )
        self.assertIn("e2e50_behavior_benchmark_quality", payload["cannot_claim"])
        self.assertIn("private_real_history_behavior_lift", payload["cannot_claim"])
        self.assertIn("representative_e2e50_sample_quality", payload["cannot_claim"])
        self.assertIn("completed_50_case_e2e50_sample", payload["cannot_claim"])
        self.assertIn("live_host_behavior_lift", payload["cannot_claim"])
        self.assertIn("semantic_judge_quality", payload["cannot_claim"])
        self.assertIn("episode_arc_as_truth_layer", payload["cannot_claim"])
        self.assertIn("cognitive_load_as_emotion_or_personality_truth", payload["cannot_claim"])

        for row in payload["cases"]:
            self.assertIn("case_hash", row)
            self.assertIn("annotation_status", row)
            self.assertIn("source_family", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("source_refs", row)
            self.assertNotIn("behavior_trace", row)
            self.assertNotIn("sequence_packet", row)
            self.assertNotIn("episode_chain", row)
            self.assertNotIn("event_id", row)
            self.assertNotIn("prompt", row)

        self.assertNotIn("PRIVATE_SENTINEL_TEXT", encoded)
        self.assertNotIn("thread:e2e50-synthetic", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_unreviewed_pack_stays_diagnostic_and_sanitized(self) -> None:
        case_pack = {
            "schema_version": 1,
            "kind": "aippocampus_e2e50_annotated_case_pack",
            "cases": [
                {
                    "case_id": "PRIVATE_SENTINEL_CASE_ID",
                    "case_family": "binding_constraint_survival",
                    "source_review": {
                        "source_reviewed": False,
                        "compaction_boundary_observed": True,
                        "source_ref_hashes": ["sha256:abc123"],
                    },
                    "expected_behavior": {
                        "required_codes": ["safe_route_used"],
                        "forbidden_codes": ["forbidden_route_used"],
                    },
                    "behavior_trace": [{"code": "safe_route_used"}],
                }
            ],
        }

        payload = benchmark.run_benchmark(case_pack=case_pack)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "case_pack_incomplete")
        self.assertEqual(payload["metrics"]["source_reviewed_case_count"], 0)
        self.assertIn("manually_annotated_case_pack_ready", payload["cannot_claim"])
        self.assertNotIn("PRIVATE_SENTINEL_CASE_ID", encoded)
        self.assertNotIn("forbidden_route_used", encoded)

    def test_private_annotation_summary_reports_readiness_blocker_without_rows(self) -> None:
        summary = {
            "kind": "aippocampus_e2e50_private_annotation_summary",
            "status": "private_annotation_blocked",
            "privacy": "hash_count_only_no_text_no_paths_no_ids_no_raw_refs",
            "private_text_exported": False,
            "reviewed_candidate_count": 17,
            "retained_case_count": 7,
            "behavior_seed_count": 6,
            "annotation_category_counts": {
                "gold": 4,
                "calibration": 2,
                "negative_control": 1,
                "source_visible_no_op": 0,
                "duplicate": 3,
                "rejected": 7,
                "blocker": 0,
                "unknown": 0,
            },
            "blocker_class_counts": {
                "retained_candidate": 6,
                "negative_control": 1,
                "duplicate_candidate": 3,
                "subagent_or_goal_context_noise": 5,
                "high_later_remention": 1,
                "source_visible_no_op": 1,
            },
            "blocker_status": {
                "min_retained_cases": 20,
                "retained_case_shortfall": 13,
                "min_negative_controls": 1,
                "negative_control_shortfall": 0,
            },
            "annotations": [
                {
                    "thread_hash": "sha256:PRIVATE_THREAD_HASH",
                    "reason": "PRIVATE_REASON_SHOULD_NOT_LEAK",
                }
            ],
        }

        payload = benchmark.run_benchmark(private_annotation_summary=summary)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        readiness = payload["private_annotation_readiness"]

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(
            payload["status"],
            "case_pack_contract_passed_private_annotation_blocked",
        )
        self.assertFalse(readiness["gate_ok"])
        self.assertEqual(readiness["status"], "private_annotation_blocked")
        self.assertEqual(readiness["reviewed_candidate_count"], 17)
        self.assertEqual(readiness["retained_case_count"], 7)
        self.assertEqual(readiness["retained_case_shortfall"], 13)
        self.assertEqual(readiness["negative_control_shortfall"], 0)
        self.assertIn("private_retained_case_shortfall", readiness["blocker_codes"])
        self.assertIn(
            "private_local_e2e50_annotation_summary_readiness_recorded",
            payload["can_claim"],
        )
        self.assertIn("completed_private_history_20_case_pack", payload["cannot_claim"])
        self.assertNotIn("PRIVATE_THREAD_HASH", encoded)
        self.assertNotIn("PRIVATE_REASON_SHOULD_NOT_LEAK", encoded)
        self.assertNotIn("annotations", readiness)

    def test_incomplete_pack_reports_20_case_blocker_without_20_case_claim(self) -> None:
        case_pack = benchmark.load_fixture()
        case_pack["cases"] = case_pack["cases"][:19]

        payload = benchmark.run_benchmark(case_pack=case_pack)

        self.assertFalse(payload["ok"])
        self.assertIn("below_20_case_seed_target", payload["blocker_codes"])
        self.assertNotIn(
            "public_safe_20_case_seed_pack_contract_scored",
            payload["can_claim"],
        )

    def test_seed_pack_requires_negative_control_status(self) -> None:
        case_pack = benchmark.load_fixture()
        case_pack = copy.deepcopy(case_pack)
        for case in case_pack["cases"]:
            if case.get("annotation_status") == "negative_control":
                case["annotation_status"] = "calibration_seed"

        payload = benchmark.run_benchmark(case_pack=case_pack)

        self.assertFalse(payload["ok"])
        self.assertIn("missing_negative_control_candidate", payload["blocker_codes"])
        self.assertIn("missing_required_annotation_status", payload["blocker_codes"])

    def test_seed_pack_requires_known_source_family_without_leaking_source_text(self) -> None:
        case_pack = benchmark.load_fixture()
        case_pack = copy.deepcopy(case_pack)
        case_pack["cases"][0]["source_family"] = "private_raw_thread"

        payload = benchmark.run_benchmark(case_pack=case_pack)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["ok"])
        self.assertIn("unknown_source_family", payload["blocker_codes"])
        self.assertNotIn("private_raw_thread", encoded)

    def test_sequence_and_load_overclaim_blocks_case_contract_without_leaking_events(self) -> None:
        case_pack = {
            "schema_version": 1,
            "kind": "aippocampus_e2e50_annotated_case_pack",
            "cases": [
                {
                    "case_id": "PRIVATE_OVERCLAIM_CASE",
                    "case_family": "behavior_backed_rejected_route",
                    "source_review": {
                        "source_reviewed": True,
                        "compaction_boundary_observed": True,
                        "source_ref_hashes": ["sha256:abc123"],
                    },
                    "expected_behavior": {
                        "required_codes": ["known_bad_route_avoided"],
                        "forbidden_codes": ["forbidden_route_retried"],
                    },
                    "behavior_trace": [{"code": "known_bad_route_avoided"}],
                    "episode_chain": {
                        "episode_kind": "rejected_route_arc",
                        "event_order": ["attempted_route"],
                        "source_ref_hashes": ["sha256:abc123"],
                        "causal_edges": [],
                        "truth_status": "source_backed_chain_not_current_validity_fact",
                        "current_validity": "needs_reopen",
                        "expected_valid": True,
                    },
                    "sequence_packet": {
                        "kind": "aippocampus_sequence_packet",
                        "timeline": [
                            {
                                "event_id": "PRIVATE_EVENT_ID",
                                "event_kind": "attempted_route",
                                "source_ref_hash": "sha256:abc123",
                            }
                        ],
                        "current_assessment": {
                            "source_thickness": "thin",
                            "freshness": "aging",
                            "proposed_use": "warn",
                            "truth_boundary": "derived_weather_not_source_fact",
                        },
                        "cannot_claim": ["current_validity_requires_source_reopen"],
                    },
                    "cognitive_load": {
                        "strain_signal_counts": {"failed_tool_event": 0},
                        "load_boost_bucket": "high",
                        "load_reason_codes": ["high_load_without_observable_signal"],
                        "projection_claims": ["personality truth"],
                        "decay": {"applied": False},
                        "projection_boundary": "routing_caution_not_affect_or_personality_truth",
                    },
                }
            ],
        }

        payload = benchmark.run_benchmark(case_pack=case_pack)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["ok"])
        self.assertIn("sequence_single_point_overclaim", payload["blocker_codes"])
        self.assertIn("sequence_source_thin_overclaim", payload["blocker_codes"])
        self.assertIn("load_source_truth_override", payload["blocker_codes"])
        self.assertIn("load_weight_false_positive", payload["blocker_codes"])
        self.assertIn("overpersonalization_from_load_signal", payload["blocker_codes"])
        self.assertEqual(payload["metrics"]["single_point_overclaim_rate"], 1.0)
        self.assertEqual(payload["metrics"]["load_weight_false_positive_rate"], 1.0)
        self.assertEqual(payload["metrics"]["load_source_truth_override_count"], 1)
        self.assertEqual(payload["metrics"]["overpersonalization_from_load_signal_count"], 1)
        self.assertNotIn("PRIVATE_OVERCLAIM_CASE", encoded)
        self.assertNotIn("PRIVATE_EVENT_ID", encoded)


if __name__ == "__main__":
    unittest.main()
