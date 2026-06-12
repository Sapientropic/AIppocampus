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


def _structural_report() -> dict[str, object]:
    report = _fixture_report()
    report["evaluation"] = {
        "mode": "retrieval_only",
        "line_reranker_mode": "structural",
        "top_k": 10,
    }
    report["metrics"] = {
        "question_count": 3,
        "evidence_line_case_count": 3,
        "evidence_hit_top10": 1,
        "evidence_hit_rate_top10": 0.3333,
        "evidence_mrr": 0.5,
        "reranked_evidence_hit_top10": 2,
        "reranked_evidence_hit_rate_top10": 0.6667,
        "reranked_evidence_mrr": 0.75,
        "line_reranker_attempted_count": 3,
        "line_reranker_available_count": 3,
        "line_reranker_error_count": 0,
        "line_reranker_candidate_count_avg": 12.5,
        "line_reranker_usage": {"local_scored_candidates": 36},
        "line_reranker_latency_ms": {"count": 0},
        "line_reranker_cache": {},
        "line_reranker_metadata": {},
    }
    report["cases"] = [
        {
            "case_type": "longmemeval_single-session-user",
            "evidence_rank": 12,
            "evidence_rank_bucket": "rank_11_20",
            "evidence_hit_top10": False,
            "evidence_context_rescue_top10": True,
            "same_session_wrong_line_top10": True,
            "line_reranker_candidate_contains_evidence": True,
            "source_joined_candidate_contains_evidence": True,
            "semantic_only_evidence_rank": 1,
            "reranked_evidence_rank": 1,
            "semantic_bridge_lift_top10": True,
            "line_reranker_error_kinds": [],
            "evidence_miss_category": "context_visible_exact_line_miss",
        },
        {
            "case_type": "longmemeval_multi-session",
            "evidence_rank": 8,
            "evidence_rank_bucket": "rank_6_10",
            "evidence_hit_top10": True,
            "evidence_context_rescue_top10": False,
            "same_session_wrong_line_top10": False,
            "line_reranker_candidate_contains_evidence": True,
            "source_joined_candidate_contains_evidence": True,
            "semantic_only_evidence_rank": 8,
            "reranked_evidence_rank": 8,
            "semantic_bridge_lift_top10": False,
            "line_reranker_error_kinds": [],
            "evidence_miss_category": "exact_line_found_top_k",
        },
        {
            "case_type": "longmemeval_multi-session",
            "evidence_rank": None,
            "evidence_rank_bucket": "not_retrieved",
            "evidence_hit_top10": False,
            "evidence_context_rescue_top10": False,
            "same_session_wrong_line_top10": False,
            "line_reranker_candidate_contains_evidence": False,
            "source_joined_candidate_contains_evidence": False,
            "semantic_only_evidence_rank": None,
            "reranked_evidence_rank": None,
            "semantic_bridge_lift_top10": False,
            "line_reranker_error_kinds": [],
            "evidence_miss_category": "source_window_not_recovered",
        },
    ]
    return report


def _lexical_baseline_report() -> dict[str, object]:
    report = _structural_report()
    report["evaluation"] = {
        "mode": "retrieval_only",
        "line_reranker_mode": "lexical",
        "top_k": 10,
    }
    report["metrics"] = {
        **dict(report["metrics"]),
        "reranked_evidence_hit_top10": 1,
        "reranked_evidence_hit_rate_top10": 0.3333,
        "reranked_evidence_mrr": 0.5,
        "line_reranker_candidate_count_avg": 11.0,
    }
    cases = list(report["cases"])  # type: ignore[arg-type]
    first_case = dict(cases[0])
    first_case["semantic_only_evidence_rank"] = None
    first_case["reranked_evidence_rank"] = 12
    first_case["semantic_bridge_lift_top10"] = False
    cases[0] = first_case
    report["cases"] = cases
    return report


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

    def test_full_split_analysis_compares_against_lexical_and_distinguishes_cache_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current_path = Path(tmp) / "structural.json"
            lexical_path = Path(tmp) / "lexical.json"
            current_path.write_text(json.dumps(_structural_report()), encoding="utf-8")
            lexical_path.write_text(
                json.dumps(_lexical_baseline_report()),
                encoding="utf-8",
            )

            payload = analysis.analyze_rerank_report(
                current_path,
                baseline_report_path=lexical_path,
                full_run_questions=3,
            )

        self.assertEqual(payload["source_issue"].split("/")[-1], "1193")
        self.assertEqual(payload["status"], "full_split_exact_line_repair_improved")
        comparison = payload["baseline_comparison"]
        self.assertEqual(comparison["baseline_mode"], "lexical")
        self.assertEqual(comparison["reranked_evidence_r_at_10_delta"]["numerator"], 1)
        self.assertEqual(comparison["decision"], "improved_over_baseline")
        self.assertIn(
            "context_visible_exact_line_miss",
            payload["metrics"]["per_miss_taxonomy"],
        )
        self.assertEqual(
            payload["metrics"]["average_candidate_count"],
            12.5,
        )
        cache_paths = payload["semantic_cache_path_evaluation"]
        self.assertIn("cold_online_semantic_latency", cache_paths)
        self.assertIn("warm_query_cache_latency", cache_paths)
        self.assertIn("source_side_cache_hot_path_latency", cache_paths)
        self.assertIn("source_side_cache_build_cost", cache_paths)
        self.assertIn("semantic_cache_hit_rate", cache_paths)
        self.assertIn("semantic_cache_invalidation_count", cache_paths)


if __name__ == "__main__":
    unittest.main()
