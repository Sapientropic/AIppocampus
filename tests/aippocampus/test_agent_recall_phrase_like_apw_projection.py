from __future__ import annotations

import json
import unittest

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.recall import (
    agent_continuity_cli_support,
    foreground_action_card,
)


class AgentRecallPhraseLikeApwProjectionTests(unittest.TestCase):
    def test_phrase_like_cue_keeps_registry_search_before_current_source_apw(self) -> None:
        """Projection unit for the registry source_window follow-through dogfood path."""
        cue = "这样后续就不会变成审查 agent 不断开 issue、实现 agent 窄修、CI 越跑越胖的循环"
        public = agent_continuity_cli_support.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": cue,
                "last_recall_cache_available": True,
                "recall_selector_id": "sel_phrase_like_current_apw",
                "foreground_action_card": foreground_action_card.build_recall_foreground_action_card(
                    status="ok",
                    query=cue,
                    source_registered=True,
                    memory_packets=[
                        {
                            "route_id": "route-nearby-workflow",
                            "route_topic": "workflow issue loop",
                            "route_kind": "clean_source_route",
                            "output_mode": "reopenable_route",
                            "claim_permission": "no_claim_before_reopen",
                            "source_anchor_gate": {
                                "status": "blocked",
                                "reason": "opened_source_validation_artifact",
                            },
                        }
                    ],
                    deepen_requests=[
                        {
                            "route_id": "route-nearby-workflow",
                            "request_index": 1,
                            "handle": {"kind": "source_ref"},
                        }
                    ],
                ),
                "memory_packets": [
                    {
                        "route_id": "route-nearby-workflow",
                        "route_topic": "workflow issue loop",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                    }
                ],
                "associative_path_policy": {
                    "apw_candidate_input_available": True,
                    "ordinary_recall_recovery_needed": True,
                    "run_fallback": True,
                    "promotion_mode": "semi_default_recovery",
                    "explicit_requested": False,
                },
                "associative_path_fallback": {
                    "kind": "aippocampus_associative_path_recall_fallback",
                    "status": "route_candidate",
                    "request_index": 6,
                    "label": "APW source route: 实现 / 越跑越胖的循环",
                    "candidate_source_kind": "current_clean_source",
                    "matched_cue_anchors": ["实现", "agent", "issue", "CI", "越跑越胖的循环"],
                    "meaningful_cue_anchors": ["实现", "越跑越胖的循环"],
                    "route_choice_posture": "associative_path_semi_default_recovery",
                    "source_anchor_gate": {
                        "status": "pass",
                        "target_source_matched": True,
                        "opened_anchor_hits": 4,
                        "required_anchor_hits": 3,
                        "meaningful_anchor_hits": 2,
                        "required_meaningful_anchor_hits": 2,
                    },
                },
            },
            query=cue,
        )

        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertEqual(
            public["foreground_action"]["id"],
            "search_registry_sources_for_original_cue_anchors",
        )
        self.assertEqual(public["foreground_action"]["tool_name"], "search_memory")
        self.assertEqual(
            public["foreground_action"]["arguments"]["scope"],
            "all_registered_sources",
        )
        self.assertFalse(public["foreground_action"]["arguments"].get("open_source", False))
        self.assertIn("越跑越胖的循环", public["foreground_action"]["arguments"]["query"])
        self.assertNotIn("deepen_associative_path_fallback", encoded)
        self.assertNotIn("associative_path_fallback", public)
        self.assertNotIn("source_anchor_gate", encoded)
        self.assertEqual(executable_command_violations(public), [])


if __name__ == "__main__":
    unittest.main()
