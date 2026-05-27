from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import subconscious_agent as agent  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


class SubconsciousAgentTests(unittest.TestCase):
    def test_agent_initial_payload_keeps_turns_before_variable_objective(self) -> None:
        payload = json.loads(
            agent.agent_initial_payload(
                "Find durable edges from this run.",
                [{"turn_ref": "t0", "user": "A", "assistant": "B"}],
                max_steps=4,
                min_tool_steps=1,
            )
        )
        keys = list(payload.keys())

        self.assertLess(keys.index("initial_turns"), keys.index("objective"))
        self.assertLess(keys.index("minimum_tool_steps_before_final"), keys.index("objective"))

    def test_initial_payload_redacts_external_model_sensitive_text(self) -> None:
        payload = agent.agent_initial_payload(
            "review memory routing",
            [
                {
                    "turn_ref": "t0",
                    "user": f"帮我看 token={FAKE_TEST_SECRET_VALUE} 和 {fake_test_windows_path('agent.txt')}",
                    "assistant": FAKE_TEST_OPENAI_API_KEY,
                }
            ],
            max_steps=1,
            min_tool_steps=0,
        )

        self.assertNotIn(FAKE_TEST_SECRET_VALUE, payload)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, payload)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, payload)
        self.assertIn("<redacted:secret>", payload)
        self.assertIn("<redacted:local-path>", payload)

    def test_validate_agent_edges_accepts_tool_observation_refs(self) -> None:
        parsed = {
            "edges": [
                {
                    "src": "Go runtime",
                    "dst": "gotd",
                    "edge_type": "depends_on",
                    "confidence": 0.88,
                    "why": "The observed clean-source hit ties the runtime spike to gotd.",
                    "source_refs": ["o0"],
                }
            ]
        }
        source_bank = {
            "o0": {
                "thread_key": "session:one",
                "title": "T-Sense",
                "project_label": "T-Sense",
                "turn_index": 40,
                "source_line": 1202,
            }
        }

        edges = agent.validate_agent_edges(parsed, source_bank)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["source_refs"][0]["ref"], "o0")
        self.assertEqual(edges[0]["source_refs"][0]["source_line"], 1202)

    def test_run_agent_can_use_clean_source_tool_then_final_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages_path = root / "messages.jsonl"
            messages_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message_id": "m1",
                                "turn_id": "turn-1",
                                "source_line": 10,
                                "role": "user",
                                "phase": "",
                                "turn_index": 1,
                                "text": "T-Sense 本地底座改成 Go runtime 吗？",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "message_id": "m2",
                                "turn_id": "turn-1",
                                "source_line": 11,
                                "role": "assistant",
                                "phase": "final_answer",
                                "is_final": True,
                                "turn_index": 1,
                                "text": "建议先做 Go runtime spike，并用 gotd 验证 Telegram 核心路径。",
                            },
                            ensure_ascii=False,
                        ),
                    ]
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
                                "title": "T-Sense test",
                                "project_label": "T-Sense",
                                "project_tags": ["T-Sense"],
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
                            "project:t": {
                                "project_label": "T-Sense",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:one",
                                        "title": "T-Sense test",
                                        "project_label": "T-Sense",
                                        "turn_id": "turn-1",
                                        "turn_index": 1,
                                        "user": "T-Sense 本地底座改成 Go runtime 吗？",
                                        "assistant": "建议先做 Go runtime spike，并用 gotd 验证 Telegram 核心路径。",
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
                if len(calls) == 1:
                    content = {
                        "action": "tool",
                        "tool": "search_clean_source",
                        "args": {"terms": ["Go runtime", "gotd"], "limit": 1},
                        "why": "Need source evidence before proposing an edge.",
                    }
                elif len(calls) == 2:
                    content = {"action": "final", "edges": []}
                else:
                    content = {
                        "action": "final",
                        "edges": [
                            {
                                "src": "Go runtime",
                                "dst": "gotd",
                                "edge_type": "depends_on",
                                "confidence": 0.86,
                                "why": "The tool hit links the Go runtime spike to validating gotd.",
                                "source_refs": [{"ref": "o0"}],
                            }
                        ],
                    }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "prompt_cache_hit_tokens": 9,
                        "prompt_cache_miss_tokens": 1,
                    },
                }

            result = agent.run_agent(
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                output_path=root / "subconscious_edges.jsonl",
                project="T-Sense",
                objective="test",
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

        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(result["tool_steps"]), 1)
        self.assertEqual(result["edges"][0]["source_refs"][0]["ref"], "o0")
        self.assertEqual(result["cache"]["hit_rate"], 0.9)

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
                        "text": f"api_key={FAKE_TEST_OPENAI_API_KEY} {fake_test_windows_path('agent-tool.txt')}",
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
                                "title": "Secret test",
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
                                        "title": "Secret test",
                                        "turn_id": "turn-1",
                                        "turn_index": 1,
                                        "user": "find api key source",
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
                        "args": {"terms": ["api_key"], "limit": 1},
                    }
                    if len(calls) == 1
                    else {"action": "final", "edges": []}
                )
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            agent.run_agent(
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                output_path=root / "subconscious_edges.jsonl",
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
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, second_call)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, second_call)
        self.assertIn("<redacted:api-key>", second_call)
        self.assertIn("<redacted:local-path>", second_call)


if __name__ == "__main__":
    unittest.main()
