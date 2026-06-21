from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]

promotion = import_benchmark_module("benchmark_family_promotion_candidates")

class BenchmarkFamilyPromotionCandidateTests(unittest.TestCase):
    def test_decision_report_distinguishes_promoted_attention_from_remaining_candidates(
        self,
    ) -> None:
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
        self.assertTrue(promoted["public_cohort_completed"]["explicit_agent_recall_auto_gate_ok"])
        deferred = {item["family_id"]: item["reason"] for item in report["deferred_families"]}
        self.assertIn("e2e50_silent_constraint", deferred)
        self.assertIn("#279", deferred["e2e50_silent_constraint"])
        self.assertIn("rollout_hard_event", deferred)
        self.assertTrue(report["public_quality_gate_ok"])
        self.assertTrue(report["quality_gate_ok"])
        metrics = report["metrics"]
        self.assertEqual(
            metrics["case_count_scope"],
            "selected_and_promoted_public_quality_family_surfaces",
        )
        self.assertEqual(metrics["evaluated_public_quality_family_count"], 3)
        self.assertEqual(metrics["selected_public_cohort_case_count"], 450)
        self.assertEqual(metrics["selected_holdout_case_count"], 113)
        self.assertEqual(
            metrics["public_quality_gate_rate"],
            {
                "numerator": 3,
                "denominator": 3,
                "rate": 1.0,
                "unit": "evaluated_public_quality_family",
            },
        )
        self.assertEqual(
            metrics["selected_usefulness_blocker_zero_rate"],
            {
                "numerator": 10,
                "denominator": 10,
                "rate": 1.0,
                "unit": "required_usefulness_control_observation",
            },
        )

    def test_remaining_candidates_have_maturity_metadata_without_quality_promotion(self) -> None:
        report = promotion.build_family_promotion_candidate_report()

        for family in report["selected_families"]:
            with self.subTest(family=family["family_id"]):
                current = family["current_contract_maturity"]
                candidate = family["public_cohort_candidate"]
                measurement = family["public_cohort_measurement"]
                gates = family["gate_status"]

                self.assertEqual(current["benchmark_maturity_level"], "contract_smoke")
                self.assertTrue(current["contract_gate_ok"])
                self.assertFalse(current["quality_gate_ok"])
                self.assertEqual(
                    candidate["benchmark_maturity_level"],
                    "public_cohort_candidate",
                )
                self.assertEqual(
                    candidate["metadata_interpretation"],
                    "target_design_superseded_by_observed_public_cohort_measurement",
                )
                self.assertGreaterEqual(candidate["minimum_family_case_floor"], 30)
                self.assertTrue(candidate["sample_floor_met"])
                self.assertGreater(candidate["holdout_case_count"], 0)
                self.assertEqual(candidate["holdout_used_for_tuning_count"], 0)
                self.assertTrue(candidate["wilson_or_uncertainty_reported"])
                self.assertTrue(candidate["contract_gate_ok"])
                self.assertTrue(candidate["usefulness_gate_ok"])
                self.assertTrue(candidate["quality_gate_ok"])
                self.assertFalse(candidate["holdout_not_run"])
                self.assertEqual(candidate["quality_gate_blockers"], [])
                self.assertEqual(
                    measurement["observed_result_interpretation"],
                    "observed_score_not_target_metadata",
                )
                self.assertGreater(measurement["public_cohort_case_count"], 0)
                self.assertGreater(measurement["holdout_case_count"], 0)
                self.assertEqual(measurement["holdout_used_for_tuning_count"], 0)
                self.assertTrue(measurement["usefulness_gate_ok"])
                self.assertTrue(measurement["attention_cost_ok"])
                self.assertTrue(measurement["quality_gate_ok"])
                self.assertTrue(gates["contract_gate_ok"])
                self.assertTrue(gates["usefulness_gate_ok"])
                self.assertTrue(gates["quality_gate_ok"])

    def test_selected_unmeasured_families_emit_measurement_actions(self) -> None:
        report = promotion.build_family_promotion_candidate_report()
        completed = {action["family_id"]: action for action in report["completed_measurements"]}

        self.assertEqual(set(completed), {"agent_continuity_loop", "map_rot_lifecycle_debt"})
        self.assertEqual(report["next_measurement_actions"], [])
        agent_action = completed["agent_continuity_loop"]
        self.assertIn("--public-cohort", agent_action["command"])
        self.assertEqual(agent_action["historical_owner_issue"], "#1969")
        self.assertEqual(agent_action["historical_owner_issue_state"], "closed_historical")
        self.assertEqual(agent_action["current_issue"], "#2396")
        self.assertTrue(
            agent_action["output_artifact"].startswith("docs/evidence/benchmarks/reports/")
        )
        self.assertGreaterEqual(agent_action["public_cohort_case_count"], 180)
        self.assertGreaterEqual(agent_action["holdout_case_count"], 45)

    def test_usefulness_negative_controls_are_required_before_promotion(self) -> None:
        report = promotion.build_family_promotion_candidate_report()
        required = set(promotion.REQUIRED_USEFULNESS_NEGATIVE_CONTROLS)

        for family in report["selected_families"]:
            with self.subTest(family=family["family_id"]):
                controls = {
                    control["control_id"] for control in family["usefulness_promotion_blockers"]
                }
                self.assertLessEqual(required, controls)
                for control in family["usefulness_promotion_blockers"]:
                    self.assertEqual(control["promotion_threshold"], 0)
                    self.assertEqual(control["observed_count"], 0)
                    self.assertEqual(control["observed_rate"], 0.0)
                    self.assertTrue(control["gate_ok"])
                    self.assertFalse(control["blocks_usefulness_gate"])

    def test_report_is_public_safe_and_separates_gate_names(self) -> None:
        report = promotion.build_family_promotion_candidate_report()

        self.assertEqual(
            report["gate_separation"],
            {
                "contract_gate_ok": "current deterministic contract still passes",
                "usefulness_gate_ok": "observed public/holdout cohort usefulness blockers must be zero",
                "public_quality_gate_ok": "true only for named public/holdout surfaces with sample floor and no tuning leak",
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
