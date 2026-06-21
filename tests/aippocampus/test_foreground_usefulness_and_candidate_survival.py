from __future__ import annotations

import json
import unittest

from aippocampus_runtime.ops import foreground_output_audit
from aippocampus_runtime.recall import candidate_survival, continuity_usefulness


class ContinuityUsefulnessAndCandidateSurvivalTests(unittest.TestCase):
    def test_canonical_usefulness_group_separates_safety_from_attention_cost(self) -> None:
        safety_clean_noisy = continuity_usefulness.continuity_usefulness_metrics(
            {
                "surface_id": "correct_but_noisy_packet",
                "red_line_counts": {
                    "privacy_leak_count": 0,
                    "unsupported_claim_count": 0,
                    "stale_as_current_count": 0,
                },
                "manual_query_invention_count": 0,
                "blind_deepen_required_count": 2,
                "packet_triage_distinctiveness": 0.25,
                "wrong_route_drag_count": 0,
                "useful_packet_count": 1,
                "packet_count": 1,
                "foreground_protocol_noise_bytes": 900,
                "useful_guidance_bytes": 120,
                "time_to_first_useful_packet_ms_proxy": 400,
            }
        )
        natural = continuity_usefulness.continuity_usefulness_metrics(
            {
                "surface_id": "natural_continuity_packet",
                "manual_query_invention_count": 0,
                "blind_deepen_required_count": 0,
                "packet_triage_distinctiveness": 0.82,
                "wrong_route_drag_count": 0,
                "useful_packet_count": 2,
                "packet_count": 2,
                "foreground_protocol_noise_bytes": 80,
                "useful_guidance_bytes": 520,
                "time_to_first_useful_packet_ms_proxy": 120,
            }
        )

        self.assertTrue(safety_clean_noisy["safety_gate_ok"])
        self.assertFalse(safety_clean_noisy["usefulness_gate_ok"])
        self.assertFalse(safety_clean_noisy["attention_cost_ok"])
        self.assertEqual(safety_clean_noisy["quality_gate_ok"], False)
        self.assertGreater(safety_clean_noisy["foreground_protocol_noise_ratio"], 0.8)
        self.assertIn("blind_deepen_required", safety_clean_noisy["usefulness_blockers"])

        self.assertTrue(natural["safety_gate_ok"])
        self.assertTrue(natural["usefulness_gate_ok"])
        self.assertTrue(natural["attention_cost_ok"])
        self.assertTrue(natural["quality_gate_ok"])
        self.assertGreater(natural["attention_saved_vs_spent_proxy"], 0)

    def test_action_permission_ladder_blocks_safe_route_demoted_to_scent(self) -> None:
        overconservative = continuity_usefulness.continuity_usefulness_metrics(
            {
                "surface_id": "safe_route_demoted_to_scent",
                "action_permission_level": "scent",
                "safe_route_evidence_present_count": 1,
                "manual_query_invention_count": 1,
                "blind_deepen_required_count": 1,
                "packet_triage_distinctiveness": 0.82,
                "wrong_route_drag_count": 0,
                "useful_packet_count": 1,
                "packet_count": 1,
                "foreground_protocol_noise_bytes": 60,
                "useful_guidance_bytes": 460,
                "fresh_agent_active_pull_success_count": 1,
                "fresh_agent_broad_search_before_recall_count": 1,
                "deepen_handle_misuse_count": 1,
                "copy_pasteable_deepen_target_present_count": 0,
                "recall_to_source_reopen_success_count": 0,
                "recall_to_source_reopen_attempt_count": 1,
            }
        )
        natural = continuity_usefulness.continuity_usefulness_metrics(
            {
                "surface_id": "natural_actionable_route",
                "action_permission_level": "actionable_route",
                "safe_route_evidence_present_count": 2,
                "manual_query_invention_count": 0,
                "blind_deepen_required_count": 0,
                "packet_triage_distinctiveness": 0.86,
                "wrong_route_drag_count": 0,
                "useful_packet_count": 2,
                "packet_count": 2,
                "foreground_protocol_noise_bytes": 70,
                "useful_guidance_bytes": 540,
                "fresh_agent_active_pull_success_count": 2,
                "fresh_agent_broad_search_before_recall_count": 0,
                "deepen_handle_misuse_count": 0,
                "copy_pasteable_deepen_target_present_count": 2,
                "recall_to_source_reopen_success_count": 2,
                "recall_to_source_reopen_attempt_count": 2,
            }
        )

        self.assertEqual(overconservative["action_permission_level"], "scent")
        self.assertEqual(overconservative["minimum_useful_action_permission_level"], "actionable_route")
        self.assertEqual(overconservative["usefulness_lost_by_demoting_to_scent_count"], 1)
        self.assertEqual(overconservative["main_agent_extra_work_count"], 4)
        self.assertEqual(overconservative["copy_pasteable_deepen_target_present_count"], 0)
        self.assertEqual(overconservative["recall_to_source_reopen_success_rate"], 0.0)
        self.assertIn("safe_route_demoted_to_scent", overconservative["usefulness_blockers"])
        self.assertIn("deepen_handle_misuse", overconservative["usefulness_blockers"])
        self.assertIn(
            "copy_pasteable_deepen_target_missing",
            overconservative["usefulness_blockers"],
        )
        self.assertFalse(overconservative["usefulness_gate_ok"])
        self.assertFalse(overconservative["quality_gate_ok"])

        self.assertEqual(natural["action_permission_level"], "actionable_route")
        self.assertEqual(natural["minimum_useful_action_permission_level"], "actionable_route")
        self.assertEqual(natural["usefulness_lost_by_demoting_to_scent_count"], 0)
        self.assertEqual(natural["main_agent_extra_work_count"], 0)
        self.assertEqual(natural["recall_to_source_reopen_success_rate"], 1.0)
        self.assertTrue(natural["usefulness_gate_ok"])
        self.assertTrue(natural["quality_gate_ok"])

    def test_foreground_output_audit_matrix_covers_overreach_and_overfiltering(self) -> None:
        report = foreground_output_audit.build_foreground_output_audit_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        matrix = {row["surface_kind"]: row for row in report["audit_matrix"]}
        by_case = {case["case_id"]: case for case in report["fixture_cases"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(
            set(matrix),
            {"hook", "active_recall", "aippo", "router", "bounded_summary", "macro"},
        )
        self.assertEqual(by_case["overreaching_packet"]["agency_gate_ok"], False)
        self.assertEqual(by_case["overfiltered_packet"]["usefulness_gate_ok"], False)
        self.assertEqual(by_case["healthy_navigation_packet"]["agency_gate_ok"], True)
        self.assertEqual(by_case["healthy_navigation_packet"]["usefulness_gate_ok"], True)
        self.assertEqual(report["metrics"]["authority_overreach_count"], 1)
        self.assertEqual(report["metrics"]["creativity_suppression_count"], 1)
        self.assertEqual(report["metrics"]["agency_preserving_packet_count"], 1)
        self.assertEqual(report["red_lines"]["decision_language_in_navigation_packet_count"], 0)
        self.assertNotIn("PRIVATE_FOREGROUND_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_candidate_survival_reports_false_negatives_separately_from_safety(self) -> None:
        report = candidate_survival.build_candidate_survival_fixture_report()
        by_case = {case["case_id"]: case for case in report["cases"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["safety_gate_ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertFalse(report["usefulness_gate_ok"])
        self.assertEqual(report["metrics"]["candidate_dropped_later_useful_count"], 1)
        self.assertEqual(report["metrics"]["candidate_parked_later_useful_count"], 1)
        self.assertEqual(report["metrics"]["direction_only_false_positive_count"], 1)
        self.assertEqual(report["metrics"]["direction_only_false_negative_count"], 1)
        self.assertEqual(report["metrics"]["silent_nudge_drift_count"], 1)
        self.assertEqual(report["metrics"]["useful_candidate_suppressed_count"], 2)
        self.assertEqual(report["metrics"]["emergent_bridge_preserved_count"], 1)
        self.assertGreater(report["metrics"]["overconservative_filter_stack_score"], 0)

        preserved = by_case["weak_source_emergence_preserved"]
        self.assertEqual(preserved["foreground_projection"], "navigation_only")
        self.assertFalse(preserved["fact_claim_allowed"])
        self.assertEqual(preserved["action_grammar"], "direction_only")

        starved = by_case["correct_but_creatively_starved"]
        self.assertTrue(starved["safety_gate_ok"])
        self.assertFalse(starved["usefulness_gate_ok"])
        self.assertNotIn("PRIVATE_CANDIDATE_SENTINEL", encoded)

if __name__ == "__main__":
    unittest.main()
