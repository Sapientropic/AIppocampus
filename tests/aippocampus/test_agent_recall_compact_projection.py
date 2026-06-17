from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import agent_continuity  # noqa: E402


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
        action = public["foreground_action"]
        self.assertEqual(action["action_id"], "deepen_top_route_blindly")
        self.assertEqual(action["route_label_specificity_floor"], 0.0)
        self.assertEqual(action["topic_label_present_count"], 0)
        self.assertIn("tighter cue", action["why"])
        for route in public["routes"]:
            self.assertIn("choice_reason", route)
            self.assertIn("thread_candidate", route["choice_reason"])
            self.assertIn("labels_low_specificity", route["choice_reason"])
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("C:\\", encoded)


if __name__ == "__main__":
    unittest.main()
