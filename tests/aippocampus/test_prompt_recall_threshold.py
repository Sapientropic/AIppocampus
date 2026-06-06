from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.prompt_recall_threshold import (  # noqa: E402
    scent_threshold_policy,
)


def _reason_codes(policy: dict) -> set[str]:
    return {
        str(item.get("reason"))
        for item in policy.get("adjustments") or []
        if isinstance(item, dict)
    }


class PromptRecallThresholdTests(unittest.TestCase):
    def test_topic_signal_accumulator_eases_after_repeated_weak_same_topic_turns(self) -> None:
        policy = scent_threshold_policy(
            prompt="qa 这个方向继续看一下",
            thread_id="thread-a",
            topic_epoch="epoch-topic",
            topic_signal_state={
                "status": "hit",
                "weak_signal_count": 3,
                "positive_strength": 3.0,
                "negative_strength": 0.0,
                "topic_fingerprint": "sig_public",
            },
            base_threshold=5.0,
        )

        self.assertLess(policy["effective_threshold"], policy["base_threshold"])
        self.assertIn("topic_signal_accumulator_eased", _reason_codes(policy))
        self.assertEqual(policy["topic_signal_accumulator"]["topic_fingerprint"], "sig_public")
        encoded = json.dumps(policy, ensure_ascii=False)
        self.assertNotIn("qa 这个方向继续看一下", encoded)
        self.assertNotIn("thread-a", encoded)

    def test_negative_topic_signal_and_lock_roi_suppress_default_scent_only(self) -> None:
        suppressed = scent_threshold_policy(
            prompt="qa 这个方向再看看",
            thread_id="thread-a",
            topic_epoch="epoch-topic",
            topic_signal_state={
                "status": "hit",
                "weak_signal_count": 0,
                "positive_strength": 0.0,
                "negative_strength": 3.0,
                "topic_fingerprint": "sig_public",
            },
            route_roi_summary={
                "source_backed_hit_count": 0,
                "wrong_or_stale_route_count": 3,
            },
            base_threshold=5.0,
        )
        explicit = scent_threshold_policy(
            prompt="请帮我找回之前 qa 的那段 source-backed evidence",
            thread_id="thread-a",
            topic_epoch="epoch-topic",
            topic_signal_state={
                "status": "hit",
                "weak_signal_count": 0,
                "positive_strength": 0.0,
                "negative_strength": 3.0,
                "topic_fingerprint": "sig_public",
            },
            route_roi_summary={
                "source_backed_hit_count": 0,
                "wrong_or_stale_route_count": 3,
            },
            explicit_recall_intent=True,
            base_threshold=5.0,
        )

        self.assertGreater(suppressed["effective_threshold"], suppressed["base_threshold"])
        self.assertIn("topic_signal_negative_roi_suppressed", _reason_codes(suppressed))
        self.assertIn("active_lock_roi_suppressed", _reason_codes(suppressed))
        self.assertEqual(explicit["effective_threshold"], explicit["base_threshold"])
        self.assertNotIn("topic_signal_negative_roi_suppressed", _reason_codes(explicit))
        self.assertNotIn("active_lock_roi_suppressed", _reason_codes(explicit))

    def test_source_backed_lock_roi_reinforces_route_without_evidence_promotion(self) -> None:
        policy = scent_threshold_policy(
            prompt="qa 这个方向再看看",
            thread_id="thread-a",
            topic_epoch="epoch-topic",
            route_roi_summary={
                "source_backed_hit_count": 2,
                "wrong_or_stale_route_count": 0,
            },
            base_threshold=5.0,
        )

        self.assertLess(policy["effective_threshold"], policy["base_threshold"])
        self.assertIn("active_lock_roi_reinforced", _reason_codes(policy))
        self.assertEqual(policy["risk_boundary"], "normal")
        self.assertEqual(policy["route_roi_summary"]["source_backed_hit_count"], 2)


if __name__ == "__main__":
    unittest.main()
