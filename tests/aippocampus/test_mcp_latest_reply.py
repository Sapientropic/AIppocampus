from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.mcp import server as mcp  # noqa: E402


class McpLatestReplyTests(unittest.TestCase):
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
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def call_latest_reply(self, **arguments: object) -> dict:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 44,
                "method": "tools/call",
                "params": {"name": "latest_reply", "arguments": arguments},
            }
        )
        return self.tool_payload(response)

    def test_latest_reply_uses_clean_source_before_raw_rollout(self) -> None:
        payload = self.call_latest_reply(cwd=str(self.cwd))

        self.assertEqual(payload["status"], "clean_source_final_answer")
        self.assertEqual(payload["message"]["message_id"], "msg_final")
        self.assertEqual(payload["detail"], "compact")
        self.assertIn("agent_next_action", payload)
        self.assertNotIn("text", payload["message"])

        full_payload = self.call_latest_reply(cwd=str(self.cwd), detail="full")
        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("text", full_payload["message"])

    def test_latest_reply_mcp_marks_commentary_only_rollout_as_not_closeout(self) -> None:
        rollout = self.cwd / "commentary-only.jsonl"
        commentary_text = "I am still checking things; not final."
        rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-06-16T00:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "hi"},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-06-16T00:00:01Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "phase": "commentary",
                                "message": commentary_text,
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        payload = self.call_latest_reply(cwd=str(self.cwd), rollout=str(rollout))
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["status"], "only_commentary_found")
        self.assertTrue(payload["not_final_closeout"])
        self.assertNotIn(commentary_text, encoded)
        self.assertNotIn("preview", payload["message"])
        self.assertIn("agent recall", payload["agent_next_action"])


if __name__ == "__main__":
    unittest.main()
