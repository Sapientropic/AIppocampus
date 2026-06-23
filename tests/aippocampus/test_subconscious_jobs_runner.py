from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aippocampus_runtime.subconscious import (
    jobs,
)
from tests.aippocampus.redaction_fixtures import (
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)
from tests.aippocampus.timing_fixtures import host_timeout_sleep

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
JOBS_RUNNER = SCRIPTS / "aippocampus_runtime" / "subconscious" / "jobs.py"

class SubconsciousJobsRunnerTests(unittest.TestCase):
    def test_source_semantic_worker_no_key_reports_unavailable_without_blocking_deterministic_jobs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:origin",
                                        "title": "AIppocampus origin",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "我们把这个叫小海马体。",
                                        "assistant": "机械飞升也是一个连续性隐喻。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            missing_env = "MISSING_SOURCE_ALIAS_KEY_FOR_TEST"
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(missing_env, None)
                result = jobs.run_jobs(
                    jobs=["source_alias_mining", "question_tracking"],
                    registry_path=registry_path,
                    timeline_path=timeline_path,
                    concept_graph_path=root / "missing.sqlite",
                    jobs_output_path=root / "subconscious_jobs.jsonl",
                    edges_output_path=root / "subconscious_edges.jsonl",
                    project="AIppocampus",
                    objective="test source semantic no-key behavior",
                    max_turns=4,
                    max_steps=1,
                    min_tool_steps=0,
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    api_key=None,
                    api_key_env=missing_env,
                    max_tokens=None,
                    timeout=1,
                    temperature=0.2,
                    concurrency=1,
                    samples_per_job=1,
                    no_write=True,
                )

        by_job = {row["job"]: row for row in result["jobs"]}
        public = jobs.public_jobs_payload(result)

        self.assertFalse(result["ok"])
        self.assertTrue(result["semantic_worker_unavailable"])
        self.assertEqual(result["semantic_worker_mode"], "semantic_worker_unavailable_deterministic_only")
        self.assertTrue(by_job["source_alias_mining"]["semantic_worker_unavailable"])
        self.assertTrue(by_job["question_tracking"]["ok"])
        self.assertTrue(public["semantic_worker_unavailable"])
        self.assertEqual(public["semantic_worker_unavailable_reason"], "missing_provider_key")

    def test_run_jobs_can_execute_samples_concurrently_without_parallel_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"
            active = 0
            max_active = 0
            lock = threading.Lock()
            call_count = 0

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal active, max_active, call_count
                with lock:
                    active += 1
                    call_count += 1
                    max_active = max(max_active, active)
                    current = call_count
                host_timeout_sleep(
                    0.05,
                    reason="keep concurrent job samples overlapping long enough to measure fanout",
                )
                with lock:
                    active -= 1
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": f"Concurrent finding {current}",
                            "summary": "DeepSeek sample produced a source-backed finding.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift", "trigger_mining"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="AIppocampus",
                objective="test concurrent jobs",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=4,
                samples_per_job=2,
                chat_fn=fake_chat,
            )

            self.assertEqual(result["job_count"], 4)
            self.assertGreater(max_active, 1)
            self.assertTrue(jobs_output.exists())
            lines = jobs_output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)
            self.assertTrue(all("aippocampus_subconscious_job_finding" in line for line in lines))

    def test_openai_compatible_route_caps_subconscious_job_concurrency_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "provider route 怎么收口？",
                                        "assistant": "用 local/offline capability 做保守 fallback。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, base_url, max_tokens, timeout, temperature
                self.assertEqual(model, "local-jobs-model")
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Provider boundary",
                            "summary": "Local provider route keeps conservative defaults.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            with patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_jobs",
                    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-jobs-model",
                    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_JOBS_KEY",
                    "LOCAL_JOBS_KEY": "present",
                },
                clear=False,
            ):
                result = jobs.run_jobs(
                    jobs=["project_drift", "trigger_mining"],
                    registry_path=registry_path,
                    timeline_path=timeline_path,
                    concept_graph_path=root / "missing.sqlite",
                    jobs_output_path=root / "subconscious_jobs.jsonl",
                    edges_output_path=root / "subconscious_edges.jsonl",
                    project="AIppocampus",
                    objective="test local provider boundary",
                    max_turns=4,
                    max_steps=1,
                    min_tool_steps=0,
                    model=jobs.DEFAULT_MODEL,
                    base_url=jobs.DEFAULT_BASE_URL,
                    api_key=None,
                    max_tokens=None,
                    timeout=1,
                    temperature=0.2,
                    concurrency=4,
                    samples_per_job=1,
                    model_route="local_jobs",
                    chat_fn=fake_chat,
                )

            self.assertEqual(result["concurrency"], 1)
            self.assertEqual(result["model_route"]["provider"], "local-test")
            self.assertEqual(result["cache"], {"available": False, "kind": "none"})
            self.assertEqual(result["jobs"][0]["model"], "local-jobs-model")
            staged = json.loads(
                (root / "subconscious_jobs.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(staged["source"], "external_model_subconscious_jobs")
            self.assertEqual(staged["model_route"]["provider"], "local-test")

    def test_run_jobs_warms_first_sample_before_same_prefix_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"
            sample1_finished = threading.Event()
            sample2_started_before_warm = False
            lock = threading.Lock()

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal sample2_started_before_warm
                payload = json.loads(messages[1]["content"])
                sample_two = "Diversity sample 2/2" in str(payload.get("objective") or "")
                with lock:
                    if sample_two and not sample1_finished.is_set():
                        sample2_started_before_warm = True
                host_timeout_sleep(
                    0.02,
                    reason="keep first sample active while testing prefix warmup ordering",
                )
                if not sample_two:
                    sample1_finished.set()
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Warmup finding",
                            "summary": "DeepSeek sample produced a source-backed finding.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="AIppocampus",
                objective="test cache warmup ordering",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=2,
                samples_per_job=2,
                chat_fn=fake_chat,
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(sample2_started_before_warm)

    def test_run_one_job_repairs_malformed_json_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            calls = 0

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal calls
                calls += 1
                if calls == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"action":"final","findings":[{"title":"broken"'
                                }
                            }
                        ],
                        "usage": {"total_tokens": 1},
                    }
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Repaired finding",
                            "summary": "The malformed first response was repaired into source-backed JSON.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_one_job(
                job="project_drift",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test malformed repair",
                max_turns=4,
                max_steps=2,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
                no_write=True,
            )

            self.assertEqual(calls, 2)
            self.assertEqual(result["finding_count"], 1)
            self.assertEqual(result["findings"][0]["title"], "Repaired finding")

    def test_tool_observations_are_redacted_before_second_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages_path = root / "messages.jsonl"
            messages_path.write_text(
                json.dumps(
                    {
                        "message_id": "m1",
                        "turn_id": "turn-1",
                        "source_line": 10,
                        "role": "user",
                        "phase": "",
                        "turn_index": 1,
                        "text": f"token={FAKE_TEST_SECRET_VALUE} {fake_test_windows_path('jobs-tool.txt')}",
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
                        "threads": [
                            {
                                "thread_key": "session:one",
                                "title": "Secret job test",
                                "project_label": "AIppocampus",
                                "project_tags": ["AIppocampus"],
                                "paths": {"clean_source_messages_jsonl": str(messages_path)},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:one",
                                        "title": "Secret job test",
                                        "turn_id": "turn-1",
                                        "turn_index": 1,
                                        "user": "find token source",
                                        "assistant": "ok",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            calls: list[list[dict[str, str]]] = []

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                calls.append(messages)
                content = (
                    {
                        "action": "tool",
                        "tool": "search_clean_source",
                        "args": {"terms": ["token"], "limit": 1},
                    }
                    if len(calls) == 1
                    else {"action": "final", "findings": []}
                )
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            jobs.run_one_job(
                job="project_drift",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test redaction",
                max_turns=4,
                max_steps=2,
                min_tool_steps=1,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
                no_write=True,
            )

        second_call = json.dumps(calls[1], ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, second_call)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, second_call)
        self.assertIn("<redacted:secret>", second_call)
        self.assertIn("<redacted:local-path>", second_call)

    def test_run_jobs_isolates_failed_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "多线程 hook 会不会重复启动？",
                                        "assistant": "scheduler 用 lease 折叠重复启动。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                if "Diversity sample 1/2" in messages[1]["content"]:
                    raise RuntimeError("simulated malformed provider response")
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Surviving sample",
                            "summary": "A second sample should survive even when the first fails.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test failure isolation",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=2,
                samples_per_job=2,
                chat_fn=fake_chat,
                no_write=True,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["partial_failure"])
            self.assertEqual(result["successful_job_count"], 1)
            self.assertEqual(result["failure_count"], 1)
            self.assertEqual(result["finding_count"], 1)

if __name__ == "__main__":
    unittest.main()
