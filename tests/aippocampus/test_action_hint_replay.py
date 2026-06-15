from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks.action_hint_replay import (  # noqa: E402
    public_replay_cases,
    run_action_hint_replay,
)


class ActionHintReplayTests(unittest.TestCase):
    def test_public_replay_fixture_covers_required_positive_and_negative_cases(self) -> None:
        cases = public_replay_cases()
        signals = {case["expected_signal"] for case in cases}

        self.assertIn("stale_route_avoided", signals)
        self.assertIn("source_reopen_before_claim", signals)
        self.assertIn("learned_preflight_before_broad_test", signals)
        self.assertIn("active_anchor_evidence_capture", signals)
        self.assertIn("unrelated_suppressed", signals)
        self.assertIn("source_visible_suppression", signals)
        self.assertIn("private_blocked_suppression", signals)
        self.assertIn("stale_refuted_suppression", signals)
        self.assertIn("anti_nag_suppression", signals)
        self.assertIn("low_confidence_suppression", signals)

    def test_replay_reports_usefulness_cost_and_red_lines_separately(self) -> None:
        report = run_action_hint_replay()

        self.assertEqual(report["kind"], "aippocampus_action_hint_replay_telemetry")
        self.assertTrue(report["contract_gate_ok"])
        self.assertFalse(report["public_quality_gate_ok"])
        self.assertFalse(report["quality_gate_ok"])
        self.assertFalse(report["runtime_policy_adoption_gate_ok"])
        self.assertEqual(report["usefulness_metrics"]["positive_case_count"], 4)
        self.assertEqual(report["usefulness_metrics"]["hinted_positive_count"], 4)
        self.assertEqual(report["cost_metrics"]["false_positive_count"], 0)
        self.assertEqual(report["cost_metrics"]["anti_nag_suppression_count"], 1)
        self.assertEqual(report["cost_metrics"]["source_visible_suppression_count"], 1)
        self.assertEqual(report["red_lines"]["source_truth_overclaim_count"], 0)
        self.assertEqual(report["red_lines"]["raw_tool_or_source_leak_count"], 0)
        self.assertEqual(report["red_lines"]["command_rewrite_count"], 0)
        self.assertEqual(report["red_lines"]["permission_system_behavior_count"], 0)
        self.assertTrue(report["promotion_gates"]["replay_fixture_gate_ok"])
        self.assertFalse(report["promotion_gates"]["live_default_adoption_gate_ok"])
        self.assertIn("causal_real_user_lift", report["cannot_claim"])

    def test_replay_output_omits_raw_private_payload_sentinels(self) -> None:
        serialized = json.dumps(run_action_hint_replay(), ensure_ascii=False)

        self.assertNotIn("PRIVATE_SOURCE_CLAIM_SENTINEL", serialized)
        self.assertNotIn("sk-REPLAY", serialized)
        self.assertNotIn("E:/private", serialized)
        self.assertNotIn("test_secret.py --token", serialized)


if __name__ == "__main__":
    unittest.main()
