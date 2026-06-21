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
        self.assertEqual(report["metrics"]["case_count"], 7)
        self.assertEqual(report["red_lines"]["wrong_hop_drag_count"], 0)
        self.assertEqual(report["red_lines"]["scope_violation_count"], 0)
        self.assertEqual(report["red_lines"]["default_ranking_influence_count"], 0)
        self.assertGreaterEqual(report["metrics"]["top_action_specificity_ok_count"], 7)
        self.assertGreaterEqual(report["metrics"]["apw_action_emitted_count"], 3)
        self.assertEqual(
            report["metrics"]["agent_followed_apw_action_count"],
            report["metrics"]["apw_action_emitted_count"],
        )
        self.assertEqual(
            report["metrics"]["source_reopen_success_count"],
            report["metrics"]["apw_action_emitted_count"],
        )
        self.assertGreaterEqual(report["metrics"]["task_usefulness_outcome_count"], 3)
        self.assertIn("stale_route_stays_shadowed", {row["case_id"] for row in report["rows"]})
        self.assertIn(
            "source_free_semantic_bridge_evaporates",
            {row["case_id"] for row in report["rows"]},
        )
        self.assertEqual(report["warnings"]["route_count_without_executable_action_count"], 0)
        self.assertEqual(report["warnings"]["action_without_source_reopen_success_count"], 0)
        self.assertEqual(report["warnings"]["decision_mismatch_count"], 0)
        self.assertTrue(report["boundary"]["navigation_lift_is_not_source_evidence"])
        self.assertEqual(report["boundary"]["follow_through_mode"], "proxy_action_path")
        self.assertFalse(report["boundary"]["default_recall_influence_allowed"])
        self.assertIn("broad_live_recall_quality", report["cannot_claim"])

    def test_gate_warns_when_route_count_lift_creates_wrong_hop_drag(self) -> None:
        cases = copy.deepcopy(benchmark.fixture_path_walker_cases())
        cases[0]["candidates"][0]["route_terms"].append("slime mold")
        report = benchmark.evaluate_path_walker_gate(cases)

        self.assertFalse(report["ok"], report)
        self.assertGreater(report["warnings"]["route_count_lift_without_usefulness_count"], 0)


if __name__ == "__main__":
    unittest.main()
