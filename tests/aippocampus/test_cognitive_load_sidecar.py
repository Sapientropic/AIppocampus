from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import cognitive_load_sidecar as sidecar  # noqa: E402


class CognitiveLoadSidecarTests(unittest.TestCase):
    def test_high_load_source_gets_bounded_boost_without_collapsing_score_reasons(self) -> None:
        high_ref = {"source_id": "thread:pitfall", "message_id": "m-high", "line": 42}
        ordinary_ref = {"source_id": "thread:ordinary", "message_id": "m-ordinary", "line": 7}
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-correction",
                    "event_type": "user_correction",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [high_ref],
                    "source_reopened": True,
                    "caution_hint_reviewed": True,
                    "caution_hint_useful": True,
                },
                {
                    "event_id": "evt-red-test",
                    "event_type": "failed_test",
                    "timestamp": "2026-06-05T00:05:00Z",
                    "source_refs": [high_ref],
                    "load_weight_reviewed": True,
                },
                {
                    "event_id": "evt-ordinary",
                    "event_type": "clarification",
                    "timestamp": "2026-06-05T00:10:00Z",
                    "source_refs": [ordinary_ref],
                },
            ],
            now="2026-06-06T00:00:00Z",
        )

        ranked = sidecar.apply_cognitive_load_boosts(
            [
                {
                    "candidate_id": "ordinary-keyword-match",
                    "source_refs": [ordinary_ref],
                    "semantic_score": 0.82,
                    "source_authority": 0.9,
                },
                {
                    "candidate_id": "expensive-debugging-pitfall",
                    "source_refs": [high_ref],
                    "semantic_score": 0.74,
                    "source_authority": 0.92,
                },
            ],
            payload,
        )

        self.assertEqual(ranked[0]["candidate_id"], "expensive-debugging-pitfall")
        self.assertLessEqual(ranked[0]["score_breakdown"]["cognitive_load_boost"], 0.16)
        self.assertIn("semantic_score", ranked[0]["score_breakdown"])
        self.assertIn("source_authority", ranked[0]["score_breakdown"])
        self.assertIn("cognitive_load_boost", ranked[0]["score_breakdown"])
        self.assertEqual(payload["metrics"]["high_load_source_reopen_rate"], 0.333333)
        self.assertEqual(payload["metrics"]["caution_hint_useful_rate"], 1.0)
        self.assertEqual(payload["metrics"]["load_weight_false_positive_rate"], 0.0)
        self.assertEqual(
            ranked[0]["cognitive_load"]["projection_boundary"],
            "routing_caution_not_affect_or_personality_truth",
        )
        self.assertIn("source_reopen_recommended", ranked[0]["cognitive_load"]["advisory_action"])

    def test_load_signal_cannot_override_weak_superseded_or_untrusted_source(self) -> None:
        ref = {"source_id": "thread:superseded", "message_id": "m-old", "line": 9}
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-rollback",
                    "event_type": "rollback_or_revert",
                    "timestamp": "2026-05-25T00:00:00Z",
                    "source_refs": [ref],
                    "superseded_by_source_ref": {"source_id": "thread:newer", "message_id": "m-new"},
                }
            ],
            now="2026-06-06T00:00:00Z",
        )

        ranked = sidecar.apply_cognitive_load_boosts(
            [
                {
                    "candidate_id": "stale-high-load-source",
                    "source_refs": [ref],
                    "semantic_score": 0.91,
                    "source_authority": 0.2,
                    "source_status": "superseded",
                }
            ],
            payload,
        )

        self.assertEqual(ranked[0]["score_breakdown"]["cognitive_load_boost"], 0.0)
        self.assertEqual(ranked[0]["cognitive_load"]["advisory_action"], "refresh_sources")
        self.assertIn("source_truth_not_overridden", ranked[0]["cognitive_load"]["cannot_claim"])
        self.assertEqual(payload["metrics"]["invalidated_entry_count"], 1)

    def test_public_projection_omits_raw_paths_and_emotion_or_personality_claims(self) -> None:
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-private",
                    "event_type": "failed_command",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [
                        {
                            "source_id": "thread:private",
                            "message_id": "m-private",
                            "line": 12,
                            "path": "C:\\Users\\private\\raw-rollout.jsonl",
                        }
                    ],
                    "raw_note": "The user was stressed and has an anxious personality.",
                }
            ],
            now="2026-06-06T00:00:00Z",
        )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertFalse(payload["privacy_boundary"]["raw_paths_emitted"])
        self.assertFalse(payload["privacy_boundary"]["emotion_or_personality_claims_emitted"])
        self.assertEqual(payload["metrics"]["overpersonalization_from_load_signal_count"], 0)
        self.assertIn("cognitive_load_as_affect_or_user_trait", payload["cannot_claim"])
        self.assertNotIn("C:\\Users\\private", encoded)
        self.assertNotIn("stressed", encoded)
        self.assertNotIn("anxious personality", encoded)


if __name__ == "__main__":
    unittest.main()
