from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import core
from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp import tool_handlers as mcp_handlers
from aippocampus_runtime.recall import (
    agent_continuity,
    apw_route_identity,
    associative_path_fallback,
)
from aippocampus_runtime.registry import store as registry_store
from conversation_sources import ConversationSourceRef
from tests.aippocampus.frontstage_assertions import assert_compact_detail_affordances
from tests.aippocampus.mcp_server_fixtures import (
    assert_recall_template_action,
    field_path_count,
)
from tests.aippocampus.product_probe_helpers import (
    call_mcp_tool_payload,
    mcp_response_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

class AippocampusMcpServerRecallTests(unittest.TestCase):
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

    def append_clean_message(self, row: dict[str, object]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": row.get("turn_id"),
                        "turn_index": row.get("turn_index"),
                        "message_ids": [row.get("message_id") or row.get("id")],
                        "assistant_phase": row.get("phase") or row.get("role"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def write_registry_clean_source(
        self,
        *,
        registry_dir: Path,
        thread_key: str,
        message_id: str,
        source_text: str,
    ) -> Path:
        clean = self.cwd / "registry-source" / thread_key.replace(":", "-") / "clean-source"
        clean.mkdir(parents=True)
        row = {
            "message_id": message_id,
            "turn_id": f"turn-{message_id}",
            "turn_index": 23,
            "source_id": f"src-{message_id}",
            "source_line": 90,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": source_text,
        }
        (clean / "messages.jsonl").write_text(
            json.dumps(row, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": row["turn_id"],
                    "turn_index": row["turn_index"],
                    "message_ids": [message_id],
                    "assistant_phase": "final_answer",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "2026-06-22T00:00:00Z",
                    "threads": [
                        {
                            "thread_key": thread_key,
                            "title": "registry APW MCP source",
                            "project_label": "AIppocampus",
                            "paths": {
                                "clean_source_dir": str(clean),
                                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return clean

    def assert_mcp_apw_roundtrip(
        self,
        *,
        cue: str,
        message_id: str,
        source_id: str,
        source_line: int,
        source_text: str,
        cache_name: str,
        feedback_path: Path | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        cache_path = self.cwd / cache_name
        recall_args = {
            "query": cue,
            "cwd": str(self.cwd),
            "clean_source_dir": str(self.clean),
            "registry_dir": str(self.cwd / "registry"),
            "apw_fallback": True,
            "last_recall_path": str(cache_path),
            **({"apw_feedback_path": str(feedback_path)} if feedback_path else {}),
        }
        full_recall_payload = call_mcp_tool_payload(
            "agent_recall",
            {**recall_args, "detail": "full"},
        )
        compact_recall_payload = call_mcp_tool_payload(
            "agent_recall",
            {**recall_args, "detail": "compact"},
        )

        self.assertIn(full_recall_payload["status"], {"ok", "no_routes"})
        self.assertTrue(
            full_recall_payload["associative_path_policy"]["apw_candidate_input_available"]
        )
        self.assertEqual(full_recall_payload["associative_path_fallback"]["status"], "route_candidate")
        action = compact_recall_payload["foreground_action"]
        self.assertEqual(action["id"], "deepen_associative_path_fallback")
        self.assertEqual(action["tool_name"], "agent_deepen")
        identity = full_recall_payload["associative_path_fallback"]["apw_route_identity"]
        self.assertEqual(
            identity["source_ref_digest"],
            full_recall_payload["associative_path_fallback"]["source_ref_digest"],
        )
        self.assertIn("recall_selector", action["arguments"])
        self.assertNotIn("associative_path_policy", compact_recall_payload)
        self.assertNotIn("associative_path_fallback", compact_recall_payload)
        self.assertNotIn("last_recall_cache_available", compact_recall_payload)
        self.assertNotIn("route_count", compact_recall_payload)
        self.assertNotIn("safe_next_actions", compact_recall_payload)
        self.assertNotIn("weak_route_recovery_card", compact_recall_payload)
        self.assertLessEqual(field_path_count(compact_recall_payload), 60)
        self.assertEqual(executable_command_violations(compact_recall_payload), [])

        deepen_payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": action["arguments"]["request_index"],
                "recall_selector": action["arguments"]["recall_selector"],
                "last_recall_path": str(cache_path),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "detail": "full",
            },
        )
        self.assertEqual(deepen_payload["status"], "ok")
        source_refs = deepen_payload["result"]["source_refs"]
        self.assertEqual(source_refs[0]["message_id"], message_id)
        self.assertEqual(
            deepen_payload["result"]["apw_route_identity"]["source_ref_digest"],
            identity["source_ref_digest"],
        )
        window_text = "\n".join(
            str(message.get("text") or "")
            for message in deepen_payload["result"]["source_window"]["messages"]
            if isinstance(message, dict)
        )
        self.assertIn(source_text, window_text)
        self.assertEqual(
            identity["source_ref_digest"],
            apw_route_identity.source_ref_digest(
                [
                    {
                        "source_id": source_id,
                        "message_id": message_id,
                        "turn_id": deepen_payload["result"]["source_refs"][0].get("turn_id"),
                        "turn_index": deepen_payload["result"]["source_refs"][0].get("turn_index"),
                        "line": source_line,
                    }
                ]
            ),
        )
        return full_recall_payload, deepen_payload

    def test_mcp_first_apw_current_clean_source_roundtrip_and_feedback_gate(self) -> None:
        registry = self.cwd / "registry"
        registry.mkdir()
        self.append_clean_message(
            {
                "message_id": "msg-mcp-cn-apw",
                "turn_id": "turn-mcp-cn-apw",
                "turn_index": 8,
                "source_id": "src-mcp-cn-apw",
                "source_line": 30,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "公开 fixture 锚点：黏菌 联想回忆 探索算法，供 MCP APW gate 追踪。",
            }
        )
        self.append_clean_message(
            {
                "message_id": "msg-mcp-en-apw",
                "turn_id": "turn-mcp-en-apw",
                "turn_index": 9,
                "source_id": "src-mcp-en-apw",
                "source_line": 31,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "The source-shape narrative mesh slime mold pathlet is the English MCP APW gate.",
            }
        )
        feedback_path = self.cwd / "apw-feedback.jsonl"

        with mock.patch.dict(
            "os.environ",
            {associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery"},
        ):
            cn_recall, _cn_deepen = self.assert_mcp_apw_roundtrip(
                cue="黏菌 联想回忆 探索算法",
                message_id="msg-mcp-cn-apw",
                source_id="src-mcp-cn-apw",
                source_line=30,
                source_text="黏菌 联想回忆 探索算法",
                cache_name="mcp-cn-last-recall.json",
                feedback_path=feedback_path,
            )
            self.assert_mcp_apw_roundtrip(
                cue="source-shape narrative mesh slime mold pathlet",
                message_id="msg-mcp-en-apw",
                source_id="src-mcp-en-apw",
                source_line=31,
                source_text="source-shape narrative mesh slime mold pathlet",
                cache_name="mcp-en-last-recall.json",
            )
            diagnostic = call_mcp_tool_payload(
                "recall_diagnostic",
                {
                    "cue": "黏菌 联想回忆 探索算法",
                    "cwd": str(self.cwd),
                    "clean_source_dir": str(self.clean),
                    "registry_dir": str(registry),
                    "include_associative_path_diagnostics": True,
                },
            )
            apw_diagnostic = diagnostic["associative_path_diagnostics"]
            self.assertEqual(apw_diagnostic["decision"], "route_candidates")
            self.assertEqual(
                apw_diagnostic["top_candidates"][0]["apw_route_identity"]["source_ref_digest"],
                cn_recall["associative_path_fallback"]["apw_route_identity"]["source_ref_digest"],
            )

            identity = cn_recall["associative_path_fallback"]["apw_route_identity"]
            receipt = agent_continuity.capture_feedback(
                route_id=str(identity["feedback_target_id"]),
                outcome="wrong_route",
                route_kind="active_path",
                feedback_path=feedback_path,
            )
            self.assertTrue(receipt["wrote_event"])

            rerun = call_mcp_tool_payload(
                "agent_recall",
                {
                    "query": "黏菌 联想回忆 探索算法",
                    "cwd": str(self.cwd),
                    "clean_source_dir": str(self.clean),
                    "registry_dir": str(registry),
                    "apw_fallback": True,
                    "detail": "full",
                    "last_recall_path": str(self.cwd / "mcp-cn-rerun-last-recall.json"),
                    "apw_feedback_path": str(feedback_path),
                },
            )

        self.assertTrue(rerun["associative_path_policy"]["apw_candidate_input_available"])
        self.assertEqual(rerun["associative_path_fallback"]["status"], "abstained")
        self.assertIn("negative_feedback_evaporated", rerun["associative_path_fallback"]["reason_codes"])

    def test_mcp_first_apw_registry_clean_source_roundtrip(self) -> None:
        registry = self.cwd / "registry"
        self.write_registry_clean_source(
            registry_dir=registry,
            thread_key="session:mcp-registry-apw",
            message_id="msg-mcp-registry-apw",
            source_text="我们认真讨论过黏菌启发的联想回忆和探索算法，MCP 必须 deepen 打开这条 source。",
        )
        cache_path = self.cwd / "mcp-registry-last-recall.json"

        with mock.patch.dict(
            "os.environ",
            {associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery"},
        ):
            recall_args = {
                "query": "黏菌 联想回忆 探索算法",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(registry),
                "apw_fallback": True,
                "last_recall_path": str(cache_path),
            }
            recall_payload = call_mcp_tool_payload(
                "agent_recall",
                {**recall_args, "detail": "full"},
            )
            compact_recall_payload = call_mcp_tool_payload(
                "agent_recall",
                {**recall_args, "detail": "compact"},
            )

        self.assertTrue(recall_payload["associative_path_policy"]["apw_candidate_input_available"])
        self.assertEqual(recall_payload["associative_path_fallback"]["status"], "route_candidate")
        self.assertEqual(
            recall_payload["associative_path_fallback"]["candidate_source_kind"],
            "registry_clean_source",
        )
        action = compact_recall_payload["foreground_action"]
        self.assertEqual(action["id"], "deepen_associative_path_fallback")
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertIn("recall_selector", action["arguments"])

        deepen_payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": action["arguments"]["request_index"],
                "recall_selector": action["arguments"]["recall_selector"],
                "last_recall_path": str(cache_path),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(registry),
                "detail": "full",
            },
        )

        self.assertEqual(deepen_payload["status"], "ok")
        self.assertEqual(deepen_payload["result"]["source_refs"][0]["message_id"], "msg-mcp-registry-apw")
        self.assertEqual(
            deepen_payload["result"]["apw_route_identity"]["source_ref_digest"],
            recall_payload["associative_path_fallback"]["apw_route_identity"]["source_ref_digest"],
        )
        window_text = "\n".join(
            str(message.get("text") or "")
            for message in deepen_payload["result"]["source_window"]["messages"]
            if isinstance(message, dict)
        )
        self.assertIn("黏菌启发的联想回忆和探索算法", window_text)

        diagnostic = call_mcp_tool_payload(
            "recall_diagnostic",
            {
                "cue": "黏菌 联想回忆 探索算法",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(registry),
                "include_associative_path_diagnostics": True,
            },
        )
        apw_diagnostic = diagnostic["associative_path_diagnostics"]
        self.assertEqual(apw_diagnostic["decision"], "route_candidates")
        self.assertEqual(
            apw_diagnostic["metrics"]["candidate_source_counts"]["registry_clean_source"],
            1,
        )

    def test_register_thread_requires_explicit_write_shape(self) -> None:
        with mock.patch.object(mcp_handlers.registry, "register_current_thread") as register:
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
        empty_payload = mcp_response_payload(empty_response)
        missing_confirm_payload = mcp_response_payload(missing_confirm_response)
        self.assertEqual(empty_payload["error"]["code"], "explicit_write_required")
        self.assertEqual(missing_confirm_payload["error"]["code"], "explicit_write_required")
        for payload in (empty_payload, missing_confirm_payload):
            self.assertEqual(payload["status"], "needs_input")
            self.assertEqual(payload["surface_class"], "foreground_recovery_card")
            self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", payload)
            self.assertEqual(payload["foreground_action"]["tool_name"], "list_threads")
            self.assertTrue(payload["safe_next_actions"][0]["template_only"])
            self.assertEqual(payload["safe_next_actions"][0]["requires"], ["cwd", "provider", "confirm_write"])
            self.assertEqual(executable_command_violations(payload), [])
        register.assert_not_called()

    def test_register_thread_passes_explicit_provider_to_registry(self) -> None:
        with mock.patch.object(
            mcp_handlers.registry,
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

        payload = mcp_response_payload(response)
        self.assertEqual(payload["status"], "registered")
        provider = register.call_args.kwargs["provider"]
        self.assertEqual(provider.name, "codex")

    def test_register_thread_default_response_is_compact_and_omits_session_meta(self) -> None:
        with mock.patch.object(
            mcp_handlers.registry,
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

        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError"), payload)
        self.assertEqual(payload["status"], "registered")
        self.assertTrue(payload["thread_handle"].startswith("thread_"))
        self.assertNotEqual(payload["thread_handle"], "session:private-raw-thread-id")
        self.assertTrue(payload["thread_key_redacted"])
        self.assertEqual(payload["title"], "AIppocampus issue cleanup")
        self.assertEqual(payload["message_count"], 4300)
        self.assertTrue(payload["has_clean_source"])
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn("session:private-raw-thread-id", encoded)
        self.assertNotIn("session_meta", encoded)
        self.assertNotIn("base_instructions", encoded)
        self.assertNotIn("full host instructions", encoded)
        self.assertNotIn(str(self.clean), encoded)

    def test_register_thread_reports_retryable_registry_writer_busy(self) -> None:
        with mock.patch.object(
            mcp_handlers.registry,
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
        payload = mcp_response_payload(response)
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
            mock.patch.object(mcp_handlers, "create_conversation_provider", return_value=FixtureProvider()),
            mock.patch.object(mcp_handlers.registry, "thread_key_for", side_effect=fake_thread_key),
            mock.patch.object(mcp_handlers.aippocampus_health, "health_report", return_value={}),
        ):
            threads = [
                threading.Thread(target=call_register, args=(workspace_a, 41)),
                threading.Thread(target=call_register, args=(workspace_b, 42)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=registry_store.DEFAULT_REGISTRY_WRITER_WAIT_TIMEOUT_SECONDS + 5)

        alive_threads = [thread.name for thread in threads if thread.is_alive()]
        self.assertFalse(errors)
        self.assertFalse(
            alive_threads,
            f"register_thread worker(s) did not finish; responses={len(responses)} errors={errors!r}",
        )
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

        payload = mcp_response_payload(response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertIn("structuredContent", response["result"])
        self.assertFalse(response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["surface"], "mcp_search_memory_compact")
        self.assertNotIn("runtime_provenance", payload)
        self.assertNotIn("output_boundary", payload)
        self.assertGreaterEqual(payload["match_count"], 1)
        self.assertNotIn("matches", payload)
        self.assertEqual(payload["source_hits"][0]["index"], 1)
        self.assertLessEqual(len(payload["source_hits"]), 2)
        self.assertTrue(payload["source_hits"][0]["snippet_omitted"])
        self.assertNotIn("message_id", payload["source_hits"][0])
        self.assertNotIn("snippet_preview", payload["source_hits"][0])
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)

    def test_search_memory_can_emit_source_preview_when_explicitly_requested(self) -> None:
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

        payload = mcp_response_payload(response)
        self.assertFalse(response["result"].get("isError", False))
        self.assertNotIn("matches", payload)
        self.assertEqual(payload["source_hits"][0]["index"], 1)
        self.assertFalse(payload["source_hits"][0]["snippet_omitted"])
        self.assertIn("不是摘要替代事实", payload["source_hits"][0]["snippet_preview"])

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "clean source 摘要",
                        "cwd": str(self.cwd),
                        "max": 3,
                        "include_source_snippets": True,
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = mcp_response_payload(full_response)
        self.assertEqual(full_payload["matches"][0]["message_id"], "msg_final")
        self.assertIn("不是摘要替代事实", full_payload["matches"][0]["snippet"])

    def test_search_memory_all_registered_sources_scope_matches_cli_projection(self) -> None:
        registry_clean = self.cwd / "registry-thread" / "clean-source"
        registry_clean.mkdir(parents=True)
        (registry_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_registry",
                    "message_id": "msg_registry",
                    "source_line": 7,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 2,
                    "is_final": True,
                    "text": "The MCP registry-wide exact phrase lives outside the current thread.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:registry",
                            "title": "Registry route",
                            "paths": {
                                "workspace": str(self.cwd / "private-workspace"),
                                "clean_source_messages_jsonl": str(registry_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3101,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "registry-wide exact phrase",
                        "cwd": str(self.cwd),
                        "registry_dir": str(self.cwd),
                        "scope": "all_registered_sources",
                    },
                },
            }
        )
        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_registry_source_search")
        self.assertEqual(payload["mcp_search_scope"], "all_registered_sources")
        self.assertEqual(payload["match_count"], 1)
        self.assertNotIn("matches", payload)
        self.assertEqual(payload["source_hits"][0]["index"], 1)
        self.assertIn("--thread-key session:registry", payload["foreground_action"]["command"])
        self.assertIn(
            "aippocampus search --open-source --thread-key session:registry",
            encoded,
        )
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("privacy", payload)

    def test_search_memory_all_registered_sources_keeps_duplicate_refs_reopenable_in_full_detail(self) -> None:
        duplicate_text = "MCP duplicate source ref exact phrase is mirrored."
        threads = []
        for index in range(1, 3):
            registry_clean = self.cwd / f"mcp-duplicate-{index}" / "clean-source"
            registry_clean.mkdir(parents=True)
            (registry_clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "id": f"msg_duplicate_{index}",
                        "message_id": f"msg_duplicate_{index}",
                        "source_line": 20 + index,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": index,
                        "is_final": True,
                        "text": duplicate_text,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:mcp-duplicate-{index}",
                    "title": f"MCP duplicate {index}",
                    "paths": {
                        "clean_source_messages_jsonl": str(registry_clean / "messages.jsonl"),
                        "sqlite": str(self.cwd / f"missing-mcp-duplicate-{index}.sqlite"),
                    },
                }
            )
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
            encoding="utf-8",
        )

        compact_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3103,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "MCP duplicate source ref exact phrase",
                        "cwd": str(self.cwd),
                        "registry_dir": str(self.cwd),
                        "scope": "all_registered_sources",
                    },
                },
            }
        )
        compact_payload = mcp_response_payload(compact_response)
        compact_encoded = json.dumps(compact_payload, ensure_ascii=False)

        self.assertEqual(compact_payload["match_count"], 1)
        self.assertEqual(compact_payload["source_hits"][0]["source_count"], 2)
        self.assertNotIn("matches", compact_payload)
        self.assertNotIn("duplicate_source_refs", compact_encoded)

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3104,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "MCP duplicate source ref exact phrase",
                        "cwd": str(self.cwd),
                        "registry_dir": str(self.cwd),
                        "scope": "all_registered_sources",
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = mcp_response_payload(full_response)
        duplicate_refs = full_payload["matches"][0]["duplicate_source_refs"]

        self.assertEqual([ref["source_ref_index"] for ref in duplicate_refs], [1, 2])
        self.assertIn("--thread-key session:mcp-duplicate-2", duplicate_refs[1]["source_window_command"])
        self.assertIn("--source-ref-index 2", duplicate_refs[1]["last_search_reopen_command"])

        open_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3105,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "MCP duplicate source ref exact phrase",
                        "cwd": str(self.cwd),
                        "registry_dir": str(self.cwd),
                        "scope": "all_registered_sources",
                        "open_source": True,
                        "thread_key": "session:mcp-duplicate-2",
                        "message_id": "msg_duplicate_2",
                        "line": 22,
                        "detail": "full",
                    },
                },
            }
        )
        open_payload = mcp_response_payload(open_response)

        self.assertEqual(open_payload["kind"], "aippocampus_registry_source_window")
        self.assertEqual(open_payload["source_boundary"]["authority"], "source_open")
        self.assertEqual(open_payload["source_route"]["thread_key"], "session:mcp-duplicate-2")
        self.assertIn(duplicate_text, json.dumps(open_payload["source_window"], ensure_ascii=False))
        self.assertNotIn(str(self.cwd), json.dumps(open_payload, ensure_ascii=False))

    def test_search_memory_all_registered_sources_uses_configured_registry_when_registry_dir_omitted(self) -> None:
        registry_clean = self.cwd / "registry-cwd-thread" / "clean-source"
        registry_clean.mkdir(parents=True)
        (registry_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_registry_cwd",
                    "message_id": "msg_registry_cwd",
                    "source_line": 11,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "The MCP cwd fallback registry exact phrase is discoverable.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:registry-cwd",
                            "title": "Registry cwd route",
                            "paths": {
                                "clean_source_messages_jsonl": str(registry_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-cwd.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with mock.patch.dict("os.environ", {"AIPPOCAMPUS_REGISTRY_DIR": str(self.cwd)}):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3102,
                    "method": "tools/call",
                    "params": {
                        "name": "search_memory",
                        "arguments": {
                            "query": "cwd fallback registry exact phrase",
                            "cwd": str(self.cwd),
                            "scope": "all_registered_sources",
                        },
                    },
                }
            )
        payload = mcp_response_payload(response)

        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["mcp_search_scope"], "all_registered_sources")
        self.assertEqual(payload["match_count"], 1)
        self.assertNotIn("matches", payload)
        self.assertIn("--thread-key session:registry-cwd", payload["foreground_action"]["command"])

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

        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertIn("structuredContent", response["result"])
        self.assertFalse(response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertEqual(payload["kind"], "aippocampus_recall_context")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["surface"], "mcp_recall_context_legacy_compact")
        self.assertEqual(payload["legacy_tool_state"], "legacy_detail_only")
        self.assertEqual(
            payload["foreground_action"]["id"],
            "use_agent_recall_for_foreground_continuity",
        )
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn("route_count", payload)
        self.assertNotIn("metrics", payload)
        self.assertIn("source_backed_claims", payload["claim_boundary"]["must_reopen_for"])
        self.assertNotIn("source_boundary", payload)
        route = payload["routes"][0]
        self.assertEqual(route["evidence_level"], "needs_reopen")
        self.assertEqual(route["action"]["tool_name"], "recall_deepen")
        self.assertEqual(route["action"]["arguments"]["message_id"], "msg_final")
        self.assertNotIn("handle", route)
        self.assertNotIn("source_refs", route)
        self.assertNotIn("source_ref_count", route)
        self.assertNotIn("handle_sha256_12", route)
        self.assertNotIn("suggested_next", route)
        self.assertNotIn("source_reopen_path", route)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("继续", encoded)
        self.assertLessEqual(len(encoded.encode("utf-8")), 5_000)
        self.assertLessEqual(len(payload), 20)
        self.assertLessEqual(field_path_count(payload), 120)

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

        payload = mcp_response_payload(response)
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
        handle = mcp_response_payload(context_response)["routes"][0]["handle"]

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

        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_recall_deepen")
        self.assertEqual(payload["support_level"], "evidence")
        self.assertEqual(payload["evidence_level"], "source_backed")
        self.assertEqual(payload["source_refs"][0]["message_id"], "msg_final")
        self.assertEqual(payload["source_reopen_path"]["tool"], "get_turn_context")
        self.assertIn("不是摘要替代事实", payload["source_window"]["messages"][1]["text"])
        self.assertEqual(
            payload["source_window"]["messages"][0]["source_use_class"],
            "foreground_continuity_source",
        )
        self.assertEqual(
            payload["source_window"]["messages"][1]["source_use_class"],
            "foreground_continuity_source",
        )
        self.assertNotIn("no_raw_private_paths", payload["source_boundary"])
        self.assertTrue(payload["source_boundary"]["private_paths_may_exist_in_source_text"])
        self.assertTrue(payload["source_boundary"]["default_projection_redacts_private_paths"])
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

        payload = mcp_response_payload(response)
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
        route = mcp_response_payload(context_response)["routes"][0]

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

        payload = mcp_response_payload(response)
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
        reopen_args = mcp_response_payload(context_response)["routes"][0]["source_reopen_path"][
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

        payload = mcp_response_payload(response)
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
        payload = mcp_response_payload(response)
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
        payload = mcp_response_payload(response)
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
        handle = mcp_response_payload(context_response)["routes"][0]["handle"]
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
        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["error"]["code"], "stale_recall_handle")
        self.assertNotIn("Later source", encoded)

    def test_recall_deepen_redacts_local_paths_inside_source_window_text(self) -> None:
        local_path = "X:" + "\\synthetic-private\\workspace\\secret.txt"
        forward_path = "E:/synthetic-private/workspace/process.jsonl"
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
                "text": f"Path boundary example lives at {local_path}.",
            }
        )
        self.messages.append(
            {
                "message_id": "msg_process",
                "turn_id": "turn_process",
                "source_id": "src_test",
                "source_line": 13,
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 4,
                "is_final": False,
                "text": f"<subagent_notification> audit payload opened {forward_path}",
            }
        )
        self.messages.append(
            {
                "message_id": "msg_process_final",
                "turn_id": "turn_process",
                "source_id": "src_test",
                "source_line": 14,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 4,
                "is_final": True,
                "text": "Ordinary closure route should remain the foreground continuity source.",
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
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_process",
                        "turn_index": 4,
                        "message_ids": ["msg_process", "msg_process_final"],
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
        handle = mcp_response_payload(context_response)["routes"][0]["handle"]

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

        payload = mcp_response_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertNotIn(local_path, encoded)
        self.assertIn("<redacted:local-path>", encoded)
        self.assertNotIn(forward_path, encoded)
        self.assertNotIn("no_raw_private_paths", payload["source_boundary"])

        context_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 310,
                "method": "tools/call",
                "params": {
                    "name": "recall_context",
                    "arguments": {
                        "intent": "Ordinary closure route",
                        "cwd": str(self.cwd),
                        "detail": "full",
                    },
                },
            }
        )
        handle = mcp_response_payload(context_response)["routes"][0]["handle"]
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 311,
                "method": "tools/call",
                "params": {
                    "name": "recall_deepen",
                    "arguments": {"handle": handle, "cwd": str(self.cwd)},
                },
            }
        )
        payload = mcp_response_payload(response)
        by_id = {item["message_id"]: item for item in payload["source_window"]["messages"]}
        self.assertEqual(by_id["msg_process"]["source_use_class"], "audit_or_commentary_source")
        self.assertEqual(by_id["msg_process"]["ordinary_continuity_priority"], "low")
        self.assertEqual(
            by_id["msg_process_final"]["source_use_class"],
            "foreground_continuity_source",
        )
        self.assertNotIn(forward_path, json.dumps(payload, ensure_ascii=False))

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

        payload = mcp_response_payload(response)
        self.assertNotIn("limit", payload)

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3301,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {
                        "query": "source",
                        "cwd": str(self.cwd),
                        "max": 9999,
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = mcp_response_payload(full_response)
        self.assertEqual(full_payload["limit"], 25)

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

        payload = mcp_response_payload(response)
        self.assertNotIn("source", payload)
        self.assertNotIn(str(self.clean), json.dumps(payload, ensure_ascii=False))

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
        private_payload = mcp_response_payload(private_response)
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

        payload = mcp_response_payload(response)
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

        payload = mcp_response_payload(response)
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
        payload = mcp_response_payload(response)
        self.assertEqual(payload["error"]["code"], "missing_turn_selector")
        self.assertIn("turn_id", payload["error"]["required_any"])
        self.assertEqual(
            payload["foreground_action"]["tool_name"],
            "agent_recall",
        )
        self.assertIn("arguments_template", payload["foreground_action"])
        self.assertNotIn("details", payload["error"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_deepen_tools_return_recovery_cards_for_missing_selectors(self) -> None:
        agent_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4100,
                "method": "tools/call",
                "params": {"name": "agent_deepen", "arguments": {"cwd": str(self.cwd)}},
            }
        )
        recall_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4101,
                "method": "tools/call",
                "params": {"name": "recall_deepen", "arguments": {"cwd": str(self.cwd)}},
            }
        )

        self.assertTrue(agent_response["result"]["isError"])
        agent_payload = mcp_response_payload(agent_response)
        self.assertEqual(agent_payload["status"], "needs_input")
        self.assertEqual(agent_payload["surface_class"], "foreground_recovery_card")
        self.assertEqual(agent_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(agent_payload["error"]["code"], "missing_recall_handle")
        self.assertNotIn("operator_detail", agent_payload)
        self.assertNotIn("boundary_detail", agent_payload)
        assert_compact_detail_affordances(self, agent_payload, surface="mcp.agent_deepen.missing_selector")
        assert_recall_template_action(self, agent_payload["foreground_action"])
        self.assertIn("foreground_action", agent_payload)
        self.assertIn(
            "aippocampus agent deepen --request",
            agent_payload["follow_up_action"]["command_template"],
        )
        self.assertIn("--recall-selector {recall_selector}", agent_payload["follow_up_action"]["command_template"])
        self.assertEqual(agent_payload["follow_up_action"]["requires"], ["recall_selector", "request_index"])

        self.assertTrue(recall_response["result"]["isError"])
        recall_payload = mcp_response_payload(recall_response)
        self.assertEqual(recall_payload["error"]["code"], "missing_recall_handle")
        self.assertIn("foreground_action", recall_payload)
        self.assertNotIn("agent_next_action", recall_payload)
        self.assertNotIn("details", recall_payload["error"])
        self.assertEqual(recall_payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertIn("arguments_template", recall_payload["foreground_action"])
        self.assertEqual(recall_payload["staged_followup"][1]["tool_name"], "agent_deepen")
        action_surface = json.dumps(
            {
                "foreground_action": recall_payload.get("foreground_action"),
                "safe_next_actions": recall_payload.get("safe_next_actions"),
                "staged_followup": recall_payload.get("staged_followup"),
            },
            ensure_ascii=False,
        )
        self.assertNotIn("recall_context", action_surface)
        self.assertNotIn("recall_deepen", action_surface)
        self.assertEqual(executable_command_violations(recall_payload), [])

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
        payload = mcp_response_payload(response)
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
        payload = mcp_response_payload(response)
        self.assertEqual(payload["error"]["code"], "clean_source_unavailable")
        self.assertEqual(
            payload["error"]["details"]["clean_source_dir"], mcp_handlers.LOCAL_PATH_REDACTION
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

        payload = mcp_response_payload(response)
        self.assertEqual(payload["error"]["details"]["clean_source_dir"], str(missing_clean))

if __name__ == "__main__":
    unittest.main()
