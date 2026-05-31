import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import retrieval, score_fusion, segment_search  # noqa: E402
from aippocampus_runtime.recall.scoring_policy import (  # noqa: E402
    ACTIVE_RECALL_POLICY,
    PHASE_WEIGHT_POLICY,
    RAG_CHUNK_TEXT_POLICY,
    RETRIEVAL_DIVERSITY_POLICY,
    RETRIEVAL_TEXT_POLICY,
    SEGMENT_MERGE_POLICY,
)


class RecallScoringPolicyTests(unittest.TestCase):
    def _row(self, *, role: str, phase: str = "", is_final: int = 0) -> sqlite3.Row:
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.execute("CREATE TABLE messages (role TEXT, phase TEXT, is_final INTEGER)")
            con.execute(
                "INSERT INTO messages (role, phase, is_final) VALUES (?, ?, ?)",
                (role, phase, is_final),
            )
            return con.execute("SELECT role, phase, is_final FROM messages").fetchone()
        finally:
            con.close()

    def test_phase_weight_policy_names_source_preference(self) -> None:
        self.assertGreater(PHASE_WEIGHT_POLICY.final_answer, PHASE_WEIGHT_POLICY.user)
        self.assertLess(PHASE_WEIGHT_POLICY.commentary, 0.0)
        self.assertLess(PHASE_WEIGHT_POLICY.tool, PHASE_WEIGHT_POLICY.commentary)

        self.assertEqual(
            retrieval.phase_weight(self._row(role="assistant", phase="final_answer")),
            PHASE_WEIGHT_POLICY.final_answer,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="user")),
            PHASE_WEIGHT_POLICY.user,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="assistant", phase="commentary")),
            PHASE_WEIGHT_POLICY.commentary,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="tool")),
            PHASE_WEIGHT_POLICY.tool,
        )

    def test_text_score_helpers_read_named_policy_values(self) -> None:
        text_score = score_fusion.retrieval_text_score(
            {"fts": 5.0, "rag_chunk": 2.0},
            literal_hits=2,
            expanded_hits=5,
            anchor_hits=3,
            phase_weight=PHASE_WEIGHT_POLICY.final_answer,
        )
        self.assertEqual(
            text_score,
            5.0
            + 2.0
            + 2 * RETRIEVAL_TEXT_POLICY.literal_hit
            + 3 * RETRIEVAL_TEXT_POLICY.expanded_hit
            + 3 * RETRIEVAL_TEXT_POLICY.anchor_hit
            + PHASE_WEIGHT_POLICY.final_answer,
        )

        chunk_score = score_fusion.rag_chunk_text_score(
            {"chunk_fts": 4.0, "chunk_literal_scan": RAG_CHUNK_TEXT_POLICY.literal_scan_signal},
            literal_hits=1,
            expanded_hits=4,
            anchor_hits=2,
        )
        self.assertEqual(
            chunk_score,
            4.0
            + RAG_CHUNK_TEXT_POLICY.literal_scan_signal
            + RAG_CHUNK_TEXT_POLICY.literal_hit
            + 3 * RAG_CHUNK_TEXT_POLICY.expanded_hit
            + 2 * RAG_CHUNK_TEXT_POLICY.anchor_hit,
        )

    def test_active_recall_policy_names_decision_bands(self) -> None:
        self.assertLess(ACTIVE_RECALL_POLICY.search_threshold, ACTIVE_RECALL_POLICY.high_threshold)

        medium = retrieval.active_recall_decision(
            "请帮我回忆一下之前那个实现边界",
            [],
            None,
        )
        self.assertEqual(medium["decision"], "search")
        self.assertEqual(medium["confidence"], "medium")
        self.assertGreaterEqual(medium["score"], ACTIVE_RECALL_POLICY.search_threshold)
        self.assertLess(medium["score"], ACTIVE_RECALL_POLICY.high_threshold)

        high = retrieval.active_recall_decision(
            "继续之前那个记忆和上下文相关的长期项目",
            [{"title": "长期项目", "score": 12.0}],
            {"index": {"stale": True}, "checkpoint": {"due": True}},
        )
        self.assertEqual(high["decision"], "search")
        self.assertEqual(high["confidence"], "high")
        self.assertGreaterEqual(high["score"], ACTIVE_RECALL_POLICY.high_threshold)

    def test_diversity_policy_keeps_one_nearby_bucket_from_crowding_out_source_hits(self) -> None:
        self.assertGreater(RETRIEVAL_DIVERSITY_POLICY.bucket_repeat_penalty, 0.0)
        self.assertGreater(RETRIEVAL_DIVERSITY_POLICY.nearby_line_penalty, 0.0)

        selected = retrieval.diversify_results(
            [
                {"id": 1, "line": 10, "role": "assistant", "score": 100.0, "signals": {}},
                {"id": 2, "line": 20, "role": "assistant", "score": 99.0, "signals": {}},
                {"id": 3, "line": 450, "role": "assistant", "score": 88.0, "signals": {}},
            ],
            limit=2,
        )

        self.assertEqual([item["id"] for item in selected], [1, 3])

    def test_segment_merge_policy_keeps_one_segment_from_crowding_out_other_hits(self) -> None:
        self.assertGreater(SEGMENT_MERGE_POLICY.same_segment_penalty, 0.0)
        self.assertGreater(SEGMENT_MERGE_POLICY.nearby_line_penalty, 0.0)

        selected = segment_search.merge_topk(
            [
                {
                    "segment_id": "seg-a",
                    "id": 1,
                    "line": 10,
                    "role": "assistant",
                    "phase": "final_answer",
                    "score": 50.0,
                    "signals": {},
                },
                {
                    "segment_id": "seg-a",
                    "id": 2,
                    "line": 20,
                    "role": "assistant",
                    "score": 49.0,
                    "signals": {},
                },
                {
                    "segment_id": "seg-b",
                    "id": 1,
                    "line": 300,
                    "role": "assistant",
                    "score": 43.0,
                    "signals": {},
                },
            ],
            limit=2,
        )

        self.assertEqual([item["segment_id"] for item in selected], ["seg-a", "seg-b"])


if __name__ == "__main__":
    unittest.main()
