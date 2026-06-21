from __future__ import annotations

import json
import unittest

from aippocampus_runtime.recall import hook_agent_affordance as affordance


class HookAgentAffordanceTests(unittest.TestCase):
    def test_fixture_report_covers_active_pull_path_without_context_delivery(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["schema_version"], "hook-agent-affordance-v0")
        self.assertEqual(report["metrics"]["usable_lead_emitted_count"], 2)
        self.assertEqual(report["metrics"]["agent_pull_suggested_count"], 2)
        self.assertEqual(report["metrics"]["agent_pull_follow_through_rate"], 1.0)
        self.assertEqual(report["metrics"]["hook_full_context_delivery_count"], 0)
        self.assertEqual(report["metrics"]["manual_search_fallback_count"], 0)
        self.assertEqual(report["metrics"]["manual_search_before_ai_pull_count"], 0)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertEqual(report["metrics"]["false_activation_count"], 0)
        self.assertEqual(report["metrics"]["read_current_repo_first_count"], 1)

        self.assertEqual(
            by_id["work_task_aippo_available"]["affordance"]["suggested_agent_action"],
            "agent_aippo",
        )
        self.assertEqual(
            by_id["vague_old_route_source_required"]["affordance"]["suggested_agent_action"],
            "agent_deepen",
        )
        self.assertEqual(
            by_id["current_code_question_no_pull"]["affordance"][
                "suggested_agent_action"
            ],
            "read_current_repo_first",
        )

    def test_agent_policy_follows_affordance_before_manual_search(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        by_id = {case["case_id"]: case for case in report["agent_policy_cases"]}

        aippo = by_id["hook_aippo_before_manual_search"]["agent_policy"]
        recall = by_id["hook_recall_before_broad_history_search"]["agent_policy"]
        deepen = by_id["hook_deepen_before_broad_history_search"]["agent_policy"]

        self.assertEqual(aippo["next_step"], "call_agent_aippo")
        self.assertEqual(aippo["tool"], "aippocampus agent aippo")
        self.assertTrue(aippo["agent_pull_before_manual_search"])
        self.assertTrue(aippo["aippo_first_activation"])
        self.assertFalse(aippo["manual_search_before_ai_pull"])

        self.assertEqual(recall["next_step"], "call_agent_recall")
        self.assertEqual(recall["tool"], "aippocampus agent recall")
        self.assertTrue(recall["broad_repo_history_search_suppressed"])

        self.assertEqual(deepen["next_step"], "call_agent_deepen")
        self.assertEqual(deepen["tool"], "aippocampus agent deepen")
        self.assertTrue(deepen["source_reopen_required_before_claim"])

        self.assertEqual(report["metrics"]["agent_pull_follow_through_rate"], 1.0)
        self.assertEqual(report["metrics"]["useful_continuity_ignored_count"], 0)
        self.assertGreaterEqual(report["metrics"]["aippo_first_activation_count"], 1)

    def test_format_includes_host_fallback_when_tool_visibility_unknown(self) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"candidate_type": "memory_route"}],
            }
        )
        text = affordance.format_hook_agent_affordance(packet)

        self.assertIsNotNone(text)
        self.assertEqual(packet["tool_visibility"], "unknown")
        self.assertIn("If AIppocampus tools are not visible", text or "")
        self.assertIn("discover/load AIppocampus tools", text or "")
        self.assertIn("then call agent_recall", text or "")
        self.assertIn('aippocampus agent recall "<short cue>" --json', text or "")
        self.assertIn("Tool discovery is not source evidence", text or "")
        self.assertIn("Use as route only", text or "")

    def test_format_omits_host_fallback_when_tool_visibility_is_visible(self) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"candidate_type": "memory_route"}],
                "tool_visibility": "visible",
            }
        )
        text = affordance.format_hook_agent_affordance(packet)

        self.assertEqual(packet["tool_visibility"], "visible")
        self.assertNotIn("If AIppocampus tools are not visible", text or "")
        self.assertNotIn("discover/load AIppocampus tools", text or "")
        self.assertNotIn("CLI fallback:", text or "")

    def test_format_distinguishes_cli_fallback_only_from_unknown_visibility(self) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"candidate_type": "memory_route"}],
                "tool_visibility": "cli_fallback_only",
            }
        )
        text = affordance.format_hook_agent_affordance(packet)

        self.assertEqual(packet["tool_visibility"], "cli_fallback_only")
        self.assertIn("CLI fallback:", text or "")
        self.assertIn('aippocampus agent recall "<short cue>" --json', text or "")
        self.assertIn("Tool fallback is route-only", text or "")
        self.assertNotIn("discover/load AIppocampus tools", text or "")

    def test_deepen_fallback_starts_with_recall_when_no_route_is_selected(self) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"candidate_type": "memory_route"}],
                "semantic_source_reopen_route": True,
                "tool_visibility": "unknown",
            }
        )
        text = affordance.format_hook_agent_affordance(packet)

        self.assertEqual(packet["suggested_agent_action"], "agent_deepen")
        self.assertIn("then call agent_deepen", text or "")
        self.assertIn('aippocampus agent recall "<short cue>" --json', text or "")
        self.assertIn("follow the emitted --recall-selector deepen action", text or "")
        self.assertNotIn("handle", text or "")

    def test_distinctive_ambient_tiny_affordance_emits_agent_recall_action_only(
        self,
    ) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "skip",
                "confidence": "medium",
                "ambient_recall": {
                    "tiny_agent_recall_affordance": {
                        "status": "host_replay_ready_action_only",
                        "suggested_agent_action": "agent_recall",
                        "cue_shape": "relationship continuity / old UX review",
                        "source_open_gates_passed": True,
                        "safety_blockers": [],
                        "not_evidence": True,
                    }
                },
            }
        )
        policy = affordance.agent_policy_decision_from_affordance(packet)
        text = affordance.format_hook_agent_affordance(packet)

        self.assertTrue(packet["usable_continuity_lead"])
        self.assertEqual(packet["suggested_agent_action"], "agent_recall")
        self.assertEqual(
            packet["suggested_query_seed"],
            "relationship continuity / old UX review",
        )
        self.assertIn("ambient_tiny_agent_recall", packet["lead_kinds"])
        self.assertIn("ambient_tiny_agent_recall_ready", packet["reason_codes"])
        self.assertTrue(packet["not_enough_for_claim"])
        self.assertEqual(policy["next_step"], "call_agent_recall")
        self.assertEqual(policy["claim_permission"], "navigation_only_not_fact")
        self.assertIn("Next: call agent_recall", text or "")
        self.assertNotIn("source_refs", text or "")

    def test_tiny_affordance_safety_blockers_keep_hook_quiet(self) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "skip",
                "confidence": "medium",
                "ambient_recall": {
                    "tiny_agent_recall_affordance": {
                        "status": "host_replay_ready_action_only",
                        "suggested_agent_action": "agent_recall",
                        "cue_shape": "stale route drag",
                        "source_open_gates_passed": True,
                        "safety_blockers": ["wrong_route_drag_present"],
                        "not_evidence": True,
                    }
                },
            }
        )

        self.assertFalse(packet["usable_continuity_lead"])
        self.assertEqual(packet["suggested_agent_action"], "stay_silent")
        self.assertEqual(affordance.format_hook_agent_affordance(packet), None)

    def test_low_risk_aippo_posture_and_strong_claim_boundaries_are_separate(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        by_id = {case["case_id"]: case for case in report["agent_policy_cases"]}

        aippo = by_id["aippo_working_contract_low_risk_posture"]["agent_policy"]
        public_claim = by_id["exact_public_claim_forces_deepen"]["agent_policy"]
        exact_claim = by_id["exact_claim_forces_deepen"]["agent_policy"]
        stale_claim = by_id["stale_claim_forces_deepen"]["agent_policy"]

        self.assertTrue(aippo["low_risk_working_contract_used_without_reopen"])
        self.assertEqual(
            aippo["claim_permission"],
            "low_risk_guidance_allowed_no_fact_claim",
        )
        self.assertFalse(aippo["source_reopen_required_before_claim"])

        self.assertTrue(public_claim["agent_pull_before_manual_search"])
        self.assertTrue(public_claim["source_reopen_required_before_claim"])
        self.assertEqual(public_claim["claim_permission"], "must_deepen_before_claim")
        self.assertTrue(exact_claim["source_reopen_required_before_claim"])
        self.assertEqual(exact_claim["claim_permission"], "must_deepen_before_claim")
        self.assertTrue(stale_claim["source_reopen_required_before_claim"])
        self.assertEqual(stale_claim["claim_permission"], "must_deepen_before_claim")
        self.assertEqual(report["metrics"]["strong_claim_without_deepen_count"], 0)

    def test_architecture_avatar_and_episode_diagnostics_are_agent_reachable_without_fact_authority(
        self,
    ) -> None:
        packet = affordance.build_hook_agent_affordance(
            {
                "decision": "scent",
                "confidence": "medium",
                "ambient_recall": {
                    "cards": [
                        {
                            "provenance_class": "avatar_state",
                            "action_grammar": "direction_only",
                        },
                        {
                            "provenance_class": "episode_arc_route",
                            "action_grammar": "direction_only",
                        },
                    ]
                },
                "architecture_diagnostics": [
                    {
                        "surface": "cognitive_observatory",
                        "authority": "navigation_only",
                    }
                ],
            }
        )
        policy = affordance.agent_policy_decision_from_affordance(packet)

        self.assertTrue(packet["usable_continuity_lead"])
        self.assertEqual(packet["suggested_agent_action"], "agent_recall")
        self.assertIn("avatar_posture", packet["lead_kinds"])
        self.assertIn("episode_arc", packet["lead_kinds"])
        self.assertIn("architecture_diagnostic", packet["lead_kinds"])
        self.assertIn("avatar_posture_available", packet["reason_codes"])
        self.assertIn("episode_arc_route_available", packet["reason_codes"])
        self.assertIn("architecture_diagnostic_available", packet["reason_codes"])
        self.assertTrue(packet["not_enough_for_claim"])
        self.assertEqual(policy["next_step"], "call_agent_recall")
        self.assertEqual(policy["claim_permission"], "navigation_only_not_fact")

    def test_fixture_report_is_public_safe_and_source_non_authoritative(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertFalse(report["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["local_paths_emitted"])
        self.assertFalse(report["privacy_boundary"]["source_refs_emitted"])
        self.assertEqual(report["privacy_boundary"]["forbidden_payload_marker_count"], 0)
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)
        for case in report["cases"]:
            packet = case["affordance"]
            self.assertTrue(packet["not_enough_for_claim"])
            self.assertEqual(
                packet["privacy_boundary"],
                "no raw source, no local paths, no source refs in hook",
            )

if __name__ == "__main__":
    unittest.main()
