from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (BENCHMARKS, REPO_ROOT / "tools" / "aippocampus" / "smoke"):
    sys.path.insert(0, str(_path))

import benchmark_longmemeval as benchmark  # noqa: E402


class LongMemEvalBenchmarkTests(unittest.TestCase):
    def test_missing_dataset_returns_skipped_payload_with_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-longmemeval.json"

            payload = benchmark.run_longmemeval_benchmark(
                split_name="longmemeval-v1-oracle",
                data_file=path,
                max_questions=2,
                min_questions=1,
            )

        self.assertEqual(payload["kind"], "aippocampus_longmemeval_benchmark")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"])
        self.assertIn("longmemeval_retrieval_score", payload["cannot_claim"])
        self.assertEqual(payload["benchmark"]["verification"]["expected_bytes"], 15388478)
        self.assertEqual(
            payload["benchmark"]["verification"]["expected_sha256"],
            "821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c",
        )
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])

    def test_oracle_fixture_reports_sanitized_retrieval_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            fixture = [
                {
                    "question_id": "q-mini",
                    "question_type": "single-session-user",
                    "question": "What degree did I graduate with?",
                    "answer": "Business Administration",
                    "question_date": "2023/05/30 (Tue) 23:40",
                    "haystack_dates": [
                        "2023/05/20 (Sat) 02:21",
                        "2023/05/21 (Sun) 03:24",
                    ],
                    "haystack_session_ids": ["distractor", "answer_session"],
                    "answer_session_ids": ["answer_session"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": "Let's talk about my favorite hiking trail.",
                            }
                        ],
                        [
                            {
                                "role": "user",
                                "content": "I graduated with a Business Administration degree.",
                                "has_answer": True,
                            }
                        ],
                    ],
                }
            ]
            path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            split = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
            expected = benchmark.file_sha256(path)
            patched = benchmark.LongMemEvalSplit(
                dataset=split.dataset,
                filename=split.filename,
                expected_sha256=expected,
                expected_bytes=path.stat().st_size,
                benchmark_label=split.benchmark_label,
                default_role=split.default_role,
            )
            original = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
            benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = patched
            try:
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=2,
                    min_questions=1,
                    top_k=5,
                )
            finally:
                benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = original

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "retrieval_sufficient")
        self.assertEqual(payload["metrics"]["question_count"], 1)
        self.assertEqual(payload["metrics"]["session_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top5"], 1.0)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Business Administration degree", dumped)
        self.assertIn("longmemeval_qa_score", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
