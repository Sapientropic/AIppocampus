from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
TESTS = REPO_ROOT / "tests" / "aippocampus"
for _path in (BENCHMARKS, REPO_ROOT / "tools" / "aippocampus" / "smoke", TESTS):
    sys.path.insert(0, str(_path))

import benchmark_longmemeval_answer as benchmark  # noqa: E402
from test_benchmark_longmemeval import (  # noqa: E402
    patched_oracle_split,
    write_context_visible_miss_fixture,
    write_oracle_fixture,
)


def write_update_fixture(path: Path) -> None:
    fixture = [
        {
            "question_id": "q-update",
            "question_type": "knowledge-update",
            "question": "Where is the updated blue badge stored now?",
            "answer": "drawer nine",
            "question_date": "2023/05/30 (Tue) 23:40",
            "haystack_dates": ["2023/05/20 (Sat) 02:21"],
            "haystack_session_ids": ["answer-session"],
            "answer_session_ids": ["answer-session"],
            "haystack_sessions": [
                [
                    {
                        "role": "user",
                        "content": "Earlier it was in drawer eight.",
                    },
                    {
                        "role": "assistant",
                        "content": "The updated blue badge is now in drawer nine.",
                        "has_answer": True,
                    },
                ]
            ],
        }
    ]
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


