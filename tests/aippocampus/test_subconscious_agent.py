from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aippocampus_runtime.subconscious import agent, job_circuits, runtime
from tests.aippocampus.redaction_fixtures import (
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


class SubconsciousAgentTests(unittest.TestCase):
    def test_read_only_tool_registry_drives_prompt_payload_and_dispatcher(self) -> None:
        payload = json.loads(
            agent.agent_initial_payload(
                "Find durable edges from this run.",
                [{"turn_ref": "t0", "user": "A", "assistant": "B"}],
                max_steps=4,
                min_tool_steps=1,
            )
        )
        jobs_payload = json.loads(
            job_circuits.jobs_initial_payload(
                "concept_edges",
                "Use a distinct sample angle.",
                [{"turn_ref": "t0", "user": "A", "assistant": "B"}],
                max_steps=4,
                min_tool_steps=1,
            )
        )
        registry_names = set(runtime.READ_ONLY_TOOL_REGISTRY)

        self.assertEqual(set(payload["available_tools"]), registry_names)
        self.assertEqual(set(jobs_payload["available_tools"]), registry_names)
        self.assertEqual(set(runtime.read_only_tool_names()), registry_names)
        self.assertEqual(set(runtime.dispatchable_tool_names()), registry_names)
        self.assertEqual(
            runtime.TOOL_CONTRACT_VERSION,
            payload["tool_contract_version"],
        )
        self.assertEqual(
            runtime.TOOL_CONTRACT_VERSION,
            jobs_payload["tool_contract_version"],
        )
        for name in registry_names:
            self.assertIn(name, runtime.AGENT_SYSTEM_PROMPT)
            self.assertEqual(
                payload["available_tools"][name],
                runtime.available_tools_payload()[name],
            )
            self.assertEqual(
                jobs_payload["available_tools"][name],
                runtime.available_tools_payload()[name],
            )

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

    def test_agent_run_config_factory_derives_default_paths_from_registry_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            class Args:
                registry = None
                registry_dir = str(root)
                timeline = None
                concept_graph = None
                output = None
                project = "AIppocampus"
                objective = "test"
                max_turns = 4
                max_steps = 2
                min_tool_steps = 1
                model = "deepseek-v4-flash"
                base_url = "https://example.invalid"
                api_key_env = "MISSING_TEST_KEY"
                max_tokens = None
                timeout = 9
                temperature = 0.2
                dry_run = True
                no_write = False

            config = agent.agent_run_config_from_args(Args())

        self.assertEqual(config.registry_path, (root / "threads.json").resolve())
        self.assertEqual(config.timeline_path, (root / "project_timeline.json").resolve())
        self.assertEqual(config.output_path, (root / "subconscious_edges.jsonl").resolve())
        self.assertEqual(config.api_key, None)
        self.assertTrue(config.dry_run)

    def test_dry_run_reports_tool_contract_version_for_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = agent.run_agent(
                registry_path=root / "threads.json",
                timeline_path=timeline_path,
                concept_graph_path=root / "concept.sqlite",
                output_path=root / "edges.jsonl",
                project="AIppocampus",
                objective="audit dry run",
                max_turns=4,
                max_steps=2,
                min_tool_steps=1,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key=None,
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                dry_run=True,
                no_write=True,
            )

        self.assertEqual(result["tool_contract_version"], runtime.TOOL_CONTRACT_VERSION)
        self.assertIn(runtime.TOOL_CONTRACT_VERSION, result["prompt_preview"])

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

    def test_validate_agent_edges_keeps_ref_shapes_and_rejection_policy_shared(self) -> None:
        parsed = {
            "edges": [
                {
                    "src": "tool-using agent",
                    "dst": "source-backed validation",
                    "edge_type": "invented_type",
                    "confidence": 1.7,
                    "why": "String, dict, and observation refs share the edge policy.",
                    "source_refs": ["t0", {"turn_ref": "t1"}, {"obs_ref": "o0"}, {"ref": "o1"}, "t2"],
                },
                {
                    "src": "low confidence",
                    "dst": "must drop",
                    "edge_type": "related",
                    "confidence": 0.44,
                    "source_refs": ["t0"],
                },
                {
                    "src": "问题",
                    "dst": "generic concept must drop",
                    "edge_type": "related",
                    "confidence": 0.9,
                    "source_refs": ["t0"],
                },
                {
                    "src": "missing source",
                    "dst": "must drop",
                    "edge_type": "related",
                    "confidence": 0.9,
                    "source_refs": ["missing"],
                },
            ]
        }
        source_bank = {
            ref: {
                "turn_ref": ref if ref.startswith("t") else None,
                "thread_key": f"session:{ref}",
                "title": "AIppocampus",
                "project_label": "AIppocampus",
                "turn_index": idx,
                "source_line": 120 + idx,
            }
            for idx, ref in enumerate(["t0", "t1", "o0", "o1", "t2"])
        }

        edges = agent.validate_agent_edges(parsed, source_bank)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["edge_type"], "related")
        self.assertEqual(edges[0]["confidence"], 1.0)
        self.assertEqual(
            [ref["ref"] for ref in edges[0]["source_refs"]],
            ["t0", "t1", "o0", "o1"],
        )
        self.assertEqual(edges[0]["source_refs"][2]["source_line"], 122)

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
        self.assertEqual(result["tool_grounding"]["status"], "tool_grounded")
        self.assertEqual(result["tool_grounding"]["tool_observation_ref_count"], 1)
        self.assertEqual(result["tool_grounding"]["final_edges_with_observation_refs"], 1)
        repair_call = json.dumps(calls[2], ensure_ascii=False)
        self.assertIn("observation_refs", repair_call)
        self.assertIn("o0", repair_call)
        self.assertEqual(result["cache"]["hit_rate"], 0.9)

    def test_agent_reports_initial_only_after_nonuseful_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
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
                                        "user": "本地底座要做 Go runtime spike。",
                                        "assistant": "用 gotd 验证核心路径。",
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
                        "tool": "recent_edges",
                        "args": {"terms": ["nothing-here"], "limit": 2},
                        "why": "Check whether this edge already exists.",
                    }
                    if len(calls) == 1
                    else {
                        "action": "final",
                        "edges": [
                            {
                                "src": "Go runtime",
                                "dst": "gotd",
                                "edge_type": "depends_on",
                                "confidence": 0.82,
                                "why": "The initial source turn ties the spike to gotd validation.",
                                "source_refs": [{"ref": "t0"}],
                            }
                        ],
                    }
                )
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = agent.run_agent(
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                output_path=root / "subconscious_edges.jsonl",
                project="T-Sense",
                objective="test non-useful tool grounding",
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

        grounding = result["tool_grounding"]
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(grounding["status"], "initial_only_after_tool")
        self.assertEqual(grounding["tool_observation_ref_count"], 0)
        self.assertEqual(grounding["final_edges_with_observation_refs"], 0)
        self.assertEqual(grounding["final_edges_with_initial_refs"], 1)
        self.assertEqual(grounding["useless_tool_call_count"], 1)
        self.assertEqual(grounding["useless_tool_calls"][0]["tool"], "recent_edges")
        self.assertEqual(grounding["useless_tool_calls"][0]["reason"], "empty_recent_edges")

    def test_recent_edges_reads_bounded_tail_when_old_prefix_is_not_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_path = Path(tmp) / "subconscious_edges.jsonl"
            tail_row = {
                "kind": "aippocampus_subconscious_edge",
                "status": "staging",
                "src": "bounded recent edge",
                "dst": "tail window",
                "edge_type": "related",
                "confidence": 0.84,
                "source": "test",
                "why": "The recent tool should not parse the whole historical file.",
            }
            with staging_path.open("wb") as fh:
                fh.write(b"\xff\xfe historical corrupt prefix that must stay outside the tail\n")
                fh.write(b"x\n" * 150_000)
                fh.write(json.dumps(tail_row, ensure_ascii=False).encode("utf-8") + b"\n")

            result = runtime.tool_recent_edges(
                staging_path=staging_path,
                args={"terms": ["bounded"], "limit": 1},
            )

        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(result["edges"][0]["src"], "bounded recent edge")

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
