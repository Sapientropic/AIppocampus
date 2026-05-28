from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    sys.path.insert(0, str(_path))

import benchmark_warm_ambient_recall as benchmark  # noqa: E402
import build_warm_ambient_trace_cases as trace_builder  # noqa: E402


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
        deep_case = next(case for case in payload["cases"] if case["case_id"] == "deep_archival_original_wording")
        self.assertEqual(deep_case["mode"], "deep_archival_recall")
        self.assertEqual(deep_case["source_validation_statuses"], {"supported": 1})
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

    def test_labeled_trace_expectations_cover_source_echo_and_topic(self) -> None:
        case = benchmark.WarmBenchmarkCase(
            case_id="labeled_trace",
            prompt="继续校准真实 trace",
            prompt_trace=[],
            expected_min_source_validation_statuses={"supported": 1},
            expected_min_current_thread_echo_count=1,
            expected_max_current_thread_echo_count=1,
            expected_topic_epoch_actions=("reuse", "rotate"),
        )

        summary = benchmark.summarize_case(
            case,
            {
                "available": True,
                "status": "ready",
                "mode": "source_backed_recall_card",
                "confidence": "high",
                "scout_count": 50,
                "scouts": [{"ok": True, "useful": True}],
                "accepted_scout_count": 1,
                "failed_scout_count": 0,
                "current_thread_echo_count": 1,
                "topic_epoch_decision": {"action": "rotate"},
                "cards": [{"source_validation": {"status": "supported"}}],
                "elapsed_ms": 1.0,
            },
        )

        self.assertTrue(summary["expectation_passed"])
        self.assertEqual(summary["expectation_failures"], [])

    def test_labeled_trace_expectation_failures_are_case_level_metrics(self) -> None:
        case = benchmark.WarmBenchmarkCase(
            case_id="labeled_trace",
            prompt="继续校准真实 trace",
            prompt_trace=[],
            expected_min_source_validation_statuses={"supported": 2},
            expected_min_current_thread_echo_count=1,
            expected_max_current_thread_echo_count=1,
            expected_topic_epoch_actions=("rotate",),
        )

        summary = benchmark.summarize_case(
            case,
            {
                "available": True,
                "status": "ready",
                "mode": "active_gentle_nudge",
                "confidence": "medium",
                "scout_count": 50,
                "scouts": [{"ok": True, "useful": True}],
                "accepted_scout_count": 1,
                "failed_scout_count": 0,
                "current_thread_echo_count": 2,
                "topic_epoch_decision": {"action": "reuse"},
                "cards": [{"source_validation": {"status": "supported"}}],
                "elapsed_ms": 1.0,
            },
        )

        self.assertFalse(summary["expectation_passed"])
        self.assertEqual(
            summary["expectation_failures"],
            [
                "topic_epoch_action",
                "source_validation:supported",
                "current_thread_echo:max",
            ],
        )

    def test_trace_case_builder_exports_sanitized_registry_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_path = "E:" + "\\private\\trace\\memory.md"
            private_title = "E:" + "\\private\\registry title"
            fake_key = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
            clean_dir = root / "registry" / "threads" / "session-test" / "clean-source"
            clean_dir.mkdir(parents=True)
            messages = clean_dir / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-secret",
                            "source_line": 1,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "api" + "_key=" + fake_key,
                        },
                        {
                            "message_id": "msg-context",
                            "source_line": 2,
                            "role": "assistant",
                            "phase": "final_answer",
                            "is_final": True,
                            "text": f"旧上下文提到 {local_path}，不应原样进入 case。",
                        },
                        {
                            "message_id": "msg-user",
                            "source_line": 3,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "继续推进 ambient recall 的真实 prompt trace 校准。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = root / "registry" / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:test",
                                "title": private_title,
                                "paths": {"clean_source_messages_jsonl": str(messages)},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                registry_path=registry_path,
                limit=5,
                per_thread=5,
                trace_window=2,
            )

        raw = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["case_count"], 1)
        self.assertEqual(payload["skipped"]["redacted_prompt"], 1)
        self.assertTrue(payload["cases"][0]["case_id"].startswith("trace_"))
        self.assertEqual(payload["cases"][0]["current_thread_key"], "session:test")
        self.assertEqual(payload["cases"][0]["expected_available"], None)
        self.assertEqual(payload["cases"][0]["expected_min_cards"], 0)
        self.assertEqual(payload["cases"][0]["prompt"], "继续推进 ambient recall 的真实 prompt trace 校准。")
        self.assertEqual(payload["cases"][0]["prompt_trace"][-1]["source_refs"][0]["line"], 3)
        self.assertIn("<redacted:local-path>", raw)
        self.assertNotIn(fake_key, raw)
        self.assertNotIn("E:" + "\\private", raw)
        self.assertNotIn(str(root), raw)

    def test_trace_case_builder_can_emit_manual_label_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_dir = root / "clean"
            clean_dir.mkdir()
            messages = clean_dir / "messages.jsonl"
            messages.write_text(
                json.dumps(
                    {
                        "message_id": "msg-1",
                        "source_line": 1,
                        "role": "user",
                        "phase": "recent_prompt",
                        "text": "继续校准 source-ref validation 和 topic drift。",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:trace",
                                "paths": {"clean_source_messages_jsonl": str(messages)},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                registry_path=registry_path,
                limit=1,
                label_template=True,
            )

        case = payload["cases"][0]
        self.assertTrue(payload["label_template"])
        self.assertEqual(case["expected_topic_epoch_actions"], [])
        self.assertEqual(case["expected_min_source_validation_statuses"], {})
        self.assertIsNone(case["expected_min_current_thread_echo_count"])
        self.assertIsNone(case["expected_max_current_thread_echo_count"])
        self.assertIn("source-ref", case["label_notes"])

    def test_trace_case_builder_output_feeds_warm_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_dir = root / "clean"
            clean_dir.mkdir()
            messages = clean_dir / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-1",
                            "source_line": 10,
                            "role": "assistant",
                            "phase": "final_answer",
                            "is_final": True,
                            "text": "detached warm job 会把 late results 写回 thread cache。",
                        },
                        {
                            "message_id": "msg-2",
                            "source_line": 11,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "继续校准 detached warm job。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:trace",
                                "paths": {"clean_source_messages_jsonl": str(messages)},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            payload = trace_builder.build_trace_cases(registry_path=registry_path, limit=1)
            cases_file = root / "warm-cases.jsonl"
            trace_builder.write_cases_file(payload["cases"], cases_file, jsonl=True)

            benchmark_payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=root / "workspace",
                cases_file=cases_file,
                live=False,
            )

        self.assertTrue(benchmark_payload["ok"])
        self.assertEqual(benchmark_payload["metrics"]["case_count"], 1)
        self.assertNotIn("detached warm job", json.dumps(benchmark_payload, ensure_ascii=False))

    def test_cases_file_redacts_private_case_id_before_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_id = "E:" + "\\private\\trace\\warm.jsonl"
            cases_file = root / "cases.json"
            cases_file.write_text(
                json.dumps(
                    [
                        {
                            "case_id": private_id,
                            "prompt": "继续校准 detached warm job",
                            "prompt_trace": [],
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
        self.assertTrue(payload["cases"][0]["case_id"].startswith("case_"))
        self.assertNotIn(private_id, raw)
        self.assertNotIn("private", raw.casefold())

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

    def test_quorum_first_benchmark_defaults_observed_rate_to_quorum_slice(self) -> None:
        fake_result = {
            "available": True,
            "status": "ready",
            "mode": "active_gentle_nudge",
            "confidence": "medium",
            "quorum_met": True,
            "scout_count": 50,
            "scouts": [{"ok": True, "useful": True} for _ in range(3)],
            "accepted_scout_count": 3,
            "failed_scout_count": 0,
            "cards": [{"source_validation": {"status": "missing_source_refs"}}],
            "elapsed_ms": 1.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(benchmark.warm, "run_warm_ambient_recall", return_value=fake_result):
                payload = benchmark.run_warm_ambient_recall_benchmark(
                    cwd=Path(tmp) / "workspace",
                    live=False,
                    case_limit=1,
                    wait_all=False,
                    quorum=3,
                )

        self.assertTrue(payload["quality_gates"]["passed"])
        self.assertEqual(payload["quality_gates"]["thresholds"]["min_observed_scout_rate"], 0.06)

    def test_missing_source_refs_are_reported_separately_from_false_evidence(self) -> None:
        metrics = benchmark.summarize_metrics(
            [
                {
                    "case_id": "missing",
                    "available": True,
                    "configured_scout_count": 50,
                    "observed_scout_result_count": 50,
                    "failed_scout_count": 0,
                    "card_count": 3,
                    "expectation_passed": True,
                    "source_validation_statuses": {
                        "missing_source_refs": 3,
                        "unsupported": 1,
                        "missing_source_ref": 1,
                    },
                }
            ]
        )

        self.assertEqual(metrics["missing_source_refs_count"], 3)
        self.assertEqual(metrics["false_evidence_count"], 2)

    def test_quality_gates_can_optionally_bound_missing_source_refs(self) -> None:
        gates = benchmark.evaluate_quality_gates(
            cases=[
                {
                    "case_id": "missing",
                    "available": True,
                    "configured_scout_count": 50,
                    "observed_scout_result_count": 50,
                    "failed_scout_count": 0,
                    "expectation_passed": True,
                    "source_validation_statuses": {"missing_source_refs": 2},
                }
            ],
            max_missing_source_refs_count=1,
        )

        self.assertFalse(gates["passed"])
        self.assertIn("missing_source_refs_count", gates["failed"])

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

    def test_live_benchmark_does_not_default_to_rigid_scout_max_tokens(self) -> None:
        fake_result = {
            "available": False,
            "status": "ready",
            "mode": "silent_tuning",
            "confidence": "low",
            "quorum_met": False,
            "scout_count": 50,
            "scouts": [],
            "accepted_scout_count": 0,
            "failed_scout_count": 0,
            "cards": [],
            "elapsed_ms": 1.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TRACE_TEST_KEY": "present"}):
                with patch.object(benchmark.warm, "run_warm_ambient_recall", return_value=fake_result) as run:
                    benchmark.run_warm_ambient_recall_benchmark(
                        cwd=Path(tmp) / "workspace",
                        live=True,
                        case_limit=1,
                        api_key_env="TRACE_TEST_KEY",
                        min_available_rate=0.0,
                        min_observed_scout_rate=0.0,
                        min_case_pass_rate=0.0,
                    )

        self.assertIsNone(run.call_args.kwargs["max_tokens"])

    def test_live_benchmark_accepts_custom_scout_max_tokens(self) -> None:
        fake_result = {
            "available": False,
            "status": "ready",
            "mode": "silent_tuning",
            "confidence": "low",
            "quorum_met": False,
            "scout_count": 50,
            "scouts": [],
            "accepted_scout_count": 0,
            "failed_scout_count": 0,
            "cards": [],
            "elapsed_ms": 1.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TRACE_TEST_KEY": "present"}):
                with patch.object(benchmark.warm, "run_warm_ambient_recall", return_value=fake_result) as run:
                    benchmark.run_warm_ambient_recall_benchmark(
                        cwd=Path(tmp) / "workspace",
                        live=True,
                        case_limit=1,
                        api_key_env="TRACE_TEST_KEY",
                        max_tokens=1536,
                        min_available_rate=0.0,
                        min_observed_scout_rate=0.0,
                        min_case_pass_rate=0.0,
                    )

        self.assertEqual(run.call_args.kwargs["max_tokens"], 1536)


if __name__ == "__main__":
    unittest.main()
