from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

benchmark = import_benchmark_module("benchmark_amemgym")

RAW_PROFILE = "RAW PROFILE TEXT MUST NOT LEAK"
RAW_QUERY = "RAW QUERY TEXT MUST NOT LEAK"
RAW_ANSWER = "RAW ANSWER TEXT MUST NOT LEAK"
RAW_UPDATE = "RAW UPDATE TEXT MUST NOT LEAK"
LOCAL_PATH_SENTINEL = "LOCAL_PRIVATE_PATH_SENTINEL\\amemgym\\data.json"

class AMemGymSmokeTests(unittest.TestCase):
    def test_missing_dataset_returns_public_safe_metadata_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.run_amemgym_smoke(dataset_path=Path(tmp) / "missing.json")

        self.assertEqual(payload["kind"], "aippocampus_amemgym_metadata_smoke")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["metrics"]["official_expected_rows"], 20)
        self.assertEqual(payload["metrics"]["observed_row_count"], 0)
        self.assertEqual(payload["source"]["official_dataset"]["config"], "v1.base")
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertIn("official_amemgym_score", payload["cannot_claim"])
        self.assertIn("interactive_on_policy_agent_quality", payload["cannot_claim"])

    def test_metadata_smoke_reports_shape_and_stays_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = Path(tmp) / "data.json"
            _write_fixture(dataset_path)

            payload = benchmark.run_amemgym_smoke(dataset_path=dataset_path, case_limit=10)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "metadata_smoke")
        self.assertEqual(payload["metrics"]["observed_row_count"], 2)
        self.assertEqual(payload["schema_observation"]["required_top_level_fields_present_rate"], 1.0)
        self.assertEqual(payload["schema_observation"]["period_count"], 2)
        self.assertEqual(payload["schema_observation"]["session_count"], 2)
        self.assertEqual(payload["schema_observation"]["update_count"], 3)
        self.assertEqual(payload["schema_observation"]["qa_count"], 3)
        self.assertEqual(payload["schema_observation"]["answer_choice_count"], 6)
        self.assertEqual(payload["metrics"]["current_state_source_hit_rate"], 0.5)
        self.assertEqual(payload["metrics"]["stale_state_as_current_rate"], 0.5)
        self.assertEqual(payload["metrics"]["unsupported_personalization_rate"], 0.5)
        self.assertIn("native_accuracy_requires_predictions", payload["evaluation_layers"]["native_metrics"])

        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in (RAW_PROFILE, RAW_QUERY, RAW_ANSWER, RAW_UPDATE, LOCAL_PATH_SENTINEL, str(dataset_path)):
            self.assertNotIn(forbidden, dumped)

    def test_overlay_slice_scores_predictions_without_collapsing_claim_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_path = root / "data.json"
            prediction_path = root / "predictions.jsonl"
            template_path = root / "template.jsonl"
            _write_fixture(dataset_path)
            _write_predictions(prediction_path)

            payload = benchmark.run_amemgym_smoke(
                dataset_path=dataset_path,
                predictions_path=prediction_path,
                prediction_template_output=template_path,
                case_limit=10,
            )

            template_rows = [
                json.loads(line)
                for line in template_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(payload["status"], "overlay_metrics_smoke")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["metrics"]["sample_count"], 3)
        self.assertAlmostEqual(payload["metrics"]["accuracy"], 2 / 3)
        self.assertAlmostEqual(payload["metrics"]["normalized_memory_score"], 2 / 3)
        self.assertAlmostEqual(payload["metrics"]["source_reopen_success"], 2 / 3)
        self.assertAlmostEqual(payload["metrics"]["current_state_source_hit"], 2 / 3)
        self.assertAlmostEqual(payload["metrics"]["stale_state_as_current_rate"], 1 / 3)
        self.assertAlmostEqual(payload["metrics"]["unsupported_personalization_rate"], 1 / 3)
        self.assertAlmostEqual(payload["metrics"]["scent_as_evidence_rate"], 1 / 3)
        self.assertAlmostEqual(payload["metrics"]["answer_correct_but_unsupported_rate"], 1 / 3)
        self.assertEqual(payload["metrics"]["write_failure_rate"], 1 / 3)
        self.assertEqual(payload["metrics"]["read_failure_rate"], 1 / 3)
        self.assertEqual(payload["metrics"]["utilization_failure_rate"], 1 / 3)
        self.assertEqual(payload["claim_boundary"]["amemgym_score"], "not_claimed")
        self.assertEqual(payload["claim_boundary"]["source_backed_fidelity"], "overlay_metrics_only")
        self.assertEqual(payload["claim_boundary"]["cost_latency"], "reported_without_model_cost")
        self.assertEqual(template_rows[0]["prediction"], "")
        dumped_template = json.dumps(template_rows, ensure_ascii=False)
        for forbidden in (RAW_PROFILE, RAW_QUERY, RAW_ANSWER, RAW_UPDATE):
            self.assertNotIn(forbidden, dumped_template)

