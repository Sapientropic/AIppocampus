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
from aippocampus_runtime.recall.route_notes import extract_route_note_candidates  # noqa: E402


class ActivePathPacketTests(unittest.TestCase):
    def test_route_notes_feed_packet_without_promoting_commentary_to_truth(self) -> None:
        messages = [
            {
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "message_id": "msg-user-1",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 10,
                "text": "Please continue the migration.",
            },
            {
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 1,
                "message_id": "msg-commentary-reject",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 11,
                "text": (
                    "The direct shell command failed; reject that route before rerunning "
                    "E:\\Users\\Private\\secret.txt with api_key=sk-test-secret."
                ),
            },
            {
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "turn_index": 1,
                "message_id": "msg-final-1",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 14,
                "text": "Use the source-reopen route instead of the failed shell route.",
            },
            {
                "role": "user",
                "phase": "",
                "turn_index": 2,
                "message_id": "msg-user-2",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 20,
                "text": "What remains unresolved?",
            },
            {
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 2,
                "message_id": "msg-commentary-open",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 21,
                "text": "Open question: whether the route note should point at tool or final evidence.",
            },
            {
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "turn_index": 2,
                "message_id": "msg-final-2",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 25,
                "text": "The remaining question is the tool/final evidence join.",
            },
            {
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 3,
                "message_id": "msg-commentary-floating",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 31,
                "text": "Handoff hint without adjacent evidence should not become a route note.",
            },
        ]
        events = [
            {
                "event_id": "evt-failed-shell",
                "turn_index": 1,
                "event_kind": "tool_call_observed",
                "hard_event_kind": "tool_call_failed",
                "status": "failed",
                "command_class": "test",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "failure_family": "assertion_failure",
                "source_id": "clean:route-notes",
                "thread_key": "session:route-notes",
                "source_line": 13,
                "path_fingerprints": ["sha256:1234567890abcdef"],
                "text": "raw stdout blob and E:\\Users\\Private\\secret.txt must stay private",
            }
        ]

        notes = extract_route_note_candidates(messages, events=events)
        packet = build_active_path_packet(route_notes=notes)

        self.assertEqual(notes["kind"], "aippocampus_route_note_candidates")
        self.assertTrue(notes["no_write"])
        self.assertTrue(notes["contract"]["commentary_is_process_evidence_not_source_truth"])
        self.assertEqual(notes["metrics"]["candidate_count"], 2)
        self.assertEqual(notes["metrics"]["diagnostic_only_count"], 1)
        self.assertGreaterEqual(notes["metrics"]["joined_tool_evidence_count"], 1)
        self.assertEqual(
            set(notes["taxonomy"]),
            {
                "intent_before_tool",
                "decision_breadcrumb",
                "rejected_route",
                "open_question",
                "handoff_hint",
                "source_to_action_link",
            },
        )

        note_types = {row["note_type"] for row in notes["rows"]}
        self.assertIn("rejected_route", note_types)
        self.assertIn("open_question", note_types)
        for row in notes["rows"]:
            self.assertEqual(row["output_authority"], "navigation_only")
            self.assertTrue(row["source_reopen_required_before_claim"])
            self.assertTrue(row["source_refs"])
            self.assertTrue(row["joined_evidence_refs"])
            self.assertIn("route_note", row["reason_codes"])

        route_note_paths = [path for path in packet["paths"] if path["origin"] == "route_note"]
        self.assertGreaterEqual(len(route_note_paths), 2)
        self.assertTrue(all(path["route"] == "reopen" for path in route_note_paths))
        self.assertTrue(all(path["source_boundary"]["source_reopen_required"] for path in route_note_paths))

        serialized = json.dumps({"notes": notes, "packet": packet}, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("direct shell command", serialized)
        self.assertNotIn("raw stdout", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("Private", serialized)
        self.assertNotIn("sk-test-secret", serialized)
        self.assertNotIn("api_key", serialized)

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
