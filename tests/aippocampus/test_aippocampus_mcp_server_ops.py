from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import core
from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp import tool_handlers as mcp_handlers
from aippocampus_runtime.ops import telepathy_handoff_store
from aippocampus_runtime.sync import bundle as sync_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

class AippocampusMcpServerOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.old_registry_dir = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(self.cwd / "default-registry")
        self.clean = core.default_thread_clean_source_dir(self.cwd)
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
        if self.old_registry_dir is None:
            os.environ.pop("AIPPOCAMPUS_REGISTRY_DIR", None)
        else:
            os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = self.old_registry_dir
        self.tmp.cleanup()

    def tool_payload(self, response: dict) -> dict:
        structured = response["result"].get("structuredContent")
        if isinstance(structured, dict):
            return structured
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def call_tool_payload(self, name: str, arguments: dict[str, object]) -> dict:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": f"call-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return self.tool_payload(response)

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
        self.assertEqual(
            payload["command_template"],
            'aippocampus sync status --sync-dir "{sync_dir}" --json',
        )
        self.assertEqual(payload["requires"], ["sync_dir_or_object_store_url"])
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["requires"], ["sync_dir"])
        self.assertTrue(payload["foreground_action"]["template_only"])
        self.assertTrue(
            any(action["requires"] == ["object_store_url"] for action in payload["safe_next_actions"])
        )
        self.assertNotIn("python -m aippocampus_runtime", encoded)

    def test_sync_status_can_report_http_object_store_backend(self) -> None:
        with mock.patch.object(
            mcp_handlers.sync_object_storage,
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
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIn("foreground_action", payload)
        self.assertEqual(payload["foreground_action"]["tool_name"], "register_thread")
        self.assertEqual(payload["foreground_action"]["arguments_template"]["cwd"], "{project_cwd}")
        self.assertTrue(payload["foreground_action"]["template_only"])
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_list_threads_redacts_registry_paths_by_default(self) -> None:
        registry_dir = self.cwd / "registry"
        registry_dir.mkdir()
        (registry_dir / "threads.json").write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:test",
                            "project_key": "project:local:abc123",
                            "title": "Local registry thread",
                            "session_meta": {
                                "id": "session-test",
                                "cwd": str(self.cwd),
                                "timestamp": "2026-06-24T00:00:00Z",
                                "base_instructions": {"text": "raw host instructions"},
                                "dynamic_tools": [{"name": "private_tool", "schema": "large"}],
                            },
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
        self.assertEqual(payload["registry"], mcp_handlers.LOCAL_PATH_REDACTION)
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(
            payload["identifier_boundary"],
            "compact_thread_handles_are_stable_local_fingerprints",
        )
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIn("foreground_action", payload)
        self.assertEqual(payload["foreground_action"]["tool_name"], "recall_context")
        self.assertEqual(payload["foreground_action"]["arguments_template"], {"intent": "{task_or_memory_cue}"})
        self.assertTrue(payload["foreground_action"]["template_only"])
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn("debug", encoded)
        self.assertNotIn("paths", payload["threads"][0])
        self.assertTrue(payload["threads"][0]["thread_key_redacted"])
        self.assertTrue(payload["threads"][0]["thread_handle"].startswith("thread_"))
        self.assertEqual(
            payload["threads"][0]["thread_handle_authority"],
            "diagnostic_local_fingerprint",
        )
        self.assertFalse(payload["threads"][0]["thread_handle_usable_as_source_selector"])

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
        self.assertEqual(
            full_payload["identifier_boundary"],
            "compact_thread_handles_are_stable_local_fingerprints",
        )
        self.assertEqual(
            full_payload["threads"][0]["detail_profile"],
            "full_without_private_identifiers",
        )
        self.assertTrue(full_payload["threads"][0]["thread_key_redacted"])
        self.assertTrue(full_payload["threads"][0]["raw_session_metadata_omitted"])
        self.assertTrue(
            full_payload["threads"][0]["session_meta_summary"][
                "base_instructions_text_omitted"
            ]
        )
        self.assertTrue(full_payload["threads"][0]["session_meta_summary"]["dynamic_tools_omitted"])
        self.assertNotIn("session:test", full_encoded)
        self.assertNotIn("session-test", full_encoded)
        self.assertNotIn("project:local:abc123", full_encoded)
        self.assertNotIn("raw host instructions", full_encoded)
        self.assertNotIn("private_tool", full_encoded)
        self.assertNotIn(str(self.cwd), full_encoded)
        self.assertNotIn("paths", full_payload["threads"][0])
        self.assertNotIn("debug", full_payload["threads"][0])

        private_id_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 682,
                "method": "tools/call",
                "params": {
                    "name": "list_threads",
                    "arguments": {
                        "registry_dir": str(registry_dir),
                        "detail": "full",
                        "include_private_identifiers": True,
                    },
                },
            }
        )
        private_id_payload = self.tool_payload(private_id_response)
        self.assertEqual(private_id_payload["threads"][0]["thread_key"], "session:test")
        self.assertEqual(
            private_id_payload["threads"][0]["paths"]["workspace"],
            mcp_handlers.LOCAL_PATH_REDACTION,
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
        self.assertEqual(list_payload["store_path"], mcp_handlers.LOCAL_PATH_REDACTION)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)

    def test_telepathy_handoff_mcp_empty_and_missing_cards_have_recovery_actions(self) -> None:
        store = self.cwd / "empty-handoffs.jsonl"
        list_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 73,
                "method": "tools/call",
                "params": {
                    "name": "list_telepathy_handoffs",
                    "arguments": {"cwd": str(self.cwd), "store_path": str(store)},
                },
            }
        )
        list_payload = self.tool_payload(list_response)

        missing_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 74,
                "method": "tools/call",
                "params": {
                    "name": "deepen_telepathy_handoff",
                    "arguments": {
                        "cwd": str(self.cwd),
                        "store_path": str(store),
                        "card_id": "missing-card",
                    },
                },
            }
        )
        missing_payload = self.tool_payload(missing_response)
        encoded = json.dumps([list_payload, missing_payload], ensure_ascii=False, sort_keys=True)

        self.assertFalse(list_response["result"].get("isError", False))
        self.assertEqual(list_payload["count"], 0)
        self.assertEqual(
            list_payload["empty_state"]["state"],
            "no_matching_telepathy_handoffs",
        )
        empty_action = list_payload["empty_state"]["foreground_action"]
        self.assertEqual(empty_action["id"], "continue_with_normal_recall")
        self.assertEqual(empty_action["command_template"], 'aippocampus agent recall "{cue}" --json')
        self.assertEqual(empty_action["tool_name"], "agent_recall")
        self.assertEqual(empty_action["arguments_template"], {"query": "{cue}"})
        self.assertEqual(list_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIn("foreground_action", list_payload)
        self.assertEqual(list_payload["foreground_action"], empty_action)
        self.assertNotIn(empty_action, list_payload["safe_next_actions"])
        self.assertIn("recall/search", empty_action["why"])
        self.assertEqual(executable_command_violations(list_payload), [])
        self.assertTrue(missing_response["result"].get("isError", False))
        self.assertEqual(missing_payload["error"]["code"], "handoff_not_found")
        self.assertEqual(missing_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIn("foreground_action", missing_payload)
        self.assertNotIn(missing_payload["foreground_action"], missing_payload["safe_next_actions"])
        self.assertIn("telepathy list --status all", missing_payload["foreground_action"]["command"])
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("empty-handoffs.jsonl", encoded)

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

    def test_search_memory_metadata_only_has_structured_authority_next_action(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5601,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "clean source",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 2,
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(response["result"].get("isError", False), payload)
        self.assertIn("structuredContent", response["result"])
        self.assertFalse(response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["kind"], "aippocampus_search_result")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["surface"], "mcp_search_memory_compact")
        self.assertEqual(payload["source_boundary"]["authority"], "reopenable_route")
        self.assertTrue(payload["source_boundary"]["capped_snippets_are_bounded_receipts"])
        self.assertEqual(payload["foreground_action"]["id"], "recall_context_from_search")
        self.assertEqual(payload["foreground_action"]["tool_name"], "recall_context")
        self.assertEqual(payload["foreground_action"]["arguments"]["intent"], "clean source")
        self.assertEqual(payload["foreground_action"]["claim_boundary"], "source_reopen_required_before_claim")
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertIn("foreground_action", payload)
        self.assertNotIn("matches", payload)
        self.assertTrue(payload["source_hits"][0]["snippet_omitted"])
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertNotIn("runtime_provenance", payload)
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn(str(self.cwd), encoded)

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
            mcp_handlers.aippocampus_health, "health_report", side_effect=fake_health_report
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
            mcp_handlers.aippocampus_health, "health_report", side_effect=fake_health_report
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
                    {"id": "checkpoint", "severity": "info", "reason": "checkpoint can wait"},
                    {
                        "id": "storage_gc_rebuildable_cache",
                        "severity": "warning",
                        "reason": "generated cache pressure",
                        "facade_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                    },
                ],
                "checks": [{"name": f"large-{index}", "path": str(self.cwd / f"{index}.jsonl")} for index in range(12)],
                "debug": {
                    "command": f"python {self.cwd / 'tools' / 'health.py'} --cwd {self.cwd}",
                },
            }

        with mock.patch.object(
            mcp_handlers.aippocampus_health, "health_report", side_effect=fake_health_report
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
        self.assertIn("structuredContent", response["result"])
        self.assertFalse(response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["kind"], "aippocampus_health_card")
        self.assertEqual(payload["ok"], False)
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertIn("foreground_action", payload)
        self.assertIn(
            "storage_gc_rebuildable_cache",
            payload["maintenance_summary"]["recommended_action_ids"],
        )
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertEqual(payload["foreground_action"]["id"], "try_agent_recall_with_cue")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertFalse(payload["blocks_first_recall"])
        self.assertEqual(payload["maintenance_next_action"]["id"], "build_index")
        self.assertNotIn("recall_capability", payload)
        self.assertNotIn("source_reopen_success", encoded)
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("debug", encoded)
        self.assertNotIn("runtime_provenance", payload)
        self.assertNotIn("operator_detail_command", payload)
        self.assertNotIn("checks", payload)
        self.assertNotIn("recommended_actions", payload)
        self.assertNotIn("freshness", payload)
        self.assertNotIn("storage_pressure", payload)
        self.assertNotIn("host_state_confounds", payload)

    def test_memory_health_full_keeps_operator_diagnostics(self) -> None:
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
                ],
                "debug": {
                    "command": f"python {self.cwd / 'tools' / 'health.py'} --cwd {self.cwd}",
                },
            }

        with mock.patch.object(
            mcp_handlers.aippocampus_health,
            "health_report",
            side_effect=fake_health_report,
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5810,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd), "detail": "full"},
                    },
                }
            )

        full_payload = self.tool_payload(response)
        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("recommended_actions", full_payload)
        self.assertIn("debug", full_payload)

    def test_memory_health_exception_returns_recovery_card_not_bare_tool_error(self) -> None:
        with mock.patch.object(
            mcp_handlers.aippocampus_health,
            "health_report",
            side_effect=FileNotFoundError(f"no rollout found for cwd: {self.cwd}"),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 582,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd)},
                    },
                }
            )
            full_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5820,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd), "detail": "full"},
                    },
                }
            )

        self.assertFalse(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("structuredContent", response["result"])
        self.assertFalse(response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertEqual(payload["kind"], "aippocampus_memory_health_recovery")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["error"]["code"], "health_artifacts_missing_recall_available")
        self.assertNotIn("recall_capability", payload)
        self.assertNotIn("source_reopen_success", encoded)
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertIn("safe_next_actions", payload)
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertEqual(payload["safe_next_actions"][0]["tool_name"], "agent_deepen")
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn("runtime_provenance", payload)
        self.assertNotIn(str(self.cwd), encoded)
        full_payload = self.tool_payload(full_response)
        self.assertEqual(full_payload["detail"], "full")
        self.assertTrue(full_payload["recall_capability"]["source_reopen_success"])

    def test_agent_recall_import_failure_returns_foreground_runtime_recovery_card(self) -> None:
        with mock.patch.object(
            mcp_handlers,
            "agent_continuity_module",
            side_effect=ImportError(
                f"cannot import name compact_aippo_guidance_card from {self.cwd}\\old.py"
            ),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 583,
                    "method": "tools/call",
                    "params": {
                        "name": "agent_recall",
                        "arguments": {"query": "stale mcp runtime", "cwd": str(self.cwd)},
                    },
                }
            )

        self.assertTrue(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_foreground_mcp_runtime_recovery")
        self.assertEqual(payload["status"], "foreground_mcp_runtime_mismatch")
        self.assertEqual(payload["error"]["code"], "foreground_mcp_runtime_mismatch")
        self.assertIn("reload", payload["recovery_actions"][0])
        self.assertEqual(payload["foreground_action"]["id"], "reload_mcp_transport")
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertIn("aippocampus agent recall", payload["safe_next_actions"][0]["command_template"])
        self.assertEqual(payload["safe_next_actions"][0]["requires"], ["cue"])
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn(str(self.cwd), encoded)

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
        payload = responses[2]["result"].get("structuredContent")
        if not isinstance(payload, dict):
            payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertNotIn("matches", payload)
        self.assertEqual(payload["source_hits"][0]["index"], 1)
        self.assertFalse(payload["source_hits"][0]["snippet_omitted"])
        self.assertIn("clean source", payload["source_hits"][0]["snippet_preview"])

if __name__ == "__main__":
    unittest.main()
