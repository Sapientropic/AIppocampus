from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_REPORTS = REPO_ROOT / "docs" / "evidence" / "benchmarks"


class PublishedBenchmarkReportsTests(unittest.TestCase):
    def test_react_vcs_report_exposes_ci_and_zero_violation_upper_bound(self) -> None:
        report = json.loads(
            (BENCHMARK_REPORTS / "react-real-vcs-100-gold-2026-05-31.json").read_text(
                encoding="utf-8",
            )
        )
        source_window = report["arms"]["source_window"]["rate_estimates"]

        recall = source_window["future_event_flag_recall"]
        self.assertEqual(recall["denominator"], 105)
        self.assertEqual(recall["confidence_interval"]["lower"], 0.9647)

        violation_rate = source_window["anti_drift_violation_rate"]
        self.assertEqual(violation_rate["numerator"], 0)
        self.assertEqual(violation_rate["confidence_interval"]["upper"], 0.0353)

        markdown = (BENCHMARK_REPORTS / "react-real-vcs-100-gold-2026-05-31.md").read_text(
            encoding="utf-8",
        )
        self.assertIn("95% Wilson CI 96.47%-100.00%, n=105", markdown)
        self.assertIn("95% Wilson upper bound 3.53% (n=105)", markdown)

    def test_public_longitudinal_report_marks_small_contract_smokes(self) -> None:
        report = json.loads(
            (
                BENCHMARK_REPORTS / "public-longitudinal-users-measurement-2026-05-31.json"
            ).read_text(encoding="utf-8")
        )
        tracks = report["tracks"]

        pseudo_gold = tracks["public_pseudo_user_contract_smoke"]["gold"]
        self.assertTrue(pseudo_gold["sample_size_warnings"]["accuracy"]["low_inference"])
        self.assertEqual(pseudo_gold["rate_estimates"]["accuracy"]["denominator"], 15)
        self.assertEqual(
            pseudo_gold["rate_estimates"]["source_event_false_positive_case_rate"][
                "confidence_interval"
            ]["upper"],
            0.2039,
        )

        vcs_gold = tracks["vcs_future_event_recall_scaffold"]["gold"]
        self.assertTrue(vcs_gold["sample_size_warnings"]["future_event_flag_recall"]["low_inference"])
        self.assertEqual(
            vcs_gold["rate_estimates"]["future_event_flag_recall"]["confidence_interval"]["lower"],
            0.6097,
        )

        rollout_gold = tracks["rollout_behavior_event_recall_scaffold"]["gold"]
        self.assertEqual(
            rollout_gold["rate_estimates"]["anti_drift_violation_rate"]["confidence_interval"][
                "upper"
            ],
            0.5615,
        )

        markdown = (
            BENCHMARK_REPORTS / "public-longitudinal-users-measurement-2026-05-31.md"
        ).read_text(encoding="utf-8")
        self.assertIn("low-inference contract-smoke", markdown)
        self.assertIn("95% Wilson upper bound 56.15% (n=3)", markdown)


if __name__ == "__main__":
    unittest.main()
