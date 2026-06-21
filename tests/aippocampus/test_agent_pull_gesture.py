from __future__ import annotations

import json
import unittest

from aippocampus_runtime.recall import agent_pull_gesture as gesture


class AgentPullGestureTests(unittest.TestCase):
    def test_default_gesture_covers_copyable_agent_human_and_hook_paths(self) -> None:
        report = gesture.build_agent_pull_gesture_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["gesture_name"], "source_backed_continuity_gesture_v1")
        self.assertIn("recall(query, context)", report["reference_workflow"][1])
        self.assertEqual(
            set(report["surface_coverage"]),
            {"human_cli", "agent_native_facade", "hook_plus_pull"},
        )

        magic = by_id["fresh_thread_magic_moment"]
        self.assertTrue(magic["should_pull"])
        self.assertEqual(magic["surface"], "agent_native_facade")
        self.assertEqual(magic["memory_packet"]["output_mode"], "bounded_summary_as_route")
        self.assertLessEqual(
            magic["foreground_packet_bytes"],
            report["foreground_packet_budget_bytes"],
        )

    def test_low_risk_hint_and_aippo_activation_do_not_require_full_source_dump(self) -> None:
        report = gesture.build_agent_pull_gesture_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        low_risk = by_id["low_risk_style_hint"]
        aippo = by_id["project_aippo_activation"]

        self.assertEqual(low_risk["next_safe_action"], "use_hint")
        self.assertEqual(low_risk["memory_packet"]["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(low_risk["bounded_summary_sufficient"])

        self.assertTrue(aippo["aippo_activation_attempted"])
        self.assertTrue(aippo["aippo_activation_succeeded"])
        self.assertEqual(aippo["memory_packet"]["output_mode"], "bounded_summary_as_route")
        self.assertNotIn("source_handles", json.dumps(aippo["memory_packet"], sort_keys=True))
        self.assertEqual(report["metrics"]["bounded_summary_sufficient_count"], 2)
        self.assertEqual(report["metrics"]["aippo_activation_success_rate"], 1.0)

    def test_source_backed_claims_must_deepen_before_use(self) -> None:
        report = gesture.build_agent_pull_gesture_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        claim = by_id["public_claim_requires_deepen"]

        self.assertTrue(claim["should_pull"])
        self.assertTrue(claim["deepen_required"])
        self.assertTrue(claim["deepen_followed"])
        self.assertEqual(claim["next_safe_action"], "reopen_source")
        self.assertEqual(claim["deepen_result"]["status"], "source_route")
        self.assertEqual(report["metrics"]["deepen_required_follow_through_rate"], 1.0)
        self.assertEqual(report["red_lines"]["source_backed_claim_without_reopen"], 0)

    def test_negative_and_anti_nag_controls_prevent_memory_fishing(self) -> None:
        report = gesture.build_agent_pull_gesture_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        negative = by_id["negative_small_talk_no_pull"]
        repeated = by_id["anti_nag_repeated_pull_suppressed"]

        self.assertFalse(negative["should_pull"])
        self.assertEqual(negative["next_safe_action"], "stay_silent")
        self.assertIsNone(negative["memory_packet"])

        self.assertFalse(repeated["should_pull"])
        self.assertIn("anti_nag_recent_pull", repeated["reason_codes"])
        self.assertEqual(report["metrics"]["unnecessary_pull_count"], 0)
        self.assertEqual(report["metrics"]["wrong_route_drag_count"], 0)
        self.assertEqual(report["red_lines"]["constant_memory_fishing_count"], 0)

    def test_public_fixture_output_is_compact_and_redacted(self) -> None:
        report = gesture.build_agent_pull_gesture_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertLessEqual(
            report["metrics"]["foreground_packet_max_bytes"],
            report["foreground_packet_budget_bytes"],
        )
        self.assertEqual(report["metrics"]["manual_query_invention_count"], 0)
        self.assertFalse(report["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["raw_private_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["local_paths_emitted"])
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)

if __name__ == "__main__":
    unittest.main()
