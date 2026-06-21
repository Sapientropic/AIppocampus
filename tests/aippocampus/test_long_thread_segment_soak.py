from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_smoke_module

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = ROOT / "tools" / "aippocampus" / "smoke"

soak = import_smoke_module("smoke_long_thread_segment_soak")

class LongThreadSegmentSoakTests(unittest.TestCase):
    def test_soak_builds_real_segments_and_reports_quality_without_private_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = soak.run_long_thread_segment_soak(
                workspace=Path(tmp) / "workspace",
                turn_count=96,
                segment_max_messages=32,
                query_limit=4,
                fanout_budget=2,
                include_monolithic=True,
            )

        self.assertTrue(payload["ok"], json.dumps(payload, indent=2))
        self.assertEqual(payload["kind"], "aippocampus_long_thread_segment_soak")
        self.assertEqual(payload["status"], "passed")
        self.assertGreaterEqual(payload["capacity_metrics"]["segment_count"], 4)
        self.assertGreater(payload["capacity_metrics"]["rollout_bytes"], 0)
        self.assertGreater(payload["timing_ms"]["segment_build_wall"], 0)
        self.assertIn("full_fanout", payload["query_modes"])
        self.assertIn("budgeted_fanout", payload["query_modes"])
        self.assertIn("monolithic", payload["query_modes"])
        self.assertEqual(payload["quality_metrics"]["query_count"], 4)
        self.assertEqual(payload["quality_metrics"]["full_fanout_hit_rate"], 1.0)
        self.assertEqual(payload["quality_metrics"]["monolithic_hit_rate"], 1.0)
        self.assertEqual(payload["metrics"]["generated_soak_case_count"], 4)
        self.assertEqual(payload["metrics"]["long_thread_replay_case_count"], 0)
        self.assertEqual(payload["metrics"]["synthetic_policy_fixture_case_count"], 0)
        self.assertEqual(payload["metrics"]["monolithic_target_hit_rate"], 1.0)
        self.assertEqual(payload["metrics"]["full_fanout_target_hit_rate"], 1.0)
        self.assertGreaterEqual(payload["metrics"]["budgeted_fanout_target_hit_rate"], 0.25)
        self.assertEqual(payload["metrics"]["answer_support_after_source_reopen_rate"], 0.0)
        self.assertEqual(payload["metrics"]["raw_private_text_leak_count"], 0)
        self.assertEqual(payload["metrics"]["absolute_path_leak_count"], 0)
        self.assertGreaterEqual(payload["metrics"]["query_latency_p50_ms"], 0.0)
        self.assertGreaterEqual(
            payload["metrics"]["query_latency_p95_ms"],
            payload["metrics"]["query_latency_p50_ms"],
        )
        self.assertGreaterEqual(payload["quality_metrics"]["budgeted_fanout_hit_rate"], 0.25)
        self.assertGreaterEqual(payload["quality_metrics"]["full_vs_monolithic_agreement_rate"], 0.75)
        self.assertTrue(payload["quality_metrics"]["quality_gate_ok"])
        self.assertFalse(payload["privacy_boundary"]["reads_private_registry"])
        self.assertFalse(payload["privacy_boundary"]["emits_private_text"])
        self.assertFalse(payload["privacy_boundary"]["emits_absolute_paths"])
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(Path(tmp)), encoded)
        self.assertIn("public_safe_generated_rollout", payload["data_boundary"]["input_shape"])
        self.assertIn("real_file_fixture_not_gb_claim", payload["cannot_claim"])

    def test_budgeted_fanout_exposes_skipped_segments_instead_of_claiming_full_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = soak.run_long_thread_segment_soak(
                workspace=Path(tmp) / "workspace",
                turn_count=120,
                segment_max_messages=30,
                query_limit=5,
                fanout_budget=1,
                include_monolithic=False,
            )

        self.assertTrue(payload["ok"], json.dumps(payload, indent=2))
        self.assertGreater(payload["capacity_metrics"]["segment_count"], 4)
        budgeted = payload["query_modes"]["budgeted_fanout"]
        skipped = [row["fanout"]["skipped_segment_count"] for row in budgeted["queries"]]
        self.assertTrue(any(count > 0 for count in skipped))
        self.assertLess(
            payload["quality_metrics"]["budgeted_fanout_hit_rate"],
            payload["quality_metrics"]["full_fanout_hit_rate"],
        )
        self.assertIn("budgeted_fanout_is_not_full_quality_claim", payload["cannot_claim"])

if __name__ == "__main__":
    unittest.main()