class LongMemEvalAnswerBenchmarkTests(unittest.TestCase):
    def test_answer_quality_normalizes_equivalent_number_forms(self) -> None:
        quality = benchmark.answer_quality("drawer 9", "drawer nine")

        self.assertTrue(quality["strong_match"], quality)
        self.assertGreaterEqual(quality["token_overlap_rate"], 0.8)

    def test_reader_prompt_marks_bounded_evidence_as_answerable_when_supported(self) -> None:
        messages = benchmark.reader_messages(
            "Where did the blue badge note say to look?",
            [
                {
                    "line": 2,
                    "role": "assistant",
                    "session_rank": 1,
                    "nearest_hit_rank": 1,
                    "context_distance": 0,
                    "text": "The object is in drawer nine.",
                }
            ],
        )
        user_payload = json.loads(messages[1]["content"])
        first_line = user_payload["candidate_source_lines"][0]

        self.assertEqual(
            user_payload["source_support_scope"],
            "bounded_evidence_answerable_when_lines_support",
        )
        self.assertIn("do_not_abstain_merely_because_context_is_bounded", user_payload["answer_policy"])
        self.assertEqual(first_line["salience_hint"], "direct_retrieval_hit")

    def test_failure_taxonomy_separates_reader_error_and_over_abstention(self) -> None:
        provider_error = benchmark.classify_failure(
            retrieval_row={
                "case_type": "longmemeval_single-session-user",
                "has_line_evidence": True,
                "evidence_context_hit_top10": True,
            },
            prediction=benchmark.ReaderPrediction(
                attempted=True,
                status="reader_error",
                error_kind="provider_error",
            ),
            quality={"token_overlap_rate": 0.0},
            context_sufficient=True,
            answer_correct=False,
            candidate_contains_evidence=True,
            top_k=10,
        )
        over_abstention = benchmark.classify_failure(
            retrieval_row={
                "case_type": "longmemeval_single-session-user",
                "has_line_evidence": True,
                "evidence_context_hit_top10": True,
            },
            prediction=benchmark.ReaderPrediction(
                attempted=True,
                status="answered",
                abstained=True,
            ),
            quality={"token_overlap_rate": 0.0},
            context_sufficient=True,
            answer_correct=False,
            candidate_contains_evidence=True,
            top_k=10,
        )

        self.assertEqual(provider_error, "reader_provider_error")
        self.assertEqual(over_abstention, "over_abstention_boundary_false_negative")

    def test_context_visible_missing_candidate_is_packaging_failure(self) -> None:
        row = benchmark.score_answer_case(
            case={
                "case_id": "case-packaging",
                "expected": {"lines": [2]},
            },
            retrieval_row={
                "case_type": "longmemeval_single-session-user",
                "source_id_sha1": "sourcehash",
                "question_id_sha1": "questionhash",
                "query_sha1": "queryhash",
                "has_line_evidence": True,
                "session_rank": 1,
                "evidence_rank": 2,
                "evidence_context_rank": 1,
                "session_hit_top10": True,
                "evidence_hit_top10": True,
                "evidence_context_hit_top10": True,
                "evidence_miss_category": "exact_line_found_top_k",
            },
            candidates=[
                {
                    "line": 1,
                    "role": "user",
                    "session_rank": 1,
                    "nearest_hit_rank": 1,
                    "context_distance": 0,
                }
            ],
            candidate_latency_ms=0.1,
            candidate_warning_count=0,
            gold={"answer": "drawer nine"},
            prediction=benchmark.ReaderPrediction(
                attempted=True,
                status="answered",
                answer_text="drawer eight",
            ),
            top_k=10,
        )

        self.assertEqual(
            row["answer"]["failure_category"],
            "insufficient_evidence_packaging",
        )

    def test_failure_review_and_expansion_gate_are_public_safe(self) -> None:
        payload = {
            "answer": {
                "metrics": {
                    "case_count": 3,
                    "answer_correct_count": 1,
                    "failure_taxonomy_counts": {
                        "answered_correctly": 1,
                        "reader_provider_error": 1,
                        "deterministic_judge_mismatch": 1,
                        "over_abstention_boundary_false_negative": 1,
                    },
                }
            },
            "cases": [
                {
                    "case_id": "ok",
                    "answer": {"failure_category": "answered_correctly"},
                },
                {
                    "case_id": "err",
                    "case_type": "longmemeval_single-session-user",
                    "source_id_sha1": "source-a",
                    "question_id_sha1": "question-a",
                    "answer_sha1": "answer-a",
                    "retrieval": {
                        "candidate_contains_evidence": True,
                        "evidence_context_hit_top10": True,
                        "evidence_rank": 1,
                        "evidence_context_rank": 1,
                    },
                    "reader": {
                        "status": "reader_error",
                        "error_kind": "provider_error",
                        "answer_text_sha1": None,
                    },
                    "answer": {
                        "failure_category": "reader_provider_error",
                        "context_sufficient": True,
                        "answer_quality": {"token_overlap_rate": 0.0},
                    },
                },
                {
                    "case_id": "judge",
                    "case_type": "longmemeval_single-session-user",
                    "source_id_sha1": "source-b",
                    "question_id_sha1": "question-b",
                    "answer_sha1": "answer-b",
                    "retrieval": {
                        "candidate_contains_evidence": True,
                        "evidence_context_hit_top10": True,
                        "evidence_rank": 2,
                        "evidence_context_rank": 1,
                    },
                    "reader": {
                        "status": "answered",
                        "answer_text_sha1": "predicted-b",
                    },
                    "answer": {
                        "failure_category": "deterministic_judge_mismatch",
                        "context_sufficient": True,
                        "answer_quality": {"token_overlap_rate": 0.5},
                    },
                },
                {
                    "case_id": "abstain",
                    "case_type": "longmemeval_single-session-user",
                    "source_id_sha1": "source-c",
                    "question_id_sha1": "question-c",
                    "answer_sha1": "answer-c",
                    "retrieval": {
                        "candidate_contains_evidence": True,
                        "evidence_context_hit_top10": True,
                        "evidence_rank": 3,
                        "evidence_context_rank": 1,
                    },
                    "reader": {
                        "status": "answered",
                        "abstained": True,
                        "answer_text_sha1": None,
                    },
                    "answer": {
                        "failure_category": "over_abstention_boundary_false_negative",
                        "context_sufficient": True,
                        "answer_quality": {"token_overlap_rate": 0.0},
                    },
                },
            ],
        }

        review = benchmark.build_failure_review(payload)
        gate = benchmark.expansion_go_no_go(review)
        dumped = json.dumps(review, ensure_ascii=False)

        self.assertEqual(review["non_correct_case_count"], 3)
        self.assertEqual(review["taxonomy_counts"]["reader_provider_error"], 1)
        self.assertEqual(review["taxonomy_counts"]["deterministic_judge_mismatch"], 1)
        self.assertEqual(
            review["taxonomy_counts"]["over_abstention_boundary_false_negative"],
            1,
        )
        abstain_row = next(row for row in review["cases"] if row["case_id"] == "abstain")
        self.assertEqual(abstain_row["reader_outcome"], "abstained")
        self.assertEqual(gate["status"], "no_go")
        self.assertIn("reader_provider_error", gate["blockers"])
        self.assertNotIn("raw question", dumped)

    def test_missing_dataset_returns_answer_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-longmemeval.json"

            payload = benchmark.run_longmemeval_answer_benchmark(
                split_name="longmemeval-v1-oracle",
                data_file=path,
                max_questions=2,
                min_questions=1,
            )

        self.assertEqual(payload["kind"], "aippocampus_longmemeval_answer_benchmark")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["retrieval"]["metrics"]["question_count"], 0)
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 0)
        self.assertIn("answer_generation_quality", payload["cannot_claim"])
        self.assertFalse(payload["privacy_boundary"]["raw_answer_text_emitted"])
        self.assertTrue(payload["sanitized_report_validation"]["ok"])

    def test_dry_run_fixture_builds_sanitized_schema_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_answer_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    reader_mode="dry-run",
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "dry_run_schema_ready")
        self.assertEqual(payload["evaluation"]["reader"]["mode"], "dry-run")
        self.assertEqual(payload["retrieval"]["metrics"]["question_count"], 1)
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 0)
        self.assertEqual(
            payload["answer"]["metrics"]["failure_taxonomy_counts"]["reader_not_run"],
            1,
        )
        self.assertEqual(payload["latency"]["reader_ms"]["count"], 0)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn("retrieval marker", dumped)
        self.assertNotIn(str(path), dumped)
        self.assertTrue(payload["sanitized_report_validation"]["ok"])

    def test_provider_mode_requires_budget_before_reader_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            partial_path = root / "answer.partial.json"
            checkpoint_path = root / "answer-budget.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path), patch.dict(
                "os.environ",
                {"AIPPOCAMPUS_LONGMEMEVAL_READER_API_KEY": "reader-key"},
            ), patch(
                "benchmark_longmemeval_answer.standard_public.call_chat_json",
                side_effect=AssertionError("provider should not be called"),
            ):
                payload = benchmark.run_longmemeval_answer_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    reader_mode="provider",
                    partial_output=partial_path,
                    provider_budget_checkpoint=checkpoint_path,
                )

            partial = json.loads(partial_path.read_text(encoding="utf-8"))
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "skipped_provider_budget_not_declared")
        budget = payload["provider_execution_budget"]
        self.assertFalse(budget["ok_to_start"])
        self.assertEqual(budget["stop_reason"], "provider_budget_preflight_failed")
        self.assertEqual(
            budget["validation_errors"],
            ["missing_provider_call_cap", "missing_token_or_cost_budget"],
        )
        self.assertEqual(partial["provider_execution_budget"], budget)
        self.assertEqual(checkpoint["provider_execution_budget"], budget)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn("reader-key", dumped)
        self.assertNotIn(str(path), dumped)

    def test_provider_mode_scores_answer_latency_usage_and_citations(self) -> None:
        captured_messages: list[list[dict[str, str]]] = []

        def fake_call_chat_json(
            messages: list[dict[str, str]],
            api_key: str,
            model: str,
            base_url: str,
            max_tokens: int | None,
            timeout: float,
            temperature: float,
            **kwargs: object,
        ) -> dict[str, Any]:
            captured_messages.append(messages)
            self.assertEqual(api_key, "reader-key")
            self.assertEqual(model, "reader-test-model")
            self.assertEqual(base_url, "https://api.deepseek.com/v1")
            self.assertEqual(max_tokens, 128)
            self.assertEqual(timeout, 7)
            self.assertEqual(temperature, 0.0)
            self.assertEqual(kwargs["cache_contract"], "deepseek_prefix_v1")
            self.assertEqual(kwargs["service_name"], "DeepSeek LongMemEval reader API")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "drawer nine",
                                    "abstained": False,
                                    "citation_lines": [2],
                                    "confidence": 0.91,
                                }
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                    "total_tokens": 35,
                    "prompt_cache_hit_tokens": 10,
                    "prompt_cache_miss_tokens": 20,
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            partial_path = root / "answer.partial.json"
            checkpoint_path = root / "answer-budget.json"
            write_context_visible_miss_fixture(path)
            with patched_oracle_split(path), patch.dict(
                "os.environ",
                {"AIPPOCAMPUS_LONGMEMEVAL_READER_API_KEY": "reader-key"},
            ), patch(
                "benchmark_longmemeval_answer.standard_public.call_chat_json",
                fake_call_chat_json,
            ):
                payload = benchmark.run_longmemeval_answer_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=1,
                    reader_mode="provider",
                    reader_model="reader-test-model",
                    reader_base_url="https://api.deepseek.com/v1",
                    reader_timeout=7,
                    reader_max_tokens=128,
                    reader_input_cost_per_million=0.10,
                    reader_output_cost_per_million=0.20,
                    partial_output=partial_path,
                    provider_budget_checkpoint=checkpoint_path,
                    max_provider_calls=1,
                    max_provider_total_tokens=1000,
                    provider_cost_unknown=True,
                )
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "answer_scored")
        self.assertEqual(len(captured_messages), 1)
        user_payload = json.loads(captured_messages[0][1]["content"])
        self.assertEqual(user_payload["prompt_version"], benchmark.READER_PROMPT_VERSION)
        self.assertIn("drawer nine", captured_messages[0][1]["content"])
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 1)
        self.assertEqual(payload["answer"]["metrics"]["answer_correct_count"], 1)
        self.assertEqual(payload["answer"]["metrics"]["answer_correct_rate"], 1.0)
        self.assertEqual(payload["token_usage"]["total_tokens"], 35)
        self.assertEqual(payload["reader_cache"]["hit_tokens"], 10)
        self.assertEqual(
            payload["cost"]["status"],
            "estimated_from_user_supplied_token_prices",
        )
        budget = payload["provider_execution_budget"]
        self.assertTrue(budget["ok_to_start"])
        self.assertEqual(budget["completed_units"], 1)
        self.assertEqual(budget["token_usage"]["total_tokens"], 35)
        self.assertEqual(budget["cache_usage"]["hit_tokens"], 10)
        self.assertEqual(checkpoint["provider_execution_budget"], budget)
        self.assertEqual(payload["cases"][0]["reader"]["cited_candidate_line_count"], 1)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("drawer nine", dumped)
        self.assertNotIn("blue badge note", dumped)
        self.assertNotIn("reader-key", dumped)
        self.assertNotIn(str(path), dumped)
        self.assertTrue(payload["sanitized_report_validation"]["ok"])

    def test_provider_wrong_update_answer_uses_stale_update_taxonomy(self) -> None:
        def fake_call_chat_json(
            messages: list[dict[str, str]],
            **_: object,
        ) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "drawer eight",
                                    "abstained": False,
                                    "citation_lines": [1],
                                    "confidence": 0.72,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            write_update_fixture(path)
            with patched_oracle_split(path), patch.dict(
                "os.environ",
                {"AIPPOCAMPUS_LONGMEMEVAL_READER_API_KEY": "reader-key"},
            ), patch(
                "benchmark_longmemeval_answer.standard_public.call_chat_json",
                fake_call_chat_json,
            ):
                payload = benchmark.run_longmemeval_answer_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    reader_mode="provider",
                    partial_output=root / "answer.partial.json",
                    provider_budget_checkpoint=root / "answer-budget.json",
                    max_provider_calls=1,
                    max_provider_total_tokens=1000,
                    provider_cost_unknown=True,
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(
            payload["answer"]["metrics"]["failure_taxonomy_counts"][
                "stale_update_confusion"
            ],
            1,
        )
        self.assertFalse(payload["cases"][0]["answer"]["answer_correct"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("drawer eight", dumped)
        self.assertNotIn("drawer nine", dumped)

    def test_sanitized_report_validator_rejects_leaks(self) -> None:
        payload = {
            "path": "C:\\Users\\Administrator\\secret\\report.json",
            "answer": "drawer nine",
            "token": "sk-" + ("a" * 30),
        }

        result = benchmark.validate_sanitized_report(
            payload,
            forbidden_texts=["drawer nine"],
        )

        self.assertFalse(result["ok"])
        kinds = {error["kind"] for error in result["errors"]}
        self.assertIn("absolute_path_leak", kinds)
        self.assertIn("raw_text_leak", kinds)
        self.assertIn("credential_like_string", kinds)


if __name__ == "__main__":
    unittest.main()
