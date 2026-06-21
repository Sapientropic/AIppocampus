from __future__ import annotations

import unittest

import simulate_multilingual_prompt_hook as smoke


class MultilingualPromptHookSmokeTests(unittest.TestCase):
    def test_seeded_and_unseeded_reports_have_different_claim_boundaries(self) -> None:
        rows = [{"ok": True, "name": "ru_memory"}, {"ok": False, "name": "ru_code"}]

        seeded = smoke.summarize_rows(
            rows,
            seeded_semantic_cues=True,
            semantic_gate="off",
        )
        unseeded = smoke.summarize_rows(
            rows,
            seeded_semantic_cues=False,
            semantic_gate="off",
        )

        self.assertEqual(seeded["passed"], 1)
        self.assertEqual(seeded["total"], 2)
        self.assertEqual(seeded["coverage_mode"], "seeded_semantic_cue_reuse")
        self.assertIn(
            "cold_natural_multilingual_recall_quality",
            seeded["cannot_claim"],
        )
        self.assertEqual(unseeded["coverage_mode"], "unseeded_local_fallback")
        self.assertIn("seeded_cue_cache_reuse_quality", unseeded["cannot_claim"])
        self.assertIn(
            "live_semantic_gate_quality",
            unseeded["cannot_claim"],
        )

if __name__ == "__main__":
    unittest.main()
