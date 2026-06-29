from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source.registry_search import search_registry_sources
from aippocampus_runtime.source.relationship_origin import RELATIONSHIP_ORIGIN_ROUTE_TOPIC
from aippocampus_runtime.source.route_topics import (
    route_topic_for_clean_hit,
    route_topic_low_coverage_acceptance,
)
from tests.aippocampus.cli_fixtures import parse_cli_json, run_aippocampus_cli
from tests.aippocampus.product_probe_helpers import (
    SourceOpenExpectation,
    assert_cli_recall_deepens_to_source,
    assert_mcp_recall_deepens_to_source,
    call_mcp_tool_payload,
    write_clean_source_thread,
)


class RelationshipOriginRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.registry = self.cwd / "registry"
        self.clean.mkdir(parents=True)
        self.registry.mkdir()
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        write_clean_source_thread(
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
        recall, _deepen = assert_cli_recall_deepens_to_source(
            self,
            cue="小海马体 agent 持续性 用户关系 可以回去 初心",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            last_recall_path=cache,
            expectation=SourceOpenExpectation(
                recall_matched_cue_family="relationship_origin",
                recall_source_chain_role="original_external_hippocampus_design",
                thread_key="session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
                message_id="msg_c1d289e0359648aa0194",
                window_terms=("thread-memory-index", "外置小海马体"),
            ),
        )
        self.assertIn(
            "origin_reflection",
            {packet.get("source_chain_role") for packet in recall["memory_packets"]},
        )
        self.assertNotIn("msg_generic", json.dumps(recall["memory_packets"], ensure_ascii=False))
        semantic = recall["recall_context_diagnostics"]["semantic_trigger_diagnostics"]
        self.assertGreaterEqual(semantic["reviewed_seed_trigger_match_count"], 1)
        self.assertTrue(semantic["reviewed_seed_triggers_are_query_scent_only"])

    def test_origin_essay_cue_prefers_canonical_doc_handoff_in_cli_and_mcp(self) -> None:
        cue = "未干的地图 origin essay source-backed continuity"
        cli_cache = self.cwd / "cli-origin-essay-last-recall.json"
        expectation = SourceOpenExpectation(
            recall_source_chain_role="canonical_doc",
            deepen_source_chain_role="canonical_doc",
            target_source_matched=True,
            message_id="msg_ea1e9e5ea23db0e8519e",
            window_terms=("《未干的地图》", "origin essay", "source-backed continuity"),
        )
        cli_recall, _cli_deepen = assert_cli_recall_deepens_to_source(
            self,
            cue=cue,
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            last_recall_path=cli_cache,
            expectation=expectation,
        )
        self.assertEqual(cli_recall["source_anchor_gate"]["status"], "passed")
        self.assertEqual(
            cli_recall["source_anchor_gate"]["reason"],
            "canonical_origin_doc_source_chain_reopened",
        )
        self.assertGreaterEqual(cli_recall["source_anchor_gate"]["opened_anchor_hits"], 2)

        mcp_cache = self.cwd / "mcp-origin-essay-last-recall.json"
        mcp_recall, _mcp_deepen = assert_mcp_recall_deepens_to_source(
            self,
            cue=cue,
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            last_recall_path=mcp_cache,
            expectation=expectation,
        )
        self.assertEqual(mcp_recall["source_anchor_gate"]["status"], "passed")

    def test_mcp_agent_recall_origin_route_deepens_source(self) -> None:
        cache = self.cwd / "mcp-last-recall.json"
        assert_mcp_recall_deepens_to_source(
            self,
            cue="最早那条机械飞升和海马体的讨论",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            last_recall_path=cache,
            expectation=SourceOpenExpectation(
                recall_matched_cue_family="relationship_origin",
                recall_source_chain_role="original_mechanical_ascension_source",
                thread_key="session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
                message_id="msg_b2dfe27431403cdc8ffa",
                window_terms=("机械飞升", "机仆"),
            ),
        )

    def test_route_topics_match_non_ascii_origin_cues(self) -> None:
        topic = route_topic_for_clean_hit(
            {
                "role": "user",
                "phase": "decision",
                "snippet": "后来我们把未干的地图、小海马体、机械飞升放在同一条连续性线上。",
                "scope_labels": [],
                "semantic_scope_labels": [],
            },
            intent="生命还能变成什么",
        )

        self.assertEqual(topic["route_topic"], RELATIONSHIP_ORIGIN_ROUTE_TOPIC)
        self.assertEqual(topic["label_granularity"], "topic_label")

    def test_low_coverage_topic_acceptance_requires_shared_origin_topic(self) -> None:
        accepted = route_topic_low_coverage_acceptance(
            {
                "role": "user",
                "phase": "decision",
                "snippet": "我们把未干的地图和机械飞升当成连续性隐喻。",
                "scope_labels": [],
                "semantic_scope_labels": [],
            },
            intent="小海马体 生命还能变成什么",
            query_profile={"accepted": False},
        )
        unrelated = route_topic_low_coverage_acceptance(
            {
                "role": "user",
                "phase": "decision",
                "snippet": "我们把未干的地图和机械飞升当成连续性隐喻。",
                "scope_labels": [],
                "semantic_scope_labels": [],
            },
            intent="project triage milestone roadmap",
            query_profile={"accepted": False},
        )

        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["route_topic"], RELATIONSHIP_ORIGIN_ROUTE_TOPIC)
        self.assertEqual(accepted["acceptance_reason"], "shared_route_topic_label_navigation_only")
        self.assertEqual(unrelated, {})

    def test_registry_wide_source_hit_becomes_cli_and_mcp_search_open_action(self) -> None:
        cli_cache = self.cwd / "cli-registry-source-last-recall.json"
        cue = "黏菌 联想回忆 探索算法"
        cli_recall_proc = run_aippocampus_cli(
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
            "compact",
            "--json",
        )
        cli_recall = parse_cli_json(
            self,
            cli_recall_proc,
            expected_returncode=2,
            label="aippocampus agent recall registry search recovery",
        )
        self.assertEqual(
            cli_recall["foreground_action"]["id"],
            "search_registry_sources_for_original_cue_anchors",
        )
        cli_search_proc = run_aippocampus_cli(
            "search",
            "--all",
            cue,
            "--cwd",
            str(self.cwd),
            "--registry-dir",
            str(self.registry),
            "--json",
        )
        cli_search = parse_cli_json(self, cli_search_proc)
        self.assertEqual(cli_search["foreground_action"]["id"], "open_registry_search_source_window")
        self.assertEqual(
            cli_search["foreground_action"]["arguments"]["thread_key"],
            "session:registry-technical-source",
        )
        cli_open_proc = run_aippocampus_cli(
            "search",
            "--open-source",
            "--thread-key",
            cli_search["foreground_action"]["arguments"]["thread_key"],
            "--message-id",
            cli_search["foreground_action"]["arguments"]["message_id"],
            "--line",
            str(cli_search["foreground_action"]["arguments"]["line"]),
            "--registry-dir",
            str(self.registry),
            "--json",
        )
        cli_open = parse_cli_json(self, cli_open_proc)
        self.assertEqual(cli_open["status"], "ok")
        self.assertIn("黏菌", json.dumps(cli_open["source_window"], ensure_ascii=False))
        self.assertIn("探索算法", json.dumps(cli_open["source_window"], ensure_ascii=False))

        mcp_cache = self.cwd / "mcp-registry-source-last-recall.json"
        mcp_recall = call_mcp_tool_payload(
            "agent_recall",
            {
                "query": cue,
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(self.registry),
                "last_recall_path": str(mcp_cache),
                "detail": "compact",
            },
        )
        self.assertEqual(
            mcp_recall["foreground_action"]["id"],
            "search_registry_sources_for_original_cue_anchors",
        )
        mcp_search = call_mcp_tool_payload(
            "search_memory",
            {
                "cwd": str(self.cwd),
                "registry_dir": str(self.registry),
                **mcp_recall["foreground_action"]["arguments"],
            },
        )
        self.assertEqual(mcp_search["foreground_action"]["id"], "open_registry_search_source_window")
        mcp_open = call_mcp_tool_payload(
            "search_memory",
            {
                "cwd": str(self.cwd),
                "registry_dir": str(self.registry),
                **mcp_search["foreground_action"]["arguments"],
            },
        )
        self.assertEqual(mcp_open["source_scope"], "opened_source_window")
        self.assertIn(
            "黏菌",
            json.dumps(mcp_open["source_window_preview"], ensure_ascii=False),
        )
        self.assertIn(
            "探索算法",
            json.dumps(mcp_open["source_window_preview"], ensure_ascii=False),
        )

    def test_source_backed_semantic_trigger_becomes_deepen_route(self) -> None:
        cache = self.cwd / "semantic-trigger-last-recall.json"
        recall, _deepen = assert_cli_recall_deepens_to_source(
            self,
            cue="桥接语义航标",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            last_recall_path=cache,
            expectation=SourceOpenExpectation(
                recall_matched_cue_family="semantic_trigger_source",
                thread_key="session:semantic-source-backed",
                window_terms=("Source-backed semantic trigger route",),
            ),
        )
        semantic = recall["recall_context_diagnostics"]["semantic_trigger_diagnostics"]
        self.assertEqual(semantic["trigger_source_routes"], 1)
        self.assertIn("桥接语义航标", semantic["matched_trigger_terms"])


if __name__ == "__main__":
    unittest.main()
