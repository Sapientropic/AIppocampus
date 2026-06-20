from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import loadbearing_fixture  # noqa: E402


class MacroTopologyLoadbearingTests(unittest.TestCase):
    def test_macro_topology_dogfood_report_separates_usefulness_from_safety(self) -> None:
        report = loadbearing_fixture.build_macro_topology_loadbearing_fixture_report()
        metrics = report["metrics"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(metrics["macro_state_derived_count"], 1)
        self.assertGreaterEqual(metrics["macro_state_degraded_count"], 1)
        self.assertGreaterEqual(metrics["macro_guidance_surface_count"], 1)
        self.assertGreaterEqual(metrics["topology_preflight_checked_count"], 1)
        self.assertGreaterEqual(metrics["borromean_repair_hint_count"], 1)
        self.assertGreaterEqual(metrics["route_cycle_redirect_count"], 1)
        self.assertGreaterEqual(metrics["missing_middle_review_count"], 1)
        self.assertGreaterEqual(metrics["weak_bridge_review_count"], 1)
        self.assertGreaterEqual(metrics["useful_route_change_count"], 2)
        self.assertGreaterEqual(metrics["macro_replay_case_count"], 4)
        self.assertGreaterEqual(metrics["topology_replay_case_count"], 6)
        self.assertGreaterEqual(metrics["fixture_replay_complete_count"], 1)
        self.assertEqual(metrics["real_producer_complete_count"], 0)
        self.assertFalse(metrics["runtime_line_signal_producer_present"])
        self.assertGreaterEqual(metrics["real_foreground_packet_path_count"], 1)
        self.assertEqual(metrics["false_positive_or_overfilter_count"], 0)
        self.assertEqual(metrics["authority_upgrade_violation_count"], 0)
        self.assertEqual(metrics["raw_private_text_leak_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])
        self.assertIn("macro_total_encoder", report["load_bearing_primitives"])
        self.assertIn("borromean_relation", report["load_bearing_primitives"])
        self.assertIn("weak_bridge", report["review_only_primitives"])
        self.assertIn("knot", report["research_only_primitives"])
        self.assertNotIn("PRIVATE_TOPOLOGY_TEXT", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_macro_routing_replay_excludes_fixture_only_controls(self) -> None:
        report = loadbearing_fixture.build_macro_routing_replay_report()
        metrics = report["metrics"]
        by_id = {row["case_id"]: row for row in report["cases"]}

        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(metrics["macro_replay_case_count"], 4)
        self.assertEqual(metrics["macro_fixture_only_case_count"], 1)
        self.assertEqual(metrics["fixture_replay_complete_count"], 1)
        self.assertEqual(metrics["fixture_replay_partial_count"], 1)
        self.assertEqual(metrics["real_producer_complete_count"], 0)
        self.assertEqual(metrics["real_producer_partial_count"], 0)
        self.assertFalse(metrics["runtime_line_signal_producer_present"])
        self.assertEqual(metrics["runtime_macro_state_write_count"], 0)
        self.assertGreaterEqual(metrics["macro_helpful_route_change_count"], 1)
        self.assertGreaterEqual(metrics["macro_helpful_deepen_or_recheck_change_count"], 1)
        self.assertGreaterEqual(metrics["macro_no_help_correctly_ignored_count"], 3)
        self.assertEqual(metrics["default_fixture_hexagram_rejected_count"], 1)
        self.assertEqual(metrics["false_positive_or_noise_count"], 0)
        self.assertEqual(metrics["authority_upgrade_violation_count"], 0)
        self.assertEqual(metrics["raw_private_text_leak_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])
        self.assertIn("runtime_line_signal_producer", report["cannot_claim"])
        self.assertTrue(report["boundary"]["fixture_replay_not_counted_as_runtime_producer"])

        self.assertEqual(by_id["derived_complete_helps"]["case_origin"], "public_replay")
        self.assertTrue(by_id["derived_complete_helps"]["route_changed"])
        self.assertTrue(by_id["derived_complete_helps"]["deepen_or_recheck_changed"])
        self.assertFalse(by_id["derived_partial_quiet"]["route_changed"])
        self.assertFalse(by_id["ambiguous_conflict_quiet"]["route_changed"])
        self.assertFalse(by_id["private_blocked_quiet"]["route_changed"])
        self.assertEqual(by_id["fixture_default_guard"]["case_origin"], "fixture_contract")
        self.assertTrue(by_id["fixture_default_guard"]["fixture_default_hexagram"])

    def test_topology_foreground_replay_measures_action_delta_not_just_diagnostics(self) -> None:
        report = loadbearing_fixture.build_topology_foreground_replay_report()
        metrics = report["metrics"]
        by_id = {row["case_id"]: row for row in report["cases"]}

        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(metrics["topology_replay_case_count"], 6)
        self.assertEqual(metrics["topology_fixture_only_case_count"], 0)
        self.assertGreaterEqual(metrics["real_foreground_packet_path_count"], 1)
        self.assertGreaterEqual(metrics["topology_helpful_action_change_count"], 4)
        self.assertGreaterEqual(metrics["topology_safety_catch_count"], 4)
        self.assertGreaterEqual(metrics["topology_no_help_correctly_ignored_count"], 1)
        self.assertEqual(metrics["healthy_packet_unchanged_count"], 1)
        self.assertEqual(metrics["agency_suppression_relief_count"], 1)
        self.assertEqual(metrics["annotation_or_vocabulary_blocked_count"], 1)
        self.assertEqual(metrics["false_positive_or_overfilter_count"], 0)
        self.assertEqual(metrics["foreground_noise_added_count"], 0)
        self.assertEqual(metrics["authority_upgrade_violation_count"], 0)
        self.assertEqual(metrics["raw_private_text_leak_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])

        self.assertEqual(by_id["borromean_missing_source"]["action_taken"], "needs_reopen")
        self.assertTrue(by_id["borromean_missing_source"]["useful_action_delta"])
        self.assertEqual(by_id["borromean_missing_user_need"]["action_taken"], "repair_hint_added")
        self.assertEqual(by_id["borromean_missing_agent_agency"]["action_taken"], "downgraded")
        self.assertEqual(by_id["route_cycle_redirect"]["action_taken"], "repair_hint_added")
        self.assertEqual(by_id["healthy_packet_unchanged"]["action_taken"], "allowed")
        self.assertFalse(by_id["healthy_packet_unchanged"]["foreground_noise_added"])
        self.assertFalse(by_id["annotation_vocabulary_guard"]["useful_action_delta"])
        self.assertTrue(by_id["annotation_vocabulary_guard"]["annotation_vocabulary_guard"])


if __name__ == "__main__":
    unittest.main()