def _write_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "id": "fixture-user-1",
                    "start_time": "2026-01-01T00:00:00Z",
                    "user_profile": RAW_PROFILE,
                    "state_schema": {
                        "favorite_tea": ["green", "oolong"],
                        "meeting_size": ["small", "large"],
                    },
                    "periods": [
                        {
                            "period_id": "p1",
                            "sessions": [
                                {
                                    "session_id": "s1",
                                    "updates": [
                                        {
                                            "state": {"favorite_tea": "green", "meeting_size": "small"},
                                            "text": RAW_UPDATE,
                                            "source": LOCAL_PATH_SENTINEL,
                                        },
                                        {
                                            "state": {"favorite_tea": "oolong", "meeting_size": "small"},
                                            "text": "CURRENT RAW UPDATE MUST NOT LEAK",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                    "qas": [
                        {
                            "query": RAW_QUERY,
                            "required_info": ["favorite_tea"],
                            "answer_choices": [
                                {"state": ["green"], "answer": "stale " + RAW_ANSWER, "type": "preference"},
                                {"state": ["oolong"], "answer": "current " + RAW_ANSWER, "type": "preference"},
                            ],
                        },
                        {
                            "query": "What snack should be prepared?",
                            "required_info": ["snack"],
                            "answer_choices": [
                                {"state": ["cookies"], "answer": "unsupported " + RAW_ANSWER, "type": "unsupported"},
                                {"state": ["fruit"], "answer": "second unsupported " + RAW_ANSWER, "type": "unsupported"},
                            ],
                        },
                    ],
                },
                {
                    "id": "fixture-user-2",
                    "start_time": "2026-01-02T00:00:00Z",
                    "user_profile": "SECOND RAW PROFILE MUST NOT LEAK",
                    "state_schema": {"meeting_size": ["small", "large"]},
                    "periods": [
                        {
                            "period_id": "p2",
                            "sessions": [
                                {
                                    "session_id": "s2",
                                    "updates": [
                                        {"state": {"meeting_size": "large"}, "text": "SECOND RAW UPDATE"}
                                    ],
                                }
                            ],
                        }
                    ],
                    "qas": [
                        {
                            "query": "How should the room be arranged?",
                            "required_info": ["meeting_size"],
                            "answer_choices": [
                                {"state": ["small"], "answer": "small room " + RAW_ANSWER, "type": "experience"},
                                {"state": ["large"], "answer": "large room " + RAW_ANSWER, "type": "experience"},
                            ],
                        }
                    ],
                },
            ],
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

def _write_predictions(path: Path) -> None:
    rows = [
        {
            "case_id": "fixture-user-1:q1",
            "prediction": "current " + RAW_ANSWER,
            "source_refs": ["fixture-user-1:p1:s1:u2"],
            "used_current_state": True,
        },
        {
            "case_id": "fixture-user-1:q2",
            "prediction": "unsupported " + RAW_ANSWER,
            "source_refs": ["scent:snack"],
            "unsupported_personalization": True,
            "scent_as_evidence": True,
        },
        {
            "case_id": "fixture-user-2:q1",
            "prediction": "small room " + RAW_ANSWER,
            "source_refs": ["fixture-user-2:p2:s2:u1"],
            "used_stale_state": True,
            "write_failure": True,
            "read_failure": True,
            "utilization_failure": True,
        },
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

if __name__ == "__main__":
    unittest.main()
