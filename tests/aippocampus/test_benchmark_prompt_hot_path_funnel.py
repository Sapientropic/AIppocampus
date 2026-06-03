from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_prompt_hot_path_funnel as benchmark  # noqa: E402


class PromptHotPathFunnelBenchmarkTests(unittest.TestCase):
    def test_report_pairs_latency_with_quality_metrics(self) -> None:
        report = benchmark.run_benchmark()

        self.assertEqual(report["kind"], "aippocampus_prompt_hot_path_funnel_benchmark")
        self.assertTrue(report["ok"])
        self.assertEqual(report["config"]["local_only"], True)
        self.assertEqual(report["config"]["uses_external_model"], False)
        self.assertEqual(report["metrics"]["case_count"], 4)
        self.assertIn("p50_latency_ms", report["metrics"])
        self.assertIn("p95_latency_ms", report["metrics"])
        self.assertIn("false_skip_rate", report["metrics"])
        self.assertIn("wrong_scent_rate", report["metrics"])
        self.assertIn("source_reopen_promotion_rate", report["metrics"])
        self.assertEqual(report["metrics"]["false_evidence_count"], 0)
        self.assertIn("speed alone", " ".join(report["cannot_claim"]))


if __name__ == "__main__":
    unittest.main()
