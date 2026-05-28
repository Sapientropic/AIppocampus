from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    sys.path.insert(0, str(_path))

import benchmark_warm_ambient_recall as benchmark  # noqa: E402


class WarmAmbientRecallBenchmarkTests(unittest.TestCase):
    def test_deterministic_benchmark_emits_sanitized_metrics_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=Path(tmp) / "workspace",
                case_limit=2,
                live=False,
            )

        raw = json.dumps(payload, ensure_ascii=False).casefold()

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["live_model"])
        self.assertEqual(payload["metrics"]["case_count"], 2)
        self.assertGreater(payload["metrics"]["total_scout_calls"], 0)
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["raw_cards_emitted"], False)
        self.assertIn("prompt_sha1", payload["cases"][0])
        self.assertNotIn("那个脑内续接器", raw)
        self.assertNotIn("cards", payload["cases"][0])

    def test_deterministic_benchmark_uses_quality_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=Path(tmp) / "workspace",
                live=False,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertGreaterEqual(payload["metrics"]["case_count"], 10)
        self.assertEqual(
            payload["metrics"]["total_scout_calls"],
            payload["metrics"]["configured_scout_calls"],
        )
        self.assertTrue(payload["quality_gates"]["passed"])
        self.assertEqual(payload["quality_gates"]["failed_case_ids"], [])

    def test_benchmark_loads_cases_file_for_larger_trace_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases_file = root / "cases.json"
            cases_file.write_text(
                json.dumps(
                    [
                        {
                            "case_id": "custom_trace",
                            "prompt": "继续校准 detached warm job",
                            "prompt_trace": [
                                {
                                    "thread_key": "session:custom",
                                    "role": "user",
                                    "text": "detached warm job should write thread cache later",
                                }
                            ],
                            "expected_available": True,
                            "expected_min_cards": 1,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=root / "workspace",
                cases_file=cases_file,
                live=False,
            )

        raw = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["case_count"], 1)
        self.assertEqual(payload["cases"][0]["case_id"], "custom_trace")
        self.assertNotIn("detached warm job", raw)

    def test_quality_gates_fail_when_observed_scout_rate_is_too_low(self) -> None:
        gates = benchmark.evaluate_quality_gates(
            cases=[
                {
                    "case_id": "partial",
                    "configured_scout_count": 50,
                    "observed_scout_result_count": 3,
                    "available": True,
                    "expectation_passed": True,
                    "failed_scout_count": 0,
                    "source_validation_statuses": {},
                }
            ],
            min_available_rate=0.5,
            min_observed_scout_rate=0.9,
            min_case_pass_rate=1.0,
        )

        self.assertFalse(gates["passed"])
        self.assertIn("observed_scout_rate", gates["failed"])

    def test_benchmark_summarizes_timeout_and_rate_limit_failures(self) -> None:
        summary = benchmark.summarize_case(
            benchmark.BUILTIN_CASES[0],
            {
                "available": False,
                "status": "ready",
                "scout_count": 2,
                "scouts": [
                    {"ok": False, "error_kind": "read_timeout"},
                    {"ok": False, "error_kind": "rate_limited_429"},
                ],
                "accepted_scout_count": 0,
                "failed_scout_count": 2,
                "cards": [],
                "elapsed_ms": 100.0,
            },
        )
        metrics = benchmark.summarize_metrics([summary])

        self.assertEqual(summary["scout_error_kinds"]["read_timeout"], 1)
        self.assertEqual(summary["scout_error_kinds"]["rate_limited_429"], 1)
        self.assertEqual(metrics["scout_error_kinds"]["read_timeout"], 1)
        self.assertEqual(metrics["scout_error_kinds"]["rate_limited_429"], 1)


if __name__ == "__main__":
    unittest.main()
