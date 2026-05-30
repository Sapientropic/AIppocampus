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

    def test_calibration_report_does_not_emit_source_ref_details(self) -> None:
        payload = benchmark.run_question_tracking_calibration()
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("message_id", rendered)
        self.assertNotIn("source_line", rendered)
        self.assertNotIn("session:", rendered)


if __name__ == "__main__":
    unittest.main()
