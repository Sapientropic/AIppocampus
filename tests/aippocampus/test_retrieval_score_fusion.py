from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import retrieval_score_fusion as fusion  # noqa: E402


def source_ref(message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": "session:fusion-test",
        "message_id": message_id,
        "source_line": line,
    }


class RetrievalScoreFusionTests(unittest.TestCase):
    def test_exact_quote_context_keeps_text_priority_over_vector_and_graph(self) -> None:
        payload = fusion.blend(
            [
                {
                    "source_id": "message:exact",
                    "text_score": 100.0,
                    "vector_score": 0.10,
                    "graph_score": 0.05,
                    "source_refs": [source_ref("exact", 10)],
                },
                {
                    "source_id": "message:semantic-neighbor",
                    "text_score": 18.0,
                    "vector_score": 1.0,
                    "graph_score": 1.0,
                    "source_refs": [source_ref("neighbor", 20)],
                },
            ],
            context="exact_quote",
        )

        ranked = payload["ranked"]

        self.assertEqual(ranked[0]["source_id"], "message:exact")
        self.assertIn("exact_text_guard", ranked[0]["score_components"])
        self.assertEqual(payload["weights"]["text"], fusion.CONTEXT_WEIGHTS["exact_quote"]["text"])
        self.assertTrue(ranked[0]["source_boundary"]["ranking_scores_are_not_truth"])

    def test_question_tracking_context_can_use_vector_neighborhood_after_source_join(self) -> None:
        payload = fusion.blend(
            [
                {
                    "source_id": "question:lexical",
                    "text_score": 75.0,
                    "vector_score": 0.10,
                    "source_refs": [source_ref("lexical", 30)],
                },
                {
                    "source_id": "question:neighbor",
                    "text_score": 30.0,
                    "vector_score": 0.98,
                    "source_refs": [source_ref("neighbor", 40)],
                },
            ],
            context="question_tracking",
        )

        self.assertEqual(payload["ranked"][0]["source_id"], "question:neighbor")
        self.assertGreater(
            payload["ranked"][0]["score_components"]["vector"],
            payload["ranked"][0]["score_components"]["text"],
        )
        self.assertEqual(payload["skipped"], [])

    def test_theme_emergence_context_can_lean_on_graph_proximity(self) -> None:
        payload = fusion.blend(
            [
                {
                    "source_id": "theme:text",
                    "text_score": 80.0,
                    "graph_score": 0.05,
                    "source_refs": [source_ref("text", 50)],
                },
                {
                    "source_id": "theme:graph",
                    "text_score": 25.0,
                    "graph_score": 0.95,
                    "source_refs": [source_ref("graph", 60)],
                },
            ],
            context="theme_emergence",
        )

        self.assertEqual(payload["ranked"][0]["source_id"], "theme:graph")
        self.assertGreater(
            payload["ranked"][0]["score_components"]["graph"],
            payload["ranked"][0]["score_components"]["text"],
        )

    def test_optional_vectors_can_be_unavailable_without_hiding_text_fallback(self) -> None:
        payload = fusion.blend(
            [
                {
                    "source_id": "message:text",
                    "text_score": 42.0,
                    "source_refs": [source_ref("text", 70)],
                },
                {
                    "source_id": "message:graph",
                    "text_score": 12.0,
                    "graph_score": 0.30,
                    "source_refs": [source_ref("graph", 80)],
                },
            ],
            context="question_tracking",
            vectors_available=False,
        )

        self.assertEqual(payload["weights"]["vector"], 0.0)
        self.assertEqual(payload["ranked"][0]["source_id"], "message:text")
        self.assertTrue(payload["policy_boundary"]["vectors_optional"])

    def test_vector_or_graph_candidates_without_source_join_are_skipped(self) -> None:
        payload = fusion.blend(
            [
                {"score_kind": "vector", "score": 1.0},
                {
                    "source_id": "message:safe",
                    "text_score": 5.0,
                    "vector_score": 0.2,
                    "source_refs": [source_ref("safe", 90)],
                },
            ],
            context="question_tracking",
        )

        self.assertEqual(len(payload["ranked"]), 1)
        self.assertEqual(payload["ranked"][0]["source_id"], "message:safe")
        self.assertEqual(payload["skipped"][0]["reason"], "missing_stable_source_join")

    def test_message_id_join_is_thread_scoped_and_sqlite_id_is_ignored(self) -> None:
        payload = fusion.blend(
            [
                {
                    "id": 1,
                    "thread_key": "session:fusion-test",
                    "message_id": "msg-1",
                    "text_score": 10.0,
                    "source_refs": [source_ref("msg-1", 100)],
                },
                {
                    "id": 2,
                    "text_score": 99.0,
                },
            ]
        )

        self.assertEqual(payload["ranked"][0]["source_id"], "session:fusion-test:message_id:msg-1")
        self.assertEqual(payload["skipped"][0]["reason"], "missing_stable_source_join")

    def test_text_score_helper_matches_existing_retrieval_formula(self) -> None:
        score = fusion.retrieval_text_score(
            {"fts": 80.0, "rag_chunk": 7.0},
            literal_hits=2,
            expanded_hits=5,
            anchor_hits=3,
            phase_weight=18.0,
        )

        self.assertEqual(score, 143.5)


if __name__ == "__main__":
    unittest.main()
