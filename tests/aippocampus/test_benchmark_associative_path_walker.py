from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_associative_path_walker as benchmark  # noqa: E402


class AssociativePathWalkerBenchmarkTests(unittest.TestCase):
    def test_gate_reports_navigation_lift_separately_from_source_evidence(self) -> None:
        report = benchmark.evaluate_path_walker_gate()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["quality_gate_ok"])
        self.assertEqual(report["metrics"]["case_count"], 3)
        self.assertEqual(report["red_lines"]["wrong_hop_drag_count"], 0)
        self.assertTrue(report["boundary"]["navigation_lift_is_not_source_evidence"])
        self.assertIn("broad_live_recall_quality", report["cannot_claim"])

    def test_gate_warns_when_route_count_lift_creates_wrong_hop_drag(self) -> None:
        cases = copy.deepcopy(benchmark.fixture_path_walker_cases())
        cases[0]["candidates"][0]["route_terms"].append("slime mold")
        report = benchmark.evaluate_path_walker_gate(cases)

        self.assertFalse(report["ok"], report)
        self.assertGreater(report["warnings"]["route_count_lift_without_usefulness_count"], 0)


if __name__ == "__main__":
    unittest.main()
