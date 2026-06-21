from __future__ import annotations

import json
import shlex
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.source import latest_reply as latest_reply_module


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
        self.assertEqual(
            payload["message"]["text"],
            "AIppocampus 使用 clean source，而不是摘要替代事实。",
        )
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "open_full_latest_reply")
        self.assertEqual(payload["source_reopen_action"]["tool_name"], "get_turn_context")
        self.assertEqual(payload["source_reopen_action"]["arguments"]["message_id"], "msg_final")
        self.assertEqual(
            payload["source_reopen_action"]["claim_boundary"],
            "source_open_required_before_quoting",
        )
        self.assertLessEqual(
            payload["message"]["text_char_limit"],
            latest_reply_module.MAX_COMPACT_FINAL_ANSWER_CHARS,
        )

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
                            "payload": {
                                "type": "user_message",
                                "message": "finish recovery command card",
                            },
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
        self.assertEqual(
            shlex.split(payload["foreground_action"]["command"]),
            ["aippocampus", "agent", "recall", "finish recovery command card", "--json"],
        )
        self.assertNotIn("command_template", payload["foreground_action"])
        self.assertNotIn("latest closeout or current handoff", encoded)

    def test_latest_reply_mcp_omits_host_internal_recovery_cue_from_command(self) -> None:
        rollout = self.cwd / "host-internal-commentary.jsonl"
        cue = "<subagent_notification>internal handoff should stay out of commands</subagent_notification>"
        rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-06-16T00:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": cue},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-06-16T00:00:01Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "phase": "commentary",
                                "message": "still working; not final",
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
        action = payload["foreground_action"]

        self.assertNotIn("command", action)
        self.assertEqual(action["command_template"], 'aippocampus agent recall "{cue}" --json')
        self.assertEqual(action["cue_omission_reason"], "host_internal_cue_omitted")
        self.assertNotIn("subagent_notification", encoded)

    def test_latest_reply_mcp_no_rollout_returns_recovery_card(self) -> None:
        missing = self.cwd / "missing-project"
        missing.mkdir()
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 45,
                "method": "tools/call",
                "params": {"name": "latest_reply", "arguments": {"cwd": str(missing)}},
            }
        )
        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["status"], "no_latest_reply_source_found")
        self.assertEqual(payload["error"]["code"], "no_rollout_for_cwd")
        self.assertEqual(payload["foreground_action"]["requires"], ["cue"])
        self.assertIn("agent recall", payload["foreground_action"]["command_template"])
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(str(missing), encoded)

if __name__ == "__main__":
    unittest.main()
