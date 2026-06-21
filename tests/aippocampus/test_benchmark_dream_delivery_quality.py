from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.aippocampus.import_path_helpers import import_benchmark_module

benchmark = import_benchmark_module("benchmark_dream_delivery_quality")


class DreamDeliveryQualityBenchmarkTests(unittest.TestCase):
    def test_three_pre_registered_arms_measure_delivery_quality(self) -> None:
        report = benchmark.build_dream_delivery_quality_report()

        self.assertEqual(report["kind"], benchmark.REPORT_KIND)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["scoring_contract"]["arms"],
            [
                "baseline_no_dream",
                "dream_backstage_only",
                "dream_bounded_action_hint",
            ],
        )
        self.assertTrue(report["scoring_contract"]["arms_pre_registered"])
        self.assertFalse(report["scoring_contract"]["private_history_used"])
        self.assertEqual(report["scoring_contract"]["provider_call_count"], 0)

        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["case_count"], 6)
        self.assertGreaterEqual(metrics["bounded_route_lift_count"], 2)
        self.assertGreaterEqual(metrics["bounded_action_lift_count"], 2)
        self.assertLess(metrics["bounded_verification_cost_delta_total"], 0)
        self.assertEqual(metrics["visible_wrong_hint_count"], 0)
        self.assertEqual(metrics["visible_wrong_hint_rate"], 0.0)
        self.assertGreaterEqual(metrics["quiet_no_harm_count"], 4)
        self.assertGreaterEqual(metrics["source_ripening_count"], 2)

    def test_negative_controls_are_explicit_and_block_foreground_leaks(self) -> None:
        report = benchmark.build_dream_delivery_quality_report()
        controls = report["negative_controls"]

        self.assertEqual(controls["stale_route_suppressed_count"], 1)
        self.assertEqual(controls["noisy_hint_suppressed_count"], 1)
        self.assertEqual(controls["over_personalization_suppressed_count"], 1)
        self.assertEqual(controls["dream_only_foreground_leak_count"], 0)
        self.assertEqual(controls["source_truth_overclaim_count"], 0)
        self.assertEqual(controls["source_reopen_required_count"], 6)
        readout = report["issue_readouts"]["github_1438"]
        self.assertTrue(readout["closeout_candidate"], readout)
        self.assertFalse(readout["closeout_eligible"], readout)
        self.assertFalse(readout["decision_impact_gate_ok"], readout)
        self.assertTrue(readout["requires_human_review_before_closeout"], readout)
        self.assertEqual(readout["issue_state"], "closed_historical")
        self.assertTrue(readout["successor_required"])
        self.assertEqual(readout["successor_status"], "successor_missing")
        actions = {action["id"]: action for action in readout["review_next_actions"]}
        self.assertIn("open_dream_delivery_successor", actions)
        self.assertEqual(actions["open_dream_delivery_successor"]["status"], "successor_missing")
        self.assertIn("gh issue create", actions["open_dream_delivery_successor"]["command"])
        self.assertIn("benchmark_dream_delivery_quality.py", actions[
            "rerun_public_dream_delivery_report"
        ]["owner_path"])

    def test_report_is_public_safe_and_not_a_live_private_quality_claim(self) -> None:
        report = benchmark.build_dream_delivery_quality_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        for forbidden in [
            "raw_prompt",
            "raw_source_text",
            "source_refs",
            "thread_id",
            "message_id",
            "provider_payload",
            "SECRET_TOKEN",
            "E:\\",
            str(REPO_ROOT),
        ]:
            self.assertNotIn(forbidden, encoded)
        self.assertIn("live_default_dream_delivery_quality", report["cannot_claim"])
        self.assertIn("broad_private_history_dream_quality", report["cannot_claim"])
        self.assertEqual(report["measurement_origin"], "synthetic_fixture")
        self.assertFalse(report["observed_agent_behavior"])
        self.assertEqual(report["decision_impact"], "issue_closeout_candidate")
        self.assertFalse(report["decision_impact_gate_ok"])
        self.assertTrue(report["requires_human_review_before_closeout"])
        self.assertIn("useful_now", report)
        self.assertIn("review_next_actions", report)
        self.assertTrue(report["review_next_actions"][0]["claim_boundary"])

    def test_cli_writes_public_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dream-delivery-quality.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        REPO_ROOT
                        / "benchmarks"
                        / "aippocampus"
                        / "benchmark_dream_delivery_quality.py"
                    ),
                    "--json",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], benchmark.REPORT_KIND)
        self.assertEqual(written["kind"], benchmark.REPORT_KIND)
        self.assertTrue(written["issue_readouts"]["github_1438"]["closeout_candidate"])
        self.assertFalse(written["issue_readouts"]["github_1438"]["closeout_eligible"])

if __name__ == "__main__":
    unittest.main()
