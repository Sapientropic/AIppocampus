from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.model import client as model_client  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class ModelClientTests(unittest.TestCase):
    def test_deepseek_chat_requires_explicit_cache_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "cache_contract"):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                ),
            )

    def test_deepseek_cache_metrics_are_available_from_response_usage(self) -> None:
        response = {
            "usage": {
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 10,
            }
        }
        metrics = model_client.cache_metrics_from_response(
            response,
            model_client.ChatClientConfig(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
            ),
        )

        self.assertEqual(metrics["kind"], "deepseek_prefix")
        self.assertEqual(metrics["hit_tokens"], 90)
        self.assertEqual(metrics["miss_tokens"], 10)
        self.assertEqual(metrics["hit_rate"], 0.9)

    def test_chat_json_sanitizes_payload_and_omits_unset_max_tokens(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
            captured["timeout"] = timeout
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse()

        messages = [
            {
                "role": "user",
                "content": f"api_key={FAKE_TEST_OPENAI_API_KEY} {fake_test_windows_path('model.txt')}",
            }
        ]

        with patch("urllib.request.urlopen", fake_urlopen):
            model_client.chat_json(
                messages,
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    max_tokens=None,
                    timeout=7,
                    temperature=0.2,
                ),
            )

        body = json.dumps(captured["body"], ensure_ascii=False)
        self.assertEqual(captured["timeout"], 7)
        self.assertNotIn("max_tokens", captured["body"])
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, body)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, body)
        self.assertIn("<redacted:api-key>", body)
        self.assertIn("<redacted:local-path>", body)

    def test_api_key_requires_https_unless_base_url_is_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires HTTPS"):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="http://api.example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                ),
            )

    def test_loopback_http_base_url_keeps_local_proxy_compatibility(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="local-model",
                    base_url="http://localhost:11434/v1",
                    timeout=3,
                ),
            )

        self.assertEqual(captured["url"], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(captured["timeout"], 3)

    def test_chat_json_includes_sanitized_user_id_when_configured(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    user_id="aip-warm-abc_123",
                ),
            )

        self.assertEqual(captured["body"]["user_id"], "aip-warm-abc_123")

    def test_chat_json_can_disable_model_thinking_without_forcing_temperature(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    thinking="disabled",
                ),
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertNotIn("temperature", captured["body"])

    def test_chat_json_sends_explicit_temperature_when_sampling_is_supported(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    thinking="disabled",
                    temperature=0.2,
                ),
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["body"]["temperature"], 0.2)

    def test_chat_json_omits_temperature_for_enabled_thinking(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    temperature=0.2,
                    thinking="enabled",
                ),
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "enabled"})
        self.assertNotIn("temperature", captured["body"])

    def test_chat_json_sends_reasoning_effort_and_omits_sampling_params(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    reasoning_effort="high",
                ),
            )

        self.assertEqual(captured["body"]["reasoning_effort"], "high")
        self.assertNotIn("temperature", captured["body"])
        self.assertNotIn("thinking", captured["body"])

    def test_chat_json_rejects_reasoning_effort_when_thinking_disabled(self) -> None:
        with self.assertRaisesRegex(ValueError, "reasoning_effort"):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    thinking="disabled",
                    reasoning_effort="high",
                ),
            )

    def test_chat_json_strips_reasoning_content_with_diagnostic(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "reasoning_content": "private hidden chain of thought",
                                    "content": "{}",
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
            del req, timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            response = model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                ),
            )

        message = response["choices"][0]["message"]
        self.assertNotIn("reasoning_content", message)
        self.assertEqual(message["content"], "{}")
        diagnostic = response["aippocampus_diagnostics"]["reasoning_content"]
        self.assertEqual(diagnostic["handling"], "discarded_without_storage")
        self.assertFalse(diagnostic["tool_call_continuation_supported"])
        self.assertNotIn("private hidden chain of thought", json.dumps(response))

    def test_chat_json_rejects_reasoning_content_tool_call_continuation_gap(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "reasoning_content": "private hidden chain of thought",
                                    "content": "",
                                    "tool_calls": [{"id": "call_1"}],
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(req: Request, timeout: int) -> FakeResponse:
            del req, timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "tool_calls"):
                model_client.chat_json(
                    [{"role": "user", "content": "{}"}],
                    model_client.ChatClientConfig(
                        api_key="test",
                        model="deepseek-v4-flash",
                        base_url="https://example.invalid",
                        cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    ),
                )

    def test_chat_json_rejects_unknown_thinking_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "thinking"):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    cache_contract=model_client.DEEPSEEK_PREFIX_CACHE_CONTRACT,
                    thinking="fast",
                ),
            )

    def test_chat_json_can_omit_json_response_format_for_compatible_providers(self) -> None:
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
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="local-model",
                    base_url="http://127.0.0.1:11434/v1",
                    response_format_json=False,
                ),
            )

        self.assertNotIn("response_format", captured["body"])


if __name__ == "__main__":
    unittest.main()
