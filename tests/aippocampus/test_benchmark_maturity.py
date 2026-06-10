from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    sys.path.insert(0, str(_path))

import benchmark_agent_continuity_loop as agent_loop  # noqa: E402
import benchmark_attention_navigation_quality as attention  # noqa: E402
import benchmark_map_rot_lifecycle_debt as map_rot  # noqa: E402
import benchmark_maturity as maturity  # noqa: E402


class BenchmarkMaturityTests(unittest.TestCase):
    def test_small_contract_smoke_does_not_become_quality_gate(self) -> None:
        report = maturity.build_benchmark_maturity_report(
            benchmark_maturity_level="contract_smoke",
            case_count=12,
            passed_case_count=12,
            per_family_case_counts={
                "positive_route": 4,
                "hard_mask": 2,
                "stale_currentness": 2,
                "anti_nag": 1,
            },
            minimum_family_case_floor=30,
            external_or_public_cohort_case_count=0,
            holdout_case_count=0,
            holdout_used_for_tuning_count=0,
            contract_gate_ok=True,
            next_promotion_target="public_cohort_candidate",
        )

        self.assertTrue(report["contract_gate_ok"])
        self.assertFalse(report["quality_gate_ok"])
        self.assertFalse(report["sample_floor_met"])
        self.assertTrue(report["cannot_claim_due_to_sample_size"])
        self.assertTrue(report["wilson_or_uncertainty_reported"])
        self.assertEqual(report["failure_family_count"], 4)
        self.assertIn("sample_floor_not_met", report["quality_gate_blockers"])
        self.assertIn("holdout_missing", report["quality_gate_blockers"])
        self.assertIn("representative_public_quality", report["cannot_claim"])

    def test_public_cohort_requires_holdout_and_no_tuning_leakage(self) -> None:
        leaked = maturity.build_benchmark_maturity_report(
            benchmark_maturity_level="public_cohort",
            case_count=120,
            passed_case_count=118,
            per_family_case_counts={"positive": 60, "negative": 60},
            minimum_family_case_floor=30,
            external_or_public_cohort_case_count=120,
            holdout_case_count=20,
            holdout_used_for_tuning_count=1,
            contract_gate_ok=True,
            next_promotion_target="holdout_quality",
        )

        self.assertTrue(leaked["sample_floor_met"])
        self.assertFalse(leaked["quality_gate_ok"])
        self.assertIn("holdout_used_for_tuning", leaked["quality_gate_blockers"])

    def test_small_existing_reports_declare_contract_smoke_maturity(self) -> None:
        reports = [
            attention.run_attention_navigation_quality(),
            map_rot.build_report(),
            agent_loop.run_agent_continuity_loop(),
        ]

        for report in reports:
            with self.subTest(kind=report["kind"]):
                meta = report["benchmark_maturity"]
                self.assertEqual(meta["benchmark_maturity_level"], "contract_smoke")
                self.assertTrue(meta["contract_gate_ok"])
                self.assertFalse(meta["quality_gate_ok"])
                self.assertFalse(meta["sample_floor_met"])
                self.assertTrue(meta["cannot_claim_due_to_sample_size"])
                self.assertEqual(report["contract_gate_ok"], report["ok"])
                self.assertFalse(report["quality_gate_ok"])
                self.assertEqual(
                    report["quality_gate"]["status"],
                    "contract_gate_passed_quality_gate_not_promoted",
                )
                self.assertIn("next_promotion_target", meta)


if __name__ == "__main__":
    unittest.main()
