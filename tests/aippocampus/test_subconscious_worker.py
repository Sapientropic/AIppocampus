from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import subconscious_worker as worker  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class SubconsciousWorkerTests(unittest.TestCase):
    def test_append_staging_edges_sanitizes_private_staging_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "subconscious_edges.jsonl"
            local_path = fake_test_windows_path("subconscious-edge-secret.txt")

            worker.append_staging_edges(
                output,
                [
                    {
                        "src": "runtime",
                        "dst": "privacy boundary",
                        "edge_type": "depends_on",
                        "confidence": 0.82,
                        "why": f"Bearer {FAKE_TEST_BEARER_TOKEN} in {local_path}",
                        "source_refs": [{"thread_key": "thread:edge", "line": 7}],
                    }
                ],
                model="deepseek-test",
                batch_id="batch-edge",
                usage={"total_tokens": 19},
                model_route={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.example/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                },
            )

            raw = output.read_text(encoding="utf-8")
            event = json.loads(raw)

            self.assertEqual(event["source_refs"], [{"thread_key": "thread:edge", "line": 7}])
            self.assertEqual(event["model_route"], {"provider": "deepseek"})
            self.assertNotIn("base_url", event["model_route"])
            self.assertNotIn("api_key_env", event["model_route"])
            self.assertNotIn(FAKE_TEST_BEARER_TOKEN, raw)
            self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, raw)
            self.assertIn("<redacted:bearer-token>", raw)
            self.assertIn("<redacted:local-path>", raw)

    def test_select_turns_and_validate_edges_are_source_backed(self) -> None:
        timeline = {
            "projects": {
                "project:t": {
                    "project_label": "T-Sense",
                    "latest_turns": [
                        {
                            "thread_key": "session:one",
                            "title": "T-Sense latest",
                            "project_label": "T-Sense",
                            "timestamp": "2026-05-25T00:00:00Z",
                            "turn_index": 40,
                            "assistant_line": 1202,
                            "topic_terms": ["Go runtime", "gotd"],
                            "user": "本地底座换语言",
                            "assistant": "做 Go runtime spike，验证 gotd。",
                        }
                    ],
                }
            }
        }
        turns = worker.select_timeline_turns(timeline, project="T-Sense", max_turns=1)
        parsed = {
            "edges": [
                {
                    "src": "本地底座",
                    "dst": "Go runtime",
                    "edge_type": "same_decision_space",
                    "confidence": 0.91,
                    "why": "同一轮里把本地底座换语言落到 Go runtime spike。",
                    "source_refs": [{"turn_ref": "t0"}],
                },
                {
                    "src": "幻想词",
                    "dst": "无来源",
                    "edge_type": "related",
                    "confidence": 0.99,
                    "source_refs": [{"turn_ref": "missing"}],
                },
            ]
        }

        edges = worker.validate_edges(parsed, turns)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["src"], "本地底座")
        self.assertEqual(edges[0]["source_refs"][0]["thread_key"], "session:one")

    def test_zero_max_turns_keeps_full_project_timeline_slice(self) -> None:
        latest_turns = [
            {
                "thread_key": f"session:{idx}",
                "timestamp": f"2026-05-25T00:0{idx}:00Z",
                "turn_index": idx,
                "user": f"user {idx}",
                "assistant": f"assistant {idx}",
            }
            for idx in range(3)
        ]
        turns = worker.select_timeline_turns(
            {"projects": {"project:t": {"project_label": "T-Sense", "latest_turns": latest_turns}}},
            project="T-Sense",
            max_turns=0,
        )

        self.assertEqual(len(turns), 3)

    def test_external_model_turn_payloads_redact_secrets_and_local_paths(self) -> None:
        timeline = {
            "projects": {
                "project:ai": {
                    "project_label": "AIppocampus",
                    "latest_turns": [
                        {
                            "thread_key": "session:secret",
                            "timestamp": "2026-05-25T00:00:00Z",
                            "turn_index": 1,
                            "user": (
                                f"继续海马体配置，api_key={FAKE_TEST_OPENAI_API_KEY} "
                                f"本地文件在 {fake_test_windows_path('token.txt')}"
                            ),
                            "assistant": f"Authorization: Bearer {FAKE_TEST_BEARER_TOKEN}",
                        }
                    ],
                }
            }
        }

        turns = worker.select_timeline_turns(timeline, project="AIppocampus", max_turns=1)
        payload = worker.user_prompt_for_turns(turns)

        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, payload)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, payload)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, payload)
        self.assertIn("<redacted:api-key>", payload)
        self.assertIn("<redacted:local-path>", payload)

    def test_call_deepseek_omits_max_tokens_by_default(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
            del timeout
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            worker.call_deepseek(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                turns=[],
                max_tokens=None,
                timeout=1,
            )

        self.assertNotIn("max_tokens", captured["body"])

    def test_openai_compatible_route_omits_json_response_format_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            output_path = root / "subconscious_edges.jsonl"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:one",
                                        "title": "AIppocampus",
                                        "timestamp": "2026-05-25T00:00:00Z",
                                        "turn_index": 1,
                                        "user": "继续清理 provider 路由。",
                                        "assistant": "用 capability gate 防止 DeepSeek 字段外泄。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            class FakeResponse:
                def __enter__(self) -> "FakeResponse":
                    return self

                def __exit__(self, *_: object) -> None:
                    return None

                def read(self) -> bytes:
                    content = {
                        "concepts": [
                            {"label": "provider capability gate", "kind": "workflow", "confidence": 0.9}
                        ],
                        "edges": [
                            {
                                "src": "provider route",
                                "dst": "capability gate",
                                "edge_type": "depends_on",
                                "confidence": 0.9,
                                "source_refs": [{"turn_ref": "t0"}],
                            }
                        ],
                    }
                    return json.dumps(
                        {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]},
                        ensure_ascii=False,
                    ).encode("utf-8")

            def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
                del timeout
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return FakeResponse()

            with patch("urllib.request.urlopen", fake_urlopen), patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_worker",
                    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-worker-model",
                    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_WORKER_KEY",
                    "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON": "false",
                    "LOCAL_WORKER_KEY": "present",
                },
                clear=False,
            ):
                result = worker.run_worker(
                    timeline_path=timeline_path,
                    output_path=output_path,
                    project="AIppocampus",
                    max_turns=1,
                    model=worker.DEFAULT_MODEL,
                    base_url=worker.DEFAULT_BASE_URL,
                    api_key=None,
                    model_route="local_worker",
                )

            self.assertNotIn("response_format", captured["body"])
            self.assertEqual(result["model"], "local-worker-model")
            self.assertEqual(result["model_route"]["provider"], "local-test")
            self.assertEqual(result["cache"], {"available": False, "kind": "none"})
            staged = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(staged["source"], "external_model_subconscious")
            self.assertEqual(staged["model_route"]["provider"], "local-test")

    def test_cli_model_route_uses_route_api_key_env_before_default_deepseek_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps({"projects": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            class FakeResponse:
                def __enter__(self) -> "FakeResponse":
                    return self

                def __exit__(self, *_: object) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {"choices": [{"message": {"content": json.dumps({"edges": []})}}]},
                        ensure_ascii=False,
                    ).encode("utf-8")

            def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
                del timeout
                captured["authorization"] = req.get_header("Authorization")
                return FakeResponse()

            stdout = io.StringIO()
            with (
                patch("urllib.request.urlopen", fake_urlopen),
                patch.object(
                    sys,
                    "argv",
                    [
                        "subconscious_worker.py",
                        "--timeline",
                        str(timeline_path),
                        "--output",
                        str(root / "edges.jsonl"),
                        "--model-route",
                        "local_worker_cli",
                        "--no-write",
                        "--json",
                    ],
                ),
                patch.dict(
                    os.environ,
                    {
                        "DEEPSEEK_API_KEY": "wrong-deepseek-key",
                        "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_worker_cli",
                        "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                        "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-worker-model",
                        "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                        "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_WORKER_CLI_KEY",
                        "LOCAL_WORKER_CLI_KEY": "right-local-key",
                    },
                    clear=False,
                ),
                contextlib.redirect_stdout(stdout),
            ):
                code = worker.main()

        self.assertEqual(code, 0, stdout.getvalue())
        self.assertEqual(captured["authorization"], "Bearer right-local-key")

    def test_default_dry_run_stdout_omits_prompt_preview(self) -> None:
        private_result = {
            "ok": True,
            "dry_run": True,
            "turn_count": 1,
            "prompt_preview": "private prompt preview must stay out",
        }
        stdout = io.StringIO()
        with (
            patch.object(worker, "run_worker", return_value=private_result),
            patch.object(sys, "argv", ["subconscious_worker.py", "--dry-run"]),
            contextlib.redirect_stdout(stdout),
        ):
            code = worker.main()

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("dry run: 1 turn(s)", rendered)
        self.assertNotIn("private prompt preview", rendered)


if __name__ == "__main__":
    unittest.main()
