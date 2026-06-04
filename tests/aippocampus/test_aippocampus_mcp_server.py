from __future__ import annotations

import json
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

import aippocampus_mcp_server as mcp  # noqa: E402
from aippocampus_runtime import core  # noqa: E402
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

        self.assertGreaterEqual(
            names,
            {
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
            },
        )

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
                            "build_index": False,
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        self.assertEqual(payload["status"], "registered")
        provider = register.call_args.kwargs["provider"]
        self.assertEqual(provider.name, "codex")

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
        self.assertEqual(payload["matches"][0]["message_id"], "msg_final")
        self.assertIn("不是摘要替代事实", payload["matches"][0]["snippet"])

    def test_recall_context_returns_navigation_handle_without_raw_prompt_or_paths(self) -> None:
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
        self.assertEqual(payload["support_level"], "navigation")
        self.assertEqual(payload["source_boundary"]["navigation_only_not_fact"], True)
        self.assertEqual(payload["routes"][0]["evidence_level"], "needs_reopen")
        self.assertEqual(payload["routes"][0]["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["routes"][0]["suggested_next"]["tool"], "recall_deepen")
        self.assertTrue(str(payload["routes"][0]["handle"]).startswith("aippo-nav:"))
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("继续", encoded)

    def test_recall_deepen_reopens_context_handle_with_source_boundary(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 302,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {"intent": "clean source continuity", "cwd": str(self.cwd)},
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

    def test_recall_deepen_rejects_stale_context_handle_before_source_reopen(self) -> None:
        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 306,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {"intent": "clean source continuity", "cwd": str(self.cwd)},
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
                    "arguments": {"intent": "Path boundary example", "cwd": str(self.cwd)},
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

    def test_latest_reply_uses_clean_source_before_raw_rollout(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 44,
                "method": "tools/call",
                "params": {"name": "latest_reply", "arguments": {"cwd": str(self.cwd)}},
            }
        )

        payload = self.tool_payload(response)
        self.assertEqual(payload["status"], "clean_source_final_answer")
        self.assertEqual(payload["message"]["message_id"], "msg_final")

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
                            "paths": {
                                "workspace": str(self.cwd),
                                "rollout": str(self.cwd / "rollout.jsonl"),
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
        self.assertEqual(payload["registry"], mcp.LOCAL_PATH_REDACTION)
        self.assertEqual(
            payload["threads"][0]["paths"]["workspace"],
            mcp.LOCAL_PATH_REDACTION,
        )

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
        mutating_tools = ["store_memory", "write_memory", "sync_push", "install_hook"]
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
                    "arguments": {"query": "clean source", "cwd": str(self.cwd), "max": 2},
                },
            },
        ]
        stdin = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"

        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "aippocampus_mcp_server.py")],
            input=stdin,
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
