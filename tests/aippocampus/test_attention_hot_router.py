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
        self.assertEqual(
            report["score_fusion_policy"]["default_policy"],
            "calibrated_rule_grid_v1",
        )
        self.assertTrue(report["score_fusion_policy"]["hard_masks_outside_scoring"])
        self.assertEqual(masked["output_mode"], "silence")
        self.assertEqual(masked["claim_permission"], "blocked")
        self.assertFalse(masked["emitted"])
        self.assertIn("privacy_domain", masked["masks_applied"])
        self.assertEqual(
            masked["router_diagnostics"]["score_policy"],
            "calibrated_rule_grid_v1",
        )
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

    def test_action_query_features_can_outperform_prompt_only(self) -> None:
        report = router.build_action_head_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        action = by_id["action_path_issue_match"]["packet"]
        action_vote = {vote["head"]: vote for vote in action["head_votes"]}["action_head"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(action["output_mode"], "reopenable_route")
        self.assertEqual(action["claim_permission"], "no_claim_before_reopen")
        self.assertGreater(action_vote["score"], 0.8)
        self.assertIn("pending_path_match", action_vote["reason_code"])
        self.assertIn("issue_id_match", action_vote["reason_code"])
        self.assertIn("action_cue_lift", action["router_diagnostics"]["reason_codes"])
        self.assertEqual(report["metrics"]["action_cue_lift_over_prompt_only_count"], 1)

    def test_action_head_respects_masks_and_anti_nag(self) -> None:
        report = router.build_action_head_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        masked = by_id["action_matched_private_mask"]["packet"]
        suppressed = by_id["action_repeated_hint_suppressed"]["packet"]

        self.assertEqual(masked["output_mode"], "silence")
        self.assertIn("privacy_domain", masked["masks_applied"])
        self.assertGreater(
            {vote["head"]: vote for vote in masked["head_votes"]}["action_head"]["score"],
            0.8,
        )

        self.assertEqual(suppressed["output_mode"], "direction_only")
        self.assertIn("anti_nag_suppressed", suppressed["router_diagnostics"]["reason_codes"])
        self.assertLess(
            suppressed["router_diagnostics"]["raw_score_before_policy_gates"],
            suppressed["router_diagnostics"]["threshold"],
        )
        self.assertEqual(report["metrics"]["anti_nag_suppressed_count"], 1)
        self.assertEqual(report["metrics"]["masked_action_match_emission_count"], 0)
        self.assertNotIn("PRIVATE_TOOL_ARG_SENTINEL", encoded)


if __name__ == "__main__":
    unittest.main()
