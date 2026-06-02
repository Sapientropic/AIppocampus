from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_public_longitudinal_users as benchmark  # noqa: E402


class PublicLongitudinalUsersBenchmarkTests(unittest.TestCase):
    def test_checked_in_dataset_covers_coding_implicit_knowledge_families(self) -> None:
        dataset = benchmark.load_dataset()
        probe_types = {str(probe["probe_type"]) for probe in dataset.probes}
        categories = {str(claim["category"]) for claim in dataset.claims_by_id.values()}

        self.assertEqual(dataset.dataset_id, "aippocampus_public_longitudinal_users_coding_implicit_v1")
        self.assertGreaterEqual(len(dataset.user_rows), 3)
        self.assertGreaterEqual(len(dataset.probes), 15)
        self.assertLessEqual(
            {
                "rejected_route",
                "tacit_constraint",
                "workaround_rationale",
                "stale_assumption_corrected",
            },
            categories,
        )
        self.assertLessEqual(
            {
                "rejected_route",
                "workaround_rationale",
                "stale_assumption_corrected",
                "reopen_condition",
                "anti_drift_negative",
            },
            probe_types,
        )

    def test_gold_baseline_scores_perfectly_and_stays_sanitized(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_public_longitudinal_users_benchmark")
        self.assertEqual(payload["status"], "contract_smoke_scored")
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["quality_gate_ok"], payload)
        self.assertEqual(payload["dataset"]["track_role"], "scoring_contract_smoke")
        self.assertFalse(payload["dataset"]["future_event_gold_available"])
        self.assertFalse(payload["metrics"]["headline_score_allowed"])
        self.assertFalse(payload["metrics"]["future_event_gold_available"])
        self.assertIsNone(payload["metrics"]["future_event_recall_rate"])
        self.assertEqual(payload["metrics"]["accuracy"], 1.0)
        self.assertEqual(payload["metrics"]["overall_score"], 1.0)
        self.assertEqual(payload["metrics"]["forbidden_claim_violation_count"], 0)
        self.assertEqual(payload["metrics"]["source_event_false_positive_count"], 0)
        self.assertEqual(payload["metrics"]["anti_drift_pass_rate"], 1.0)
        rate_estimates = payload["metrics"]["rate_estimates"]
        self.assertEqual(rate_estimates["accuracy"]["denominator"], payload["metrics"]["total_cases"])
        self.assertEqual(rate_estimates["accuracy"]["confidence_interval"]["lower"], 0.7961)
        self.assertEqual(rate_estimates["anti_drift_pass_rate"]["denominator"], 3)
        self.assertEqual(rate_estimates["anti_drift_pass_rate"]["confidence_interval"]["lower"], 0.4385)
        self.assertEqual(rate_estimates["source_event_false_positive_case_rate"]["numerator"], 0)
        self.assertGreater(
            rate_estimates["source_event_false_positive_case_rate"]["confidence_interval"]["upper"],
            0,
        )
        self.assertFalse(payload["privacy_boundary"]["fixture_contains_private_user_data"])
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_emitted"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Do not add Redis", dumped)
        self.assertNotIn("Can we just add Redis", dumped)
        self.assertNotIn(str(REPO_ROOT), dumped)
        for case in payload["cases"]:
            self.assertIn("probe_sha1", case)
            self.assertNotIn("probe", case)
            self.assertNotIn("source_events", case)
        self.assertIn("flag_recall_over_complete_future_window", payload["cannot_claim"])
        self.assertIn("single_headline_wedge_validation", payload["cannot_claim"])

    def test_public_text_debug_mode_is_explicit(self) -> None:
        payload = benchmark.run_benchmark(include_public_text=True)

        self.assertTrue(payload["privacy_boundary"]["raw_prompt_emitted"])
        self.assertTrue(any("probe" in case for case in payload["cases"]))

    def test_empty_baseline_is_safe_but_not_a_pass(self) -> None:
        payload = benchmark.run_benchmark(baseline="empty")

        self.assertFalse(payload["ok"])
        self.assertLess(payload["metrics"]["overall_score"], 1.0)
        self.assertEqual(payload["metrics"]["forbidden_claim_violation_count"], 0)
        self.assertEqual(payload["metrics"]["source_event_false_positive_count"], 0)
        self.assertEqual(payload["metrics"]["anti_drift_pass_rate"], 1.0)

    def test_custom_predictions_catch_drift_wrong_claims_and_missing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions.jsonl"
            rows = [
                {
                    "case_id": "plu-cache-001",
                    "decision": "surface",
                    "claim_ids": ["cache-redis-rejected-no-daemon", "cache-redis-permanent-ban"],
                    "source_event_ids": ["cache-e001"],
                },
                {
                    "case_id": "plu-renderer-003",
                    "decision": "surface",
                    "claim_ids": ["renderer-fontscale-cache-rationale"],
                    "source_event_ids": [],
                },
                {
                    "case_id": "plu-dream-005",
                    "decision": "surface",
                    "claim_ids": ["dream-candidate-not-source-truth"],
                    "source_event_ids": ["dream-e002"],
                },
            ]
            predictions.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(predictions_file=predictions)

        by_case = {case["case_id"]: case for case in payload["cases"]}
        self.assertFalse(payload["ok"])
        self.assertTrue(by_case["plu-cache-001"]["forbidden_claim_violation"])
        self.assertEqual(by_case["plu-cache-001"]["unknown_claim_ids"], ["cache-redis-permanent-ban"])
        self.assertEqual(by_case["plu-renderer-003"]["missing_source_event_ids"], ["renderer-e002"])
        self.assertTrue(by_case["plu-dream-005"]["anti_drift_violation"])
        self.assertGreater(payload["prediction_diagnostics"]["missing_prediction_count"], 0)


if __name__ == "__main__":
    unittest.main()
