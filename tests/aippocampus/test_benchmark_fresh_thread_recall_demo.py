from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for path in (BENCHMARKS, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import benchmark_fresh_thread_recall_demo as benchmark  # noqa: E402


class FreshThreadRecallDemoBenchmarkTests(unittest.TestCase):
    def test_runner_reports_public_safe_three_arm_demo(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(set(payload["demo_report"]["arms"]), {"no_memory", "hook_only", "active_recall"})
        self.assertEqual(payload["metrics"]["positive_flow_count"], 6)
        self.assertEqual(payload["metrics"]["negative_control_count"], 5)
        self.assertEqual(payload["metrics"]["max_turn_depth"], 3)
        self.assertEqual(payload["metrics"]["correction_control_count"], 1)
        self.assertEqual(payload["metrics"]["threshold_edge_control_count"], 1)
        self.assertTrue(payload["quality_gates"]["three_arms_present"])
        self.assertTrue(payload["quality_gates"]["long_turn_flow_present"])
        self.assertTrue(payload["quality_gates"]["correction_controls_present"])
        self.assertTrue(payload["quality_gates"]["threshold_edge_controls_present"])
        self.assertFalse(payload["config"]["uses_live_model"])
        self.assertFalse(payload["config"]["uses_private_history"])

    def test_issue_281_public_validation_readout_is_closeout_eligible(self) -> None:
        payload = benchmark.run_benchmark()
        readout = payload["issue_readouts"]["github_281"]
        metrics = readout["metrics"]

        self.assertTrue(readout["public_validation_measured"])
        self.assertTrue(readout["closeout_eligible"])
        self.assertEqual(readout["claim_level"], "public_safe_fixture_validation")
        self.assertEqual(metrics["positive_public_flow_count"], 6)
        self.assertEqual(metrics["negative_public_control_count"], 5)
        self.assertEqual(metrics["first_turn_scent_precision"], 1.0)
        self.assertEqual(metrics["progressive_activation_gain"], 1.0)
        self.assertEqual(metrics["source_reopen_before_specific_claim_rate"], 1.0)
        self.assertEqual(metrics["irrelevant_memory_drag_rate"], 0.0)
        self.assertEqual(metrics["overpersonalization_count"], 0)
        self.assertEqual(metrics["manual_query_invention_count"], 0)
        self.assertEqual(metrics["manual_query_expected_count"], 0)
        self.assertGreaterEqual(metrics["ready_lock_use_count"], 2)
        self.assertIn("live fresh-thread quality", readout["cannot_claim"])
        self.assertIn("private real-history fresh-thread quality", readout["cannot_claim"])

    def test_issue_1749_first_magic_moment_readout_uses_source_backed_fixture(self) -> None:
        payload = benchmark.run_benchmark()
        readout = payload["issue_readouts"]["github_1749_first_magic_moment"]
        metrics = readout["metrics"]

        self.assertTrue(readout["public_fixture_measured"])
        self.assertEqual(readout["claim_level"], "product_e2e_fixture_evidence")
        self.assertGreaterEqual(metrics["agent_chose_recall_count"], 1)
        self.assertGreaterEqual(metrics["route_found_count"], 1)
        self.assertGreaterEqual(metrics["source_reopened_count"], 1)
        self.assertGreaterEqual(metrics["answer_helpful_count"], 1)
        self.assertEqual(metrics["user_reprompt_needed_count"], 0)
        self.assertEqual(metrics["foreground_friction_count"], 0)
        self.assertTrue(readout["privacy_boundary_ok"])
        self.assertIn("live first-magic-moment quality", readout["cannot_claim"])

    def test_issue_1750_agent_initiative_readout_has_positive_and_negative_controls(self) -> None:
        payload = benchmark.run_benchmark()
        readout = payload["issue_readouts"]["github_1750_agent_initiative"]
        metrics = readout["metrics"]

        self.assertTrue(readout["public_fixture_measured"])
        self.assertGreaterEqual(metrics["continuity_sensitive_case_count"], 3)
        self.assertGreaterEqual(metrics["agent_chose_recall_count"], 2)
        self.assertGreaterEqual(metrics["source_reopen_followthrough_count"], 1)
        self.assertEqual(metrics["negative_control_wrong_recall_count"], 0)
        self.assertEqual(metrics["wrong_context_drag_count"], 0)
        self.assertEqual(metrics["user_reprompt_needed_count"], 0)
        self.assertIn("negative_control", readout["case_groups"])
        self.assertIn("high_risk", readout["case_groups"])

    def test_report_has_no_private_artifacts_or_unsupported_evidence(self) -> None:
        payload = benchmark.run_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["quality_gates"]["audit"]["privacy_failure_count"], 0)
        self.assertEqual(payload["quality_gates"]["audit"]["unsupported_evidence_count"], 0)
        self.assertNotIn("sk_test", serialized)
        self.assertNotIn("private source", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)


if __name__ == "__main__":
    unittest.main()
