from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ambient_recall_cards as cards  # noqa: E402


class AmbientRecallCardTests(unittest.TestCase):
    def test_evidence_decision_becomes_source_backed_card(self) -> None:
        result = {
            "decision": "evidence",
            "confidence": "high",
            "elapsed_ms": 123.4,
            "query_terms": ["continuity", "transformation"],
            "candidates": [
                {
                    "thread_key": "session:old",
                    "title": "Old continuity thread",
                    "matched_terms": ["continuity"],
                }
            ],
            "evidence": [
                {
                    "thread_key": "session:old",
                    "title": "Old continuity thread",
                    "line": 12,
                    "phase": "final_answer",
                    "turn_index": 3,
                    "snippet": "continuity survives transformation",
                }
            ],
            "working_memory": [],
            "cognitive_map": [],
        }

        payload = cards.ambient_recall_from_decision(result)

        self.assertEqual(payload["mode"], "source_backed_recall_card")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["late_update_policy"], "warm_scouts_deferred")
        self.assertEqual(payload["cards"][0]["support_level"], "evidence")
        self.assertEqual(payload["cards"][0]["visibility"], "source_backed_recall_card")
        self.assertEqual(payload["cards"][0]["source_refs"][0]["line"], 12)
        self.assertIn("innate memory", " ".join(payload["avoid"]))

    def test_deep_archival_request_requires_source_backed_evidence(self) -> None:
        result = {
            "decision": "evidence",
            "confidence": "high",
            "elapsed_ms": 123.4,
            "deep_archival_requested": True,
            "evidence": [
                {
                    "thread_key": "session:old",
                    "title": "Old continuity thread",
                    "line": 12,
                    "phase": "final_answer",
                    "turn_index": 3,
                    "snippet": "continuity survives transformation",
                }
            ],
            "working_memory": [],
            "cognitive_map": [],
            "candidates": [],
        }

        payload = cards.ambient_recall_from_decision(result)

        self.assertEqual(payload["mode"], "deep_archival_recall")
        self.assertEqual(payload["cards"][0]["visibility"], "deep_archival_recall")
        self.assertEqual(payload["cards"][0]["support_level"], "evidence")
        self.assertIn("clean source", payload["cards"][0]["suggested_use"].casefold())

    def test_deep_archival_request_does_not_promote_unsourced_scent(self) -> None:
        result = {
            "decision": "scent",
            "confidence": "medium",
            "deep_archival_requested": True,
            "candidates": [{"title": "Old thread", "matched_terms": ["memory"]}],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
        }

        payload = cards.ambient_recall_from_decision(result)

        self.assertEqual(payload["mode"], "active_gentle_nudge")
        self.assertEqual(payload["cards"][0]["visibility"], "active_gentle_nudge")
        self.assertEqual(payload["cards"][0]["support_level"], "scent")

    def test_scent_decision_becomes_active_gentle_nudge_without_evidence_claim(self) -> None:
        result = {
            "decision": "scent",
            "confidence": "medium",
            "elapsed_ms": 88.0,
            "query_terms": ["ambient recall", "小海马体"],
            "candidates": [
                {
                    "thread_key": "session:old",
                    "title": "Ambient recall design",
                    "matched_terms": ["ambient recall"],
                    "anchors": ["AIppocampus ambient recall continuity"],
                }
            ],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
        }

        payload = cards.ambient_recall_from_decision(result)

        self.assertEqual(payload["mode"], "active_gentle_nudge")
        self.assertEqual(payload["cards"][0]["support_level"], "scent")
        self.assertEqual(payload["fresh_thread_packet"]["support_level"], "soft_hypothesis")
        self.assertEqual(payload["fresh_thread_packet"]["suggested_action"], "active_recall")
        self.assertEqual(payload["cards"][0]["visibility"], "active_gentle_nudge")
        self.assertEqual(payload["cards"][0]["source_refs"], [])
        self.assertIn("Ambient recall design", payload["cards"][0]["theme"])

    def test_evidence_packet_contains_source_refs_without_key_line_or_snippet(self) -> None:
        payload = cards.ambient_recall_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "elapsed_ms": 1.0,
                "evidence": [
                    {
                        "thread_key": "session:old",
                        "message_id": "msg-11",
                        "line": 77,
                        "snippet": "private wording should stay on the evidence card only",
                    }
                ],
                "working_memory": [],
                "cognitive_map": [],
                "candidates": [],
            }
        )

        packet = payload["fresh_thread_packet"]

        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["suggested_action"], "source_reopen")
        self.assertEqual(
            packet["candidate_refs"],
            [{"thread_key": "session:old", "message_id": "msg-11", "line": 77}],
        )
        self.assertNotIn("key_line", packet)
        self.assertNotIn("snippet", packet)

    def test_skip_decision_stays_silent_with_stable_shape(self) -> None:
        payload = cards.ambient_recall_from_decision(
            {
                "decision": "skip",
                "confidence": "low",
                "elapsed_ms": 3.0,
                "query_terms": [],
                "candidates": [],
                "evidence": [],
                "working_memory": [],
                "cognitive_map": [],
            }
        )

        self.assertEqual(payload["mode"], "silent_tuning")
        self.assertEqual(payload["cards"], [])
        self.assertEqual(payload["cache_status"]["status"], "not_used")

    def test_cached_cards_can_be_prioritized_over_fresh_candidates(self) -> None:
        payload = cards.ambient_recall_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "elapsed_ms": 3.0,
                "query_terms": ["ambient"],
                "candidates": [{"title": "fresh candidate", "matched_terms": ["ambient"]}],
                "evidence": [],
                "working_memory": [],
                "cognitive_map": [],
            },
            cached_cards=[
                {
                    "card_id": "cached-card",
                    "theme": "cached warm context",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                }
            ],
            cached_cards_first=True,
        )

        self.assertEqual(payload["cards"][0]["card_id"], "cached-card")
        self.assertEqual(payload["cards"][0]["theme"], "cached warm context")

    def test_card_text_redacts_local_paths_before_future_scouts_can_read_it(self) -> None:
        local_path = "E:" + "\\private\\secret\\notes.md"
        payload = cards.ambient_recall_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "elapsed_ms": 1.0,
                "query_terms": ["privacy"],
                "candidates": [],
                "evidence": [
                    {
                        "thread_key": "session:old",
                        "title": "Privacy thread",
                        "line": 7,
                        "snippet": f"See {local_path} before continuing.",
                    }
                ],
                "working_memory": [],
                "cognitive_map": [],
            }
        )

        self.assertIn("<redacted:local-path>", payload["cards"][0]["key_line"])
        self.assertNotIn(local_path[:10], payload["cards"][0]["key_line"])


if __name__ == "__main__":
    unittest.main()
