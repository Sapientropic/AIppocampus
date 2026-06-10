from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import attention_hot_router as router  # noqa: E402


class AttentionHotRouterTests(unittest.TestCase):
    def test_hard_masks_beat_high_scoring_routes(self) -> None:
        report = router.build_hot_router_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        masked = by_id["masked_high_relevance_private_route"]["packet"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(masked["output_mode"], "silence")
        self.assertEqual(masked["claim_permission"], "blocked")
        self.assertFalse(masked["emitted"])
        self.assertIn("privacy_domain", masked["masks_applied"])
        self.assertGreater(masked["router_diagnostics"]["score"], 0.8)
        self.assertEqual(report["metrics"]["masked_high_score_emission_count"], 0)

    def test_positive_stale_conflict_and_abstention_routes(self) -> None:
        report = router.build_hot_router_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        positive = by_id["positive_source_span_route"]["packet"]
        stale = by_id["stale_conflict_reopen_route"]["packet"]
        abstain = by_id["abstention_direction_only"]["packet"]

        self.assertEqual(positive["output_mode"], "reopenable_route")
        self.assertEqual(positive["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(positive["source_handles"])
        self.assertIn("lexical_head", {vote["head"] for vote in positive["head_votes"]})

        self.assertEqual(stale["output_mode"], "reopenable_route")
        self.assertEqual(stale["claim_permission"], "no_claim_before_reopen")
        self.assertIn("stale_or_conflicted_source_reopen", stale["router_diagnostics"]["reason_codes"])
        self.assertGreaterEqual(stale["router_diagnostics"]["threshold"], 0.6)

        self.assertEqual(abstain["output_mode"], "direction_only")
        self.assertEqual(abstain["claim_permission"], "no_claim_before_reopen")
        self.assertIn("below_adaptive_threshold", abstain["router_diagnostics"]["reason_codes"])
        self.assertEqual(report["metrics"]["claim_ready_without_source_open_count"], 0)
        self.assertNotIn("PRIVATE_ROUTER_TEXT_SENTINEL", encoded)

    def test_adaptive_threshold_rises_for_risk_and_conflict(self) -> None:
        report = router.build_hot_router_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        positive = by_id["positive_source_span_route"]["packet"]["router_diagnostics"]
        stale = by_id["stale_conflict_reopen_route"]["packet"]["router_diagnostics"]

        self.assertLess(positive["threshold"], stale["threshold"])
        self.assertIn("adaptive_threshold", positive)
        self.assertIn("adaptive_threshold", stale)


if __name__ == "__main__":
    unittest.main()
