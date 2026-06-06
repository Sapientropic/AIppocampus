from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.fresh_thread_scent import (  # noqa: E402
    EXAMPLE_PACKETS,
    fresh_thread_scent_packet_from_decision,
)


class FreshThreadScentPacketTests(unittest.TestCase):
    def test_scent_packet_uses_issue_282_contract_fields(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [
                    {
                        "thread_key": "session:old-thread",
                        "message_id": "msg-7",
                        "line": 42,
                        "title": "Private launch anxiety thread",
                        "snippet": "raw private text that must not appear",
                    }
                ],
            }
        )

        self.assertEqual(packet["support_level"], "soft_hypothesis")
        self.assertEqual(packet["confidence"], "medium")
        self.assertEqual(packet["sensitivity"], "caution")
        self.assertEqual(packet["freshness"], "unknown")
        self.assertEqual(packet["advisory_action"], "active_recall")
        self.assertEqual(packet["suggested_action"], "active_recall")
        self.assertEqual(
            set(packet),
            {
                "kind",
                "schema_version",
                "support_level",
                "confidence",
                "sensitivity",
                "freshness",
                "route_reason",
                "candidate_refs",
                "candidate_ref_count",
                "reopenable_ref_count",
                "advisory_action",
                "suggested_action",
                "trust_level",
                "trust_contract",
                "when_not_to_use",
                "source_boundary",
            },
        )
        self.assertEqual(
            packet["candidate_refs"],
            [{"thread_key": "session:old-thread", "message_id": "msg-7", "line": 42}],
        )
        self.assertEqual(packet["candidate_ref_count"], 1)
        self.assertEqual(packet["reopenable_ref_count"], 1)
        self.assertTrue(packet["source_boundary"]["navigation_only_until_source_reopened"])
        self.assertTrue(packet["source_boundary"]["advisory_action_is_not_final_agent_action"])
        self.assertTrue(packet["source_boundary"]["final_action_owned_by_fresh_thread_action_policy"])

    def test_packet_redacts_raw_prompt_snippets_secrets_and_local_paths(self) -> None:
        local_path = "E:" + "\\private\\gift-notes.md"
        payload = fresh_thread_scent_packet_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "prompt": f"帮我妈妈挑个礼物，notes at {local_path}",
                "route_reason": "sk_test_1234567890 should never survive",
                "evidence": [
                    {
                        "thread_key": "session:family",
                        "message_id": "msg-9",
                        "line": 88,
                        "source_id": "clean:family:msg-9",
                        "title": "Mom likes private thing",
                        "snippet": f"raw family preference at {local_path} with sk-test-secret",
                    }
                ],
            }
        )
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["support_level"], "source_required")
        self.assertEqual(payload["trust_level"], "source_required")
        self.assertFalse(payload["trust_contract"]["agent_may_answer_within_scope"])
        self.assertFalse(payload["trust_contract"]["manual_query_invention_expected"])
        self.assertEqual(payload["advisory_action"], "source_reopen")
        self.assertEqual(payload["suggested_action"], "source_reopen")
        self.assertEqual(
            payload["reopen_plan"],
            {
                "kind": "source_ref_reopen",
                "status": "ready",
                "recommended_tool": "get_turn_context",
                "arguments": {"message_id": "msg-9"},
                "candidate_ref_count": 1,
                "reopenable_ref_count": 1,
                "primary_ref": {
                    "source_id": "clean:family:msg-9",
                    "thread_key": "session:family",
                    "message_id": "msg-9",
                    "line": 88,
                },
                "reason_codes": ["source_required", "candidate_source_ref_reopenable"],
                "failure_reason_codes": [
                    "stale_handle",
                    "source_missing",
                    "permission_block",
                    "index_stale_lkg_needed",
                ],
                "manual_query_invention_expected": False,
            },
        )
        self.assertIn("clean:family:msg-9", serialized)
        self.assertNotIn("帮我妈妈", serialized)
        self.assertNotIn("raw family preference", serialized)
        self.assertNotIn("gift-notes", serialized)
        self.assertNotIn("sk_test", serialized)
        self.assertNotIn("sk-test-secret", serialized)

    def test_source_required_without_reopenable_refs_has_blocked_reopen_plan(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "evidence": [
                    {
                        "source_id": "clean:orphaned-summary",
                        "snippet": "raw summary must not leak",
                    }
                ],
            }
        )

        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["trust_level"], "source_required")
        self.assertFalse(packet["trust_contract"]["agent_may_answer_within_scope"])
        self.assertEqual(packet["candidate_ref_count"], 1)
        self.assertEqual(packet["reopenable_ref_count"], 0)
        self.assertEqual(packet["reopen_plan"]["status"], "blocked")
        self.assertEqual(packet["reopen_plan"]["recommended_tool"], "source_ref_reopen")
        self.assertEqual(packet["reopen_plan"]["candidate_ref_count"], 1)
        self.assertEqual(packet["reopen_plan"]["reopenable_ref_count"], 0)
        self.assertIn("no_reopenable_source_ref", packet["reopen_plan"]["reason_codes"])
        self.assertFalse(packet["reopen_plan"]["manual_query_invention_expected"])
        self.assertNotIn("raw summary", json.dumps(packet, ensure_ascii=False))

    def test_suppressed_packet_tells_agent_to_ignore(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "high",
                "sensitivity": "suppress",
                "freshness": "superseded",
                "candidates": [{"thread_key": "session:sensitive", "message_id": "m1"}],
            }
        )

        self.assertEqual(packet["support_level"], "suppressed")
        self.assertEqual(packet["sensitivity"], "suppress")
        self.assertEqual(packet["advisory_action"], "ignore")
        self.assertEqual(packet["suggested_action"], "ignore")
        self.assertEqual(packet["candidate_refs"], [])
        self.assertNotIn("reopen_plan", packet)
        self.assertIn("Do not use suppressed packets", " ".join(packet["when_not_to_use"]))

    def test_contract_includes_examples_for_all_support_levels(self) -> None:
        examples_by_level = {packet["support_level"]: packet for packet in EXAMPLE_PACKETS}

        self.assertEqual(
            set(examples_by_level),
            {"silent_scent", "soft_hypothesis", "source_required", "suppressed"},
        )
        for packet in EXAMPLE_PACKETS:
            self.assertTrue(packet["source_boundary"]["navigation_only_until_source_reopened"])
            self.assertNotIn("snippet", json.dumps(packet, ensure_ascii=False))

    def test_public_safe_demo_cues_do_not_become_prompt_dumps(self) -> None:
        cases = [
            ("我觉得压力好大", "stress-pressure", "ask_light_question"),
            ("帮我妈妈挑个礼物", "family-gift", "active_recall"),
            ("我想建个网站", "frontend-taste", "active_recall"),
            ("new repo with no AGENTS.md", "portable-engineering-style", "active_recall"),
        ]

        for prompt, source_id, expected_action in cases:
            with self.subTest(prompt=prompt):
                packet = fresh_thread_scent_packet_from_decision(
                    {
                        "decision": "scent",
                        "confidence": "low" if expected_action == "ask_light_question" else "medium",
                        "prompt": prompt,
                        "candidates": [{"source_id": source_id, "thread_key": "session:demo"}],
                    }
                )
                serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True)

                self.assertEqual(packet["support_level"], "soft_hypothesis")
                self.assertEqual(packet["advisory_action"], expected_action)
                self.assertEqual(packet["suggested_action"], expected_action)
                self.assertIn(source_id, serialized)
                self.assertNotIn(prompt, serialized)
                self.assertNotIn("AGENTS.md", serialized)


if __name__ == "__main__":
    unittest.main()
