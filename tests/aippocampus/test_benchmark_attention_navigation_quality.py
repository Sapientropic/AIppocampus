from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_attention_navigation_quality as benchmark  # noqa: E402


class AttentionNavigationQualityBenchmarkTests(unittest.TestCase):
    def test_report_measures_navigation_quality_and_red_lines_separately(self) -> None:
        payload = benchmark.run_attention_navigation_quality()
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["kind"], "aippocampus_attention_navigation_quality")
        self.assertTrue(payload["ok"], json.dumps(payload, ensure_ascii=False, indent=2))
        self.assertNotIn("score", payload)
        self.assertNotIn("aggregate_score", payload)

        families = {case["family"] for case in payload["cases"]}
        self.assertTrue(
            {
                "positive_route",
                "hard_mask",
                "stale_currentness",
                "conflict",
                "action_time",
                "anti_nag",
            }.issubset(families)
        )

        metrics = payload["metrics"]
        self.assertEqual(metrics["route_precision_at_1"]["rate"], 1.0)
        self.assertEqual(metrics["route_recall_at_k"]["rate"], 1.0)
        self.assertEqual(metrics["source_reopen_success_rate"]["rate"], 1.0)
        self.assertEqual(metrics["wrong_source_evidence_rate"]["rate"], 0.0)
        self.assertEqual(metrics["false_preactivation_rate"]["rate"], 0.0)

        red_lines = payload["hard_red_lines"]
        for name, value in red_lines.items():
            with self.subTest(red_line=name):
                self.assertEqual(value, 0)

        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["private_text_emitted"])
        self.assertNotIn("PRIVATE_", rendered)
        self.assertNotIn("gold_answer", rendered)
        self.assertIn("broad_memory_qa_quality", payload["cannot_claim"])
        self.assertIn("live_host_behavior_lift", payload["cannot_claim"])

    def test_red_line_violation_fails_even_when_average_route_rate_is_high(self) -> None:
        cases = benchmark.fixture_navigation_quality_cases()
        bad_cases = copy.deepcopy(cases)
        masked = next(case for case in bad_cases if case["family"] == "hard_mask")
        masked["packet"]["emitted"] = True
        masked["packet"]["source_handles"] = [
            {"source_id": "clean:private", "segment_id": "leaked", "reopen_required": True}
        ]

        payload = benchmark.evaluate_navigation_quality_cases(bad_cases)

        self.assertFalse(payload["ok"])
        self.assertGreater(payload["hard_red_lines"]["privacy_bypass_count"], 0)
        self.assertGreater(payload["hard_red_lines"]["masked_source_resurrection_count"], 0)
        self.assertGreater(payload["metrics"]["route_precision_at_1"]["rate"], 0.8)
        self.assertNotIn("aggregate_score", payload)


if __name__ == "__main__":
    unittest.main()
