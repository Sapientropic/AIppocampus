from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.contracts import executable_command_violations  # noqa: E402
from aippocampus_runtime.mcp import server as mcp  # noqa: E402


class McpMemoryHealthRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
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
        self.assertEqual(deepen_payload["result"]["evidence_level"], "source_backed")
        self.assertTrue(deepen_payload["result"]["metrics"]["source_reopen_success"])

        with mock.patch.object(
            mcp.aippocampus_health,
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
        self.assertEqual(payload["agent_next_action"]["id"], "try_agent_recall_with_cue")
        self.assertEqual(payload["agent_next_action"]["tool_name"], "agent_recall")
        self.assertEqual(payload["safe_next_actions"][0]["tool_name"], "agent_recall")
        self.assertNotEqual(payload["agent_next_action"]["id"], "recover_or_continue_without_memory")
        self.assertNotIn(
            "onboard --provider auto --status --json",
            json.dumps(payload["safe_next_actions"][0]),
        )
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("AIppocampus 使用 clean source", encoded)
        self.assertNotIn("小海马体", encoded)


if __name__ == "__main__":
    unittest.main()
