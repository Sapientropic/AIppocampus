from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import registry  # noqa: E402


class RegisterRolloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "Project Alpha"
        self.cwd.mkdir()
        self.rollout = self.root / "rollout-other-thread.jsonl"
        self.registry_dir = self.root / "registry"
        self._write_rollout()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append(
            {
                "type": "session_meta",
                "payload": {
                    "id": "session-other",
                    "timestamp": "2026-05-26T03:00:00Z",
                    "cwd": str(self.cwd),
                    "originator": "Codex Desktop",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:01Z",
                "payload": {"type": "user_message", "message": "把这个旧线程纳入 AIppocampus 记忆范围。"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:02Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "旧线程已经注册为可检索的 clean-source 原文参考。",
                },
            }
        )

    def test_register_rollout_writes_per_thread_store_and_project_tags(self) -> None:
        result = registry.register_rollout_thread(
            self.rollout,
            project="Life OS",
            tags=["codex", "memory"],
            registry_dir=self.registry_dir,
        )

        entry = result["entry"]
        self.assertEqual(entry["thread_key"], "session:session-other")
        self.assertEqual(entry["artifact_scope"], "registry_thread_store")
        self.assertEqual(entry["project_label"], "Life OS")
        self.assertIn("memory", entry["project_tags"])
        self.assertEqual(entry["clean_message_count"], 2)

        clean_messages = Path(entry["paths"]["clean_source_messages_jsonl"])
        self.assertTrue(clean_messages.exists())
        self.assertIn("旧线程已经注册", clean_messages.read_text(encoding="utf-8"))
        self.assertIn("threads", entry["paths"]["registry_thread_store"])

        score, hits = registry.deep_search_entry(entry, ["clean-source"], max_hits=2)
        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["source"], "clean_source")
        self.assertEqual(hits[0]["phase"], "final_answer")

        metadata_score = registry.entry_search_score(entry, ["Life OS"])
        self.assertGreater(metadata_score, 0)

        data = json.loads((self.registry_dir / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(data["threads"][0]["thread_key"], "session:session-other")

    def test_scan_sessions_dry_run_reports_unregistered_rollouts(self) -> None:
        original_home = registry.codex_home
        registry.codex_home = lambda: self.root
        sessions = self.root / "sessions" / "2026" / "05" / "26"
        sessions.mkdir(parents=True)
        target = sessions / "rollout-copy.jsonl"
        target.write_text(self.rollout.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            result = registry.scan_session_rollouts(registry_dir=self.registry_dir, dry_run=True)
        finally:
            registry.codex_home = original_home

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["planned"][0]["thread_key"], "session:session-other")

    def test_deep_search_demotes_injected_skill_hits(self) -> None:
        clean_dir = self.root / "clean"
        clean_dir.mkdir()
        messages = clean_dir / "messages.jsonl"
        rows = [
            {
                "message_id": "msg-noise",
                "turn_id": "turn-noise",
                "source_line": 10,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "<skill><name>aippocampus</name> AIppocampus CodexHome global project</skill>",
            },
            {
                "message_id": "msg-real",
                "turn_id": "turn-real",
                "source_line": 20,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 2,
                "is_final": True,
                "text": "AIppocampus 生成产物默认写到 CodexHome global store，project-local 只是兼容模式。",
            },
        ]
        messages.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
        entry = {
            "paths": {
                "clean_source_messages_jsonl": str(messages),
            }
        }

        score, hits = registry.deep_search_entry(entry, ["AIppocampus", "CodexHome", "global", "project"], max_hits=2)

        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["message_id"], "msg-real")
        self.assertTrue(hits[1]["search_noise"])
        self.assertLess(hits[1]["rank_score"], hits[0]["rank_score"])


if __name__ == "__main__":
    unittest.main()
