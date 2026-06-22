from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import core
from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp import tool_handlers as mcp_tools


class McpMemoryHealthRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.old_registry_dir = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(self.cwd / "default-registry")
        self.clean = core.default_thread_clean_source_dir(self.cwd)
        self.clean.mkdir(parents=True)
        messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
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
            for item in messages:
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
        return json.loads(response["result"]["content"][0]["text"])

    def test_memory_health_split_state_when_recall_can_reopen_source(self) -> None:
        last_recall_env = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
        old_last_recall = os.environ.get(last_recall_env)
        os.environ[last_recall_env] = str(self.cwd / "health-split-agent-last-recall.json")
        self.addCleanup(
            lambda: os.environ.pop(last_recall_env, None)
            if old_last_recall is None
            else os.environ.__setitem__(last_recall_env, old_last_recall)
        )

        recall_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5821,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {"query": "clean source continuity", "cwd": str(self.cwd), "max": 2},
                },
            }
        )
        recall_payload = self.tool_payload(recall_response)
        self.assertFalse(recall_response["result"].get("isError", False), recall_payload)
        self.assertEqual(recall_payload["status"], "ok")
        self.assertEqual(recall_payload["foreground_action"]["tool_name"], "agent_deepen")

        deepen_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5822,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": recall_payload["foreground_action"]["arguments"],
                },
            }
        )
        deepen_payload = self.tool_payload(deepen_response)
        self.assertFalse(deepen_response["result"].get("isError", False), deepen_payload)
        self.assertEqual(deepen_payload["status"], "ok")
        self.assertEqual(deepen_payload["detail"], "compact")
        self.assertEqual(deepen_payload["evidence_level"], "source_backed")
        self.assertTrue(deepen_payload["source_window_summary"]["has_exact_source"])
        self.assertNotIn("result", deepen_payload)

        with mock.patch.object(
            mcp_tools.aippocampus_health,
            "health_report",
            side_effect=FileNotFoundError(f"no rollout found for cwd: {self.cwd}"),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5823,
                    "method": "tools/call",
                    "params": {"name": "memory_health", "arguments": {"cwd": str(self.cwd)}},
                }
            )

        self.assertFalse(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_memory_health_recovery")
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["health_artifacts_missing"])
        self.assertTrue(payload["recall_capability"]["clean_source_available"])
        self.assertTrue(payload["recall_capability"]["recall_tool_available"])
        self.assertEqual(payload["recall_capability"]["route_probe_status"], "routes_available")
        self.assertGreaterEqual(payload["recall_capability"]["route_count"], 1)
        self.assertTrue(payload["recall_capability"]["deepen_tool_available"])
        self.assertTrue(payload["recall_capability"]["source_reopen_success"])
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "try_agent_recall_with_cue")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertNotEqual(payload["foreground_action"]["id"], "recover_or_continue_without_memory")
        self.assertNotIn(
            "onboard --provider auto --status --json",
            json.dumps(payload["safe_next_actions"][0]),
        )
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("AIppocampus 使用 clean source", encoded)
        self.assertNotIn("小海马体", encoded)

    def test_memory_health_keeps_recall_primary_when_health_report_is_pessimistic(self) -> None:
        pessimistic_health = {
            "kind": "aippocampus_health_report",
            "ok": False,
            "status": "needs_maintenance",
            "product_readiness": {
                "ordinary_first_recall_usable": False,
                "status": "needs_maintenance",
                "blocking_action_count": 1,
                "high_severity_action_count": 1,
            },
            "recommended_actions": [
                {
                    "id": "build_clean_source",
                    "severity": "critical",
                    "reason": "clean-source messages.jsonl is missing",
                    "command_template": 'aippocampus maintenance --cwd "{cwd}"',
                    "requires": ["cwd"],
                    "template_only": True,
                }
            ],
            "freshness": {"clean_source_message_delta": 22},
        }

        with mock.patch.object(
            mcp_tools.aippocampus_health,
            "health_report",
            return_value=pessimistic_health,
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5824,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd), "detail": "compact"},
                    },
                }
            )

        self.assertFalse(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_health_card")
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["health_artifacts_missing"])
        self.assertTrue(payload["recall_capability"]["recall_tool_available"])
        self.assertEqual(payload["recall_capability"]["route_probe_status"], "routes_available")
        self.assertGreaterEqual(payload["recall_capability"]["route_count"], 1)
        self.assertTrue(payload["recall_capability"]["source_reopen_success"])
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "try_agent_recall_with_cue")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertFalse(payload["blocks_first_recall"])
        self.assertIn("maintenance_next_action", payload)
        self.assertEqual(payload["maintenance_next_action"]["id"], "build_clean_source")
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("AIppocampus 使用 clean source", encoded)
        self.assertNotIn("小海马体", encoded)

    def test_memory_health_keeps_onboarding_recovery_when_recall_cannot_reopen(self) -> None:
        with (
            mock.patch.object(
                mcp_tools.aippocampus_health,
                "health_report",
                side_effect=FileNotFoundError(f"no rollout found for cwd: {self.cwd}"),
            ),
            mock.patch.object(
                mcp_tools.memory_health_recovery,
                "_recall_probe",
                return_value={
                    "clean_source_available": False,
                    "recall_tool_available": True,
                    "route_probe_status": "clean_source_missing_probe_no_routes",
                    "route_count": 0,
                    "deepen_tool_available": False,
                    "source_reopen_success": False,
                },
            ),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5825,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_health",
                        "arguments": {"cwd": str(self.cwd)},
                    },
                }
            )

        self.assertFalse(response["result"].get("isError", False))
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_memory_health_recovery")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["error"]["code"], "health_unavailable")
        self.assertNotIn("agent_next_action", payload)
        self.assertIn("safe_next_actions", payload)
        self.assertIn("onboard --provider auto --status --json", payload["foreground_action"]["command"])
        self.assertEqual(
            payload["safe_next_actions"][2]["command_template"],
            'aippocampus search "{exact_phrase}" --json',
        )
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn(str(self.cwd), encoded)

if __name__ == "__main__":
    unittest.main()
