from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
benchmark = import_benchmark_module("benchmark_activation_dogfood_usefulness")


class ActivationDogfoodUsefulnessBenchmarkTests(unittest.TestCase):
    def test_probe_reports_candidate_funnel_and_user_visible_metrics(self) -> None:
        report = benchmark.build_activation_dogfood_usefulness_report()
        warm = report["arm_metrics"]["warm_replay_signal"]
        cold = report["arm_metrics"]["cold_no_activation"]

        self.assertEqual(report["kind"], benchmark.REPORT_KIND)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["case_count"], 4)
        self.assertTrue(report["comparison_contract"]["candidate_funnel_split_counts"])
        self.assertGreater(warm["generated_candidate_count"], 0)
        self.assertGreater(warm["verifier_seen_candidate_count"], 0)
        self.assertGreaterEqual(warm["useful_source_open_hit_count"], cold["useful_source_open_hit_count"])
        self.assertLess(report["deltas"]["manual_search_fallback_delta"], 0)
        self.assertLess(report["deltas"]["wrong_route_drag_delta"], 0)
        self.assertLess(report["deltas"]["noisy_surfacing_delta"], 0)
        self.assertEqual(warm["signal_role_counts"]["process_supervision"], 1)
        self.assertEqual(warm["signal_role_counts"]["hard_negative"], 1)
        self.assertFalse(report["decision"]["default_live_claim_promoted"])

    def test_probe_consumes_replayable_trajectory_without_public_leakage(self) -> None:
        report = benchmark.build_activation_dogfood_usefulness_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        origins = {case["origin"] for case in report["case_summaries"]}

        self.assertIn("replayable_behavior_trajectory", origins)
        self.assertIn("default_dream_delivery_quality", report["cannot_claim"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertFalse(report["privacy_boundary"]["local_paths_serialized"])

    def test_cli_json_runs(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "benchmarks" / "aippocampus" / "benchmark_activation_dogfood_usefulness.py"),
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], benchmark.REPORT_KIND)


if __name__ == "__main__":
    unittest.main()
