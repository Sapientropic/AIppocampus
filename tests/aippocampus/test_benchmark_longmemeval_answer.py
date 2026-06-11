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
            path = Path(tmp) / "longmemeval_oracle.json"
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
                )

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
            path = Path(tmp) / "longmemeval_oracle.json"
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
