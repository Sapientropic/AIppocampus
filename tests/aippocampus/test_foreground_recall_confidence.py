from __future__ import annotations

import unittest

from aippocampus_runtime.recall.foreground_confidence import (
    foreground_recall_confidence_decision,
)


class ForegroundRecallConfidenceTests(unittest.TestCase):
    def test_cue_only_overlap_below_floor_refines_instead_of_emit(self) -> None:
        decision = foreground_recall_confidence_decision(
            prompt="关于记忆检索还有印象吗",
            candidates=[{"route_id": "route:generic", "score": 0.12}],
            working_memory_matches=[],
            query_terms=["记忆", "检索"],
            explicit=[],
            associative=["记忆"],
            cognitive_map_matches=[],
            semantic_memory_cue=False,
            positive_evidence_intent=False,
            has_memory_cue=True,
            suppressed=False,
            top_score=0.12,
            working_score=0.0,
            scent_threshold=0.4,
        )

        self.assertFalse(decision["emit"])
        self.assertEqual(decision["decision"], "refine_low_specificity")
        self.assertIn("cue_only_below_confidence_floor", decision["reason_codes"])
        self.assertEqual(decision["claim_permission"], "no_claim_before_reopen")

    def test_fallback_only_candidate_below_floor_refines(self) -> None:
        decision = foreground_recall_confidence_decision(
            prompt="还记得 workflow 吗",
            candidates=[{"thread_key": "thread:fallback", "fallback": True, "score": 0.2}],
            working_memory_matches=[],
            query_terms=["workflow"],
            explicit=[],
            associative=["记得"],
            cognitive_map_matches=[],
            semantic_memory_cue=False,
            positive_evidence_intent=False,
            has_memory_cue=True,
            suppressed=False,
            top_score=0.2,
            working_score=0.0,
            scent_threshold=0.5,
        )

        self.assertFalse(decision["emit"])
        self.assertIn("fallback_only_below_confidence_floor", decision["reason_codes"])

    def test_empty_zero_score_candidate_refines(self) -> None:
        decision = foreground_recall_confidence_decision(
            prompt="找一下旧线索",
            candidates=[{"route_id": "route:zero", "score": 0.0}],
            working_memory_matches=[],
            query_terms=["旧线索"],
            explicit=["找"],
            associative=[],
            cognitive_map_matches=[],
            semantic_memory_cue=False,
            positive_evidence_intent=False,
            has_memory_cue=True,
            suppressed=False,
            top_score=0.0,
            working_score=0.0,
            scent_threshold=0.5,
        )

        self.assertFalse(decision["emit"])
        self.assertIn("zero_score_below_confidence_floor", decision["reason_codes"])

    def test_explicit_source_route_still_emits_confidently(self) -> None:
        decision = foreground_recall_confidence_decision(
            prompt="请 reopen 上次 source-backed 结论",
            candidates=[
                {
                    "thread_key": "thread:source",
                    "source_refs": [{"thread_key": "thread:source", "source_id": "src"}],
                    "score": 0.18,
                }
            ],
            working_memory_matches=[],
            query_terms=["source-backed"],
            explicit=["reopen"],
            associative=[],
            cognitive_map_matches=[],
            semantic_memory_cue=False,
            positive_evidence_intent=True,
            has_memory_cue=True,
            suppressed=False,
            top_score=0.18,
            working_score=0.0,
            scent_threshold=0.5,
        )

        self.assertTrue(decision["emit"])
        self.assertEqual(decision["decision"], "emit_confident_route")
        self.assertIn("reopenable_route_shape_present", decision["reason_codes"])

if __name__ == "__main__":
    unittest.main()
