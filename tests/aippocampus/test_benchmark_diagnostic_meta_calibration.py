from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_diagnostic_meta_calibration as benchmark  # noqa: E402


class DiagnosticMetaCalibrationBenchmarkTests(unittest.TestCase):
    def test_fixture_report_separates_safety_quality_and_insufficient_denominators(self) -> None:
        payload = benchmark.build_diagnostic_meta_calibration_report()

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_diagnostic_meta_calibration_report")
        self.assertEqual(payload["metrics"]["runtime_weight_change_count"], 0)
        self.assertFalse(payload["policy_boundary"]["runtime_weights_changed"])
        self.assertTrue(payload["policy_boundary"]["passing_meta_calibration_is_not_answer_truth"])
        self.assertEqual(
            payload["family_reports"]["macro_yi"]["status"],
            "not_enough_evidence",
        )
        self.assertEqual(
            payload["family_reports"]["dream_topology"]["metrics"]["safety_failure_rate"],
            0.5,
        )
        self.assertEqual(
            payload["local_global_compatibility_fixture"]["authority_level"],
            "navigation_only",
        )
        self.assertEqual(
            payload["local_global_compatibility_fixture"]["claim_permission"],
            "navigation_only_not_fact",
        )
        self.assertIn("answer_truth_from_meta_calibration", payload["cannot_claim"])

        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in ("PRIVATE_", "raw_private_source_text", "C:\\", "/Users/"):
            self.assertNotIn(forbidden, dumped)

    def test_custom_sparse_rows_do_not_invent_metrics(self) -> None:
        payload = benchmark.build_diagnostic_meta_calibration_report(
            [
                {
                    "family": "attention_semantic_route",
                    "case_id": "one",
                    "predicted": "reopen_first",
                    "label": "reopen_first",
                    "safety_gate": "pass",
                    "quality_gate": "useful",
                }
            ],
            min_denominator=2,
        )

        attention = payload["family_reports"]["attention_semantic_route"]
        self.assertEqual(attention["status"], "not_enough_evidence")
        self.assertEqual(attention["metrics"], {})
        self.assertEqual(
            attention["review_recommendation"],
            "collect_more_fixture_labels_before_calibrating",
        )


if __name__ == "__main__":
    unittest.main()
