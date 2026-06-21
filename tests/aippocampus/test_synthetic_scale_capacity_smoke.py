from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_smoke_module

REPO_ROOT = Path(__file__).resolve().parents[2]

scale_smoke = import_smoke_module("smoke_synthetic_scale_capacity")

class SyntheticScaleCapacitySmokeTests(unittest.TestCase):
    def test_default_smoke_models_gb_scale_without_private_artifacts(self) -> None:
        payload = scale_smoke.build_synthetic_scale_capacity_smoke()
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_synthetic_scale_capacity_smoke")
        self.assertEqual(payload["metrics"]["canonical_clean_source_human"], "4.0 GB")
        self.assertGreater(payload["metrics"]["segment_count"], 1)
        self.assertIn("clean_source_gb_scale", payload["warnings"])
        self.assertIn("query_fanout", payload["warnings"])
        self.assertFalse(payload["privacy_boundary"]["reads_private_registry"])
        self.assertFalse(payload["privacy_boundary"]["creates_large_files"])
        self.assertNotIn(str(REPO_ROOT), rendered)
        self.assertIn("real_gb_registry_runtime", payload["cannot_claim"])

    def test_generated_index_amplification_can_be_a_blocker(self) -> None:
        payload = scale_smoke.build_synthetic_scale_capacity_smoke(
            generated_index_ratio=4.0,
            generated_index_warning_ratio=1.0,
            generated_index_blocker_ratio=3.0,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("generated_index_amplification", payload["blockers"])
        self.assertEqual(
            payload["thresholds"]["generated_index_amplification"]["state"], "blocker"
        )

    def test_small_slice_can_pass_without_warnings(self) -> None:
        payload = scale_smoke.build_synthetic_scale_capacity_smoke(
            clean_source_gib=0.1,
            thread_count=2,
            generated_index_ratio=0.2,
            segment_size_mib=128,
            sync_policy_ratio=0.1,
            fanout_budget=16,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "simulated")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["blockers"], [])

if __name__ == "__main__":
    unittest.main()
