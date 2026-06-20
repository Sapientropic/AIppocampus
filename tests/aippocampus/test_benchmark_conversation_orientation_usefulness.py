from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_conversation_orientation_usefulness as benchmark  # noqa: E402


class ConversationOrientationUsefulnessBenchmarkTests(unittest.TestCase):
    def test_compact_working_orientation_can_pass_without_overclaim(self) -> None:
        report = benchmark.evaluate_conversation_orientation_usefulness()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["quality_gate_ok"])
        self.assertEqual(report["metrics"]["first_useful_orientation_rate"]["rate"], 1.0)
        self.assertGreater(report["metrics"]["strict_safe_but_useless_count"], 0)
        self.assertEqual(report["metrics"]["source_truth_overclaim_count"], 0)
        self.assertTrue(report["claim_boundary"]["working_orientation_is_not_source_truth"])
        self.assertIn("working_orientation_as_source_truth", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
