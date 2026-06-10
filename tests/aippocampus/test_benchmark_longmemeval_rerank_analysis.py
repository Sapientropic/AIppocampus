from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (BENCHMARKS,):
    sys.path.insert(0, str(_path))

import benchmark_longmemeval_rerank_analysis as analysis  # noqa: E402


def _fixture_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "aippocampus_longmemeval_benchmark",
        "status": "retrieval_sufficient",
        "ok": True,
        "generated_at": "2026-06-10T00:00:00Z",
        "benchmark": {
            "split": "longmemeval-v1-small",
            "dataset_version": "longmemeval-cleaned 2025-09",
            "dataset_url": "https://example.test/longmemeval_s_cleaned.json",
            "local_path_sha1": "abc123",
        },
        "evaluation": {
            "mode": "retrieval_only",
            "line_reranker_mode": "semantic",
            "top_k": 10,
            "llm_rerank_arm": {
                "arm": "llm_window_to_line_rerank",
                "prompt_version": "llm-window-to-line-rerank-v1",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "input_boundary": {
                    "withheld_from_model": [
                        "gold_answer",
                        "expected_lines",
                        "miss_taxonomy",
                    ]
                },
            },
        },
        "metrics": {
            "question_count": 3,
            "evidence_line_case_count": 3,
            "evidence_hit_top10": 2,
            "evidence_hit_rate_top10": 0.6667,
            "evidence_mrr": 0.5,
            "reranked_evidence_hit_top10": 2,
            "reranked_evidence_hit_rate_top10": 0.6667,
            "reranked_evidence_mrr": 0.6667,
            "line_reranker_attempted_count": 3,
            "line_reranker_available_count": 3,
            "line_reranker_error_count": 0,
            "line_reranker_usage": {
                "total_tokens": 3000,
                "prompt_cache_hit_tokens": 900,
                "prompt_cache_miss_tokens": 2100,
            },
            "line_reranker_latency_ms": {"count": 3, "avg": 1000.0, "max": 2000.0},
            "line_reranker_cache": {"hit_rate": 0.3},
            "line_reranker_metadata": {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "prompt_version": "llm-window-to-line-rerank-v1",
                "cost_status": "provider_cost_not_reported",
            },
        },
        "cases": [
            {
                "case_id": "case-a",
                "case_type": "longmemeval_single-session-user",
                "evidence_rank": 12,
                "evidence_rank_bucket": "rank_11_20",
                "evidence_hit_top10": False,
                "evidence_context_rescue_top10": True,
                "same_session_wrong_line_top10": True,
                "reranked_evidence_rank": 1,
                "reranked_evidence_hit_top10": True,
                "semantic_bridge_lift_top10": True,
                "line_reranker_error_kinds": [],
            },
            {
                "case_id": "case-b",
                "case_type": "longmemeval_multi-session",
                "evidence_rank": 1,
                "evidence_rank_bucket": "rank_1",
                "evidence_hit_top10": True,
                "evidence_context_rescue_top10": False,
                "same_session_wrong_line_top10": False,
                "reranked_evidence_rank": 21,
                "reranked_evidence_hit_top10": False,
                "semantic_bridge_lift_top10": False,
                "line_reranker_error_kinds": [],
            },
            {
                "case_id": "case-c",
                "case_type": "longmemeval_multi-session",
                "evidence_rank": None,
                "evidence_rank_bucket": "not_retrieved",
                "evidence_hit_top10": False,
                "evidence_context_rescue_top10": False,
                "same_session_wrong_line_top10": False,
                "reranked_evidence_rank": None,
                "reranked_evidence_hit_top10": False,
                "semantic_bridge_lift_top10": False,
                "line_reranker_error_kinds": ["timeout"],
            },
        ],
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["answer_generation_quality"],
    }


class LongMemEvalRerankAnalysisTests(unittest.TestCase):
    def test_analysis_adds_ladder_taxonomy_and_budget_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "semantic-pilot.json"
            report_path.write_text(json.dumps(_fixture_report()), encoding="utf-8")

            payload = analysis.analyze_rerank_report(report_path, full_run_questions=500)

        self.assertEqual(payload["kind"], "aippocampus_longmemeval_rerank_analysis")
        self.assertEqual(payload["status"], "pilot_analyzed_full_run_not_default")
        self.assertEqual(
            payload["metrics"]["baseline_evidence_recall_by_k"]["r_at_10"]["numerator"],
            1,
        )
        self.assertEqual(
            payload["metrics"]["reranked_evidence_recall_by_k"]["r_at_1"]["numerator"],
            1,
        )
        self.assertEqual(payload["metrics"]["semantic_bridge_lift_top10"], 1)
        self.assertEqual(payload["metrics"]["rerank_regression_count_top10"], 1)
        self.assertEqual(payload["metrics"]["context_visible_rescue_conversion_count"], 1)
        self.assertEqual(payload["metrics"]["same_session_wrong_line_reduction_count"], 1)
        self.assertIn("rank_11_20->rank_1", payload["metrics"]["rank_bucket_movement_counts"])
        self.assertIn(
            "longmemeval_multi-session",
            payload["metrics"]["per_case_type"],
        )
        projection = payload["full_500_projection"]
        self.assertEqual(projection["projected_total_tokens"], 500000)
        self.assertEqual(projection["decision"], "not_run_by_default")
        self.assertIn("explicit_operator_budget_approval", projection["required_before_full_run"])

    def test_analysis_output_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "semantic-pilot.json"
            report_path.write_text(json.dumps(_fixture_report()), encoding="utf-8")

            payload = analysis.analyze_rerank_report(report_path)

        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["snippets_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertNotIn(str(REPO_ROOT), rendered)
        self.assertNotIn("longmemeval_s_cleaned.json", rendered)
        self.assertNotIn("case-a", rendered)


if __name__ == "__main__":
    unittest.main()
