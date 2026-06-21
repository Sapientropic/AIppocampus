from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

benchmark = import_benchmark_module("benchmark_source_evidence_retrieval")

class StandardLineRerankerContractTests(unittest.TestCase):
    def test_semantic_line_reranker_prompt_excludes_gold_scoring_fields(self) -> None:
        messages = benchmark.semantic_line_reranker_messages(
            question="Where did the public marker appear?",
            candidates=[
                {
                    "line": 7,
                    "role": "user",
                    "session_rank": 1,
                    "nearest_hit_rank": 1,
                    "context_distance": 0,
                    "text": "The public marker appears in the visible source line.",
                    "has_answer": True,
                    "expected_lines": [7],
                    "answer": "hidden gold answer marker",
                }
            ],
        )

        dumped = json.dumps(messages, ensure_ascii=False)
        self.assertIn("llm-window-to-line-rerank-v1", dumped)
        self.assertIn("The public marker appears", dumped)
        self.assertNotIn("hidden gold answer marker", dumped)
        self.assertNotIn("has_answer", dumped)
        self.assertNotIn("expected_lines", dumped)
        self.assertNotIn("miss_taxonomy", dumped)

    def test_semantic_reranker_output_is_filtered_to_candidate_lines(self) -> None:
        ranked = benchmark.ranked_unique_lines(
            [999, 2, 2, 1],
            [{"line": 1}, {"line": 2}],
        )

        self.assertEqual(ranked, [2, 1])

    def test_line_reranker_failure_is_diagnostic_not_baseline_failure(self) -> None:
        def timeout_reranker(
            question: str,
            candidates: list[dict],
            **_: object,
        ) -> dict:
            self.assertIn("blue orchard", question)
            self.assertTrue(candidates)
            raise TimeoutError("model request timed out")

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=1,
                    role="user",
                    text="The blue orchard code was 917.",
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])
            case = {
                "case_id": "rerank-failure",
                "dataset": "synthetic",
                "case_type": "single_session_user_fact",
                "source_id_sha1": "source",
                "question_id_sha1": "question",
                "query": "What was the blue orchard code?",
                "query_sha1": "query",
                "query_terms": ["blue", "orchard", "code"],
                "sqlite_path": sqlite_path,
                "expected": {
                    "lines": [1],
                    "sessions": ["D1"],
                    "line_to_session": {"1": "D1"},
                    "has_line_evidence": True,
                },
            }

            row = benchmark.evaluate_standard_retrieval_case(
                case,
                top_k=1,
                candidate_limit=8,
                context_radius=0,
                include_private_text=False,
                line_reranker_mode="custom",
                line_reranker_fn=timeout_reranker,
            )

        self.assertTrue(row["evidence_hit_top1"])
        self.assertTrue(row["reranked_evidence_hit_top1"])
        self.assertEqual(row["line_reranker_error_kinds"], ["timeout"])
        self.assertEqual(row["line_reranker_error_count"], 1)
        metrics = benchmark.summarize_standard_retrieval_results(
            [row],
            top_k=1,
            context_radius=0,
        )
        self.assertEqual(metrics["line_reranker_error_kind_counts"]["timeout"], 1)
        self.assertEqual(metrics["evidence_hit_rate_top1"], 1.0)

if __name__ == "__main__":
    unittest.main()
