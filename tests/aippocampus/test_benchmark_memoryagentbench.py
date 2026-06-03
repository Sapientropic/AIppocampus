from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_memoryagentbench as benchmark  # noqa: E402

RAW_CONTEXT_AR = "SECRET AR CONTEXT SHOULD ONLY APPEAR IN EXPLICIT CASE PACKS"
RAW_QUESTION_AR = "RAW AR QUESTION SHOULD NOT APPEAR IN DEFAULT REPORTS"
RAW_ANSWER_AR = "RAW AR ANSWER SHOULD NEVER BE MODEL INPUT"
RAW_CONTEXT_TTL = "SECRET TTL CONTEXT SHOULD NOT APPEAR IN DEFAULT REPORTS"
RAW_ANSWER_TTL = "RAW TTL ANSWER LABEL SHOULD NEVER BE MODEL INPUT"
LOCAL_PATH_SENTINEL = "LOCAL_PRIVATE_PATH_SENTINEL\\memoryagentbench.parquet"


class MemoryAgentBenchSmokeTests(unittest.TestCase):
    def test_missing_dataset_returns_public_safe_metadata_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.run_memoryagentbench_smoke(dataset_dir=Path(tmp) / "missing")

        self.assertEqual(payload["kind"], "aippocampus_memoryagentbench_metadata_smoke")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["metrics"]["official_expected_total_rows"], 146)
        self.assertEqual(payload["metrics"]["observed_row_count"], 0)
        self.assertEqual(payload["metrics"]["observed_split_count"], 0)
        self.assertEqual(payload["splits"]["Accurate_Retrieval"]["expected_rows"], 22)
        self.assertEqual(payload["splits"]["Long_Range_Understanding"]["expected_rows"], 110)
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertIn("official_memoryagentbench_score", payload["cannot_claim"])
        self.assertIn("official_runner_compatibility", payload["cannot_claim"])

    def test_metadata_smoke_reports_schema_and_stays_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp) / "memoryagentbench"
            self._write_fixture(dataset_dir)

            payload = benchmark.run_memoryagentbench_smoke(dataset_dir=dataset_dir, case_limit=10)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "metadata_smoke")
        self.assertEqual(payload["metrics"]["official_expected_split_count"], 4)
        self.assertEqual(payload["metrics"]["official_expected_total_rows"], 146)
        self.assertEqual(payload["metrics"]["observed_split_count"], 4)
        self.assertEqual(payload["metrics"]["observed_row_count"], 4)

        accurate = payload["splits"]["Accurate_Retrieval"]
        ttl = payload["splits"]["Test_Time_Learning"]
        conflict = payload["splits"]["Conflict_Resolution"]
        self.assertEqual(accurate["observed_rows"], 1)
        self.assertIn("question_answering", accurate["task_families"])
        self.assertIn("substring_exact_match", accurate["metric_families"])
        self.assertIn("context", accurate["raw_text_fields_present"])
        self.assertEqual(
            accurate["support_status"]["source_evidence"],
            "diagnostic_requires_source_ref_mapping",
        )
        self.assertEqual(ttl["support_status"]["write_policy"], "diagnostic_requires_incremental_replay")
        self.assertEqual(
            conflict["support_status"]["conflict_resolution"],
            "diagnostic_requires_update_forgetting_contract",
        )
        self.assertEqual(payload["evaluation_layers"]["llm_as_judge"], "diagnostic_only_not_source_truth")

        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in (
            RAW_CONTEXT_AR,
            RAW_QUESTION_AR,
            RAW_ANSWER_AR,
            RAW_CONTEXT_TTL,
            RAW_ANSWER_TTL,
            LOCAL_PATH_SENTINEL,
            str(dataset_dir),
        ):
            self.assertNotIn(forbidden, dumped)
        for metric in ("official_score", "leaderboard_score", "merged_metric", "memoryagentbench_accuracy"):
            self.assertNotIn(metric, payload["metrics"])

    def test_case_pack_and_prediction_template_are_explicit_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_dir = root / "memoryagentbench"
            case_pack_path = root / "case-pack.json"
            template_path = root / "predictions-template.jsonl"
            self._write_fixture(dataset_dir)

            payload = benchmark.run_memoryagentbench_smoke(
                dataset_dir=dataset_dir,
                case_pack_output=case_pack_path,
                prediction_template_output=template_path,
                case_limit=3,
            )

            case_pack = json.loads(case_pack_path.read_text(encoding="utf-8"))
            template_rows = [
                json.loads(line)
                for line in template_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(payload["artifacts"]["case_pack_written"])
        self.assertTrue(payload["artifacts"]["prediction_template_written"])
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertTrue(payload["privacy_boundary"]["case_pack_raw_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["prediction_template_raw_text_emitted"])
        self.assertFalse(case_pack["label_boundary"]["answer_text_included"])
        self.assertFalse(case_pack["label_boundary"]["gold_labels_included"])
        self.assertIn(RAW_CONTEXT_AR, json.dumps(case_pack, ensure_ascii=False))
        self.assertIn(RAW_QUESTION_AR, json.dumps(case_pack, ensure_ascii=False))
        self.assertNotIn(RAW_ANSWER_AR, json.dumps(case_pack, ensure_ascii=False))
        self.assertNotIn("answers", case_pack["cases"][0])
        self.assertEqual(template_rows[0]["prediction"], "")
        dumped_template = json.dumps(template_rows, ensure_ascii=False)
        self.assertNotIn(RAW_CONTEXT_AR, dumped_template)
        self.assertNotIn(RAW_QUESTION_AR, dumped_template)
        self.assertNotIn(RAW_ANSWER_AR, dumped_template)

    def test_runner_does_not_emit_official_or_collapsed_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp) / "memoryagentbench"
            self._write_fixture(dataset_dir)

            payload = benchmark.run_memoryagentbench_smoke(dataset_dir=dataset_dir)

        metric_keys = set(payload["metrics"])
        self.assertNotIn("official_memoryagentbench_score", metric_keys)
        self.assertNotIn("leaderboard_score", metric_keys)
        self.assertNotIn("merged_retrieval_generation_judge_score", metric_keys)
        self.assertIn("llm_judge_as_source_truth", payload["cannot_claim"])
        self.assertIn("static_retrieval_covers_test_time_learning", payload["cannot_claim"])
        self.assertIn("static_retrieval_covers_conflict_resolution", payload["cannot_claim"])

    @staticmethod
    def _write_fixture(dataset_dir: Path) -> None:
        dataset_dir.mkdir(parents=True, exist_ok=True)
        rows_by_split = {
            "Accurate_Retrieval": [
                {
                    "context": RAW_CONTEXT_AR,
                    "questions": [RAW_QUESTION_AR],
                    "answers": [[RAW_ANSWER_AR]],
                    "metadata": {
                        "source": LOCAL_PATH_SENTINEL,
                        "question_types": ["lookup"],
                        "qa_pair_ids": ["ar-1"],
                        "local_debug_path": LOCAL_PATH_SENTINEL,
                    },
                    "metric": "substring_exact_match",
                    "task_type": "question_answering",
                }
            ],
            "Test_Time_Learning": [
                {
                    "context": RAW_CONTEXT_TTL,
                    "questions": ["RAW TTL QUESTION"],
                    "answers": [[RAW_ANSWER_TTL]],
                    "metadata": {"source": "ICL_banking", "question_types": ["classification"]},
                    "metric": "exact_match",
                    "task_type": "classification",
                }
            ],
            "Long_Range_Understanding": [
                {
                    "context": "SECRET LRU SUMMARY",
                    "questions": ["RAW LRU QUESTION"],
                    "answers": [["RAW LRU ANSWER"]],
                    "metadata": {"source": "detectiveQA", "question_types": ["timeline"]},
                    "metric": "exact_match",
                    "task_type": "long_range_understanding",
                }
            ],
            "Conflict_Resolution": [
                {
                    "context": "SECRET CR CONTEXT",
                    "questions": ["RAW CR QUESTION"],
                    "answers": [["RAW CR ANSWER"]],
                    "metadata": {"source": "fact_sh", "question_types": ["conflict"]},
                    "metric": "substring_exact_match",
                    "task_type": "conflict_resolution",
                }
            ],
        }
        for split, rows in rows_by_split.items():
            path = dataset_dir / f"{split}.jsonl"
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )


if __name__ == "__main__":
    unittest.main()
