from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime import core  # noqa: E402
from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.ops import provider_key_bridge, telepathy_handoff_store  # noqa: E402
from aippocampus_runtime.registry import store as registry_store  # noqa: E402
from aippocampus_runtime.sync import bundle as sync_bundle  # noqa: E402
from conversation_sources import ConversationSourceRef  # noqa: E402


class AippocampusMcpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self.messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "小海马体需要 source-backed continuity。",
            },
            {
                "message_id": "msg_final",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "AIppocampus 使用 clean source，而不是摘要替代事实。",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in self.messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_1",
                        "turn_index": 1,
                        "message_ids": ["msg_user", "msg_final"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def tool_payload(self, response: dict) -> dict:
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def test_initialize_and_tools_list_expose_stage4_memory_tools(self) -> None:
        init = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("tools", init["result"]["capabilities"])

        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertGreaterEqual(
            names,
            {
                "agent_recall",
                "agent_aippo",
                "agent_deepen",
                "agent_explain",
                "search_memory",
                "recall_context",
                "recall_deepen",
                "recall_diagnostic",
                "latest_reply",
                "get_turn_context",
                "list_threads",
                "register_thread",
                "sync_status",
                "memory_health",
                "list_telepathy_handoffs",
                "deepen_telepathy_handoff",
            },
        )
        agent_deepen_schema = by_name["agent_deepen"]["inputSchema"]
        self.assertNotIn("handle", agent_deepen_schema.get("required") or [])
        self.assertIn("request_index", agent_deepen_schema["properties"])
        self.assertIn("last_recall", agent_deepen_schema["properties"])
        self.assertIn("Find source-backed continuity routes", by_name["agent_recall"]["description"])
        self.assertIn("Get low-risk working guidance", by_name["agent_aippo"]["description"])
        self.assertIn("Open the selected recall route", by_name["agent_deepen"]["description"])
        self.assertIn("Search clean source", by_name["search_memory"]["description"])
        schema_text = json.dumps(listed["result"]["tools"], ensure_ascii=False)
        self.assertNotIn("MemoryPackets", schema_text)
        self.assertNotIn("opaque", schema_text)
        self.assertIn("clean_source_dir", by_name["latest_reply"]["inputSchema"]["properties"])
        self.assertEqual(
            by_name["get_turn_context"]["inputSchema"]["required_any"],
            ["turn_id", "message_id", "turn_index"],
        )

    def test_mcp_exposes_agent_native_read_tools_with_navigation_boundary(self) -> None:
        last_recall_env = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
        old_last_recall = os.environ.get(last_recall_env)
        os.environ[last_recall_env] = str(self.cwd / "agent-last-recall.json")
        self.addCleanup(
            lambda: os.environ.pop(last_recall_env, None)
            if old_last_recall is None
            else os.environ.__setitem__(last_recall_env, old_last_recall)
        )
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 201, "method": "tools/list"})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertGreaterEqual(
            names,
            {"agent_recall", "agent_aippo", "agent_deepen", "agent_explain"},
        )

        recall_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 202,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 2,
                    },
                },
            }
        )

        payload = self.tool_payload(recall_response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(recall_response["result"].get("isError", False), payload)
        self.assertEqual(payload["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(payload["mode"], "recall")
        self.assertEqual(payload["surface"], "mcp_agent_recall_compact")
        self.assertTrue(payload["opt_in_required"])
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["output_boundary"], "compact_foreground_no_local_private_handles")
        action = payload["foreground_action"]
        self.assertEqual(action["action_id"], "agent_deepen_selected_route")
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(action["arguments"]["request_index"], 1)
        self.assertTrue(action["arguments"]["last_recall"])
        self.assertEqual(action["claim_boundary"], "no_claim_before_reopen")
        self.assertNotIn("foreground_action_card", payload)
        self.assertNotIn("memory_packets", payload)
        self.assertNotIn("deepen_requests", payload)
        self.assertNotIn("copy_paste_command", encoded)
        self.assertNotIn("machine_next_command", encoded)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertTrue(payload["audit_available"])
        self.assertTrue(payload["policy_boundary"]["navigation_only_not_fact"])
        self.assertNotIn(str(self.cwd), encoded)

        deepen_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2022,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": action["arguments"],
                },
            }
        )
        deepen_payload = self.tool_payload(deepen_response)
        deepen_encoded = json.dumps(deepen_payload, ensure_ascii=False)
        self.assertFalse(deepen_response["result"].get("isError", False), deepen_payload)
        self.assertEqual(deepen_payload["mode"], "deepen")
        self.assertEqual(deepen_payload["status"], "ok")
        self.assertIn("AIppocampus 使用 clean source", deepen_encoded)
        self.assertNotIn(str(self.cwd), deepen_encoded)

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2021,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 2,
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = self.tool_payload(full_response)
        self.assertEqual(full_payload["detail"], "full")
        self.assertEqual(full_payload["surface"], "agent_cli_or_mcp_adapter")
        self.assertIn("memory_packets", full_payload)
        self.assertIn("deepen_requests", full_payload)
        self.assertIn("handle", full_payload["deepen_requests"][0])

        aippo_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 203,
                "method": "tools/call",
                "params": {
                    "name": "agent_aippo",
                    "arguments": {"task": "product usability closeout"},
                },
            }
        )
        aippo_payload = self.tool_payload(aippo_response)
        self.assertFalse(aippo_response["result"].get("isError", False), aippo_payload)
        self.assertEqual(aippo_payload["mode"], "aippo")
        self.assertTrue(aippo_payload["policy_boundary"]["navigation_only_not_fact"])

    def test_agent_recall_rejects_explicit_invalid_max_values(self) -> None:
        valid = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2031,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 1,
                    },
                },
            }
        )
        self.assertFalse(valid["result"].get("isError", False), self.tool_payload(valid))
        self.assertEqual(self.tool_payload(valid)["metrics"]["requested_max_routes"], 1)

        for request_id, value, message in [
            (2032, 0, "max must be >= 1"),
            (2033, -1, "max must be >= 1"),
            (2034, 26, "max must be <= 25"),
        ]:
            with self.subTest(value=value):
                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {
                            "name": "agent_recall",
                            "arguments": {
                                "query": "clean source continuity",
                                "cwd": str(self.cwd),
                                "clean_source_dir": str(self.clean),
                                "max": value,
                            },
                        },
                    }
                )
                payload = self.tool_payload(response)
                self.assertTrue(response["result"]["isError"])
                self.assertEqual(payload["error"]["code"], "invalid_argument")
                self.assertIn(message, payload["error"]["message"])

    def test_agent_deepen_marks_cannot_verify_as_mcp_error(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2035,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": {"handle": "not-a-navigation-handle", "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertFalse(payload["ok"])

    def test_recall_diagnostic_applies_provider_bridge_before_live_semantic_gate(self) -> None:
        env_var = "MCP_PROVIDER_BRIDGE_TEST_KEY"
        secret_value = "mcp-provider-bridge-secret-value"
        codex_home = self.cwd / "codex-home"
        dotenv = self.cwd / "provider.env"
        dotenv.write_text(f"{env_var}={secret_value}\n", encoding="utf-8")
        provider_key_bridge.write_bridge_manifest(
            provider_key_bridge.bridge_manifest_path(codex_home),
            provider_key_bridge.build_bridge_manifest(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=env_var,
                credential_dotenv=dotenv,
            ),
        )
        observed: dict[str, str | None] = {}

        def fake_report(**_kwargs: object) -> dict[str, object]:
            observed["env_value"] = os.environ.get(env_var)
            return {
                "kind": "aippocampus_recall_diagnostic",
                "ok": True,
                "surface_reports": [],
                "reasons": [],
            }

        old_value = os.environ.pop(env_var, None)
        try:
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(mcp, "recall_diagnostic_report", side_effect=fake_report),
            ):
                os.environ.pop(env_var, None)
                response = mcp.call_recall_diagnostic(
                    {
                        "cwd": str(self.cwd),
                        "cue": "vague continuity cue",
                        "run_semantic_gate": True,
                        "semantic_gate_mode": "on",
                    }
                )
        finally:
            if old_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = old_value

        payload = json.loads(response["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(observed["env_value"], secret_value)
        self.assertEqual(
            payload["provider_key_bridge"]["status"],
            "applied_to_current_mcp_process",
        )
        self.assertEqual(payload["provider_key_bridge"]["provider_env_vars"], [env_var])
        self.assertNotIn(secret_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_agent_recall_applies_provider_bridge_before_live_semantic_gate(self) -> None:
        env_var = "MCP_AGENT_RECALL_PROVIDER_BRIDGE_TEST_KEY"
        secret_value = "mcp-agent-recall-provider-bridge-secret-value"
        codex_home = self.cwd / "codex-home-agent"
        dotenv = self.cwd / "agent-provider.env"
        dotenv.write_text(f"{env_var}={secret_value}\n", encoding="utf-8")
        provider_key_bridge.write_bridge_manifest(
            provider_key_bridge.bridge_manifest_path(codex_home),
            provider_key_bridge.build_bridge_manifest(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=env_var,
                credential_dotenv=dotenv,
            ),
        )
        observed: dict[str, str | None] = {}

        class FakeAgent:
            MAX_ROUTES = 5

            @staticmethod
            def recall(*_args: object, **_kwargs: object) -> dict[str, object]:
                observed["env_value"] = os.environ.get(env_var)
                return {
                    "kind": "aippocampus_agent_continuity_path",
                    "status": "ok",
                    "semantic_gate_diagnostics": {"decision": "available"},
                }

        old_value = os.environ.pop(env_var, None)
        try:
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(mcp, "agent_continuity_module", return_value=FakeAgent),
            ):
                os.environ.pop(env_var, None)
                response = mcp.call_agent_recall(
                    {
                        "cwd": str(self.cwd),
                        "query": "vague continuity cue",
                        "run_semantic_gate": True,
                        "semantic": "on",
                    }
                )
        finally:
            if old_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = old_value

        payload = json.loads(response["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(observed["env_value"], secret_value)
        self.assertEqual(
            payload["provider_key_bridge"]["status"],
            "applied_to_current_mcp_process",
        )
        self.assertEqual(payload["provider_key_bridge"]["provider_env_vars"], [env_var])
        self.assertNotIn(secret_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_tools_only_server_returns_empty_resource_lists(self) -> None:
        resources = mcp.handle_request(
            {"jsonrpc": "2.0", "id": 21, "method": "resources/list"}
        )
        templates = mcp.handle_request(
            {"jsonrpc": "2.0", "id": 22, "method": "resources/templates/list"}
        )

        self.assertEqual(resources["result"], {"resources": []})
        self.assertEqual(templates["result"], {"resourceTemplates": []})

    def test_register_thread_requires_explicit_write_shape(self) -> None:
        with mock.patch.object(mcp.registry, "register_current_thread") as register:
            empty_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3101,
                    "method": "tools/call",
                    "params": {"name": "register_thread", "arguments": {}},
                }
            )
            missing_confirm_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3102,
                    "method": "tools/call",
                    "params": {
                        "name": "register_thread",
                        "arguments": {"cwd": str(self.cwd), "provider": "codex"},
                    },
                }
            )

        self.assertTrue(empty_response["result"]["isError"])
        self.assertTrue(missing_confirm_response["result"]["isError"])
        self.assertEqual(self.tool_payload(empty_response)["error"]["code"], "explicit_write_required")
        self.assertEqual(
            self.tool_payload(missing_confirm_response)["error"]["code"],
            "explicit_write_required",
        )
        register.assert_not_called()

    def test_register_thread_passes_explicit_provider_to_registry(self) -> None:
        with mock.patch.object(
            mcp.registry,
            "register_current_thread",
            return_value={"status": "registered"},
        ) as register:
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "tools/call",
                    "params": {
                        "name": "register_thread",
                        "arguments": {
                            "cwd": str(self.cwd),
                            "provider": "codex",
                            "confirm_write": True,
                            "build_index": False,
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        self.assertEqual(payload["status"], "registered")
        provider = register.call_args.kwargs["provider"]
        self.assertEqual(provider.name, "codex")

    def test_register_thread_default_response_is_compact_and_omits_session_meta(self) -> None:
        with mock.patch.object(
            mcp.registry,
            "register_current_thread",
            return_value={
                "status": "registered",
                "entry": {
                    "thread_key": "session:private-raw-thread-id",
                    "title": "AIppocampus issue cleanup",
                    "project_label": "AIppocampus",
                    "message_count": 4300,
                    "paths": {"clean_source_messages_jsonl": str(self.clean / "messages.jsonl")},
                    "session_meta": {
                        "id": "session-private-id",
                        "base_instructions": "full host instructions should not be in compact MCP output",
                        "tools": [{"name": "Read", "schema": {"large": True}}],
                    },
                },
            },
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 311,
                    "method": "tools/call",
                    "params": {
                        "name": "register_thread",
                        "arguments": {
                            "cwd": str(self.cwd),
                            "provider": "codex",
                            "confirm_write": True,
                            "build_index": False,
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError"), payload)
        self.assertEqual(payload["status"], "registered")
        self.assertTrue(payload["thread_handle"].startswith("thread_"))
        self.assertNotEqual(payload["thread_handle"], "session:private-raw-thread-id")
        self.assertTrue(payload["thread_key_redacted"])
        self.assertEqual(payload["title"], "AIppocampus issue cleanup")
        self.assertEqual(payload["message_count"], 4300)
        self.assertTrue(payload["has_clean_source"])
        self.assertIn("agent_next_action", payload)
        self.assertNotIn("session:private-raw-thread-id", encoded)
        self.assertNotIn("session_meta", encoded)
        self.assertNotIn("base_instructions", encoded)
        self.assertNotIn("full host instructions", encoded)
        self.assertNotIn(str(self.clean), encoded)

    def test_register_thread_reports_retryable_registry_writer_busy(self) -> None:
        with mock.patch.object(
            mcp.registry,
            "register_current_thread",
            side_effect=registry_store.RegistryWriteBusyError(
                Path("threads.json"),
                wait_timeout_seconds=0.0,
            ),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "tools/call",
                    "params": {
                        "name": "register_thread",
                        "arguments": {
                            "cwd": str(self.cwd),
                            "provider": "codex",
                            "confirm_write": True,
                            "build_index": False,
                        },
                    },
                }
            )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "registry_writer_busy")
        self.assertTrue(payload["error"]["retryable"])

    def test_concurrent_register_thread_keeps_registry_valid(self) -> None:
        registry_dir = self.cwd / "registry"
        workspace_a = self.cwd / "workspace-a"
        workspace_b = self.cwd / "workspace-b"
        workspace_a.mkdir()
        workspace_b.mkdir()
        rollouts = {
            core.path_identity_key(workspace_a): self.cwd / "rollout-a.jsonl",
            core.path_identity_key(workspace_b): self.cwd / "rollout-b.jsonl",
        }
        for rollout in rollouts.values():
            rollout.write_text(
                '{"type":"session_meta","payload":{"id":"session-test"}}\n',
                encoding="utf-8",
            )

        class FixtureProvider:
            name = "codex"

            def locate_current(
                self,
                cwd: str | Path,
                *,
                latest: bool = False,
            ) -> ConversationSourceRef:
                del latest
                cwd_path = core.canonical_path(cwd)
                return ConversationSourceRef(
                    provider=self.name,
                    path=rollouts[core.path_identity_key(cwd_path)],
                    cwd=cwd_path,
                )

        def fake_thread_key(cwd: Path, manifest: dict, rollout: Path | None) -> str:
            del manifest, rollout
            return f"workspace:{cwd.name}"

        start = threading.Barrier(2)
        responses: list[dict] = []
        errors: list[BaseException] = []

        def call_register(cwd: Path, request_id: int) -> None:
            try:
                start.wait(timeout=5)
                responses.append(
                    mcp.handle_request(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {
                                "name": "register_thread",
                                "arguments": {
                                    "cwd": str(cwd),
                                    "provider": "codex",
                                    "confirm_write": True,
                                    "registry_dir": str(registry_dir),
                                    "build_index": False,
                                    "include_private_paths": True,
                                },
                            },
                        }
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        with (
            mock.patch.object(mcp, "create_conversation_provider", return_value=FixtureProvider()),
            mock.patch.object(mcp.registry, "thread_key_for", side_effect=fake_thread_key),
            mock.patch.object(mcp.aippocampus_health, "health_report", return_value={}),
        ):
            threads = [
                threading.Thread(target=call_register, args=(workspace_a, 41)),
                threading.Thread(target=call_register, args=(workspace_b, 42)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

        self.assertFalse(errors)
        self.assertEqual(len(responses), 2)
        self.assertTrue(all(not response["result"].get("isError") for response in responses))
        registry = json.loads((registry_dir / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {entry["thread_key"] for entry in registry["threads"]},
            {"workspace:workspace-a", "workspace:workspace-b"},
        )
        registry_markdown = (registry_dir / "threads.md").read_text(encoding="utf-8")
        self.assertIn("workspace:workspace-a", registry_markdown)
        self.assertIn("workspace:workspace-b", registry_markdown)

    def test_search_memory_returns_clean_source_hits_as_tool_content(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {"query": "clean source 摘要", "cwd": str(self.cwd), "max": 3},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["output_boundary"], "public_metadata_only_no_source_snippets_or_reopen_refs")
        self.assertEqual(payload["matches"][0]["match_index"], 1)
        self.assertTrue(payload["matches"][0]["snippet_omitted"])
        self.assertTrue(payload["matches"][0]["source_refs_omitted"])
        self.assertNotIn("message_id", payload["matches"][0])
        self.assertNotIn("snippet", payload["matches"][0])
        self.assertIn("agent_next_action", payload)

    def test_search_memory_can_emit_source_snippets_when_explicitly_requested(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "clean source 摘要",
                        "cwd": str(self.cwd),
                        "max": 3,
                        "include_source_snippets": True,
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["matches"][0]["message_id"], "msg_final")
        self.assertIn("不是摘要替代事实", payload["matches"][0]["snippet"])

    def test_recall_context_default_is_compact_without_opaque_handles(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 301,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": f"继续 {self.cwd} 里的 SECRET_TOKEN=abc123 clean source 记忆",
                        "cwd": str(self.cwd),
                        "max": 3,
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_recall_context")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["output_boundary"], "compact_foreground_no_local_private_handles")
        self.assertEqual(payload["support_level"], "navigation")
        self.assertEqual(payload["source_boundary"]["navigation_only_not_fact"], True)
        route = payload["routes"][0]
        self.assertEqual(route["evidence_level"], "needs_reopen")
        self.assertEqual(route["foreground_action"]["tool_name"], "recall_deepen")
        self.assertEqual(route["foreground_action"]["arguments"]["message_id"], "msg_final")
        self.assertNotIn("handle", route)
        self.assertNotIn("source_refs", route)
        self.assertNotIn("suggested_next", route)
        self.assertNotIn("source_reopen_path", route)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("继续", encoded)

    def test_recall_context_full_detail_keeps_callable_navigation_handle(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3011,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "clean source continuity",
                        "cwd": str(self.cwd),
                        "max": 3,
                        "detail": "full",
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False), payload)
        self.assertEqual(payload["detail"], "full")
        self.assertEqual(payload["routes"][0]["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["routes"][0]["suggested_next"]["tool"], "recall_deepen")
        self.assertTrue(str(payload["routes"][0]["handle"]).startswith("aippo-nav:"))

    def test_recall_deepen_reopens_context_handle_with_source_boundary(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 302,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "clean source continuity",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        handle = self.tool_payload(context_response)["routes"][0]["handle"]

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 303,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": handle, "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_recall_deepen")
        self.assertEqual(payload["support_level"], "evidence")
        self.assertEqual(payload["evidence_level"], "source_backed")
        self.assertEqual(payload["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["source_reopen_path"]["tool"], "get_turn_context")
        self.assertIn("不是摘要替代事实", payload["source_window"]["messages"][1]["text"])
        self.assertNotIn(str(self.cwd), encoded)

    def test_recall_deepen_accepts_ambient_navigation_seed_handle(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 304,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {
                        "cwd": str(self.cwd),
                        "handle": {
                            "kind": "recall_context_seed",
                            "handle": {
                                "kind": "source_ref",
                                "source_refs": [{"message_id": "msg_user", "turn_id": "turn_1"}],
                            },
                            "suggested_tool": "recall_deepen",
                            "boundary": "navigation_only_not_fact",
                        },
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["source_refs"][0]["message_id"], "msg_user")
        self.assertEqual(payload["source_reopen_path"]["arguments"]["message_id"], "msg_user")

    def test_recall_deepen_accepts_route_object_from_recall_context(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3041,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "clean source continuity",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        route = self.tool_payload(context_response)["routes"][0]

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3042,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": route, "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False), payload)
        self.assertEqual(payload["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["source_reopen_path"]["arguments"]["turn_id"], "turn_1")

    def test_recall_deepen_accepts_source_reopen_arguments_from_recall_context(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3043,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "clean source continuity",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        reopen_args = self.tool_payload(context_response)["routes"][0]["source_reopen_path"][
            "arguments"
        ]

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3044,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": reopen_args, "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertFalse(response["result"].get("isError", False), payload)
        self.assertEqual(payload["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["source_reopen_path"]["tool"], "get_turn_context")

    def test_recall_deepen_reports_malformed_handle_as_tool_error(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 305,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": "not-a-navigation-handle", "cwd": str(self.cwd)},
                },
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "malformed_recall_handle")
        self.assertIn("deepen_requests[].handle", payload["error"]["message"])

    def test_recall_deepen_display_route_id_points_to_callable_agent_handle_field(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3051,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": "deepen:route_project_context", "cwd": str(self.cwd)},
                },
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "malformed_recall_handle")
        self.assertEqual(
            payload["error"]["details"]["callable_handle_field"],
            "deepen_requests[].handle",
        )

    def test_recall_deepen_rejects_stale_context_handle_before_source_reopen(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 306,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "clean source continuity",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        handle = self.tool_payload(context_response)["routes"][0]["handle"]
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "message_id": "msg_later",
                        "turn_id": "turn_2",
                        "source_line": 9,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 2,
                        "is_final": True,
                        "text": "Later source should stale the old navigation handle.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 307,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": handle, "cwd": str(self.cwd)},
                },
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["error"]["code"], "stale_recall_handle")
        self.assertNotIn("Later source", encoded)

    def test_recall_deepen_redacts_local_paths_inside_source_window_text(self) -> None:
        self.messages.append(
            {
                "message_id": "msg_path",
                "turn_id": "turn_path",
                "source_id": "src_test",
                "source_line": 12,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 3,
                "is_final": True,
                "text": r"Path boundary example lives at E:\private\workspace\secret.txt.",
            }
        )
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in self.messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_path",
                        "turn_index": 3,
                        "message_ids": ["msg_path"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 308,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "Path boundary example",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        handle = self.tool_payload(context_response)["routes"][0]["handle"]

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 309,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": handle, "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertNotIn(r"E:\private\workspace\secret.txt", encoded)
        self.assertIn("<redacted:local-path>", encoded)

    def test_search_memory_clamps_requested_limit_on_server_side(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 33,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {"query": "source", "cwd": str(self.cwd), "max": 9999},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual(payload["limit"], 25)

    def test_search_memory_redacts_local_source_path_by_default(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {"query": "source", "cwd": str(self.cwd), "max": 2},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual(payload["source"], mcp.LOCAL_PATH_REDACTION)

        private_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 35,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "source",
                        "cwd": str(self.cwd),
                        "max": 2,
                        "include_private_paths": True,
                    },
                },
            }
        )
        private_payload = self.tool_payload(private_response)
        self.assertIn(str(self.clean), private_payload["source"])

    def test_get_turn_context_returns_turn_messages_without_raw_rollout(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "get_turn_context",
                    "arguments": {"cwd": str(self.cwd), "turn_id": "turn_1"},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual(payload["turn"]["turn_id"], "turn_1")
        self.assertEqual(
            [item["message_id"] for item in payload["messages"]], ["msg_user", "msg_final"]
        )

    def test_get_turn_context_respects_zero_based_clean_ordinal_ordering(self) -> None:
        rows = [
            {
                "message_id": "msg_zero",
                "turn_id": "turn_zero",
                "source_line": 9,
                "role": "user",
                "turn_index": 0,
                "clean_ordinal": 0,
                "text": "first by clean ordinal",
            },
            {
                "message_id": "msg_one",
                "turn_id": "turn_zero",
                "source_line": 1,
                "role": "assistant",
                "turn_index": 0,
                "clean_ordinal": 1,
                "text": "second by clean ordinal despite lower source line",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        (self.clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": "turn_zero",
                    "turn_index": 0,
                    "message_ids": ["msg_zero", "msg_one"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4001,
                "method": "tools/call",
                "params": {
                    "name": "get_turn_context",
                    "arguments": {"cwd": str(self.cwd), "turn_index": 0},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual([item["message_id"] for item in payload["messages"]], ["msg_zero", "msg_one"])

    def test_get_turn_context_requires_explicit_selector(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "get_turn_context", "arguments": {"cwd": str(self.cwd)}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "missing_turn_selector")
        self.assertIn("turn_id", payload["error"]["details"]["required_any"])
        self.assertIn("agent_recall", payload["error"]["details"]["agent_next_action"])
        self.assertIn("example_arguments", payload["error"]["details"])

    def test_get_turn_context_reports_missing_message_id(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "get_turn_context",
                    "arguments": {"cwd": str(self.cwd), "message_id": "msg_missing"},
                },
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "message_not_found")
        self.assertEqual(payload["error"]["details"]["message_id"], "msg_missing")

    def test_get_turn_context_reports_unavailable_clean_source(self) -> None:
        missing_clean = self.cwd / "missing-clean-source"
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 43,
                "method": "tools/call",
                "params": {
                    "name": "get_turn_context",
                    "arguments": {
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(missing_clean),
                        "turn_id": "turn_1",
                    },
                },
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "clean_source_unavailable")
        self.assertEqual(
            payload["error"]["details"]["clean_source_dir"], mcp.LOCAL_PATH_REDACTION
        )
        self.assertIn("messages.jsonl", payload["error"]["details"]["missing_files"])

    def test_mcp_error_paths_can_be_opted_back_in_for_local_operator(self) -> None:
        missing_clean = self.cwd / "missing-clean-source"
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 431,
                "method": "tools/call",
                "params": {
                    "name": "get_turn_context",
                    "arguments": {
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(missing_clean),
                        "turn_id": "turn_1",
                        "include_private_paths": True,
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["details"]["clean_source_dir"], str(missing_clean))

    def test_sync_status_reads_local_sync_bundle_when_path_is_supplied(self) -> None:
        registry_dir = self.cwd / "registry"
        thread_dir = registry_dir / "threads" / "session-test" / "clean-source"
        thread_dir.mkdir(parents=True)
        (registry_dir / "threads.json").write_text(
            json.dumps({"threads": [{"thread_key": "session:test"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (thread_dir / "messages.jsonl").write_text(
            json.dumps({"message_id": "msg_1", "text": "synced"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        sync_dir = self.cwd / "sync"
        sync_bundle.push_sync_bundle(registry_dir, sync_dir)

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "sync_status",
                    "arguments": {"cwd": str(self.cwd), "sync_dir": str(sync_dir)},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertTrue(payload["manifest_exists"])
        self.assertEqual(payload["file_count"], 3)

    def test_sync_status_without_backend_returns_copyable_public_commands(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 61,
                "method": "tools/call",
                "params": {
                    "name": "sync_status",
                    "arguments": {"cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["status"], "available_requires_sync_dir")
        self.assertEqual(payload["command"], "aippocampus sync status --sync-dir <folder> --json")
        self.assertIn("agent_next_action", payload)
        self.assertNotIn("python -m aippocampus_runtime", encoded)

    def test_sync_status_can_report_http_object_store_backend(self) -> None:
        with mock.patch.object(
            mcp.sync_object_storage,
            "status_object_storage_bundle",
            return_value={"ok": True, "backend": "http_object_store", "manifest_exists": True},
        ) as status:
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 66,
                    "method": "tools/call",
                    "params": {
                        "name": "sync_status",
                        "arguments": {
                            "cwd": str(self.cwd),
                            "object_store_url": "http://127.0.0.1:9000",
                            "object_prefix": "stage3/test",
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        self.assertEqual(payload["backend"], "http_object_store")
        status.assert_called_once_with(
            "http://127.0.0.1:9000",
            prefix="stage3/test",
            token=None,
        )

    def test_list_threads_reports_missing_registry_status(self) -> None:
        missing_registry = self.cwd / "missing-registry"
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 67,
                "method": "tools/call",
                "params": {
                    "name": "list_threads",
                    "arguments": {"registry_dir": str(missing_registry)},
                },
            }
        )

        self.assertFalse(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        self.assertEqual(payload["status"], "registry_missing")
        self.assertEqual(payload["threads"], [])
        self.assertEqual(payload["count"], 0)

    def test_list_threads_redacts_registry_paths_by_default(self) -> None:
        registry_dir = self.cwd / "registry"
        registry_dir.mkdir()
        (registry_dir / "threads.json").write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:test",
                            "title": "Local registry thread",
                            "paths": {
                                "workspace": str(self.cwd),
                                "rollout": str(self.cwd / "rollout.jsonl"),
                            },
                            "debug": {
                                "command": f"python {self.cwd / 'tools' / 'audit.py'} --cwd {self.cwd}",
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 68,
                "method": "tools/call",
                "params": {
                    "name": "list_threads",
                    "arguments": {"registry_dir": str(registry_dir)},
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("session:test", encoded)
        self.assertEqual(payload["registry"], mcp.LOCAL_PATH_REDACTION)
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(
            payload["identifier_boundary"],
            "compact_thread_handles_are_stable_local_fingerprints",
        )
        self.assertIn("agent_next_action", payload)
        self.assertNotIn("debug", encoded)
        self.assertNotIn("paths", payload["threads"][0])
        self.assertTrue(payload["threads"][0]["thread_key_redacted"])
        self.assertTrue(payload["threads"][0]["thread_handle"].startswith("thread_"))

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 681,
                "method": "tools/call",
                "params": {
                    "name": "list_threads",
                    "arguments": {"registry_dir": str(registry_dir), "detail": "full"},
                },
            }
        )
        full_payload = self.tool_payload(full_response)
        full_encoded = json.dumps(full_payload, ensure_ascii=False)
        self.assertEqual(full_payload["detail"], "full")
        self.assertEqual(full_payload["threads"][0]["thread_key"], "session:test")
        self.assertNotIn(str(self.cwd), full_encoded)
        self.assertEqual(
            full_payload["threads"][0]["paths"]["workspace"],
            mcp.LOCAL_PATH_REDACTION,
        )
        self.assertIn(mcp.LOCAL_PATH_REDACTION, full_payload["threads"][0]["debug"]["command"])

    def test_unknown_tool_is_tool_error_not_protocol_crash(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "missing_tool", "arguments": {}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "unknown_tool")

    def test_unsupported_mutation_tool_is_explicit_tool_error(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 55,
                "method": "tools/call",
                "params": {"name": "delete_memory", "arguments": {}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "unsupported_mutation")
        self.assertEqual(payload["error"]["details"]["requested_tool"], "delete_memory")

    def test_unsupported_mutation_tool_family_uses_stable_error_code(self) -> None:
        mutating_tools = [
            "store_memory",
            "write_memory",
            "sync_push",
            "install_hook",
            "create_telepathy_handoff",
            "release_telepathy_handoff",
        ]
        for index, tool_name in enumerate(mutating_tools):
            with self.subTest(tool_name=tool_name):
                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 550 + index,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {}},
                    }
                )

                self.assertTrue(response["result"]["isError"])
                payload = self.tool_payload(response)
                self.assertEqual(payload["error"]["code"], "unsupported_mutation")
                self.assertEqual(payload["error"]["details"]["requested_tool"], tool_name)

    def test_telepathy_handoff_mcp_lists_and_deepens_without_writes_or_paths(self) -> None:
        store = self.cwd / "handoffs.jsonl"
        created = telepathy_handoff_store.create_handoff(
            scope="project:AIppocampus#issue:1287",
            owner="codex-a",
            source_refs=[
                {
                    "message_id": "msg_user",
                    "path": str(self.cwd / "private-rollout.jsonl"),
                    "source": "source://private/raw-handle",
                }
            ],
            store_path=store,
            cwd=self.cwd,
        )
        card_id = created["card"]["card_id"]

        list_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 71,
                "method": "tools/call",
                "params": {
                    "name": "list_telepathy_handoffs",
                    "arguments": {"cwd": str(self.cwd), "store_path": str(store)},
                },
            }
        )
        list_payload = self.tool_payload(list_response)

        deepen_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 72,
                "method": "tools/call",
                "params": {
                    "name": "deepen_telepathy_handoff",
                    "arguments": {
                        "cwd": str(self.cwd),
                        "store_path": str(store),
                        "card_id": card_id,
                    },
                },
            }
        )
        deepen_payload = self.tool_payload(deepen_response)
        encoded = json.dumps([list_payload, deepen_payload], ensure_ascii=False, sort_keys=True)

        self.assertFalse(list_response["result"].get("isError", False))
        self.assertFalse(deepen_response["result"].get("isError", False))
        self.assertEqual(list_payload["kind"], "aippocampus_telepathy_handoff_list")
        self.assertEqual(list_payload["cards"][0]["card_id"], card_id)
        self.assertEqual(deepen_payload["kind"], "aippocampus_telepathy_handoff_deepen")
        self.assertEqual(deepen_payload["source_reopen"]["source_refs"][0]["message_id"], "msg_user")
        self.assertEqual(list_payload["store_path"], mcp.LOCAL_PATH_REDACTION)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)

    def test_tools_call_rejects_malformed_arguments(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 56,
                "method": "tools/call",
                "params": {"name": "search_memory", "arguments": "query=source"},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.tool_payload(response)
        self.assertEqual(payload["error"]["code"], "malformed_arguments")
        self.assertEqual(payload["error"]["details"]["expected"], "object")

    def test_memory_health_runs_in_process_for_frozen_binary_entrypoints(self) -> None:
        old_argv = sys.argv[:]
        seen_cwd: list[Path] = []

        def fake_health_report(cwd: str | Path) -> dict:
            seen_cwd.append(Path(cwd))
            return {
                "ok": False,
                "cwd": str(cwd),
                "recommended_actions": [],
                "debug": {
                    "command": f"python {self.cwd / 'tools' / 'health.py'} --cwd {self.cwd}",
                },
            }

        with mock.patch.object(
            mcp.aippocampus_health, "health_report", side_effect=fake_health_report
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 57,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd), "include_private_paths": True},
                    },
                }
            )

        self.assertEqual(sys.argv, old_argv)
        self.assertFalse(hasattr(mcp, "subprocess"))
        self.assertFalse(response["result"].get("isError"))
        payload = self.tool_payload(response)
        self.assertEqual(payload["cwd"], str(core.canonical_path(self.cwd)))
        self.assertEqual(payload["recommended_actions"], [])
        self.assertEqual(seen_cwd, [core.canonical_path(self.cwd)])

    def test_memory_health_cwd_uses_canonical_identity_for_path_aliases(self) -> None:
        alias = self.cwd.parent / f"{self.cwd.name}-alias"
        try:
            alias.symlink_to(self.cwd, target_is_directory=True)
        except (AttributeError, NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        seen_cwd: list[Path] = []

        def fake_health_report(cwd: str | Path) -> dict:
            seen_cwd.append(Path(cwd))
            return {
                "ok": True,
                "cwd": str(cwd),
                "recommended_actions": [],
            }

        with mock.patch.object(
            mcp.aippocampus_health, "health_report", side_effect=fake_health_report
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 58,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(alias), "include_private_paths": True},
                    },
                }
            )

        self.assertFalse(response["result"].get("isError"))
        payload = self.tool_payload(response)
        self.assertEqual(
            core.workspace_identity_key(payload["cwd"]),
            core.workspace_identity_key(self.cwd),
        )
        self.assertEqual(
            [core.workspace_identity_key(item) for item in seen_cwd],
            [core.workspace_identity_key(self.cwd)],
        )

    def test_memory_health_default_is_compact_agent_budgeted_and_redacted(self) -> None:
        def fake_health_report(cwd: str | Path) -> dict:
            return {
                "ok": False,
                "cwd": str(cwd),
                "recommended_actions": [
                    {
                        "id": "build_index",
                        "severity": "warning",
                        "reason": "index is stale",
                        "command": f"python {self.cwd / 'tools' / 'build_index.py'}",
                    },
                    "repair registry",
                ],
                "checks": [{"name": f"large-{index}", "path": str(self.cwd / f"{index}.jsonl")} for index in range(12)],
                "debug": {
                    "command": f"python {self.cwd / 'tools' / 'health.py'} --cwd {self.cwd}",
                },
            }

        with mock.patch.object(
            mcp.aippocampus_health, "health_report", side_effect=fake_health_report
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 581,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd)},
                    },
                }
            )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["ok"], False)
        self.assertIn("agent_next_action", payload)
        self.assertIsInstance(payload["recommended_actions"][0], dict)
        self.assertEqual(payload["recommended_actions"][0]["id"], "build_index")
        self.assertIsInstance(payload["recommended_actions"][1], dict)
        self.assertEqual(payload["recommended_actions"][1]["id"], "recommended_action")
        self.assertIsInstance(payload["agent_next_action"], dict)
        self.assertEqual(payload["agent_next_action"]["id"], "build_index")
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("debug", encoded)
        self.assertNotIn("checks", payload)

    def test_stdio_jsonrpc_smoke_exercises_client_entrypoint(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "clean source",
                        "cwd": str(self.cwd),
                        "max": 2,
                        "include_source_snippets": True,
                    },
                },
            },
        ]
        stdin = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(SCRIPTS)
            if not existing_pythonpath
            else str(SCRIPTS) + os.pathsep + existing_pythonpath
        )

        proc = subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.mcp.server"],
            input=stdin,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertIn("search_memory", tool_names)
        payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(payload["matches"][0]["message_id"], "msg_final")


if __name__ == "__main__":
    unittest.main()
