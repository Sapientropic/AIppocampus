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
        self.assertEqual(payload["cards"][0]["visibility"], "active_gentle_nudge")
        self.assertEqual(payload["cards"][0]["source_refs"], [])
        self.assertIn("Ambient recall design", payload["cards"][0]["theme"])

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
