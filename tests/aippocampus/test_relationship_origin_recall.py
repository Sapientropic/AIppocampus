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
from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload
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
        original_20260524_clean = self.cwd / "original-20260524" / "clean-source"
        origin_reflection_clean = self.cwd / "origin-reflection" / "clean-source"
        registry_source_clean = self.cwd / "registry-source-technical" / "clean-source"
        semantic_source_clean = self.cwd / "semantic-source" / "clean-source"
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
            original_20260524_clean,
            [
                {
                    "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
                    "message_id": "msg_b2dfe27431403cdc8ffa",
                    "turn_id": "turn_original_mechanical",
                    "turn_index": 1,
                    "source_id": "src_original_mechanical",
                    "source_line": 88,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["relationship_continuity", "life_context"],
                    "text": (
                        "Test anchor for original 2026-05-24 source chain: "
                        "机械飞升, 机仆, 机械种族, 未来机械生命."
                    ),
                },
                {
                    "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
                    "message_id": "msg_c1d289e0359648aa0194",
                    "turn_id": "turn_original_external_hippocampus",
                    "turn_index": 2,
                    "source_id": "src_original_external_hippocampus",
                    "source_line": 455,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["relationship_continuity", "life_context"],
                    "text": (
                        "Test anchor for original external hippocampus design: "
                        "thread-memory-index, 外置海马体, 外置小海马体, 可以回去."
                    ),
                },
            ],
        )
        self._write_clean_thread(
            origin_reflection_clean,
            [
                {
                    "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
                    "message_id": "msg_770bba9190f4ab7b1281",
                    "turn_id": "turn_origin_reflection",
                    "turn_index": 64,
                    "source_id": "src_origin_reflection",
                    "source_line": 6494,
                    "role": "user",
                    "phase": "",
                    "is_final": False,
                    "scope_labels": ["relationship_continuity", "life_context"],
                    "text": (
                        "Test anchor for origin reflection: 初心, 源头, 关系连续性, "
                        "小海马体."
                    ),
                },
                {
                    "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
                    "message_id": "msg_ea1e9e5ea23db0e8519e",
                    "turn_id": "turn_canonical_doc_handoff",
                    "turn_index": 77,
                    "source_id": "src_canonical_doc_handoff",
                    "source_line": 6726,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["relationship_continuity", "technical_work"],
                    "text": (
                        "Canonical origin essay handoff: README is the entry, "
                        "《未干的地图》 / docs/the-unfinished-map.md is the origin "
                        "essay and source-backed continuity north star, ROADMAP "
                        "is the route, SKILL is the runtime entry."
                    ),
                }
            ],
        )
        self._write_clean_thread(
            registry_source_clean,
            [
                {
                    "thread_key": "session:registry-technical-source",
                    "message_id": "msg_slime_mold",
                    "turn_id": "turn_slime_mold",
                    "turn_index": 3,
                    "source_id": "src_slime_mold",
                    "source_line": 19,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Registry technical source anchor: 黏菌 联想回忆 探索算法.",
                }
            ],
        )
        self._write_clean_thread(
            semantic_source_clean,
            [
                {
                    "thread_key": "session:semantic-source-backed",
                    "message_id": "msg_semantic_source",
                    "turn_id": "turn_semantic_source",
                    "turn_index": 4,
                    "source_id": "src_semantic_source",
                    "source_line": 31,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": (
                        "Source-backed semantic trigger route opens this bounded source window."
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
                            "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
                            "title": "Original 2026-05-24 AIppocampus source chain",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    original_20260524_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
                            "title": "AIppocampus origin reflection",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    origin_reflection_clean / "messages.jsonl"
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
                        {
                            "thread_key": "session:registry-technical-source",
                            "title": "Technical registry source",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    registry_source_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:semantic-source-backed",
                            "title": "Semantic source-backed trigger",
                            "workspace_name": "AIppocampus",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    semantic_source_clean / "messages.jsonl"
                                )
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.registry / "semantic_triggers.jsonl").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_semantic_trigger",
                    "trigger_id": "trigger_source_backed_semantic_bridge",
                    "status": "active",
                    "title": "Source-backed semantic bridge",
                    "aliases": ["桥接语义航标"],
                    "source_refs": [
                        {
                            "thread_key": "session:semantic-source-backed",
                            "message_id": "msg_semantic_source",
                            "line": 31,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
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
        return mcp_tool_result_payload(response["result"])

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

        self.assertIn(
            exact_payload["matches"][0]["message_id"],
            {"msg_origin", "msg_b2dfe27431403cdc8ffa", "msg_c1d289e0359648aa0194"},
        )
        self.assertIn(
            fuzzy_payload["matches"][0]["message_id"],
            {"msg_origin", "msg_b2dfe27431403cdc8ffa", "msg_c1d289e0359648aa0194"},
        )
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
        self.assertEqual(recall["memory_packets"][0]["matched_cue_family"], "relationship_origin")
        self.assertEqual(
            recall["memory_packets"][0]["source_chain_role"],
            "original_external_hippocampus_design",
        )
        self.assertIn(
            "origin_reflection",
            {packet.get("source_chain_role") for packet in recall["memory_packets"]},
        )
        self.assertIn(
            "recap_orientation",
            {packet.get("source_chain_role") for packet in recall["memory_packets"]},
        )
        semantic = recall["recall_context_diagnostics"]["semantic_trigger_diagnostics"]
        self.assertGreaterEqual(semantic["reviewed_seed_trigger_match_count"], 1)
        self.assertTrue(semantic["reviewed_seed_triggers_are_query_scent_only"])
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
        self.assertEqual(
            deepen["result"]["source_refs"][0]["thread_key"],
            "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
        )
        self.assertEqual(
            deepen["result"]["source_refs"][0]["message_id"],
            "msg_c1d289e0359648aa0194",
        )
        self.assertIn("thread-memory-index", window_text)
        self.assertIn("外置小海马体", window_text)

    def test_origin_essay_cue_prefers_canonical_doc_handoff_in_cli_and_mcp(self) -> None:
        cue = "未干的地图 origin essay source-backed continuity"
        cli_cache = self.cwd / "cli-origin-essay-last-recall.json"
        cli_recall = self._cli(
            "agent",
            "recall",
            cue,
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--registry-dir",
            str(self.registry),
            "--last-recall-path",
            str(cli_cache),
            "--detail",
            "full",
            "--json",
        )
        self.assertEqual(cli_recall["status"], "ok")
        self.assertEqual(
            cli_recall["memory_packets"][0]["source_chain_role"],
            "canonical_doc",
        )
        self.assertEqual(cli_recall["source_anchor_gate"]["status"], "passed")
        self.assertEqual(
            cli_recall["source_anchor_gate"]["reason"],
            "canonical_origin_doc_source_chain_reopened",
        )
        self.assertGreaterEqual(cli_recall["source_anchor_gate"]["opened_anchor_hits"], 2)

        cli_deepen = self._cli(
            "agent",
            "deepen",
            "--request",
            "1",
            "--recall-selector",
            cli_recall["recall_selector_id"],
            "--last-recall-path",
            str(cli_cache),
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
        self.assertEqual(cli_deepen["status"], "ok")
        self.assertEqual(cli_deepen["source_chain_role"], "canonical_doc")
        self.assertTrue(cli_deepen["target_source_matched"])
        self.assertEqual(
            cli_deepen["result"]["source_refs"][0]["message_id"],
            "msg_ea1e9e5ea23db0e8519e",
        )
        cli_window = json.dumps(cli_deepen["result"]["source_window"], ensure_ascii=False)
        self.assertIn("《未干的地图》", cli_window)
        self.assertIn("origin essay", cli_window)
        self.assertIn("source-backed continuity", cli_window)

        mcp_cache = self.cwd / "mcp-origin-essay-last-recall.json"
        mcp_recall = self._mcp_tool_payload(
            "agent_recall",
            {
                "query": cue,
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "last_recall_path": str(mcp_cache),
                "detail": "full",
            },
        )
        self.assertEqual(mcp_recall["status"], "ok")
        self.assertEqual(
            mcp_recall["memory_packets"][0]["source_chain_role"],
            "canonical_doc",
        )
        self.assertEqual(mcp_recall["source_anchor_gate"]["status"], "passed")

        mcp_deepen = self._mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": mcp_recall["recall_selector_id"],
                "last_recall_path": str(mcp_cache),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "detail": "full",
            },
        )
        self.assertEqual(mcp_deepen["status"], "ok")
        self.assertEqual(mcp_deepen["source_chain_role"], "canonical_doc")
        self.assertTrue(mcp_deepen["target_source_matched"])
        self.assertEqual(
            mcp_deepen["result"]["source_refs"][0]["message_id"],
            "msg_ea1e9e5ea23db0e8519e",
        )

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
        self.assertEqual(recall["memory_packets"][0]["matched_cue_family"], "relationship_origin")
        self.assertEqual(
            recall["memory_packets"][0]["source_chain_role"],
            "original_mechanical_ascension_source",
        )
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
        self.assertEqual(
            deepen["result"]["source_refs"][0]["thread_key"],
            "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
        )
        self.assertEqual(
            deepen["result"]["source_refs"][0]["message_id"],
            "msg_b2dfe27431403cdc8ffa",
        )
        self.assertIn("机械飞升", window_text)
        self.assertIn("机仆", window_text)

    def test_registry_wide_source_hit_becomes_cli_and_mcp_deepen_route(self) -> None:
        cli_cache = self.cwd / "cli-registry-source-last-recall.json"
        cli_recall = self._cli(
            "agent",
            "recall",
            "黏菌 联想回忆 探索算法",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--registry-dir",
            str(self.registry),
            "--last-recall-path",
            str(cli_cache),
            "--detail",
            "full",
            "--json",
        )
        self.assertEqual(cli_recall["status"], "ok")
        self.assertEqual(
            cli_recall["memory_packets"][0]["matched_cue_family"],
            "registry_source_search",
        )
        self.assertEqual(
            cli_recall["foreground_action_card"]["canonical_action"]["action_id"],
            "agent_deepen_selected_route",
        )

        cli_deepen = self._cli(
            "agent",
            "deepen",
            "--request",
            "1",
            "--recall-selector",
            cli_recall["recall_selector_id"],
            "--last-recall-path",
            str(cli_cache),
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
        self.assertEqual(cli_deepen["status"], "ok")
        self.assertEqual(
            cli_deepen["result"]["source_refs"][0]["thread_key"],
            "session:registry-technical-source",
        )
        cli_window = json.dumps(cli_deepen["result"]["source_window"], ensure_ascii=False)
        self.assertIn("黏菌", cli_window)
        self.assertIn("探索算法", cli_window)

        mcp_cache = self.cwd / "mcp-registry-source-last-recall.json"
        mcp_recall = self._mcp_tool_payload(
            "agent_recall",
            {
                "query": "黏菌 联想回忆 探索算法",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "last_recall_path": str(mcp_cache),
                "detail": "full",
            },
        )
        self.assertEqual(mcp_recall["status"], "ok")
        self.assertEqual(
            mcp_recall["memory_packets"][0]["matched_cue_family"],
            "registry_source_search",
        )
        mcp_deepen = self._mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": mcp_recall["recall_selector_id"],
                "last_recall_path": str(mcp_cache),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "detail": "full",
            },
        )
        self.assertEqual(mcp_deepen["status"], "ok")
        self.assertEqual(
            mcp_deepen["result"]["source_refs"][0]["thread_key"],
            "session:registry-technical-source",
        )

    def test_source_backed_semantic_trigger_becomes_deepen_route(self) -> None:
        cache = self.cwd / "semantic-trigger-last-recall.json"
        recall = self._cli(
            "agent",
            "recall",
            "桥接语义航标",
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
        self.assertEqual(
            recall["memory_packets"][0]["matched_cue_family"],
            "semantic_trigger_source",
        )
        semantic = recall["recall_context_diagnostics"]["semantic_trigger_diagnostics"]
        self.assertEqual(semantic["trigger_source_route_count"], 1)
        self.assertIn("桥接语义航标", semantic["matched_trigger_terms"])

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
        self.assertEqual(deepen["status"], "ok")
        self.assertEqual(
            deepen["result"]["source_refs"][0]["thread_key"],
            "session:semantic-source-backed",
        )


if __name__ == "__main__":
    unittest.main()
