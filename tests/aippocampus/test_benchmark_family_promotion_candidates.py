from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_family_promotion_candidates as promotion  # noqa: E402


class BenchmarkFamilyPromotionCandidateTests(unittest.TestCase):
    def test_decision_report_distinguishes_promoted_attention_from_remaining_candidates(self) -> None:
        report = promotion.build_family_promotion_candidate_report()

        self.assertEqual(report["kind"], "aippocampus_benchmark_family_promotion_candidates")
        self.assertEqual(report["issue"], 1195)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            [family["family_id"] for family in report["selected_families"]],
            [
                "agent_continuity_loop",
                "map_rot_lifecycle_debt",
            ],
        )
        self.assertEqual(
            [family["family_id"] for family in report["promoted_families"]],
            ["attention_navigation_quality"],
        )
        promoted = report["promoted_families"][0]
        self.assertEqual(promoted["promotion_state"], "narrow_public_cohort_promoted")
        self.assertTrue(promoted["public_cohort_completed"]["public_quality_gate_ok"])
        self.assertTrue(
            promoted["public_cohort_completed"]["explicit_agent_recall_auto_gate_ok"]
        )
        deferred = {item["family_id"]: item["reason"] for item in report["deferred_families"]}
        self.assertIn("e2e50_silent_constraint", deferred)
        self.assertIn("#279", deferred["e2e50_silent_constraint"])
        self.assertIn("rollout_hard_event", deferred)

    def test_remaining_candidates_have_maturity_metadata_without_quality_promotion(self) -> None:
        report = promotion.build_family_promotion_candidate_report()

        for family in report["selected_families"]:
            with self.subTest(family=family["family_id"]):
                current = family["current_contract_maturity"]
                candidate = family["public_cohort_candidate"]
                gates = family["gate_status"]

                self.assertEqual(current["benchmark_maturity_level"], "contract_smoke")
                self.assertTrue(current["contract_gate_ok"])
                self.assertFalse(current["quality_gate_ok"])
                self.assertEqual(
                    candidate["benchmark_maturity_level"],
                    "public_cohort_candidate",
                )
                self.assertEqual(candidate["metadata_interpretation"], "target_not_observed_score")
                self.assertGreaterEqual(candidate["minimum_family_case_floor"], 30)
                self.assertTrue(candidate["sample_floor_met"])
                self.assertGreater(candidate["holdout_case_count"], 0)
                self.assertEqual(candidate["holdout_used_for_tuning_count"], 0)
                self.assertTrue(candidate["wilson_or_uncertainty_reported"])
                self.assertTrue(candidate["contract_gate_ok"])
                self.assertFalse(candidate["usefulness_gate_ok"])
                self.assertFalse(candidate["quality_gate_ok"])
                self.assertTrue(gates["contract_gate_ok"])
                self.assertFalse(gates["usefulness_gate_ok"])
                self.assertFalse(gates["quality_gate_ok"])
                self.assertIn(
                    "candidate_not_yet_measured",
                    candidate["quality_gate_blockers"],
                )

    def test_usefulness_negative_controls_are_required_before_promotion(self) -> None:
        report = promotion.build_family_promotion_candidate_report()
        required = set(promotion.REQUIRED_USEFULNESS_NEGATIVE_CONTROLS)

        for family in report["selected_families"]:
            with self.subTest(family=family["family_id"]):
                controls = {
                    control["control_id"]
                    for control in family["usefulness_promotion_blockers"]
                }
                self.assertLessEqual(required, controls)
                for control in family["usefulness_promotion_blockers"]:
                    self.assertEqual(control["promotion_threshold"], 0)
                    self.assertTrue(control["blocks_usefulness_gate"])

    def test_report_is_public_safe_and_separates_gate_names(self) -> None:
        report = promotion.build_family_promotion_candidate_report()

        self.assertEqual(
            report["gate_separation"],
            {
                "contract_gate_ok": "current deterministic contract still passes",
                "usefulness_gate_ok": "candidate cohort must prove user or agent usefulness blockers are zero",
                "public_quality_gate_ok": "true only for a named public/holdout surface, such as attention explicit-pull",
                "quality_gate_ok": "alias for the surface-specific public_quality_gate_ok",
            },
        )
        self.assertEqual(report["sanitization_check"]["status"], "passed")
        dumped = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(REPO_ROOT), dumped)
        self.assertNotIn(".aippocampus", dumped)
        self.assertNotIn("BEGIN", dumped)
        self.assertNotIn("api_key", dumped.lower())


if __name__ == "__main__":
    unittest.main()
