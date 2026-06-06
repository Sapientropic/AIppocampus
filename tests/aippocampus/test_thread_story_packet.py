from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.reflection import thread_story  # noqa: E402


class ThreadStoryPacketTests(unittest.TestCase):
    def test_source_backed_packet_keeps_story_private_and_navigation_only(self) -> None:
        payload = thread_story.run_thread_story_packet_fixture()

        self.assertTrue(payload["ok"], json.dumps(payload, ensure_ascii=False, indent=2))
        self.assertEqual(payload["kind"], "aippocampus_thread_story_packet_fixture")
        packet = payload["packet"]
        visible = packet["agent_visible"]

        self.assertEqual(packet["kind"], "aippocampus_thread_story_activation_packet")
        self.assertEqual(packet["authority"], "navigation_only")
        self.assertEqual(packet["freshness"], "current")
        self.assertEqual(packet["sensitivity"], "symbolic_affect_private")
        self.assertEqual(packet["source_ref_count"], 3)
        self.assertTrue(packet["source_refs"])
        self.assertTrue(packet["suppression_boundaries"]["raw_story_text_private"])
        self.assertTrue(packet["suppression_boundaries"]["symbolic_channels_private"])
        self.assertTrue(packet["suppression_boundaries"]["source_reopen_required_for_claims"])
        self.assertTrue(packet["suppression_boundaries"]["not_user_or_persona_model"])

        self.assertEqual(visible["visibility"], "gentle_navigation")
        self.assertIn("Thread-story packets are navigation material", visible["truth_boundary"])
        self.assertNotIn("source_refs", visible)
        self.assertNotIn("hexagram_arc", visible)
        self.assertNotIn("five_tone_arc", visible)
        serialized_visible = json.dumps(visible, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("PRIVATE_THREAD_STORY_SENTINEL", serialized_visible)
        self.assertNotIn("HEX_ARC_PRIVATE_TUN_GE", serialized_visible)
        self.assertNotIn("FIVE_TONE_PRIVATE_GONG_SHANG", serialized_visible)
        self.assertNotIn("C:\\private", serialized_visible)

    def test_negative_controls_suppress_contradiction_and_persona_claims(self) -> None:
        payload = thread_story.run_thread_story_packet_fixture()
        controls = payload["negative_controls"]

        self.assertEqual(
            controls["contradictory_symbolic_arc"]["decision"],
            "source_review_required",
        )
        self.assertEqual(
            controls["persona_claim_attempt"]["decision"],
            "suppressed",
        )
        self.assertEqual(
            controls["multi_channel_interference"]["decision"],
            "backstage_only",
        )
        for control in controls.values():
            self.assertFalse(control.get("agent_visible_emitted", True))
            self.assertTrue(control["source_reopen_required"])
            self.assertTrue(control["private_navigation_only"])

        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("PRIVATE_THREAD_STORY_SENTINEL", serialized)
        self.assertNotIn("The user is always", serialized)
        self.assertNotIn("C:\\private", serialized)

    def test_answer_boundary_probe_blocks_packet_only_factual_answer(self) -> None:
        payload = thread_story.run_thread_story_packet_fixture()
        probe = payload["answer_boundary_probe"]

        self.assertEqual(probe["mode"], "deterministic_opt_in_probe")
        self.assertEqual(probe["packet_only"]["decision"], "source_reopen_required")
        self.assertEqual(probe["source_reopened"]["decision"], "answer_allowed_with_source")
        self.assertIn("live_model_behavioral_equivalence", payload["cannot_claim"])
        self.assertIn("default_recall_or_aar_improvement", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
