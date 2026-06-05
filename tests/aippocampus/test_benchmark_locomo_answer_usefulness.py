from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_locomo_answer_usefulness as benchmark  # noqa: E402


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


class LocomoAnswerUsefulnessBenchmarkTests(unittest.TestCase):
    def test_default_contract_reports_all_layers_and_stays_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            write_fixture(dataset)

            payload = benchmark.run_benchmark(dataset_path=dataset)

        self.assertEqual(payload["kind"], "aippocampus_locomo_answer_usefulness_benchmark")
        self.assertEqual(payload["status"], "answer_usefulness_contract_scored")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["evaluation"]["answer_model"], "deterministic_oracle_fixture")
        self.assertEqual(
            payload["evaluation"]["judge_model"],
            "deterministic_locomo_answer_usefulness_v1",
        )
        self.assertEqual(payload["layers"]["source_evidence_retrieval"]["metric"], "full_evidence_recall_rate")
        self.assertEqual(payload["layers"]["context_gathering"]["metric"], "context_sufficient_rate")
        self.assertEqual(payload["layers"]["answer_generation"]["metric"], "answer_correct_rate")
        self.assertEqual(payload["layers"]["source_citation"]["metric"], "correct_source_citation_rate")
        self.assertEqual(
            payload["layers"]["unsupported_inference_refusal"]["metric"],
            "unsupported_inference_refusal_rate",
        )
        self.assertEqual(payload["arms"]["retrieved_context"]["metrics"]["answer_correct_rate"], 1.0)
        self.assertEqual(
            payload["arms"]["empty_context"]["metrics"]["unsupported_inference_refusal_rate"],
            1.0,
        )
        self.assertIn("answer_generation_quality_depends_on_fixed_answer_model", payload["cannot_claim"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("hidden park meeting", dumped)
        self.assertNotIn("blue notebook", dumped)
        self.assertNotIn(str(REPO_ROOT), dumped)

    def test_prediction_file_scores_answer_citation_and_refusal_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            predictions = Path(tmp) / "answers.jsonl"
            write_fixture(dataset)
            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0001",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": ["D1:1"],
                                "answer_text": "The meeting was on Monday.",
                                "citation_ids": ["D1:1"],
                                "refused": False,
                            }
                        ),
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0002",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": [],
                                "answer_text": "Bring a red folder.",
                                "citation_ids": [],
                                "refused": False,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=dataset,
                predictions_file=predictions,
                answer_model="fixture-answer-model",
            )

        metrics = payload["arms"]["retrieved_context"]["metrics"]
        self.assertEqual(metrics["full_evidence_recall_rate"], 0.5)
        self.assertEqual(metrics["context_sufficient_rate"], 0.5)
        self.assertEqual(metrics["answer_correct_rate"], 0.5)
        self.assertEqual(metrics["correct_source_citation_rate"], 0.5)
        self.assertEqual(metrics["unsupported_inference_refusal_rate"], 0.0)
        self.assertEqual(payload["evaluation"]["answer_model"], "fixture-answer-model")
        by_case = {
            row["case_id"]: row
            for row in payload["arms"]["retrieved_context"]["cases"]
        }
        self.assertTrue(by_case["locomo:conv-test:qa:0001"]["answer_correct"])
        self.assertFalse(by_case["locomo:conv-test:qa:0002"]["context_sufficient"])
        self.assertFalse(by_case["locomo:conv-test:qa:0002"]["unsupported_inference_refused"])

    def test_template_generation_status_is_separate_from_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            predictions = Path(tmp) / "answers.jsonl"
            template = Path(tmp) / "answers-template.jsonl"
            write_fixture(dataset)
            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0001",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": [],
                                "answer_text": "",
                                "citation_ids": [],
                                "refused": False,
                            }
                        ),
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0002",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": [],
                                "answer_text": "",
                                "citation_ids": [],
                                "refused": False,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                dataset_path=dataset,
                predictions_file=predictions,
                answer_template_output=template,
            )
            self.assertTrue(template.exists())
            template_line_count = len(template.read_text(encoding="utf-8").splitlines())

        self.assertFalse(payload["ok"], payload)
        self.assertFalse(payload["quality_gate_ok"], payload)
        self.assertTrue(payload["report_generation_ok"], payload)
        self.assertTrue(payload["artifact_generation_ok"], payload)
        self.assertTrue(payload["artifacts"]["answer_template_written"], payload)
        self.assertEqual(payload["artifacts"]["answer_template_status"], "written")
        self.assertEqual(payload["artifacts"]["answer_template_row_count"], 2)
        self.assertEqual(template_line_count, 2)

    def test_missing_dataset_returns_skip_payload_without_writing_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "missing-locomo10.json"
            template = Path(tmp) / "answers-template.jsonl"

            payload = benchmark.run_benchmark(
                dataset_path=dataset,
                answer_template_output=template,
            )
            template_exists = template.exists()

        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["quality_gate_status"], "not_scored")
        self.assertNotIn("quality_gate_ok", payload)
        self.assertTrue(payload["report_generation_ok"], payload)
        self.assertFalse(payload["artifact_generation_ok"], payload)
        self.assertEqual(payload["artifact_generation_status"], "skipped_missing_dataset")
        self.assertFalse(payload["artifacts"]["answer_template_written"], payload)
        self.assertEqual(
            payload["artifacts"]["answer_template_status"],
            "skipped_missing_dataset",
        )
        self.assertEqual(payload["artifacts"]["answer_template_row_count"], 0)
        self.assertFalse(template_exists)

    def test_deterministic_answer_quality_reports_token_overlap_and_negation_traps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            predictions = Path(tmp) / "answers.jsonl"
            write_fixture(dataset)
            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0001",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": ["D1:1"],
                                "answer_text": "The meeting was not on Monday.",
                                "citation_ids": ["D1:1"],
                                "refused": False,
                            }
                        ),
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0002",
                                "arm": "retrieved_context",
                                "retrieved_evidence_ids": ["D1:2"],
                                "answer_text": "A blue notebook was brought.",
                                "citation_ids": ["D1:2"],
                                "refused": False,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(dataset_path=dataset, predictions_file=predictions)

        metrics = payload["arms"]["retrieved_context"]["metrics"]
        self.assertEqual(metrics["legacy_substring_gold_match_rate"], 0.5)
        self.assertEqual(metrics["negation_trap_count"], 1)
        self.assertEqual(metrics["answer_correct_rate"], 0.5)
        self.assertEqual(metrics["token_overlap_strong_match_rate"], 1.0)
        by_case = {
            row["case_id"]: row
            for row in payload["arms"]["retrieved_context"]["cases"]
        }
        self.assertFalse(by_case["locomo:conv-test:qa:0001"]["answer_correct"])
        self.assertTrue(by_case["locomo:conv-test:qa:0001"]["answer_quality"]["negation_trap"])
        self.assertTrue(by_case["locomo:conv-test:qa:0002"]["answer_quality"]["strong_match"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Monday", dumped)
        self.assertNotIn("blue notebook", dumped)


if __name__ == "__main__":
    unittest.main()
