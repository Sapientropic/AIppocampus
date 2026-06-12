from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke" / "smoke_recall_navigation_promotion.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import recall_navigation_promotion  # noqa: E402


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
        self.assertTrue(
            {"stale", "conflict", "noise", "wrong_source"}.issubset(
                set(coverage["distractor_families_present"])
            )
        )
        self.assertIn("usefulness_gate_not_satisfied", report["promotion_blockers"])

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
        self.assertTrue(nav_only["route_family_selected_before_manual_search"])
        self.assertIn("fixture_only_not_live_default_path", report["promotion_blockers"])

    def test_macro_navigation_readout_measures_default_prior_candidate(self) -> None:
        report = recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        readout = report["macro_navigation_readout"]
        case = report["cases_by_id"]["macro_active_layer_and_fanout_prior"]
        nav_only = case["arms"]["feature_navigation_only"]
        plus_deepen = case["arms"]["feature_plus_deepen"]

        self.assertTrue(readout["measured"])
        self.assertEqual(readout["promotion_issue"], "#1300")
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
        self.assertNotIn("cases", payload)
        self.assertNotIn("cases_by_id", payload)


if __name__ == "__main__":
    unittest.main()
