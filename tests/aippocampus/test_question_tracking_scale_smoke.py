from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    SMOKE,
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import smoke_question_tracking_scale as scale_smoke  # noqa: E402


class QuestionTrackingScaleSmokeTests(unittest.TestCase):
    def test_smoke_reports_quadratic_pair_cost_and_source_join_boundary(self) -> None:
        payload = scale_smoke.run_question_tracking_scale_smoke(
            candidate_count=12,
            group_count=3,
        )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_question_tracking_scale_smoke")
        self.assertTrue(payload["synthetic_only"])
        self.assertEqual(payload["all_pair_count"], 66)
        self.assertGreater(payload["baseline"]["accepted_pair_count"], 0)
        self.assertGreater(payload["sidecar"]["sidecar_pair_count"], 0)
        self.assertTrue(payload["sidecar"]["source_ref_join_survived"])
        self.assertTrue(payload["sidecar"]["source_ref_key_join_survived"])
        self.assertEqual(payload["sidecar"]["source_ref_key_mismatch_count"], 0)
        self.assertEqual(payload["sidecar"]["baseline_strong_pair_coverage"], 1.0)
        self.assertEqual(payload["sidecar"]["adoption"]["decision"], "not_needed_now")
        self.assertEqual(payload["sidecar"]["default_enablement"]["decision"], "not_needed_now")
        self.assertFalse(payload["sidecar"]["adoption"]["default_prefilter_recommended"])

    def test_smoke_is_private_data_safe_by_default(self) -> None:
        payload = scale_smoke.run_question_tracking_scale_smoke(
            candidate_count=8,
            group_count=2,
        )

        self.assertFalse(payload["privacy"]["reads_private_registry"])
        self.assertFalse(payload["privacy"]["writes_formal_jobs"])
        self.assertFalse(payload["privacy"]["raw_private_text_emitted"])
        self.assertIn("real_registry_runtime_performance", payload["cannot_claim"])
        self.assertIn("default_question_index_prefilter_is_safe", payload["cannot_claim"])

    def test_synthetic_large_smoke_is_not_default_adoption_evidence(self) -> None:
        payload = scale_smoke.run_question_tracking_scale_smoke(
            candidate_count=150,
            group_count=10,
        )

        self.assertTrue(payload["ok"], payload)
        self.assertGreaterEqual(
            payload["all_pair_count"],
            payload["sidecar"]["adoption"]["pair_threshold"],
        )
        self.assertEqual(
            payload["sidecar"]["adoption"]["decision"],
            "evaluation_only_not_default",
        )
        self.assertFalse(payload["sidecar"]["adoption"]["sidecar_needed_now"])
        self.assertFalse(payload["sidecar"]["adoption"]["default_prefilter_recommended"])
        self.assertFalse(payload["sidecar"]["adoption"]["safe_to_enable_by_default"])
        self.assertIn("synthetic_only_smoke", payload["sidecar"]["adoption"]["reason_codes"])
        self.assertIn(
            "repeat the sidecar evaluation on real-history or selected registry data",
            payload["sidecar"]["adoption"]["required_before_default"],
        )

    def test_smoke_surfaces_sidecar_coverage_gap(self) -> None:
        payload = scale_smoke.run_question_tracking_scale_smoke(
            candidate_count=8,
            group_count=2,
            max_pairs=0,
        )

        self.assertFalse(payload["ok"])
        self.assertIn("sidecar_candidate_coverage_gap", payload["warnings"])
        self.assertEqual(payload["sidecar"]["baseline_strong_pair_coverage"], 0.0)
        self.assertEqual(
            payload["sidecar"]["adoption"]["decision"],
            "blocked_candidate_coverage_gap",
        )


if __name__ == "__main__":
    unittest.main()
