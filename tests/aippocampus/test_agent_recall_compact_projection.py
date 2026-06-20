from __future__ import annotations

import json
import shlex
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.contracts import executable_command_violations  # noqa: E402
from aippocampus_runtime.recall import agent_continuity, foreground_action_card  # noqa: E402


def assert_command_args(test: unittest.TestCase, command: str, expected: list[str]) -> None:
    test.assertEqual(shlex.split(command), expected)


class AgentRecallCompactProjectionTests(unittest.TestCase):
    def test_low_specificity_thread_candidate_choices_get_public_safe_differentiators(
        self,
    ) -> None:
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": "dashboard mobile continuity state",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "foreground_action_card": {
                    "decision": "use_route_first",
                    "canonical_action": {
                        "action_id": "agent_deepen_selected_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1, "last_recall": True},
                        "claim_boundary": "no_claim_before_reopen",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_thread_1",
                        "route_label": "thread_candidate: AIppocampus · 2026-06-16T21:22:14.383Z",
                        "route_kind": "thread_candidate",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                    {
                        "route_id": "route_thread_2",
                        "route_label": "thread_candidate: AIppocampus",
                        "route_kind": "thread_candidate",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                    {
                        "route_id": "route_thread_3",
                        "route_label": "thread_candidate: AIppocampus · 2026-06-16T05:10:16.284Z",
                        "route_kind": "thread_candidate",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                ],
                "metrics": {
                    "memory_packet_count": 3,
                    "deepen_request_count": 3,
                    "route_label_specificity_floor": 0.0,
                    "topic_label_present_count": 0,
                },
            }
        )

        self.assertEqual(public["route_count"], 3)
        self.assertEqual(public["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(public["foreground_action"], public["agent_next_action"])
        self.assertEqual(public["safe_next_actions"][0], public["foreground_action"])
        action = public["foreground_action"]
        self.assertEqual(action["id"], "refine_low_specificity_recall_cue")
        self.assertNotIn("action_id", action)
        self.assertEqual(action["tool_name"], "agent_recall")
        self.assertEqual(action["arguments"]["query"], "dashboard mobile continuity state")
        assert_command_args(
            self,
            action["command"],
            ["aippocampus", "agent", "recall", "dashboard mobile continuity state", "--json"],
        )
        self.assertNotIn("requires", action)
        self.assertNotIn("command_template", action)
        self.assertEqual(action["tighter_cue_template"]["requires"], ["tighter_cue"])
        self.assertEqual(
            action["tighter_cue_template"]["command_template"],
            'aippocampus agent recall "{tighter_cue}" --json',
        )
        self.assertEqual(action["route_label_specificity_floor"], 0.0)
        self.assertEqual(action["topic_label_present_count"], 0)
        self.assertIn("tighter cue", action["why"])
        self.assertEqual(action["secondary_action"]["original_id"], "agent_deepen_selected_route")
        self.assertEqual(action["secondary_action"]["id"], "deepen_top_route_low_confidence")
        self.assertEqual(action["secondary_action"]["tool_name"], "agent_deepen")
        for route in public["routes"]:
            self.assertIn("choice_reason", route)
            self.assertIn("thread_candidate", route["choice_reason"])
            self.assertIn("labels_low_specificity", route["choice_reason"])
            action = route["action"]
            self.assertEqual(action["id"], "deepen_this_route")
            self.assertEqual(action["tool_name"], "agent_deepen")
            self.assertEqual(action["route_choice_posture"], "labels_low_specificity")
            self.assertEqual(action["confidence"], "low_confidence_navigation")
            self.assertEqual(action["arguments"]["request_index"], route["route_index"])
            self.assertTrue(action["arguments"]["last_recall"])
            self.assertIn(
                f"--request {route['route_index']} --last-recall --json",
                action["command"],
            )
            self.assertEqual(action["claim_boundary"], "no_claim_before_reopen")
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertNotIn('"handle":', encoded)
        self.assertNotIn('"callable_handle":', encoded)
        self.assertNotIn('"copy_paste_command":', encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_distinguishable_route_labels_keep_deepen_primary(self) -> None:
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "foreground_action_card": {
                    "decision": "use_route_first",
                    "canonical_action": {
                        "action_id": "agent_deepen_selected_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1, "last_recall": True},
                        "claim_boundary": "no_claim_before_reopen",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_roadmap",
                        "route_topic": "roadmap closeout",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                    {
                        "route_id": "route_hooks",
                        "route_topic": "hook install boundary",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                ],
                "metrics": {
                    "memory_packet_count": 2,
                    "deepen_request_count": 2,
                    "route_label_specificity_floor": 0.42,
                    "topic_label_present_count": 2,
                },
            }
        )

        action = public["foreground_action"]
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(public["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(public["agent_next_action"], public["foreground_action"])
        self.assertEqual(public["safe_next_actions"][0], public["foreground_action"])
        self.assertNotEqual(action["id"], "refine_low_specificity_recall_cue")
        self.assertNotIn("action_id", action)
        self.assertNotIn("secondary_action", action)
        self.assertIn("topic_roadmap_closeout", public["routes"][0]["choice_reason"])

    def test_recall_selector_replaces_mutable_last_recall_in_compact_actions(self) -> None:
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "recall_selector_id": "sel_0123456789abcdef",
                "foreground_action_card": {
                    "decision": "use_route_first",
                    "canonical_action": {
                        "action_id": "agent_deepen_selected_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1, "last_recall": True},
                        "claim_boundary": "no_claim_before_reopen",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_selector",
                        "route_topic": "selector stability",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    }
                ],
            }
        )

        action = public["foreground_action"]
        route_action = public["routes"][0]["action"]
        self.assertEqual(action["arguments"]["recall_selector"], "sel_0123456789abcdef")
        self.assertNotIn("last_recall", action["arguments"])
        self.assertIn("--recall-selector sel_0123456789abcdef", action["command"])
        self.assertEqual(route_action["arguments"]["recall_selector"], "sel_0123456789abcdef")
        self.assertNotIn("last_recall", route_action["arguments"])
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertNotIn('"handle":', encoded)
        self.assertNotIn("last-recall.json", encoded)

    def test_single_generic_route_with_distinctive_cue_anchors_refines_before_deepen(
        self,
    ) -> None:
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": "关于联想回忆 黏菌 探索算法 检索不强",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "foreground_action_card": {
                    "decision": "use_route_first",
                    "canonical_action": {
                        "action_id": "agent_deepen_selected_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1, "last_recall": True},
                        "claim_boundary": "no_claim_before_reopen",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_generic",
                        "route_label": "technical_work route",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    }
                ],
                "metrics": {
                    "memory_packet_count": 1,
                    "deepen_request_count": 1,
                    "route_label_specificity_floor": 0.42,
                    "topic_label_present_count": 1,
                },
            }
        )

        action = public["foreground_action"]
        self.assertEqual(action["id"], "refine_low_specificity_recall_cue")
        self.assertEqual(action["tool_name"], "agent_recall")
        self.assertEqual(action["secondary_action"]["id"], "deepen_top_route_low_confidence")
        self.assertIn("distinctive cue anchors", action["why"])
        self.assertIn("labels_low_specificity", public["routes"][0]["choice_reason"])

    def test_recovery_actions_fill_known_recall_query_commands(self) -> None:
        no_route = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "no_routes",
                "memory_packets": [],
                "foreground_action_card": {},
            },
            query="unlikely-no-match-token-xyz-12345",
        )
        weak_route = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "foreground_action_card": {
                    "canonical_action": {"action_id": "continue_normally", "arguments": {}}
                },
                "memory_packets": [{"route_id": "route_weak", "route_kind": "direction_only"}],
                "deepen_requests": [],
            },
            query="broad direction route",
        )
        self.assertEqual(no_route["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(no_route["foreground_action"], no_route["agent_next_action"])
        self.assertEqual(no_route["safe_next_actions"][0], no_route["foreground_action"])
        self.assertEqual(no_route["foreground_action"]["id"], "recover_recall_miss")
        self.assertNotIn("action_id", no_route["foreground_action"])
        assert_command_args(
            self,
            no_route["foreground_action"]["command"],
            ["aippocampus", "search", "unlikely-no-match-token-xyz-12345", "--json"],
        )
        self.assertEqual(weak_route["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(weak_route["foreground_action"], weak_route["agent_next_action"])
        self.assertEqual(weak_route["safe_next_actions"][0], weak_route["foreground_action"])
        self.assertEqual(weak_route["foreground_action"]["id"], "recover_weak_route")
        assert_command_args(
            self,
            weak_route["foreground_action"]["command"],
            ["aippocampus", "search", "broad direction route", "--json"],
        )
        self.assertEqual(executable_command_violations(no_route), [])
        self.assertEqual(executable_command_violations(weak_route), [])

    def test_full_recall_action_card_no_routes_has_executable_recovery_action(self) -> None:
        card = foreground_action_card.build_recall_foreground_action_card(
            status="no_routes",
            memory_packets=[],
            deepen_requests=[],
            query="unlikely-no-match-token-xyz-12345",
        )

        self.assertEqual(card["decision"], "recover_no_route")
        self.assertEqual(card["canonical_action"]["tool_name"], "search_memory")
        assert_command_args(
            self,
            card["canonical_action"]["cli_command"],
            ["aippocampus", "search", "unlikely-no-match-token-xyz-12345", "--json"],
        )
        self.assertEqual(card["safe_next_actions"][0], card["canonical_action"])
        self.assertEqual(executable_command_violations(card), [])

    def test_full_recall_action_card_no_source_redirects_to_registration(self) -> None:
        card = foreground_action_card.build_recall_foreground_action_card(
            status="no_routes",
            memory_packets=[],
            deepen_requests=[],
            query="unlikely-no-match-token-xyz-12345",
            source_registered=False,
        )

        self.assertEqual(card["decision"], "recover_no_route")
        self.assertEqual(card["canonical_action"]["action_id"], "register_source_before_recall")
        self.assertEqual(card["canonical_action"]["tool_name"], "shell")
        assert_command_args(
            self,
            card["canonical_action"]["cli_command"],
            ["aippocampus", "onboard", "--provider", "codex", "--cwd", ".", "--json"],
        )
        action_ids = [action["action_id"] for action in card["safe_next_actions"]]
        self.assertEqual(action_ids[0], "register_source_before_recall")
        self.assertIn("check_onboarding_status", action_ids)
        self.assertIn("recover_recall_miss", action_ids)
        self.assertEqual(executable_command_violations(card), [])

    def test_missing_cache_recovery_uses_known_query_not_same_cue_placeholder(self) -> None:
        projected = agent_continuity.public_recall_projection(
            {
                "kind": agent_continuity.KIND,
                "schema_version": agent_continuity.SCHEMA_VERSION,
                "mode": "recall",
                "status": "ok",
                "last_recall_cache_available": False,
                "foreground_action_card": {
                    "canonical_action": {
                        "action_id": "agent_deepen_selected_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1, "last_recall": True},
                        "cli_command": "aippocampus agent deepen --request 1 --last-recall --json",
                    }
                },
                "memory_packets": [{"route_id": "route_missing_cache", "output_mode": "reopenable_route"}],
            },
            query="missing cache source cue",
        )
        encoded = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("<same cue>", encoded)
        assert_command_args(
            self,
            projected["foreground_action"]["command"],
            [
                "aippocampus",
                "agent",
                "recall",
                "missing cache source cue",
                "--json",
                "--detail",
                "full",
            ],
        )
        self.assertEqual(executable_command_violations(projected), [])


if __name__ == "__main__":
    unittest.main()
