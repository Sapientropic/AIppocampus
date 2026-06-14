from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

from benchmarks.aippocampus import benchmark_episode_arc_sequence_usefulness as benchmark  # noqa: E402


class EpisodeArcSequenceUsefulnessBenchmarkTests(unittest.TestCase):
    def test_benchmark_compares_baseline_and_episode_arc_under_same_source_budget(self) -> None:
        report = benchmark.build_episode_arc_sequence_usefulness_report()

        self.assertEqual(report["kind"], benchmark.REPORT_KIND)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["comparison_contract"]["arms"],
            ["baseline_no_episode_arc", "episode_arc_route_packet"],
        )
        self.assertTrue(report["comparison_contract"]["same_source_budget"])
        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["case_count"], 7)
        self.assertGreaterEqual(metrics["treatment_win_count"], 4)
        self.assertEqual(metrics["treatment_regression_count"], 0)
        self.assertGreater(metrics["manual_search_step_delta"], 0)
        self.assertGreaterEqual(metrics["repeated_mistake_avoidance_lift"], 2)
        self.assertGreaterEqual(metrics["correct_source_reopen_lift"], 3)
        self.assertGreaterEqual(metrics["stale_chain_suppression_lift"], 1)
        self.assertEqual(metrics["wrong_project_contamination_count"], 0)
        self.assertEqual(metrics["source_truth_overclaim_count"], 0)

    def test_report_is_public_safe_and_keeps_private_history_out_of_scope(self) -> None:
        report = benchmark.build_episode_arc_sequence_usefulness_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertNotIn('"source_refs": [', encoded)
        self.assertNotIn("thread_key", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertIn("private_history_generality", report["cannot_claim"])
        self.assertIn("live_host_behavior_lift", report["cannot_claim"])
        self.assertTrue(report["issue_readouts"]["github_1440"]["closeout_eligible"])

    def test_cli_writes_report_to_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "episode-arc-sequence-usefulness.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "benchmarks" / "aippocampus" / "benchmark_episode_arc_sequence_usefulness.py"),
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


if __name__ == "__main__":
    unittest.main()
