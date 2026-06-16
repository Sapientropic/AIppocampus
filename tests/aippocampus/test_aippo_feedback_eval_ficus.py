from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.aippo import eval_environment, feedback, ficus  # noqa: E402
from aippocampus_runtime.aippo import working_contract as aippo  # noqa: E402


class AIppoFeedbackEvalFicusTests(unittest.TestCase):
    def test_feedback_loop_groups_findings_and_updates_lifecycle_without_source_mutation(self) -> None:
        contract = aippo.build_project_workflow_public_safe_contract()
        original_contract = copy.deepcopy(contract)

        report = feedback.build_aippo_feedback_fixture_report(contract)
        by_case = {case["case_id"]: case for case in report["fixture_cases"]}
        updated = {
            clause["clause_id"]: clause
            for clause in report["updated_contract"]["clauses"]
        }
        encoded_packet = json.dumps(report["foreground_activation_packet"], ensure_ascii=False)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["kind"], "aippocampus_aippo_feedback_reripening_report")
        self.assertEqual(by_case["manual_search_reduced_before_useful_continuity"]["agent_action"], "used")
        self.assertLess(by_case["manual_search_reduced_before_useful_continuity"]["manual_search_after_packet"], 1)
        self.assertEqual(updated["clause_issue_closeout_convention"]["lifecycle"]["status"], "challenged")
        self.assertEqual(updated["clause_benchmark_default_claim"]["lifecycle"]["degrade_to"], "reopenable_route")
        self.assertEqual(by_case["self_report_success_unverified"]["feedback_status"], "feedback_unverified")
        self.assertEqual(by_case["noisy_correct_guidance_suppressed"]["recommended_lifecycle_change"], "suppress_foreground")
        self.assertEqual(report["metrics"]["aippo_grouped_finding_count"], 2)
        self.assertEqual(report["metrics"]["aippo_eval_seed_count"], 1)
        self.assertEqual(report["red_lines"]["feedback_trace_mutated_clean_source_count"], 0)
        self.assertEqual(report["red_lines"]["self_report_promoted_to_truth_count"], 0)
        self.assertEqual(contract, original_contract)
        self.assertNotIn("feedback_traces", encoded_packet)
        self.assertLessEqual(report["metrics"]["foreground_packet_bytes"], report["foreground_packet_budget_bytes"])

    def test_eval_environment_has_frozen_scorer_sampler_and_comparison_report(self) -> None:
        report = eval_environment.build_aippo_eval_environment_fixture_report()
        env = report["environment"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(env["kind"], "aippo_eval_environment")
        self.assertEqual(env["need_class"], "benchmark_claim_boundary")
        self.assertEqual(env["admission"]["eval_environment_required"], "recommended")
        self.assertEqual(env["admission"]["cost_tier"], "deterministic_fixture_low")
        self.assertIn("public_claim_boundary_risk", env["admission"]["expected_value_reason_codes"])
        self.assertIn("manual_search_reduction_observed", env["admission"]["eval_candidate_reason"])
        self.assertTrue(report["cheap_no_eval_path"]["allowed"])
        self.assertEqual(report["cheap_no_eval_path"]["base_tier"], "seed_aippo")
        self.assertTrue(report["promotion_policy"]["expensive_multi_arm_runs_require_operator_opt_in"])
        self.assertIn("feedback_reripening_high_value_or_problematic_clause", report["promotion_policy"]["promotion_sources"])
        self.assertGreaterEqual(report["metrics"]["aippo_eval_instance_count"], 5)
        self.assertEqual(report["metrics"]["trivial_for_all_arms_reject_count"], 1)
        self.assertEqual(report["metrics"]["impossible_for_all_arms_reject_count"], 1)
        self.assertEqual(report["metrics"]["novelty_reject_count"], 1)
        self.assertEqual(report["metrics"]["mutable_scorer_during_run_count"], 0)
        self.assertGreater(report["comparison"]["manual_search_delta_vs_baseline"], 0)
        self.assertGreater(report["comparison"]["route_follow_success_delta_vs_baseline"], 0)
        self.assertLess(report["comparison"]["claim_boundary_error_delta_vs_baseline"], 0)
        self.assertIn("baseline_prompt", report["rendered_prompt_pairs"][0])
        self.assertIn("aippo_prompt", report["rendered_prompt_pairs"][0])
        self.assertTrue(report["contract"]["scorer_frozen_for_run"])
        self.assertTrue(report["contract"]["source_traces_used_not_mutated"])

    def test_ficus_mvp_masks_sensitive_impressions_and_activates_stable_workflow_guidance(self) -> None:
        report = ficus.build_ficus_fixture_report()
        by_case = {case["case_id"]: case for case in report["fixture_cases"]}
        packet = report["activation_packet"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["schema"]["kind"], "ficus_aippo_schema")
        self.assertIn("explicit_correction", report["schema"]["source_authority_classes"])
        self.assertIn("sensitive_personal_domain", report["schema"]["hard_mask_categories"])
        self.assertEqual(by_case["private_sensitive_impression_masked"]["foreground_visible"], False)
        self.assertEqual(by_case["dream_candidate_without_source_support"]["ripened"], False)
        self.assertEqual(by_case["stable_workflow_preference_activates"]["foreground_visible"], True)
        self.assertEqual(packet["kind"], "aippocampus_ficus_activation_packet")
        self.assertEqual(packet["claim_permission"], "working_contract_allowed_no_fact_claim")
        self.assertGreaterEqual(report["metrics"]["ficus_search_saved_proxy_count"], 1)
        self.assertEqual(report["metrics"]["ficus_repeated_search_observed_delta"], 0)
        self.assertTrue(report["usefulness_gate"]["fixture_contract_gate_ok"])
        self.assertFalse(report["usefulness_gate"]["search_saved_proxy_counts_as_observed_usefulness"])
        self.assertFalse(report["usefulness_gate"]["usefulness_gate_ok"])
        self.assertIn("observed_repeated_search_reduction", report["cannot_claim"])
        self.assertIn("PersonaMem", report["benchmark_readiness"]["next_benchmark_gate"])
        self.assertNotIn("PRIVATE_FICUS_SENTINEL", encoded)
        self.assertNotIn("source_refs", json.dumps(packet, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
