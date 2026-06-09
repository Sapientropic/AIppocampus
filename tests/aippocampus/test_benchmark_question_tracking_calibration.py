from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
):
    sys.path.insert(0, str(_path))

import benchmark_question_tracking_calibration as benchmark  # noqa: E402


class QuestionTrackingCalibrationBenchmarkTests(unittest.TestCase):
    def test_selected_fixtures_cover_threshold_boundary_claims(self) -> None:
        payload = benchmark.run_question_tracking_calibration()

        self.assertEqual(payload["kind"], "aippocampus_question_tracking_calibration")
        self.assertEqual(payload["status"], "selected_fixture_calibration_passed")
        self.assertTrue(payload["metrics"]["obvious_recurring_retained"])
        self.assertEqual(payload["metrics"]["generic_low_information_merge_count"], 0)
        self.assertEqual(payload["metrics"]["orientation_conflict_merge_count"], 0)
        self.assertTrue(payload["metrics"]["threshold_non_regression_passed"])
        self.assertLessEqual(payload["metrics"]["threshold_missed_positive_delta"], 0)
        self.assertLessEqual(payload["metrics"]["threshold_merged_negative_delta"], 0)
        self.assertGreaterEqual(payload["metrics"]["pending_confirmation_request_count"], 1)
        self.assertIn("threshold_comparison", payload["scenarios"][0])
        self.assertIn(
            "selected_fixtures_keep_obvious_recurring_questions_linked",
            payload["can_claim"],
        )
        self.assertIn(
            "selected_fixtures_show_adaptive_thresholds_do_not_regress_static_threshold_baseline",
            payload["can_claim"],
        )
        self.assertIn("live_external_model_confirmation", payload["cannot_claim"])

    def test_reports_six_axis_pattern_separation_metrics(self) -> None:
        payload = benchmark.run_question_tracking_calibration()

        six_axis = payload["metrics"]["six_axis_dynamic_thresholds"]
        modes = six_axis["comparison_modes"]

        self.assertEqual(
            set(modes),
            {
                "fixed_similarity_threshold",
                "static_strong_threshold",
                "dynamic_six_axis_threshold",
            },
        )
        self.assertGreater(modes["fixed_similarity_threshold"]["false_merge_count"], 0)
        self.assertGreater(modes["static_strong_threshold"]["false_split_count"], 0)
        self.assertEqual(modes["dynamic_six_axis_threshold"]["false_merge_rate"], 0.0)
        self.assertEqual(modes["dynamic_six_axis_threshold"]["false_split_rate"], 0.0)
        self.assertGreaterEqual(six_axis["adaptive_improved_failure_mode_count"], 2)
        self.assertGreaterEqual(six_axis["borderline_auto_correct_count"], 1)
        self.assertEqual(six_axis["borderline_auto_wrong_count"], 0)
        self.assertEqual(six_axis["source_ref_coverage_rate"], 1.0)
        self.assertEqual(
            six_axis["case_family_counts"]["over_merge_orientation_scope_conflict"],
            1,
        )
        self.assertEqual(
            six_axis["case_family_counts"]["over_split_same_frontier"],
            1,
        )

        audited = [
            item
            for scenario in payload["scenarios"]
            for item in scenario.get("threshold_audit", [])
        ]
        self.assertTrue(audited)
        self.assertTrue(all(item["reason_codes"] for item in audited))
        self.assertTrue(
            any("intent_orientation_conflict" in item["reason_codes"] for item in audited)
        )
        self.assertTrue(any("same_phase_context" in item["reason_codes"] for item in audited))
        self.assertIn(
            "six_axis_dynamic_thresholds_are_measured_as_navigation_policy",
            payload["can_claim"],
        )
        self.assertIn("source_truth_from_dynamic_thresholds", payload["cannot_claim"])

    def test_calibration_report_does_not_emit_source_ref_details(self) -> None:
        payload = benchmark.run_question_tracking_calibration()
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("message_id", rendered)
        self.assertNotIn("source_line", rendered)
        self.assertNotIn("session:", rendered)


if __name__ == "__main__":
    unittest.main()
