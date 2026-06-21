from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"

benchmark = import_benchmark_module("benchmark_natural_handoff_usefulness")

class NaturalHandoffUsefulnessBenchmarkTests(unittest.TestCase):
    def test_report_separates_wins_no_help_and_regressions(self) -> None:
        report = benchmark.build_report()

        self.assertEqual(report["kind"], "aippocampus_natural_handoff_usefulness_validation")
        self.assertEqual(report["issue_scope"], ["#1185", "#1384"])
        self.assertEqual(report["case_count"], 6)
        self.assertEqual(report["metrics"]["win_count"], 2)
        self.assertEqual(report["metrics"]["no_help_count"], 1)
        self.assertEqual(report["metrics"]["regression_count"], 3)
        self.assertGreater(report["metrics"]["natural_handoff_success_rate"], 0)
        self.assertGreater(report["metrics"]["default_session_continuity_success_rate"], 0)
        self.assertIn("wrong_route_drag", report["metrics"]["blocker_counts"])
        self.assertIn("safe_route_demoted_to_scent", report["metrics"]["blocker_counts"])
        self.assertTrue(report["privacy_boundary"]["public_safe_synthetic_only"])
        self.assertFalse(report["privacy_boundary"]["raw_private_history_used"])
        self.assertIn("broad_default_session_product_lift", report["cannot_claim"])
        self.assertEqual(report["measurement_origin"], "synthetic_fixture")
        self.assertFalse(report["observed_agent_behavior"])
        self.assertEqual(report["decision_impact"], "issue_closeout_candidate")
        self.assertFalse(report["decision_impact_gate_ok"])
        self.assertTrue(report["requires_human_review_before_closeout"])
        self.assertIn("useful_now", report)
        self.assertNotIn("recommended_owner_status", report["promotion_readout"])

    def test_regression_blockers_emit_foreground_next_actions(self) -> None:
        report = benchmark.build_report()
        actions = {
            action["blocker_id"]: action
            for action in report["blocker_next_actions"]
        }

        self.assertIn("safe_route_demoted_to_scent", actions)
        self.assertIn("fresh_agent_broad_search_before_recall", actions)
        self.assertIn("wrong_route_drag", actions)
        self.assertIn("copy_pasteable_deepen_target_missing", actions)
        self.assertEqual(
            actions["copy_pasteable_deepen_target_missing"]["owner_issue"],
            "#1988",
        )
        self.assertTrue(actions["wrong_route_drag"]["owner_module_path"])
        self.assertTrue(actions["fresh_agent_broad_search_before_recall"]["command"])
        self.assertFalse(actions["safe_route_demoted_to_scent"]["live_product_claim"])

    def test_winning_cases_pass_usefulness_and_attention_cost_gates(self) -> None:
        report = benchmark.build_report()
        wins = [row for row in report["cases"] if row["observed_outcome"] == "win"]

        self.assertEqual(len(wins), 2)
        for row in wins:
            self.assertTrue(row["metrics"]["safety_gate_ok"])
            self.assertTrue(row["metrics"]["usefulness_gate_ok"])
            self.assertTrue(row["metrics"]["attention_cost_ok"])
            self.assertEqual(row["metrics"]["quality_gate_ok"], True)

    def test_no_help_case_is_neutral_not_promoted(self) -> None:
        report = benchmark.build_report()
        no_help = [row for row in report["cases"] if row["observed_outcome"] == "no_help"]

        self.assertEqual(len(no_help), 1)
        self.assertFalse(no_help[0]["route_available"])
        self.assertTrue(no_help[0]["clarification_prompted"])
        self.assertFalse(no_help[0]["metrics"]["quality_gate_ok"])

    def test_cli_json_is_public_safe(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_natural_handoff_usefulness.py"),
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["metrics"]["regression_count"], 3)
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["promotion_readout"]["decision_impact_gate_ok"])
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("/Users/", serialized)

if __name__ == "__main__":
    unittest.main()
