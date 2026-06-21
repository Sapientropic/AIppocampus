from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]

benchmark = import_benchmark_module("benchmark_locomo_public_users")

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

class LocomoPublicUsersBenchmarkTests(unittest.TestCase):
    def test_gold_baseline_scores_and_stays_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            write_fixture(dataset)

            payload = benchmark.run_benchmark(dataset_path=dataset)

        self.assertEqual(payload["kind"], "aippocampus_locomo_public_users_benchmark")
        self.assertEqual(payload["status"], "public_longitudinal_control_scored")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(
            payload["scoring_contract"]["role"],
            "oracle_scorer_self_check",
        )
        self.assertTrue(
            payload["scoring_contract"]["uses_gold_evidence_ids_as_prediction_input"]
        )
        self.assertFalse(payload["scoring_contract"]["system_under_test_required"])
        self.assertIn("--predictions", payload["scoring_contract"]["claim_boundary"])
        self.assertFalse(payload["scoring_contract"]["headline_score_allowed"])
        self.assertEqual(payload["dataset"]["track_role"], "public_longitudinal_conversation_control")
        self.assertEqual(payload["metrics"]["longitudinal_public_user_count"], 1)
        self.assertEqual(payload["metrics"]["session_count"], 2)
        self.assertEqual(payload["metrics"]["source_event_count"], 3)
        self.assertEqual(payload["metrics"]["scored_case_count"], 2)
        self.assertEqual(payload["metrics"]["full_evidence_recall_rate"], 1.0)
        self.assertEqual(payload["metrics"]["exact_evidence_match_rate"], 1.0)
        rate_estimates = payload["metrics"]["rate_estimates"]
        self.assertEqual(rate_estimates["full_evidence_recall_rate"]["denominator"], 2)
        self.assertEqual(
            rate_estimates["full_evidence_recall_rate"]["confidence_interval"]["method"],
            "wilson_score",
        )
        self.assertEqual(rate_estimates["false_positive_evidence_case_rate"]["numerator"], 0)
        self.assertGreater(
            rate_estimates["false_positive_evidence_case_rate"]["confidence_interval"]["upper"],
            0,
        )
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("hidden park meeting", dumped)
        self.assertNotIn("blue notebook", dumped)
        self.assertNotIn(str(REPO_ROOT), dumped)
        for case in payload["cases"]:
            self.assertIn("question_sha1", case)
            self.assertNotIn("question", case)
            self.assertNotIn("answer", case)

    def test_empty_baseline_fails_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            write_fixture(dataset)

            payload = benchmark.run_benchmark(dataset_path=dataset, baseline="empty")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["metrics"]["full_evidence_recall_rate"], 0.0)
        self.assertEqual(payload["metrics"]["missing_evidence_id_count"], 2)

    def test_custom_predictions_measure_missing_and_extra_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            predictions = Path(tmp) / "predictions.jsonl"
            write_fixture(dataset)
            predictions.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0001",
                                "evidence_ids": ["D1:1", "D2:1"],
                            }
                        ),
                        json.dumps(
                            {
                                "case_id": "locomo:conv-test:qa:0002",
                                "evidence_ids": [],
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
            )

        self.assertEqual(payload["scoring_contract"]["role"], "external_prediction_score")
        self.assertFalse(
            payload["scoring_contract"]["uses_gold_evidence_ids_as_prediction_input"]
        )
        self.assertTrue(payload["scoring_contract"]["system_under_test_required"])
        by_case = {case["case_id"]: case for case in payload["cases"]}
        self.assertFalse(payload["ok"])
        self.assertEqual(by_case["locomo:conv-test:qa:0001"]["extra_evidence_ids"], ["D2:1"])
        self.assertEqual(by_case["locomo:conv-test:qa:0002"]["missing_evidence_ids"], ["D1:2"])
        self.assertEqual(payload["metrics"]["false_positive_evidence_id_count"], 1)
        self.assertEqual(payload["metrics"]["false_positive_evidence_case_count"], 1)
        self.assertEqual(
            payload["metrics"]["rate_estimates"]["false_positive_evidence_case_rate"]["denominator"],
            2,
        )

    def test_public_text_mode_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            write_fixture(dataset)

            payload = benchmark.run_benchmark(dataset_path=dataset, include_public_text=True)

        self.assertTrue(payload["privacy_boundary"]["raw_question_text_emitted"])
        self.assertTrue(any("question" in case for case in payload["cases"]))

    def test_case_pack_and_prediction_template_are_explicit_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            case_pack_path = Path(tmp) / "case-pack.json"
            template_path = Path(tmp) / "predictions-template.jsonl"
            write_fixture(dataset)

            payload = benchmark.run_benchmark(
                dataset_path=dataset,
                case_pack_output=case_pack_path,
                prediction_template_output=template_path,
            )

            case_pack = json.loads(case_pack_path.read_text(encoding="utf-8"))
            template_rows = [
                json.loads(line)
                for line in template_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(payload["artifacts"]["case_pack_written"])
        self.assertTrue(payload["artifacts"]["prediction_template_written"])
        self.assertFalse(payload["privacy_boundary"]["raw_dialogue_text_emitted"])
        self.assertTrue(payload["privacy_boundary"]["case_pack_raw_text_emitted"])
        self.assertIn("The hidden park meeting was on Monday.", json.dumps(case_pack))
        self.assertIn("When was the hidden park meeting?", json.dumps(case_pack))
        self.assertFalse(case_pack["label_boundary"]["gold_evidence_ids_included"])
        self.assertFalse(case_pack["label_boundary"]["answer_text_included"])
        self.assertNotIn("answer", case_pack["cases"][0])
        self.assertNotIn("evidence_ids", case_pack["cases"][0])
        self.assertEqual(template_rows[0]["case_id"], "locomo:conv-test:qa:0001")
        self.assertEqual(template_rows[0]["evidence_ids"], [])
        dumped_template = json.dumps(template_rows, ensure_ascii=False)
        self.assertNotIn("hidden park meeting", dumped_template)
        self.assertNotIn("D1:1", dumped_template)

    def test_human_summary_marks_gold_baseline_as_scorer_self_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "locomo10.json"
            write_fixture(dataset)
            payload = benchmark.run_benchmark(dataset_path=dataset)

        output = StringIO()
        with redirect_stdout(output):
            benchmark.print_human_summary(payload)

        summary = output.getvalue()
        self.assertIn("oracle scorer self-check", summary)
        self.assertIn("--predictions", summary)
        self.assertIn("not system performance", summary)

    def test_missing_dataset_returns_public_safe_skip_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"

            payload = benchmark.run_benchmark(dataset_path=missing)

        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["quality_gate_status"], "not_scored")
        self.assertNotIn("quality_gate_ok", payload)
        self.assertEqual(payload["cases"], [])
        self.assertIn("public_longitudinal_user_score", payload["cannot_claim"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(REPO_ROOT), dumped)

if __name__ == "__main__":
    unittest.main()
