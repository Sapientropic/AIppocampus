from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"

benchmark = import_benchmark_module("benchmark_exact_source_search_flows")

class ExactSourceSearchFlowBenchmarkTests(unittest.TestCase):
    def test_registry_and_last_recall_search_flow_gate(self) -> None:
        report = benchmark.evaluate_exact_source_search_flows()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["quality_gate_ok"])
        self.assertEqual(report["metrics"]["case_count"], 6)
        self.assertEqual(report["red_lines"]["privacy_path_leak_count"], 0)
        self.assertEqual(report["red_lines"]["raw_registry_entry_shape_count"], 0)
        self.assertEqual(report["red_lines"]["search_miss_claims_absence_count"], 0)
        self.assertGreaterEqual(report["metrics"]["reopenable_hit_count"], 2)
        self.assertIn("absence_of_memory_from_search_miss", report["cannot_claim"])

    def test_cli_json_runner(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BENCHMARKS / "benchmark_exact_source_search_flows.py"), "--json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "aippocampus_exact_source_search_flow_benchmark")
        self.assertTrue(payload["ok"])

if __name__ == "__main__":
    unittest.main()
