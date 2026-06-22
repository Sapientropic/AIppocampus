from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.source.registry_search import search_registry_sources

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"


class RelationshipOriginRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.registry = self.cwd / "registry"
        self.clean.mkdir(parents=True)
        self.registry.mkdir()
        self._write_clean_thread(
            self.clean,
            [
                {
                    "message_id": "msg_current_decoy",
                    "turn_id": "turn_current_decoy",
                    "turn_index": 1,
                    "source_id": "src_current",
                    "source_line": 3,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Current issue workflow skill PR recall route decoy should not satisfy origin cues.",
                }
            ],
        )
        origin_clean = self.cwd / "origin-thread" / "clean-source"
        generic_clean = self.cwd / "generic-hippocampus" / "clean-source"
        self._write_clean_thread(
            origin_clean,
            [
                {
                    "message_id": "msg_origin",
                    "turn_id": "turn_origin",
                    "turn_index": 8,
                    "source_id": "src_origin",
                    "source_line": 88,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["relationship_continuity", "life_context"],
                    "text": (
                        "2026-05-24 origin route: 机械飞升, 机仆, 机械种族, "
                        "未来机械生命, 外置小海马体, 生命还能变成什么, "
                        "关系连续性 and 可以回去."
                    ),
                }
            ],
        )
        self._write_clean_thread(
            generic_clean,
            [
                {
                    "message_id": "msg_generic",
                    "turn_id": "turn_generic",
                    "turn_index": 4,
                    "source_id": "src_generic",
                    "source_line": 24,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["idea_seed", "technical_work"],
                    "text": (
                        "研究者和工程师以生物海马体为蓝本构建 AI模型；"
                        "AI项目和海马体研究主要关注记忆能力。"
                    ),
                }
            ],
        )
        (self.registry / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:generic-hippocampus",
                            "title": "Generic hippocampus research",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    generic_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:origin-route",
                            "title": "AIppocampus origin route",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    origin_clean / "messages.jsonl"
                                )
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_thread(self, clean_dir: Path, rows: list[dict[str, object]]) -> None:
        clean_dir.mkdir(parents=True, exist_ok=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (clean_dir / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(
                    json.dumps(
                        {
                            "turn_id": row["turn_id"],
                            "turn_index": row["turn_index"],
                            "message_ids": [row["message_id"]],
                            "assistant_phase": row.get("phase") or row.get("role"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def _cli(self, *args: str) -> dict[str, Any]:
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
        proc = subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return json.loads(proc.stdout)

    def _mcp_tool_payload(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": f"call-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def test_registry_origin_cue_demotes_generic_hippocampus_research(self) -> None:
        exact_payload = search_registry_sources(
            ["最早那条机械飞升和海马体的讨论"],
            registry_dir=self.registry,
            cwd=self.cwd,
            limit=5,
        )
        fuzzy_payload = search_registry_sources(
            ["小海马体 agent 持续性 用户关系 可以回去 初心"],
            registry_dir=self.registry,
            cwd=self.cwd,
            limit=5,
        )

        self.assertEqual(exact_payload["matches"][0]["message_id"], "msg_origin")
        self.assertEqual(fuzzy_payload["matches"][0]["message_id"], "msg_origin")
        self.assertNotEqual(exact_payload["matches"][0]["message_id"], "msg_generic")

    def test_cli_agent_recall_origin_route_deepens_source(self) -> None:
        cache = self.cwd / "cli-last-recall.json"
        recall = self._cli(
            "agent",
            "recall",
            "小海马体 agent 持续性 用户关系 可以回去 初心",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--registry-dir",
            str(self.registry),
            "--last-recall-path",
            str(cache),
            "--detail",
            "full",
            "--json",
        )
        self.assertEqual(recall["status"], "ok")
        self.assertEqual(recall["memory_packets"][0]["route_topic"], "relationship_origin")
        self.assertTrue(recall["recall_selector_available"])

        deepen = self._cli(
            "agent",
            "deepen",
            "--request",
            "1",
            "--recall-selector",
            recall["recall_selector_id"],
            "--last-recall-path",
            str(cache),
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--registry-dir",
            str(self.registry),
            "--detail",
            "full",
            "--json",
        )
        window_text = json.dumps(deepen["result"]["source_window"], ensure_ascii=False)
        self.assertEqual(deepen["status"], "ok")
        self.assertIn("msg_origin", window_text)
        self.assertIn("机械飞升", window_text)
        self.assertIn("外置小海马体", window_text)

    def test_mcp_agent_recall_origin_route_deepens_source(self) -> None:
        cache = self.cwd / "mcp-last-recall.json"
        recall = self._mcp_tool_payload(
            "agent_recall",
            {
                "query": "最早那条机械飞升和海马体的讨论",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "last_recall_path": str(cache),
                "detail": "full",
            },
        )
        self.assertEqual(recall["status"], "ok")
        self.assertEqual(recall["memory_packets"][0]["route_topic"], "relationship_origin")
        self.assertTrue(recall["recall_selector_available"])

        deepen = self._mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": recall["recall_selector_id"],
                "last_recall_path": str(cache),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "detail": "full",
            },
        )
        window_text = json.dumps(deepen["result"]["source_window"], ensure_ascii=False)
        self.assertEqual(deepen["status"], "ok")
        self.assertIn("msg_origin", window_text)
        self.assertIn("机械飞升", window_text)
        self.assertIn("外置小海马体", window_text)


if __name__ == "__main__":
    unittest.main()
