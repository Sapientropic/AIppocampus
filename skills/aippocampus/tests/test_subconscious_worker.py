from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import subconscious_worker as worker  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class SubconsciousWorkerTests(unittest.TestCase):
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

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            del timeout
            captured["body"] = json.loads(getattr(req, "data").decode("utf-8"))
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


if __name__ == "__main__":
    unittest.main()
