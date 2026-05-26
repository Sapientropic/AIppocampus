from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_clean_source as clean_source  # noqa: E402


class BuildCleanSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.old_codex_home = os.environ.get("CODEX_HOME")
        self.codex_home = self.cwd / "codex-home"
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.rollout = self.cwd / "rollout-test.jsonl"
        self._write_rollout()

    def tearDown(self) -> None:
        if self.old_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.old_codex_home
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append({"type": "session_meta", "payload": {"id": "session-test", "cwd": str(self.cwd)}})
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:00Z",
                "payload": {"type": "user_message", "message": "为什么我们要做 AIppocampus？"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:01Z",
                "payload": {"type": "agent_message", "phase": "commentary", "message": "我先查一下旧线程。"},
            }
        )
        self._append(
            {
                "type": "response_item",
                "timestamp": "2026-05-26T01:00:02Z",
                "payload": {"type": "function_call_output", "call_id": "call-1", "output": "very large tool output"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:03Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "AIppocampus 是一份清洗后的原文记忆库，而不是摘要。",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:01:00Z",
                "payload": {"type": "user_message", "message": "如果这一轮没有 final 呢？"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:01:01Z",
                "payload": {"type": "agent_message", "phase": "commentary", "message": "那就保留末尾 commentary 作为 fallback。"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:02:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "# AGENTS.md instructions for workspace\n重复注入，不应进 clean source。",
                },
            }
        )

    def test_clean_source_keeps_original_user_and_final_text_without_tool_noise(self) -> None:
        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)

        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["upgrade_contract"]["principle"], "approximate_locate_then_exact_reconstruct")
        self.assertIn("message_id", result["identity_policy"]["stable_join_keys"])
        self.assertEqual(result["artifact_scope"], "global_thread_store")
        self.assertEqual(result["message_count"], 4)
        self.assertEqual(result["turn_count"], 2)
        messages_path = Path(result["outputs"]["messages_jsonl"])
        turns_path = Path(result["outputs"]["turns_jsonl"])
        self.assertTrue(messages_path.exists())
        self.assertTrue(turns_path.exists())
        self.assertIn("aippocampus-registry", str(messages_path))
        self.assertFalse((self.cwd / ".aippocampus").exists())

        messages = [
            json.loads(line)
            for line in messages_path.read_text(encoding="utf-8").splitlines()
        ]
        text = "\n".join(item["text"] for item in messages)

        self.assertIn("为什么我们要做 AIppocampus？", text)
        self.assertIn("AIppocampus 是一份清洗后的原文记忆库，而不是摘要。", text)
        self.assertIn("那就保留末尾 commentary 作为 fallback。", text)
        self.assertNotIn("very large tool output", text)
        self.assertNotIn("AGENTS.md instructions", text)
        self.assertNotIn("我先查一下旧线程。", text)

        first = messages[0]
        self.assertTrue(first["source_id"].startswith("src_"))
        self.assertTrue(first["turn_id"].startswith("turn_"))
        self.assertEqual(first["id"], first["message_id"])
        self.assertTrue(first["message_id"].startswith("msg_"))
        self.assertTrue(first["semantic_key"].startswith("sem_"))
        self.assertEqual(first["signature_key"], first["message_id"])
        self.assertEqual(first["raw_start_line"], first["source_line"])
        self.assertEqual(first["raw_end_line"], first["source_line"])
        self.assertEqual(first["clean_ordinal"], 0)
        self.assertEqual(len(first["content_sha256"]), 64)

        turns = [
            json.loads(line)
            for line in turns_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(turns[0]["assistant_phase"], "final_answer")
        self.assertEqual(turns[1]["assistant_phase"], "commentary_fallback")
        self.assertEqual(turns[0]["source_id"], first["source_id"])
        self.assertEqual(turns[0]["turn_id"], first["turn_id"])
        self.assertEqual(turns[0]["user_message_id"], first["message_id"])
        self.assertEqual(turns[0]["message_ids"][0], first["message_id"])
        self.assertEqual(turns[0]["clean_start_ordinal"], 0)
        self.assertEqual(turns[0]["clean_end_ordinal"], 1)

    def test_clean_source_drops_skill_injection_blocks(self) -> None:
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:00:03Z",
                "payload": {
                    "type": "user_message",
                    "message": "<skill>\n<name>aippocampus</name>\n<path>secret-local-path</path>\n---</skill>",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:00:04Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "真实回答仍然保留。",
                },
            }
        )

        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)
        text = Path(result["outputs"]["messages_jsonl"]).read_text(encoding="utf-8")

        self.assertNotIn("<skill>", text)
        self.assertNotIn("secret-local-path", text)
        self.assertIn("真实回答仍然保留。", text)


if __name__ == "__main__":
    unittest.main()
