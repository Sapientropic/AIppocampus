from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import model_client  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class ModelClientTests(unittest.TestCase):
    def test_chat_json_sanitizes_payload_and_omits_unset_max_tokens(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            captured["timeout"] = timeout
            captured["body"] = json.loads(getattr(req, "data").decode("utf-8"))
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

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            captured["url"] = getattr(req, "full_url")
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

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            del timeout
            captured["body"] = json.loads(getattr(req, "data").decode("utf-8"))
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    user_id="aip-warm-abc_123",
                ),
            )

        self.assertEqual(captured["body"]["user_id"], "aip-warm-abc_123")

    def test_chat_json_can_disable_model_thinking(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            del timeout
            captured["body"] = json.loads(getattr(req, "data").decode("utf-8"))
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    thinking="disabled",
                ),
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertIn("temperature", captured["body"])

    def test_chat_json_omits_temperature_for_enabled_thinking(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            del timeout
            captured["body"] = json.loads(getattr(req, "data").decode("utf-8"))
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    temperature=0.2,
                    thinking="enabled",
                ),
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "enabled"})
        self.assertNotIn("temperature", captured["body"])

    def test_chat_json_rejects_unknown_thinking_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "thinking"):
            model_client.chat_json(
                [{"role": "user", "content": "{}"}],
                model_client.ChatClientConfig(
                    api_key="test",
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    thinking="fast",
                ),
            )


if __name__ == "__main__":
    unittest.main()
