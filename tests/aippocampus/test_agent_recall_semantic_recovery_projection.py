from __future__ import annotations

import json
import unittest

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.recall import agent_continuity_cli_support
from tests.aippocampus.frontstage_assertions import assert_compact_frontstage_payload


class AgentRecallSemanticRecoveryProjectionTests(unittest.TestCase):
    def test_blocked_semantic_route_keeps_source_search_primary(self) -> None:
        public = agent_continuity_cli_support.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": "preflight frontloads correctly current surface blocked by diff Ruff debt",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "recall_selector_id": "sel_blocked_semantic",
                "foreground_action_card": {
                    "decision": "recover_low_confidence_route",
                    "canonical_action": {
                        "action_id": "search_registry_sources_for_original_cue_anchors",
                        "tool_name": "search_memory",
                        "arguments": {
                            "query": (
                                "preflight frontloads correctly current surface "
                                "blocked by diff Ruff debt"
                            ),
                            "scope": "all_registered_sources",
                            "max": 5,
                        },
                        "cli_command": (
                            "aippocampus search --all 'preflight frontloads correctly "
                            "current surface blocked by diff Ruff debt' --json"
                        ),
                        "claim_boundary": "source_reopen_required_before_claim",
                    },
                    "safe_next_actions": [
                        {
                            "action_id": "inspect_low_confidence_route",
                            "tool_name": "agent_deepen",
                            "arguments": {"request_index": 1},
                            "cli_command_template": (
                                "aippocampus agent deepen --request 1 "
                                "--recall-selector {recall_selector} --json"
                            ),
                            "requires": ["recall_selector"],
                            "template_only": True,
                        }
                    ],
                },
                "memory_packets": [
                    {
                        "route_id": "route_blocked_semantic",
                        "route_label": "semantic_trigger source route",
                        "route_topic": "semantic_trigger",
                        "route_kind": "source_window",
                        "matched_cue_family": "semantic_trigger_source",
                        "source_chain_role": "semantic_trigger_source",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                        "source_anchor_gate": {
                            "status": "blocked",
                            "opened_anchor_hits": 0,
                            "required_anchor_hits": 2,
                            "target_source_matched": False,
                        },
                    },
                    {
                        "route_id": "route_ungated_semantic_sibling",
                        "route_label": "semantic_trigger source route",
                        "route_topic": "semantic_trigger",
                        "route_kind": "source_window",
                        "matched_cue_family": "semantic_trigger_source",
                        "source_chain_role": "semantic_trigger_source",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    },
                ],
                "deepen_requests": [
                    {
                        "request_index": 1,
                        "source_anchor_gate": {
                            "status": "blocked",
                            "target_source_matched": False,
                        },
                    }
                ],
                "source_anchor_gate": {
                    "status": "blocked",
                    "opened_anchor_hits": 0,
                    "required_anchor_hits": 2,
                    "target_source_matched": False,
                },
                "metrics": {
                    "memory_packet_count": 2,
                    "deepen_request_count": 1,
                    "route_label_specificity_floor": 0.0,
                    "topic_label_present_count": 0,
                },
            }
        )

        action = public["foreground_action"]
        self.assertEqual(action["id"], "search_registry_sources_for_original_cue_anchors")
        self.assertEqual(action["tool_name"], "search_memory")
        self.assertEqual(action["arguments"]["scope"], "all_registered_sources")
        self.assertNotEqual(action["id"], "deepen_semantic_recovery_route")
        self.assertEqual(public["routes"][0]["action_priority"], "secondary_preview")
        self.assertEqual(public["routes"][0]["actionability"], "preview_only")
        self.assertNotIn("safe_next_actions", public)
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("source_anchor_gate", encoded)
        self.assertNotIn("claim_boundary", encoded)
        self.assertEqual(executable_command_violations(public), [])
        assert_compact_frontstage_payload(self, public, max_top_level_diagnostics=1)


if __name__ == "__main__":
    unittest.main()
