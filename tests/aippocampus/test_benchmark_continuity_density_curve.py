from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_continuity_density_curve as density_curve  # noqa: E402
from shared.benchmark_report_contract import benchmark_report_contract_lint  # noqa: E402


class ContinuityDensityCurveBenchmarkTests(unittest.TestCase):
    def test_density_curve_has_three_tiers_and_noisy_control(self) -> None:
        report = density_curve.build_density_curve_report()
        tiers = {row["tier"]: row for row in report["tiers"]}

        self.assertEqual(report["kind"], "aippocampus_continuity_density_curve_benchmark")
        self.assertIn("cold", tiers)
        self.assertIn("light", tiers)
        self.assertIn("medium", tiers)
        self.assertIn("noisy_saturated_control", tiers)
        self.assertGreater(
            report["measured_result"]["medium_vs_cold_source_reopen_lift"],
            0,
        )
        self.assertGreater(
            report["measured_result"]["medium_vs_cold_manual_search_step_reduction"],
            0,
        )
        self.assertGreater(
            tiers["noisy_saturated_control"]["wrong_route_drag_rate"],
            tiers["medium"]["wrong_route_drag_rate"],
        )
        self.assertFalse(report["observed_agent_behavior"])
        self.assertFalse(report["privacy_boundary"]["private_history_used"])

    def test_density_curve_report_satisfies_contract_linter_shape(self) -> None:
        report = density_curve.build_density_curve_report()
        lint = benchmark_report_contract_lint(report)

        self.assertTrue(lint["ok"], lint)
        self.assertFalse(lint["boundary_only_projection"])
        self.assertIn("supports", report)
        self.assertIn("private_real_history_density_curve", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
