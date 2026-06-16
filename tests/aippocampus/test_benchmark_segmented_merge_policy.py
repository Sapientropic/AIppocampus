from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_segmented_merge_policy as benchmark  # noqa: E402


class SegmentedMergePolicyBenchmarkTests(unittest.TestCase):
    def test_default_policy_passes_required_calibration_patterns(self) -> None:
        payload = benchmark.run_segmented_merge_policy_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_segmented_merge_policy_benchmark")
        self.assertEqual(payload["status"], "policy_acceptance_passed")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["case_count"], 5)
        self.assertEqual(payload["metrics"]["passed_case_count"], 5)
        self.assertEqual(payload["metrics"]["target_hit_rate"], 1.0)
        self.assertEqual(payload["metrics"]["source_diversity_pass_rate"], 1.0)
        self.assertEqual(payload["metrics"]["adjacent_turn_pairing_success_rate"], 1.0)
        self.assertEqual(payload["metrics"]["source_key_dedupe_case_count"], 1)
        self.assertEqual(payload["metrics"]["source_key_dedupe_count"], 1)
        self.assertEqual(payload["metrics"]["stale_superseded_false_promotion_count"], 0)
        self.assertIn("real_user_recall_quality", payload["cannot_claim"])
        self.assertIn("private_history_segment_merge_quality", payload["cannot_claim"])
        self.assertEqual(
            {
                case["pattern"]
                for case in payload["cases"]
            },
            {
                "cross_segment_diversity",
                "adjacent_turn_pairing",
                "duplicate_nearby_recap_suppression",
                "stable_source_join_dedupe",
                "stale_superseded_currentness",
            },
        )

    def test_report_is_sanitized_and_explains_sensitivity(self) -> None:
        payload = benchmark.run_segmented_merge_policy_benchmark()

        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("RAW_SEGMENT_TEXT_SHOULD_NOT_EMIT", dumped)
        self.assertFalse(payload["privacy_boundary"]["raw_snippets_emitted"])
        self.assertTrue(payload["decision"]["default_policy_acceptable"])
        self.assertIn("default_policy", payload["policy"])
        self.assertIn("no_diversity_penalties", payload["sensitivity"])
        self.assertIn("no_final_answer_bonus", payload["sensitivity"])
        self.assertGreater(
            payload["sensitivity"]["no_diversity_penalties"]["regressed_case_count"],
            0,
        )
        self.assertGreater(
            payload["sensitivity"]["no_final_answer_bonus"]["regressed_case_count"],
            0,
        )

    def test_replay_cohort_separates_ranking_from_source_reopen_validation(self) -> None:
        payload = benchmark.run_segmented_merge_policy_benchmark(include_replay_cohort=True)
        metrics = payload["metrics"]

        self.assertEqual(metrics["synthetic_policy_fixture_case_count"], 5)
        self.assertEqual(metrics["generated_soak_case_count"], 0)
        self.assertGreaterEqual(metrics["long_thread_replay_case_count"], 8)
        self.assertEqual(metrics["monolithic_target_hit_rate"], 1.0)
        self.assertEqual(metrics["full_fanout_target_hit_rate"], 1.0)
        self.assertGreater(metrics["budgeted_fanout_target_hit_rate"], 0.0)
        self.assertLess(
            metrics["budgeted_fanout_target_hit_rate"],
            metrics["full_fanout_target_hit_rate"],
        )
        self.assertGreaterEqual(metrics["segmented_vs_monolithic_delta"], 0.0)
        self.assertEqual(metrics["answer_support_after_source_reopen_rate"], 1.0)
        self.assertGreater(metrics["early_segment_miss_count"], 0)
        self.assertGreater(metrics["middle_segment_miss_count"], 0)
        self.assertEqual(metrics["cross_boundary_pairing_success_rate"], 1.0)
        self.assertEqual(metrics["stale_superseded_false_promotion_count"], 0)
        self.assertEqual(metrics["duplicate_recap_overpromotion_count"], 0)
        self.assertGreater(metrics["wrong_segment_crowding_count"], 0)
        self.assertGreaterEqual(metrics["query_latency_p50_ms"], 0.0)
        self.assertGreaterEqual(metrics["query_latency_p95_ms"], metrics["query_latency_p50_ms"])
        self.assertEqual(metrics["raw_private_text_leak_count"], 0)
        self.assertEqual(metrics["absolute_path_leak_count"], 0)
        self.assertIn("replay_source_evidence", payload["evidence_cohorts"])
        self.assertEqual(
            payload["evidence_cohorts"]["replay_source_evidence"]["validation"],
            "source_open_support_checked_separately_from_ranking",
        )

        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("RAW_PRIVATE_TEXT_SHOULD_NOT_EMIT", dumped)
        self.assertNotIn(str(ROOT), dumped)

    def test_fixture_contract_rejects_too_few_patterns(self) -> None:
        fixture = {
            "schema_version": 1,
            "cases": [
                {
                    "case_id": "only-one",
                    "pattern": "cross_segment_diversity",
                    "top_k": 2,
                    "results": [],
                    "expect": {
                        "target_source_refs": [],
                        "min_unique_segments": 1,
                    },
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "at least 4"):
            benchmark.evaluate_fixture(fixture)


if __name__ == "__main__":
    unittest.main()
