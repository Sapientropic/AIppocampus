from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_LONGITUDINAL_REPORTS = (
    REPO_ROOT / "docs" / "evidence" / "benchmarks" / "reports" / "public-longitudinal"
)


class PublishedBenchmarkReportsTests(unittest.TestCase):
    def test_react_vcs_report_exposes_ci_and_zero_violation_upper_bound(self) -> None:
        report = json.loads(
            (
                PUBLIC_LONGITUDINAL_REPORTS / "react-real-vcs-100-gold-2026-05-31.json"
            ).read_text(encoding="utf-8")
        )
        source_window = report["arms"]["source_window"]["rate_estimates"]
        candidate_bias = report["candidate_discovery_bias"]

        recall = source_window["future_event_flag_recall"]
        self.assertEqual(recall["denominator"], 105)
        self.assertEqual(recall["confidence_interval"]["lower"], 0.9647)

        violation_rate = source_window["anti_drift_violation_rate"]
        self.assertEqual(violation_rate["numerator"], 0)
        self.assertEqual(violation_rate["confidence_interval"]["upper"], 0.0353)
        self.assertTrue(candidate_bias["available"])
        self.assertEqual(candidate_bias["query_candidate_count"], 434)
        self.assertEqual(candidate_bias["query_term_hit_mix_by_family"]["revert"], 169)
        self.assertEqual(
            candidate_bias["manual_reason_code_counts"]["unavailable_legacy_report"],
            329,
        )
        self.assertFalse(candidate_bias["sampled_miss_rate"]["available"])
        self.assertEqual(
            report["precision_contract"]["diagnostic_metric"],
            "diagnostic_event_identity_precision",
        )
        self.assertEqual(
            report["source_degradation_controls"]["counts_by_state"]["full_source"],
            210,
        )
        self.assertFalse(report["anti_drift_controls"]["legacy_cross_family_tags_available"])

        markdown = (
            PUBLIC_LONGITUDINAL_REPORTS / "react-real-vcs-100-gold-2026-05-31.md"
        ).read_text(encoding="utf-8")
        self.assertIn("95% Wilson CI 96.47%-100.00%, n=105", markdown)
        self.assertIn("95% Wilson upper bound 3.53% (n=105)", markdown)
        self.assertIn("Candidate Discovery Bias", markdown)
        self.assertIn("manual exclusion reasons and sampled miss rate: unavailable", markdown)
        self.assertIn("anti_drift_family_under_test", markdown)

    def test_public_longitudinal_report_marks_small_contract_smokes(self) -> None:
        report = json.loads(
            (
                PUBLIC_LONGITUDINAL_REPORTS
                / "public-longitudinal-users-measurement-2026-05-31.json"
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
            PUBLIC_LONGITUDINAL_REPORTS
            / "public-longitudinal-users-measurement-2026-05-31.md"
        ).read_text(encoding="utf-8")
        self.assertIn("low-inference contract-smoke", markdown)
        self.assertIn("95% Wilson upper bound 56.15% (n=3)", markdown)


if __name__ == "__main__":
    unittest.main()
