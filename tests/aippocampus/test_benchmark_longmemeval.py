from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (BENCHMARKS, REPO_ROOT / "tools" / "aippocampus" / "smoke"):
    sys.path.insert(0, str(_path))

import benchmark_longmemeval as benchmark  # noqa: E402


def write_oracle_fixture(path: Path, *, question_count: int = 1) -> None:
    fixture = []
    for index in range(question_count):
        fixture.append(
            {
                "question_id": f"q-mini-{index}",
                "question_type": "single-session-user",
                "question": f"Where did the retrieval marker {index} appear?",
                "answer": f"secret fixture answer marker {index}",
                "question_date": "2023/05/30 (Tue) 23:40",
                "haystack_dates": [
                    "2023/05/20 (Sat) 02:21",
                    "2023/05/21 (Sun) 03:24",
                ],
                "haystack_session_ids": [f"distractor-{index}", f"answer-session-{index}"],
                "answer_session_ids": [f"answer-session-{index}"],
                "haystack_sessions": [
                    [
                        {
                            "role": "user",
                            "content": f"Let's talk about an unrelated trail {index}.",
                        }
                    ],
                    [
                        {
                            "role": "user",
                            "content": f"The retrieval marker {index} appears in the answer session.",
                            "has_answer": True,
                        }
                    ],
                ],
            }
        )
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


@contextmanager
def patched_oracle_split(path: Path) -> Iterator[None]:
    split = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
    patched = benchmark.LongMemEvalSplit(
        dataset=split.dataset,
        filename=split.filename,
        expected_sha256=benchmark.file_sha256(path),
        expected_bytes=path.stat().st_size,
        benchmark_label=split.benchmark_label,
        default_role=split.default_role,
    )
    original = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
    benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = patched
    try:
        yield
    finally:
        benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = original


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
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=2,
                    min_questions=1,
                    top_k=5,
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "retrieval_sufficient")
        self.assertEqual(payload["metrics"]["question_count"], 1)
        self.assertEqual(payload["metrics"]["session_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top5"], 1.0)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertIn("longmemeval_qa_score", payload["cannot_claim"])

    def test_progress_callback_reports_sanitized_phase_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path, question_count=3)
            progress_events: list[dict[str, Any]] = []
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=3,
                    min_questions=3,
                    top_k=5,
                    progress_every=1,
                    progress_callback=progress_events.append,
                )

        self.assertTrue(payload["ok"], payload)
        phases = [event.get("phase") for event in progress_events]
        self.assertIn("dataset_verified", phases)
        self.assertIn("cases_building", phases)
        self.assertIn("cases_built", phases)
        self.assertIn("cases_evaluated", phases)
        building_counts = [
            int(event.get("cases_built") or 0)
            for event in progress_events
            if event.get("phase") == "cases_building"
        ]
        self.assertIn(1, building_counts)
        evaluated_counts = [
            int(event.get("cases_evaluated") or 0)
            for event in progress_events
            if event.get("phase") == "cases_evaluated"
        ]
        self.assertIn(3, evaluated_counts)
        dumped = json.dumps(progress_events, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn(str(path), dumped)

    def test_partial_output_records_interrupted_diagnostic_without_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            partial_path = Path(tmp) / "partial.json"
            write_oracle_fixture(path, question_count=3)

            def stop_after_first_eval(event: dict[str, Any]) -> None:
                if event.get("phase") == "cases_evaluated" and int(
                    event.get("cases_evaluated") or 0
                ) >= 1:
                    raise KeyboardInterrupt

            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=3,
                    min_questions=3,
                    top_k=5,
                    progress_every=1,
                    partial_output=partial_path,
                    progress_callback=stop_after_first_eval,
                )

            partial = json.loads(partial_path.read_text(encoding="utf-8"))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "partial_diagnostic_interrupted")
        self.assertEqual(partial["status"], "partial_diagnostic_interrupted")
        self.assertGreaterEqual(partial["metrics"]["cases_built"], 1)
        self.assertGreaterEqual(partial["metrics"]["cases_evaluated"], 1)
        self.assertIn("longmemeval_retrieval_score", partial["cannot_claim"])
        dumped = json.dumps(partial, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn(str(path), dumped)


if __name__ == "__main__":
    unittest.main()
