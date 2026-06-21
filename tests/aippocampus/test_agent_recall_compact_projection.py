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
from tests.aippocampus.frontstage_assertions import (  # noqa: E402
    assert_compact_frontstage_payload,
)


def assert_command_args(test: unittest.TestCase, command: str, expected: list[str]) -> None:
    test.assertEqual(shlex.split(command), expected)


class AgentRecallCompactProjectionTests(unittest.TestCase):
    def test_compact_detail_command_uses_safe_recall_cue_or_template(self) -> None:
        safe = agent_continuity.public_recall_projection(
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
                        "route_id": "route_safe_cue",
                        "route_topic": "compact detail cue",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    }
                ],
            },
            query="AIppocampus compact recall detail cue",
        )

        assert_command_args(
            self,
            safe["operator_detail_command"],
            [
                "aippocampus",
                "agent",
                "recall",
                "AIppocampus compact recall detail cue",
                "--json",
                "--detail",
                "full",
            ],
        )
        self.assertEqual(
            safe["claim_boundary"]["detail_available_with"],
            safe["operator_detail_command"],
        )
        self.assertNotIn("old decision or handoff cue", json.dumps(safe, ensure_ascii=False))

        template_only = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "no_routes",
                "opt_in_required": False,
                "foreground_action_card": {},
                "memory_packets": [],
            },
            query="old decision or handoff cue",
        )

        self.assertNotIn("operator_detail_command", template_only)
        self.assertEqual(
            template_only["operator_detail_command_template"],
            'aippocampus agent recall "{cue}" --json --detail full',
        )
        self.assertEqual(template_only["operator_detail_requires"], ["cue"])
        self.assertNotIn("detail_available_with", template_only["claim_boundary"])
        self.assertEqual(
            template_only["claim_boundary"]["detail_available_with_template"],
            'aippocampus agent recall "{cue}" --json --detail full',
        )
        self.assertEqual(template_only["claim_boundary"]["detail_requires"], ["cue"])
        self.assertEqual(executable_command_violations(template_only), [])

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
        self.assertEqual(public["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", public)
        self.assertNotIn(public["foreground_action"], public.get("safe_next_actions", []))
        action = public["foreground_action"]
        self.assertEqual(action["id"], "search_registry_sources_for_original_cue_anchors")
        self.assertNotIn("action_id", action)
        self.assertEqual(action["tool_name"], "search_memory")
        self.assertEqual(action["arguments"]["scope"], "all_registered_sources")
        self.assertIn("aippocampus search --all", action["command"])
        self.assertNotIn("secondary_action", action)
        safe_by_id = {item["id"]: item for item in public["safe_next_actions"]}
        refine_action = safe_by_id["refine_low_specificity_recall_cue"]
        deepen_action = safe_by_id["deepen_top_route_low_confidence"]
        self.assertEqual(refine_action["id"], "refine_low_specificity_recall_cue")
        self.assertEqual(refine_action["previous_low_specificity_cue"], "dashboard mobile continuity state")
        self.assertEqual(refine_action["previous_cue_role"], "context_only_not_executable")
        self.assertEqual(refine_action["requires"], ["tighter_cue"])
        self.assertNotIn("secondary_action", refine_action)
        self.assertTrue(refine_action["template_only"])
        self.assertEqual(
            refine_action["command_template"],
            'aippocampus agent recall "{tighter_cue}" --json',
        )
        self.assertEqual(refine_action["tighter_cue_template"]["requires"], ["tighter_cue"])
        self.assertEqual(
            refine_action["tighter_cue_template"]["command_template"],
            'aippocampus agent recall "{tighter_cue}" --json',
        )
        self.assertEqual(action["route_label_specificity_floor"], 0.0)
        self.assertEqual(action["topic_label_present_count"], 0)
        self.assertIn("Search all registered source", action["label"])
        self.assertEqual(deepen_action["original_id"], "agent_deepen_selected_route")
        self.assertEqual(deepen_action["id"], "deepen_top_route_low_confidence")
        self.assertEqual(deepen_action["tool_name"], "agent_deepen")
        self.assertEqual(public.get("routes", []), [])
        self.assertEqual(public["displayed_route_count"], 0)
        self.assertEqual(public["omitted_route_count"], 3)
        self.assertEqual(public["hidden_low_confidence_route_count"], 3)
        self.assertNotIn("route_selection", public["claim_boundary"]["can_use_for"])
        recovery = public["weak_route_recovery_card"]
        self.assertEqual(recovery["posture"], "labels_low_specificity")
        self.assertEqual(recovery["displayed_as_choices"], 0)
        self.assertEqual(recovery["primary_action"], "search_registry_sources_for_original_cue_anchors")
        self.assertEqual(
            recovery["source_search_fallback_action_id"],
            "search_registry_sources_for_original_cue_anchors",
        )
        self.assertEqual(recovery["deepen_action_id"], "deepen_top_route_low_confidence")
        self.assertEqual(recovery["refine_action_id"], "refine_low_specificity_recall_cue")
        self.assertNotIn("route_availability_summary", public)
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("secondary_action", encoded)
        self.assertNotIn('"handle":', encoded)
        self.assertNotIn('"callable_handle":', encoded)
        self.assertNotIn('"copy_paste_command":', encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("C:\\", encoded)
        assert_compact_frontstage_payload(self, public, max_top_level_diagnostics=1)

    def test_repeated_same_topic_low_distinctiveness_routes_refine_before_deepen(
        self,
    ) -> None:
        packets = [
            {
                "route_id": f"route_same_topic_{index}",
                "route_topic": "benchmark_claim_posture",
                "route_kind": "clean_source_route",
                "output_mode": "reopenable_route",
                "claim_permission": "no_claim_before_reopen",
            }
            for index in range(1, 6)
        ]
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": "AIppocampus UX review foreground agent usability noisy cannot_claim",
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
                "memory_packets": packets,
                "metrics": {
                    "memory_packet_count": 5,
                    "deepen_request_count": 5,
                    "packet_triage_distinctiveness": 0.4,
                    "route_label_specificity_floor": 0.0,
                    "topic_label_present_count": 5,
                },
            }
        )

        self.assertEqual(public["route_count"], 5)
        self.assertEqual(public["displayed_route_count"], 0)
        self.assertEqual(public["omitted_route_count"], 5)
        self.assertEqual(public["hidden_low_confidence_route_count"], 5)
        self.assertEqual(public["omitted_duplicate_route_label_count"], 4)
        self.assertEqual(
            public["omitted_duplicate_route_labels"],
            [
                {
                    "route_label": "Benchmark claim posture",
                    "kept_route_index": 1,
                    "omitted_count": 4,
                }
            ],
        )
        self.assertEqual(public.get("routes", []), [])
        action = public["foreground_action"]
        self.assertEqual(action["id"], "search_registry_sources_for_original_cue_anchors")
        self.assertEqual(action["route_choice_posture"], "labels_low_specificity")
        self.assertEqual(action["topic_label_present_count"], 5)
        self.assertEqual(action["packet_triage_distinctiveness"], 0.4)
        self.assertEqual(action["repeated_route_label"], "benchmark_claim_posture")
        self.assertIn("aippocampus search --all", action["command"])
        safe_by_id = {item["id"]: item for item in public["safe_next_actions"]}
        refine_action = safe_by_id["refine_low_specificity_recall_cue"]
        self.assertEqual(refine_action["requires"], ["tighter_cue"])
        self.assertEqual(
            refine_action["previous_low_specificity_cue"],
            "AIppocampus UX review foreground agent usability noisy cannot_claim",
        )
        self.assertEqual(safe_by_id["deepen_top_route_low_confidence"]["id"], "deepen_top_route_low_confidence")
        recovery = public["weak_route_recovery_card"]
        self.assertEqual(recovery["route_count"], 5)
        self.assertEqual(recovery["displayed_as_choices"], 0)
        self.assertEqual(recovery["primary_action"], "search_registry_sources_for_original_cue_anchors")
        self.assertNotIn("route_availability_summary", public)
        assert_compact_frontstage_payload(self, public, max_top_level_diagnostics=1)

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
        self.assertEqual(public["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", public)
        self.assertNotIn(public["foreground_action"], public.get("safe_next_actions", []))
        self.assertNotEqual(action["id"], "refine_low_specificity_recall_cue")
        self.assertNotIn("action_id", action)
        self.assertNotIn("secondary_action", action)
        first_route = public["routes"][0]
        self.assertEqual(first_route["index"], 1)
        self.assertEqual(first_route["label"], "Roadmap closeout")
        self.assertIn("Route 1 of 2", first_route["why_this_route"])
        self.assertIn("reopened", first_route["why_this_route"])
        self.assertEqual(first_route["action"]["tool_name"], "agent_deepen")
        encoded_routes = json.dumps(public["routes"], ensure_ascii=False)
        self.assertNotIn("route_id", encoded_routes)
        self.assertNotIn("route_family", encoded_routes)
        self.assertNotIn("choice_reason", encoded_routes)

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
        self.assertEqual(action["id"], "search_registry_sources_for_original_cue_anchors")
        self.assertEqual(action["tool_name"], "search_memory")
        safe_by_id = {item["id"]: item for item in public["safe_next_actions"]}
        self.assertEqual(safe_by_id["refine_low_specificity_recall_cue"]["id"], "refine_low_specificity_recall_cue")
        self.assertEqual(safe_by_id["deepen_top_route_low_confidence"]["id"], "deepen_top_route_low_confidence")
        self.assertIn("original cue anchors", action["why"])
        self.assertEqual(public.get("routes", []), [])
        self.assertEqual(public["hidden_low_confidence_route_count"], 1)
        self.assertEqual(public["weak_route_recovery_card"]["displayed_as_choices"], 0)
        self.assertNotIn("route_availability_summary", public)

    def test_already_opened_compact_without_source_receipt_reopens_read_only(
        self,
    ) -> None:
        public = agent_continuity.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "foreground_action_card": {
                    "decision": "use_opened_context",
                    "canonical_action": {
                        "action_id": "use_opened_route_context",
                        "tool_name": None,
                        "arguments": {},
                        "why": "same route and handle were already reopened in this local session",
                        "claim_boundary": "source_open_within_opened_context",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_already_opened",
                        "route_topic": "opened compact route",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                        "already_opened": True,
                        "opened_route_context": {
                            "status": "opened_in_this_local_session",
                            "same_route_and_handle_digest": True,
                        },
                    }
                ],
            },
            query="opened compact route cue",
        )

        action = public["foreground_action"]
        self.assertNotEqual(action["id"], "use_opened_route_context")
        self.assertEqual(action["id"], "reopen_already_opened_route_context")
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(action["arguments"], {"request_index": 1, "last_recall": True})
        assert_command_args(
            self,
            action["command"],
            ["aippocampus", "agent", "deepen", "--request", "1", "--last-recall", "--json"],
        )
        self.assertIn("current compact payload has no source-window receipt", action["why"])
        self.assertEqual(action["claim_boundary"], "no_claim_before_reopen")
        self.assertEqual(public["routes"][0]["already_opened"], True)
        self.assertEqual(public["routes"][0]["action"]["tool_name"], "agent_deepen")
        self.assertEqual(executable_command_violations(public), [])

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
        self.assertEqual(no_route["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", no_route)
        self.assertNotIn(no_route["foreground_action"], no_route.get("safe_next_actions", []))
        self.assertEqual(no_route["foreground_action"]["id"], "search_registry_sources_for_original_cue_anchors")
        self.assertNotIn("action_id", no_route["foreground_action"])
        assert_command_args(
            self,
            no_route["foreground_action"]["command"],
            ["aippocampus", "search", "--all", "unlikely-no-match-token-xyz-12345", "--json"],
        )
        self.assertEqual(weak_route["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", weak_route)
        self.assertNotIn(weak_route["foreground_action"], weak_route.get("safe_next_actions", []))
        self.assertEqual(weak_route["foreground_action"]["id"], "search_registry_sources_for_original_cue_anchors")
        assert_command_args(
            self,
            weak_route["foreground_action"]["command"],
            ["aippocampus", "search", "--all", "broad direction", "--json"],
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
