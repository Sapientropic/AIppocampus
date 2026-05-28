from __future__ import annotations

import json
import sys
import tempfile
import time
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

    def test_benchmark_runs_cases_concurrently_when_case_workers_is_set(self) -> None:
        active = 0
        max_active = 0
        original_scout = benchmark.deterministic_scout_fn

        def slow_scout(*args, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            time.sleep(0.02)
            active -= 1
            return original_scout(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(benchmark, "deterministic_scout_fn", slow_scout):
            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=Path(tmp) / "workspace",
                case_limit=4,
                live=False,
                wait_all=True,
                max_workers=1,
                case_workers=2,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["case_count"], 4)
        self.assertEqual(payload["config"]["case_workers"], 2)
        self.assertGreaterEqual(max_active, 2)

    def test_benchmark_writes_sanitized_progress_jsonl_per_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.jsonl"
            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=root / "workspace",
                case_limit=3,
                live=False,
                progress_jsonl=progress,
            )

            rows = [
                json.loads(line)
                for line in progress.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        raw = json.dumps(rows, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["event"], "case_completed")
        self.assertIn("prompt_sha1", rows[0]["case"])
        self.assertNotIn("prompt_trace", raw)
        self.assertNotIn("那个脑内续接器", raw)

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

    def test_trace_case_builder_reads_clean_source_messages_without_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-a1",
                            "source_id": "src-a",
                            "source_line": 1,
                            "role": "assistant",
                            "phase": "final_answer",
                            "text": "first conversation prior assistant line",
                        },
                        {
                            "message_id": "msg-a2",
                            "source_id": "src-a",
                            "source_line": 2,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "继续校准 benchmark corpus 的 warm recall。",
                        },
                        {
                            "message_id": "msg-b1",
                            "source_id": "src-b",
                            "source_line": 1,
                            "role": "assistant",
                            "phase": "final_answer",
                            "text": "second conversation must not leak into first trace",
                        },
                        {
                            "message_id": "msg-b2",
                            "source_id": "src-b",
                            "source_line": 2,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "继续测试另一个 corpus conversation。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="sharegpt_coding_multiturn",
                limit=2,
                per_thread=1,
                trace_window=2,
            )

        raw = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["source_mode"], "clean_source_messages")
        self.assertEqual(payload["case_count"], 2)
        self.assertTrue(payload["source_subset"]["thread_key"].startswith("corpus:"))
        self.assertEqual(payload["cases"][0]["current_thread_key"], payload["source_subset"]["thread_key"])
        self.assertEqual(payload["cases"][0]["prompt_trace"][0]["text"], "first conversation prior assistant line")
        self.assertEqual(payload["cases"][0]["prompt_trace"][-1]["source_refs"][0]["message_id"], "msg-a2")
        self.assertNotIn("second conversation must not leak", json.dumps(payload["cases"][0], ensure_ascii=False))
        self.assertNotIn(str(root), raw)

    def test_trace_case_builder_can_skip_initial_turns_for_trace_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-u1",
                            "source_id": "src-a",
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": "第一轮没有足够前文。",
                        },
                        {
                            "message_id": "msg-a1",
                            "source_id": "src-a",
                            "source_line": 2,
                            "role": "assistant",
                            "turn_index": 1,
                            "phase": "final_answer",
                            "text": "前一轮回答可作为 source-ref 上下文。",
                        },
                        {
                            "message_id": "msg-u2",
                            "source_id": "src-a",
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": "继续基于上一轮回答校准。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="sharegpt_coding_multiturn",
                limit=1,
                per_thread=1,
                trace_window=3,
                min_turn_index=2,
            )

        case = payload["cases"][0]
        self.assertEqual(payload["case_count"], 1)
        self.assertEqual(case["prompt"], "继续基于上一轮回答校准。")
        self.assertEqual([row["source_refs"][0]["message_id"] for row in case["prompt_trace"]], ["msg-u1", "msg-a1", "msg-u2"])

    def test_trace_case_builder_can_apply_separate_label_policies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-u1",
                            "source_id": "src-a",
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": "怎么设计 recall cache？",
                        },
                        {
                            "message_id": "msg-a1",
                            "source_id": "src-a",
                            "source_line": 2,
                            "role": "assistant",
                            "turn_index": 1,
                            "phase": "final_answer",
                            "text": "recall cache 要避免把当前线程回声当成外部记忆。",
                        },
                        {
                            "message_id": "msg-u2",
                            "source_id": "src-a",
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": "继续这个 recall cache 方案。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            source_payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="source_ref_supported",
            )
            echo_payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="echo_guard",
            )
            topic_payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="topic_epoch_heuristic",
            )
            vote_payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="topic_epoch_vote",
            )

        source_case = source_payload["cases"][0]
        echo_case = echo_payload["cases"][0]
        topic_case = topic_payload["cases"][0]
        vote_case = vote_payload["cases"][0]
        self.assertNotIn("current_thread_key", source_case)
        self.assertEqual(source_case["expected_min_source_validation_statuses"], {"supported": 1})
        self.assertEqual(echo_case["expected_min_current_thread_echo_count"], 1)
        self.assertEqual(echo_case["current_thread_key"], echo_payload["source_subset"]["thread_key"])
        self.assertEqual(topic_case["expected_topic_epoch_actions"], ["reuse"])
        self.assertEqual(vote_case["expected_topic_epoch_actions"], ["reuse", "rotate", "suppress"])
        self.assertIn("auto label", topic_case["label_notes"])

    def test_source_ref_label_does_not_require_current_prompt_echo_for_topic_jump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-u1",
                            "source_id": "src-a",
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": "Explain ARM register types.",
                        },
                        {
                            "message_id": "msg-a1",
                            "source_id": "src-a",
                            "source_line": 2,
                            "role": "assistant",
                            "turn_index": 1,
                            "phase": "final_answer",
                            "text": "ARM has general-purpose, status, and control registers.",
                        },
                        {
                            "message_id": "msg-u2",
                            "source_id": "src-a",
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": "what are some advanced use cases for node.js",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="source_ref_supported",
            )

        case = payload["cases"][0]
        self.assertEqual(case["expected_min_cards"], 0)
        self.assertEqual(case["expected_min_source_validation_statuses"], {})
        self.assertIn("no prior support", case["label_notes"])

    def test_echo_label_does_not_require_echo_attempt_for_long_pasted_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            long_prompt = "Okay here is the letter so far. " + ("Please smooth transitions. " * 80)
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-u1",
                            "source_id": "src-a",
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": "Draft a technical writing instructor application letter.",
                        },
                        {
                            "message_id": "msg-a1",
                            "source_id": "src-a",
                            "source_line": 2,
                            "role": "assistant",
                            "turn_index": 1,
                            "phase": "final_answer",
                            "text": "Here is a polished application letter draft.",
                        },
                        {
                            "message_id": "msg-u2",
                            "source_id": "src-a",
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": long_prompt,
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="policy",
                limit=1,
                min_turn_index=2,
                label_policy="echo_guard",
            )

        case = payload["cases"][0]
        self.assertIsNone(case["expected_min_current_thread_echo_count"])
        self.assertIn("no echo-trigger requirement", case["label_notes"])

    def test_trace_case_builder_writes_clean_source_case_pack_for_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            messages.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in [
                        {
                            "message_id": "msg-source",
                            "source_id": "src-one",
                            "source_line": 1,
                            "role": "assistant",
                            "phase": "final_answer",
                            "text": "continuity survives transformation",
                        },
                        {
                            "message_id": "msg-user",
                            "source_id": "src-one",
                            "source_line": 2,
                            "role": "user",
                            "phase": "recent_prompt",
                            "text": "找回 continuity 的原话。",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            payload = trace_builder.build_trace_cases(
                clean_source_messages=messages,
                dataset_id="tiny-corpus",
                limit=1,
                trace_window=2,
                label_template=True,
            )
            cases_path = root / "cases.jsonl"
            subset_path = root / "case-pack" / "clean-source" / "messages.jsonl"
            registry_path = root / "case-pack" / "threads.json"

            trace_builder.write_cases_file(payload["cases"], cases_path, jsonl=True)
            trace_builder.write_clean_source_case_pack(
                payload,
                messages_path=subset_path,
                registry_path=registry_path,
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            subset_rows = [
                json.loads(line)
                for line in subset_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            written_case = json.loads(cases_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(registry["threads"][0]["thread_key"], payload["source_subset"]["thread_key"])
        self.assertEqual(
            registry["threads"][0]["paths"]["clean_source_messages_jsonl"],
            str(subset_path),
        )
        self.assertEqual([row["message_id"] for row in subset_rows], ["msg-source", "msg-user"])
        self.assertEqual(payload["cases"][0]["expected_topic_epoch_actions"], [])
        self.assertEqual(written_case["case_id"], payload["cases"][0]["case_id"])

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

    def test_benchmark_metrics_aggregate_prompt_cache_hit_rate(self) -> None:
        metrics = benchmark.summarize_metrics(
            [
                {
                    "case_id": "cache-a",
                    "available": True,
                    "configured_scout_count": 50,
                    "observed_scout_result_count": 50,
                    "failed_scout_count": 0,
                    "expectation_passed": True,
                    "cache": {"available": True, "hit_tokens": 80, "miss_tokens": 20},
                },
                {
                    "case_id": "cache-b",
                    "available": True,
                    "configured_scout_count": 50,
                    "observed_scout_result_count": 50,
                    "failed_scout_count": 0,
                    "expectation_passed": True,
                    "cache": {"available": True, "hit_tokens": 20, "miss_tokens": 80},
                },
            ]
        )

        self.assertEqual(metrics["prompt_cache_hit_tokens"], 100)
        self.assertEqual(metrics["prompt_cache_miss_tokens"], 100)
        self.assertEqual(metrics["prompt_cache_hit_rate"], 0.5)

    def test_benchmark_metrics_track_trace_fallback_cards(self) -> None:
        summary = benchmark.summarize_case(
            benchmark.BUILTIN_CASES[0],
            {
                "available": True,
                "status": "ready",
                "scout_count": 50,
                "scouts": [],
                "accepted_scout_count": 0,
                "failed_scout_count": 0,
                "trace_fallback_card_count": 1,
                "cards": [{"source_validation": {"status": "supported"}}],
            },
        )
        metrics = benchmark.summarize_metrics([summary])

        self.assertEqual(summary["trace_fallback_card_count"], 1)
        self.assertEqual(metrics["trace_fallback_card_count"], 1)

    def test_case_summary_preserves_zero_prompt_cache_metrics(self) -> None:
        summary = benchmark.summarize_case(
            benchmark.BUILTIN_CASES[0],
            {
                "available": False,
                "status": "ready",
                "scout_count": 1,
                "scouts": [],
                "accepted_scout_count": 0,
                "failed_scout_count": 0,
                "cards": [],
                "cache": {"available": True, "hit_rate": 0.0, "hit_tokens": 0, "miss_tokens": 42},
            },
        )

        self.assertEqual(summary["cache"]["hit_rate"], 0.0)
        self.assertEqual(summary["cache"]["hit_tokens"], 0)
        self.assertEqual(summary["cache"]["miss_tokens"], 42)

    def test_warm_error_kind_separates_provider_busy_from_generic_scout_error(self) -> None:
        reason = 'RuntimeError: DeepSeek API HTTP 503: {"error":{"code":"service_unavailable_error"}}'

        self.assertEqual(benchmark.warm.scout_error_kind(reason), "service_unavailable_503")

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
        self.assertEqual(run.call_args.kwargs["prefix_cache_warmup_scouts"], 0)

    def test_live_benchmark_can_enable_prefix_cache_warmup(self) -> None:
        fake_result = {
            "available": False,
            "status": "ready",
            "mode": "silent_tuning",
            "confidence": "low",
            "quorum_met": False,
            "scout_count": 50,
            "prefix_cache_warmup_scout_count": 2,
            "scouts": [],
            "accepted_scout_count": 0,
            "failed_scout_count": 0,
            "cards": [],
            "elapsed_ms": 1.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TRACE_TEST_KEY": "present"}):
                with patch.object(benchmark.warm, "run_warm_ambient_recall", return_value=fake_result) as run:
                    payload = benchmark.run_warm_ambient_recall_benchmark(
                        cwd=Path(tmp) / "workspace",
                        live=True,
                        case_limit=1,
                        api_key_env="TRACE_TEST_KEY",
                        prefix_cache_warmup_scouts=2,
                        prefix_cache_warmup_delay=0.5,
                        min_available_rate=0.0,
                        min_observed_scout_rate=0.0,
                        min_case_pass_rate=0.0,
                    )

        self.assertEqual(run.call_args.kwargs["prefix_cache_warmup_scouts"], 2)
        self.assertEqual(run.call_args.kwargs["prefix_cache_warmup_delay"], 0.5)
        self.assertEqual(payload["metrics"]["prefix_cache_warmup_scout_calls"], 2)

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
