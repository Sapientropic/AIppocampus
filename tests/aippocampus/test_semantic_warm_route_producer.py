from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import semantic_warm_route_producer as producer  # noqa: E402


class SemanticWarmRouteProducerTests(unittest.TestCase):
    def test_warmed_semantic_material_routes_through_hot_router_without_truth_upgrade(self) -> None:
        report = producer.build_semantic_warm_route_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        packet = by_id["semantic_warmed_reopenable_route"]["packet"]
        votes = {vote["head"]: vote for vote in packet["head_votes"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["metrics"]["semantic_warm_route_token_count"], 3)
        self.assertEqual(report["metrics"]["semantic_warm_route_packet_count"], 3)
        self.assertEqual(packet["output_mode"], "reopenable_route")
        self.assertEqual(packet["action_grammar"], "reopenable_route")
        self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
        self.assertGreater(votes["semantic_head"]["score"], 0.8)
        self.assertEqual(report["red_lines"]["semantic_route_used_as_truth_count"], 0)

    def test_hard_masks_beat_high_semantic_relevance(self) -> None:
        report = producer.build_semantic_warm_route_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        packet = by_id["semantic_privacy_guard_masked"]["packet"]
        votes = {vote["head"]: vote for vote in packet["head_votes"]}

        self.assertEqual(packet["output_mode"], "silence")
        self.assertEqual(packet["claim_permission"], "blocked")
        self.assertFalse(packet["emitted"])
        self.assertIn("privacy_domain", packet["masks_applied"])
        self.assertGreater(votes["semantic_head"]["score"], 0.9)
        self.assertEqual(report["metrics"]["hard_mask_overrode_semantic_relevance_count"], 1)
        self.assertEqual(report["red_lines"]["masked_source_resurrection_count"], 0)

    def test_foreground_budget_uses_materialized_routes_without_fresh_semantic_calls(self) -> None:
        report = producer.build_semantic_warm_route_fixture_report()
        budget = report["foreground_budget"]

        self.assertFalse(budget["tier0_foreground"]["fresh_model_calls_allowed"])
        self.assertFalse(budget["tier1_foreground_warm_read"]["fresh_model_calls_allowed"])
        self.assertTrue(budget["tier1_foreground_warm_read"]["materialized_route_read_allowed"])
        self.assertEqual(report["metrics"]["foreground_fresh_semantic_call_count"], 0)
        self.assertEqual(report["metrics"]["foreground_semantic_budget_violation_count"], 0)

    def test_topic_epoch_reuse_and_roi_do_not_depend_on_raw_prompt_fuzzy_matching(self) -> None:
        report = producer.build_semantic_warm_route_fixture_report()
        roi = {row["scout_family"]: row for row in report["roi_status"]}

        self.assertEqual(report["metrics"]["semantic_cache_hit_count"], 1)
        self.assertEqual(report["metrics"]["semantic_related_cache_hit_count"], 1)
        self.assertEqual(report["metrics"]["topic_epoch_reuse_by_fingerprint_count"], 1)
        self.assertEqual(report["metrics"]["raw_prompt_fuzzy_match_count"], 0)
        self.assertEqual(roi["semantic_expander"]["router_action"], "diagnostic_only")
        self.assertEqual(roi["privacy_boundary_guard"]["router_action"], "guard_required")
        self.assertEqual(report["metrics"]["guard_family_retired_count"], 0)

    def test_public_debug_output_redacts_private_material(self) -> None:
        report = producer.build_semantic_warm_route_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertFalse(report["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["local_paths_emitted"])
        self.assertFalse(report["privacy_boundary"]["raw_semantic_model_reasoning_emitted"])
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("RAW_MODEL_REASONING_SENTINEL", encoded)


if __name__ == "__main__":
    unittest.main()
