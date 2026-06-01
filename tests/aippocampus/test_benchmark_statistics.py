from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_statistics as stats  # noqa: E402


class BenchmarkStatisticsTests(unittest.TestCase):
    def test_wilson_interval_reports_known_bounds(self) -> None:
        interval = stats.wilson_score_interval(97, 100)

        self.assertEqual(interval["method"], "wilson_score")
        self.assertEqual(interval["confidence_level"], 0.95)
        self.assertEqual(interval["success_count"], 97)
        self.assertEqual(interval["total_count"], 100)
        self.assertEqual(interval["point_estimate"], 0.97)
        self.assertEqual(interval["lower"], 0.9155)
        self.assertEqual(interval["upper"], 0.9897)

    def test_rate_report_keeps_point_and_lower_bound_gate_separate(self) -> None:
        report = stats.binomial_rate_report(
            "accuracy",
            numerator=99,
            denominator=100,
            threshold=0.95,
        )

        self.assertEqual(report["point_estimate"], 0.99)
        self.assertTrue(report["gate"]["passes_point_estimate"])
        self.assertFalse(report["gate"]["passes_lower_bound"])
        self.assertEqual(report["gate"]["lower_bound"], 0.9455)

    def test_empty_rate_report_is_explicitly_undefined(self) -> None:
        report = stats.binomial_rate_report("empty", numerator=3, denominator=0)

        self.assertFalse(report["defined"])
        self.assertEqual(report["numerator"], 0)
        self.assertEqual(report["point_estimate"], 0.0)
        self.assertEqual(report["confidence_interval"]["lower"], 0.0)

    def test_rate_report_clamps_impossible_success_count(self) -> None:
        report = stats.binomial_rate_report("clamped", numerator=5, denominator=3)

        self.assertEqual(report["numerator"], 3)
        self.assertEqual(report["denominator"], 3)
        self.assertEqual(report["point_estimate"], 1.0)
