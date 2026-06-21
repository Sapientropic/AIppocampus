from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke" / "smoke_recall_navigation_promotion.py"

from aippocampus_runtime.ops import recall_navigation_promotion


class RecallNavigationPromotionTests(unittest.TestCase):
    def test_promotion_harness_preregisters_same_budget_ab_arms(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        prereg = report["preregistration"]

        self.assertEqual(report["kind"], "aippocampus_recall_navigation_promotion_harness")
        self.assertEqual(
            list(prereg["arms"]),
            ["baseline_flat_recall", "feature_navigation_only", "feature_plus_deepen"],
        )
        self.assertTrue(prereg["same_source_corpus"])
        self.assertTrue(prereg["same_query_set"])
        self.assertTrue(prereg["single_variable_feature_delta"])
        self.assertEqual(prereg["packet_budget_per_arm"], 5)
        self.assertEqual(prereg["deepen_budget_per_arm"], 5)
        self.assertIn("macro_navigation", report["feature_slots"])
        self.assertIn("attention_router", report["feature_slots"])
        self.assertEqual(report["active_promotion_owner_issue"], "#2559")
        self.assertEqual(
            report["feature_slots"]["attention_router"]["promotion_issue"],
            "#2559",
        )
        self.assertEqual(
            report["feature_slots"]["attention_router"]["historical_promotion_issues"],
            ["#1301"],
        )
        self.assertEqual(
            report["feature_slots"]["macro_navigation"]["historical_promotion_issues"],
            ["#1300"],
        )
        self.assertEqual(
            report["feature_slots"]["attention_router"]["comparison_arm"],
            "attention_router_navigation_only",
        )

    def test_promotion_harness_blocks_default_until_usefulness_and_red_lines_pass(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        metrics = report["promotion_metrics"]
        coverage = report["fixture_coverage"]

        self.assertFalse(report["promotion_gate_ok"])
        self.assertFalse(report["default_adoption_allowed"])
        self.assertEqual(report["promotion_decision"], "not_promoted")
        self.assertGreaterEqual(metrics["feature_hurt_case_count"], 1)
        self.assertGreaterEqual(metrics["feature_noop_case_count"], 1)
        self.assertGreaterEqual(metrics["manual_search_fallback_count"], 1)
        self.assertGreaterEqual(metrics["correct_but_useless_warning_count"], 1)
        self.assertEqual(metrics["privacy_bypass_count"], 0)
        self.assertEqual(metrics["masked_source_resurrection_count"], 0)
        self.assertEqual(metrics["claim_without_source_reopen_count"], 0)
        self.assertNotIn("feature_noop_cases_present", report["promotion_blockers"])
        self.assertGreaterEqual(report["neutral_noop"]["case_count"], 1)
        self.assertIn("exact_query_noop_control", report["neutral_noop"]["case_ids"])
        self.assertTrue(
            {"stale", "conflict", "noise", "wrong_source"}.issubset(
                set(coverage["distractor_families_present"])
            )
        )
        self.assertIn("usefulness_gate_not_satisfied", report["promotion_blockers"])
        self.assertEqual(
            report["blocker_owner_issue_map"]["fixture_only_not_live_default_path"],
            "#2559",
        )

    def test_arm_rows_expose_attention_cost_and_wrong_route_metrics(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        case = report["cases_by_id"]["wrong_source_distractor"]

        for arm in report["preregistration"]["arms"]:
            row = case["arms"][arm]
            self.assertIn("manual_search_fallback_count", row)
            self.assertIn("wrong_source_route_count", row)
            self.assertIn("foreground_packet_bytes", row)
            self.assertIn("correct_but_useless_warning_count", row)

        nav_only = case["arms"]["feature_navigation_only"]
        plus_deepen = case["arms"]["feature_plus_deepen"]
        self.assertGreater(nav_only["wrong_source_route_count"], 0)
        self.assertEqual(plus_deepen["wrong_source_route_count"], 0)
        self.assertTrue(plus_deepen["source_reopen_follow_through"])

    def test_attention_navigation_only_arm_is_measured_but_not_promoted(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        case = report["cases_by_id"]["ar_little_hippocampus_light_continuity_cue"]
        nav_only = case["arms"]["feature_navigation_only"]

        self.assertTrue(report["attention_router_readout"]["measured"])
        self.assertEqual(
            report["attention_router_readout"]["comparison_arm"],
            "attention_router_navigation_only",
        )
        self.assertTrue(nav_only["route_actionable"])
        self.assertFalse(nav_only["source_backed_success"])
        self.assertFalse(nav_only["source_reopen_attempted"])
        self.assertEqual(nav_only["selected_next_tool"], "recall_deepen")
        self.assertEqual(nav_only["claim_without_source_reopen_count"], 0)
        self.assertFalse(nav_only["route_family_selected_before_manual_search"])
        self.assertEqual(nav_only["route_label_specificity_floor"], 0.0)
        self.assertFalse(nav_only["route_label_expected_family_match"])
        self.assertEqual(nav_only["attention_router_applied_but_no_help_count"], 1)
        self.assertIn("attention_router_no_help_cases_present", report["promotion_blockers"])
        self.assertIn(
            "attention_router_specificity_gate_not_satisfied",
            report["promotion_blockers"],
        )
        self.assertIn("fixture_only_not_live_default_path", report["promotion_blockers"])

    def test_attention_router_no_help_fixture_blocks_default_promotion(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        metrics = report["promotion_metrics"]
        case = report["cases_by_id"]["attention_router_generic_top_no_help"]
        nav_only = case["arms"]["feature_navigation_only"]

        self.assertEqual(case["case_family"], "attention_router_no_help")
        self.assertGreaterEqual(metrics["attention_router_applied_but_no_help_count"], 1)
        self.assertGreaterEqual(metrics["zero_overlap_without_bridge_reason_count"], 1)
        self.assertGreaterEqual(metrics["route_label_specificity_below_floor_count"], 1)
        self.assertEqual(nav_only["selected_query_term_overlap_count"], 0)
        self.assertFalse(nav_only["explicit_bridge_reason_present"])
        self.assertTrue(nav_only["zero_overlap_without_bridge_reason"])
        self.assertFalse(nav_only["selected_why_may_matter_specific_enough"])
        self.assertIn(
            "attention_router_bridge_reason_gate_not_satisfied",
            report["promotion_blockers"],
        )

    def test_attention_router_explicit_auto_gate_can_pass_with_public_cohort(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        gate = report["attention_router_explicit_auto_gate"]

        self.assertTrue(gate["gate_ok"])
        self.assertTrue(gate["public_quality_gate_ok"])
        self.assertTrue(gate["default_adoption_gate_ok"])
        self.assertEqual(gate["surface"], "explicit_agent_recall")
        self.assertNotIn("fixture_only_not_live_default_path", gate["blockers"])
        self.assertIn("neutral_noop_case_count", gate["metrics"])

    def test_true_attention_router_no_help_case_remains_visible_as_negative_control(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        case = report["cases_by_id"]["attention_router_generic_top_no_help"]
        gate = report["attention_router_explicit_auto_gate"]

        self.assertEqual(case["case_family"], "attention_router_no_help")
        self.assertGreaterEqual(report["promotion_metrics"]["attention_router_applied_but_no_help_count"], 1)
        self.assertIn("attention_router_generic_top_no_help", report["negative_controls"]["case_ids"])
        self.assertNotIn("attention_router_no_help_cases_present", gate["blockers"])

    def test_macro_navigation_readout_measures_default_prior_candidate(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        readout = report["macro_navigation_readout"]
        case = report["cases_by_id"]["macro_active_layer_and_fanout_prior"]
        nav_only = case["arms"]["feature_navigation_only"]
        plus_deepen = case["arms"]["feature_plus_deepen"]

        self.assertTrue(readout["measured"])
        self.assertEqual(readout["promotion_issue"], "#2559")
        self.assertEqual(readout["historical_promotion_issues"], ["#1300"])
        self.assertEqual(readout["status"], "fixture_candidate_not_promoted")
        self.assertEqual(readout["active_layer_order_delta_count"], 1)
        self.assertEqual(readout["hamming_fanout_delta_count"], 1)
        self.assertEqual(readout["momentum_recheck_diagnostic_count"], 1)
        self.assertEqual(readout["stale_as_current_count"], 0)
        self.assertEqual(readout["claim_without_source_reopen_count"], 0)
        self.assertGreaterEqual(readout["manual_search_fallback_reduction_count"], 1)
        self.assertTrue(nav_only["macro_prior_applied"])
        self.assertTrue(nav_only["macro_active_layer_order_changed"])
        self.assertTrue(nav_only["macro_hamming_fanout_delta"])
        self.assertTrue(nav_only["macro_momentum_recheck_diagnostic"])
        self.assertFalse(nav_only["source_backed_success"])
        self.assertTrue(plus_deepen["source_reopen_follow_through"])
        self.assertEqual(nav_only["selected_route_family"], "issue")
        self.assertIn("fixture_only_not_live_default_path", report["promotion_blockers"])

    def test_cli_smoke_emits_promotion_json(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SMOKE), "--json"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_recall_navigation_promotion_harness")
        self.assertFalse(payload["default_adoption_allowed"])
        self.assertEqual(payload["active_promotion_owner_issue"], "#2559")
        self.assertEqual(
            payload["macro_navigation_readout"]["promotion_issue"],
            "#2559",
        )
        self.assertEqual(
            payload["macro_navigation_readout"]["historical_promotion_issues"],
            ["#1300"],
        )
        self.assertEqual(
            payload["historical_promotion_issues"]["attention_router"],
            ["#1301"],
        )
        self.assertEqual(
            payload["blocker_owner_issue_map"]["fixture_only_not_live_default_path"],
            "#2559",
        )
        self.assertNotIn("cases", payload)
        self.assertNotIn("cases_by_id", payload)

if __name__ == "__main__":
    unittest.main()
