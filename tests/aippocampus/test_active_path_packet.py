from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.active_path_packet import build_active_path_packet  # noqa: E402


class ActivePathPacketTests(unittest.TestCase):
    def test_packet_selects_compact_source_reopenable_paths(self) -> None:
        local_path = "E:" + "\\private\\launch-notes.md"
        packet = build_active_path_packet(
            ambient_recall={
                "kind": "aippocampus_ambient_recall",
                "confidence": "high",
                "cards": [
                    {
                        "card_id": "evidence-card",
                        "theme": "Clean-source coding preference",
                        "support_level": "evidence",
                        "visibility": "source_backed_recall_card",
                        "suggested_use": "Use this bounded evidence when it changes the answer.",
                        "key_line": f"raw source wording should stay out {local_path}",
                        "source_reopen_required": False,
                        "source_refs": [
                            {
                                "thread_key": "session:current",
                                "message_id": "msg-1",
                                "line": 12,
                            }
                        ],
                    },
                    {
                        "card_id": "scent-card",
                        "theme": "Loose old route",
                        "support_level": "scent",
                        "visibility": "active_gentle_nudge",
                        "suggested_use": "Treat this as resonance only.",
                        "key_line": "raw scent text must not leak",
                        "source_refs": [],
                    },
                ],
                "fresh_thread_packet": {
                    "kind": "aippocampus_fresh_thread_scent_packet",
                    "support_level": "source_required",
                    "confidence": "medium",
                    "freshness": "current",
                    "advisory_action": "source_reopen",
                    "candidate_refs": [
                        {
                            "thread_key": "session:current",
                            "message_id": "msg-2",
                            "line": 18,
                        }
                    ],
                    "reopen_plan": {
                        "status": "ready",
                        "recommended_tool": "get_turn_context",
                    },
                },
            },
            active_locks=[
                {
                    "kind": "aippocampus_active_recall_lock",
                    "state": "ready",
                    "query_aliases": ["agency replay"],
                    "route_reasons": ["host-surface replay may be relevant"],
                    "candidate_refs": [
                        {
                            "thread_key": "session:lock",
                            "turn_id": "turn-7",
                        }
                    ],
                    "reopenable_ref_count": 1,
                    "freshness_vector": {"registry": "current"},
                }
            ],
            route_readiness=[
                {
                    "route_id": "route:superseded-sync-plan",
                    "title": "Superseded sync plan",
                    "route_status": "suppressed",
                    "currentness": "superseded",
                    "confidence": "high",
                    "suppression_reasons": ["superseded_by_new_design"],
                    "source_refs": [
                        {
                            "thread_key": "session:old",
                            "line": 44,
                        }
                    ],
                }
            ],
        )

        self.assertEqual(packet["kind"], "aippocampus_active_path_packet")
        self.assertEqual(packet["schema_version"], 1)
        self.assertGreaterEqual(packet["path_count"], 4)
        self.assertLessEqual(packet["path_count"], 7)
        self.assertTrue(packet["privacy"]["local_first"])
        self.assertFalse(packet["privacy"]["raw_source_text_serialized"])
        self.assertFalse(packet["metrics"]["manual_query_invention_expected"])
        self.assertGreaterEqual(packet["metrics"]["reopenable_path_count"], 2)
        self.assertGreaterEqual(packet["metrics"]["stale_or_superseded_path_count"], 1)
        self.assertTrue(packet["source_boundary"]["navigation_not_truth"])
        self.assertIn("source_reopen_required_before_claim", packet["cannot_claim"])

        routes = {path["route"] for path in packet["paths"]}
        self.assertIn("evidence", routes)
        self.assertIn("reopen", routes)
        self.assertIn("scent", routes)
        self.assertIn("ignore", routes)

        evidence_path = next(path for path in packet["paths"] if path["route"] == "evidence")
        self.assertEqual(evidence_path["next_action"], "use_bounded_evidence")
        self.assertFalse(evidence_path["source_boundary"]["source_reopen_required"])
        self.assertEqual(evidence_path["source_refs"][0]["message_id"], "msg-1")

        reopen_path = next(path for path in packet["paths"] if path["route"] == "reopen")
        self.assertIn(reopen_path["next_action"], {"get_turn_context", "source_reopen"})
        self.assertTrue(reopen_path["source_boundary"]["source_reopen_required"])
        self.assertTrue(reopen_path["source_refs"])

        ignored_path = next(path for path in packet["paths"] if path["route"] == "ignore")
        self.assertEqual(ignored_path["currentness"], "superseded")
        self.assertTrue(ignored_path["source_boundary"]["unsafe_to_use_as_current_fact"])
        self.assertEqual(ignored_path["next_action"], "ignore")

        serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw source wording", serialized)
        self.assertNotIn("raw scent text", serialized)
        self.assertNotIn("launch-notes", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("private", serialized.casefold())


if __name__ == "__main__":
    unittest.main()
