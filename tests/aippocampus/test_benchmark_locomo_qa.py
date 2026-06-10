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
for _path in (BENCHMARKS, REPO_ROOT / "tools" / "aippocampus" / "smoke"):
    sys.path.insert(0, str(_path))

import benchmark_locomo_qa as benchmark  # noqa: E402


def write_fixture(path: Path) -> None:
    rows = [
        {
            "sample_id": "conv-test",
            "conversation": {
                "speaker_a": "A",
                "speaker_b": "B",
                "session_1_date_time": "2024-01-01T10:00:00Z",
                "session_1": [
                    {
                        "dia_id": "D1:1",
                        "speaker": "A",
                        "text": "The hidden park meeting was on Monday.",
                    },
                    {
                        "dia_id": "D1:2",
                        "speaker": "B",
                        "text": "Bring the blue notebook.",
                    },
                ],
                "session_2_date_time": "2024-02-01T10:00:00Z",
                "session_2": [
                    {
                        "dia_id": "D2:1",
                        "speaker": "A",
                        "text": "The later session mentions no notebook.",
                    }
                ],
            },
            "qa": [
                {
                    "question": "When was the hidden park meeting?",
                    "answer": "Monday",
                    "evidence": ["D1:1"],
                    "category": 2,
                },
                {
                    "question": "What should be brought?",
                    "answer": "The blue notebook",
                    "evidence": ["D1:2"],
                    "category": 3,
                },
            ],
            "event_summary": {},
            "observation": {},
            "session_summary": {},
        }
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")


class LocomoQABenchmarkTests(unittest.TestCase):
    def test_missing_dataset_returns_answer_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-locomo10.json"

            payload = benchmark.run_locomo_qa_benchmark(
                dataset_path=path,
                max_questions=2,
                min_questions=1,
            )

        self.assertEqual(payload["kind"], "aippocampus_locomo_text_qa_benchmark")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["retrieval"]["metrics"]["question_count"], 0)
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 0)
        self.assertIn("answer_generation_quality", payload["cannot_claim"])
        self.assertFalse(payload["privacy_boundary"]["raw_answer_text_emitted"])
        self.assertTrue(payload["sanitized_report_validation"]["ok"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(path), dumped)

    def test_dry_run_fixture_builds_sanitized_schema_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locomo10.json"
            write_fixture(path)

            payload = benchmark.run_locomo_qa_benchmark(
                dataset_path=path,
                max_questions=2,
                min_questions=1,
                top_k=5,
                reader_mode="dry-run",
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "dry_run_schema_ready")
        self.assertEqual(payload["evaluation"]["reader"]["mode"], "dry-run")
        self.assertEqual(
            payload["evaluation"]["question_type_boundary"],
            "LoCoMo category values are preserved as dataset-provided category "
            "ids; this runner does not remap them to semantic labels.",
        )
        self.assertEqual(payload["retrieval"]["metrics"]["question_count"], 2)
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 0)
        self.assertEqual(
            payload["answer"]["metrics"]["failure_taxonomy_counts"]["reader_not_run"],
            2,
        )
        self.assertIn("locomo_category_2", payload["answer"]["metrics"]["by_question_type"])
        self.assertEqual(payload["latency"]["reader_ms"]["count"], 0)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("hidden park meeting", dumped)
        self.assertNotIn("blue notebook", dumped)
        self.assertNotIn(str(path), dumped)
        self.assertTrue(payload["sanitized_report_validation"]["ok"])

    def test_provider_mode_scores_answer_latency_usage_citations_and_cost(self) -> None:
        captured_messages: list[list[dict[str, str]]] = []

        def fake_call_chat_json(
            messages: list[dict[str, str]],
            api_key: str,
            model: str,
            base_url: str,
            max_tokens: int | None,
            timeout: float,
            temperature: float,
            **_: object,
        ) -> dict[str, Any]:
            captured_messages.append(messages)
            self.assertEqual(api_key, "reader-key")
            self.assertEqual(model, "reader-test-model")
            self.assertEqual(base_url, "https://api.deepseek.com/v1")
            self.assertEqual(max_tokens, 128)
            self.assertEqual(timeout, 7)
            self.assertEqual(temperature, 0.0)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "Monday",
                                    "abstained": False,
                                    "citation_lines": [1],
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
            path = Path(tmp) / "locomo10.json"
            write_fixture(path)
            with patch.dict(
                "os.environ",
                {"AIPPOCAMPUS_LOCOMO_READER_API_KEY": "reader-key"},
            ), patch(
                "benchmark_locomo_qa.standard_public.call_chat_json",
                fake_call_chat_json,
            ):
                payload = benchmark.run_locomo_qa_benchmark(
                    dataset_path=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
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
        self.assertIn("hidden park meeting", captured_messages[0][1]["content"])
        self.assertEqual(payload["answer"]["metrics"]["reader_attempted_count"], 1)
        self.assertEqual(payload["answer"]["metrics"]["answer_correct_count"], 1)
        self.assertEqual(payload["answer"]["metrics"]["answer_correct_rate"], 1.0)
        self.assertEqual(payload["answer"]["metrics"]["correct_source_citation_count"], 1)
        self.assertEqual(payload["token_usage"]["total_tokens"], 35)
        self.assertEqual(payload["reader_cache"]["hit_tokens"], 10)
        self.assertEqual(
            payload["cost"]["status"],
            "estimated_from_user_supplied_token_prices",
        )
        self.assertEqual(payload["cases"][0]["reader"]["cited_candidate_line_count"], 1)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("hidden park meeting", dumped)
        self.assertNotIn("Monday", dumped)
        self.assertNotIn("reader-key", dumped)
        self.assertNotIn(str(path), dumped)
        self.assertTrue(payload["sanitized_report_validation"]["ok"])

    def test_provider_context_visible_wrong_answer_uses_reader_miss_taxonomy(self) -> None:
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
                                    "answer": "Tuesday",
                                    "abstained": False,
                                    "citation_lines": [1],
                                    "confidence": 0.64,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
            }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locomo10.json"
            write_fixture(path)
            with patch.dict(
                "os.environ",
                {"AIPPOCAMPUS_LOCOMO_READER_API_KEY": "reader-key"},
            ), patch(
                "benchmark_locomo_qa.standard_public.call_chat_json",
                fake_call_chat_json,
            ):
                payload = benchmark.run_locomo_qa_benchmark(
                    dataset_path=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    reader_mode="provider",
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(
            payload["answer"]["metrics"]["failure_taxonomy_counts"][
                "evidence_visible_reader_miss"
            ],
            1,
        )
        self.assertFalse(payload["cases"][0]["answer"]["answer_correct"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Tuesday", dumped)
        self.assertNotIn("Monday", dumped)

    def test_sanitized_report_validator_rejects_leaks(self) -> None:
        payload = {
            "path": "C:\\Users\\Administrator\\secret\\report.json",
            "answer": "blue notebook",
            "token": "sk-" + ("a" * 30),
        }

        result = benchmark.validate_sanitized_report(
            payload,
            forbidden_texts=["blue notebook"],
        )

        self.assertFalse(result["ok"])
        kinds = {error["kind"] for error in result["errors"]}
        self.assertIn("absolute_path_leak", kinds)
        self.assertIn("raw_text_leak", kinds)
        self.assertIn("credential_like_string", kinds)


if __name__ == "__main__":
    unittest.main()
