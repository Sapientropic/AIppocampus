from __future__ import annotations

import unittest

from tools.aippocampus.smoke import smoke_source_semantic_candidate_recall as smoke


class SourceSemanticCandidateRecallEvalTests(unittest.TestCase):
    def test_recorded_semantic_candidates_show_fuzzy_lift_with_source_anchor_hits(self) -> None:
        payload = smoke.evaluate_source_semantic_candidates(recorded=True)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertEqual(payload["mode"], "recorded_semantic_candidates")
        self.assertEqual(payload["metrics"]["semantic_lift_count"], 2)
        self.assertEqual(payload["metrics"]["source_reopen_success_count"], 2)
        self.assertEqual(payload["metrics"]["anchor_hit_success_count"], 2)
        self.assertEqual(payload["metrics"]["false_positive_count"], 0)
        self.assertEqual(payload["metrics"]["live_model_call_count"], 0)
        self.assertTrue(
            all(
                case.get("claim_authority") in {None, "navigation_only"}
                for case in payload["cases"]
            )
        )

    def test_no_key_mode_reports_semantic_worker_unavailable_without_quality_claim(self) -> None:
        payload = smoke.evaluate_source_semantic_candidates(recorded=False)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "semantic_worker_unavailable")
        self.assertEqual(payload["mode"], "deterministic_no_key")
        self.assertTrue(payload["semantic_worker_unavailable"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["metrics"]["semantic_lift_count"], 0)
        self.assertIn("full_live_semantic_recall", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
