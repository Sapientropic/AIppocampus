from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall.prompt_recall_hot_path import (
    candidate_indexes_from_registry,
    run_hot_path_funnel,
)


def write_index(path: Path, messages: list[tuple[int, str, str]]) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, line INTEGER, timestamp TEXT, role TEXT, kind TEXT, "
            "phase TEXT, turn_index INTEGER, is_final INTEGER, text TEXT)"
        )
        con.executemany(
            "INSERT INTO messages "
            "(id, line, timestamp, role, kind, phase, turn_index, is_final, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    idx,
                    idx * 10,
                    "2026-06-03T00:00:00Z",
                    role,
                    "message",
                    "final_answer" if role == "assistant" else "",
                    idx,
                    1 if role == "assistant" else 0,
                    text,
                )
                for idx, role, text in messages
            ],
        )
        con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(text, tokenize='trigram')")
        con.executemany(
            "INSERT INTO messages_fts (rowid, text) VALUES (?, ?)",
            [(idx, text) for idx, _role, text in messages],
        )
        con.execute(
            "CREATE TABLE rag_chunks ("
            "id INTEGER PRIMARY KEY, start_message_id INTEGER, end_message_id INTEGER, "
            "start_line INTEGER, end_line INTEGER, roles TEXT, anchor_titles TEXT, "
            "summary TEXT, text TEXT, terms_json TEXT)"
        )
        con.execute(
            "INSERT INTO rag_chunks "
            "(id, start_message_id, end_message_id, start_line, end_line, roles, anchor_titles, summary, text, terms_json) "
            "VALUES (1, 1, 2, 10, 20, 'user,assistant', '[]', 'profile summary', "
            "'resume CV LinkedIn profile continuity', '{}')"
        )
        con.execute("CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(text, tokenize='trigram')")
        con.execute(
            "INSERT INTO rag_chunks_fts (rowid, text) VALUES (1, 'resume CV LinkedIn profile continuity')"
        )
        con.commit()
    finally:
        con.close()


class PromptHotPathFunnelTests(unittest.TestCase):
    def test_thread_profile_hit_returns_stage_trace_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "source_index.sqlite"
            write_index(index, [(1, "user", "resume profile"), (2, "assistant", "CV route")])
            result = run_hot_path_funnel(
                prompt="继续",
                query_terms=["继续"],
                candidate_indexes=[
                    {
                        "thread_key": "session:profile",
                        "index_path": index,
                        "source_refs": [{"thread_key": "session:profile", "line": 10}],
                        "thread_profile": {
                            "terms": ["resume", "profile"],
                            "representative_message_ids": [1, 2],
                        },
                    }
                ],
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["stages"][0]["stage"], "thread_profile")
        self.assertEqual(result["stages"][0]["status"], "hit")
        self.assertGreaterEqual(result["stages"][0]["candidate_count"], 1)
        self.assertIn("elapsed_ms", result["stages"][0])

    def test_bounded_trigram_fts_fallback_reuses_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "source_index.sqlite"
            write_index(
                index,
                [
                    (1, "user", "我们之前聊过 Phonics Lab Books 3 4 5 是否算完成"),
                    (2, "assistant", "图片资产完成，但音频和课程闭环还没有完全完成"),
                ],
            )
            result = run_hot_path_funnel(
                prompt="之前说 Books 3/4/5 完成了吗，继续那个",
                query_terms=["Books", "3/4/5", "完成"],
                candidate_indexes=[
                    {
                        "thread_key": "session:phonics",
                        "index_path": index,
                        "source_refs": [{"thread_key": "session:phonics", "line": 10}],
                    }
                ],
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["stages"][0]["stage"], "thread_profile")
        self.assertEqual(result["stages"][0]["status"], "skip")
        fts_stage = next(stage for stage in result["stages"] if stage["stage"] == "bounded_trigram_fts")
        self.assertEqual(fts_stage["stage"], "bounded_trigram_fts")
        self.assertEqual(fts_stage["status"], "hit")
        self.assertGreaterEqual(fts_stage["candidate_count"], 1)
        self.assertEqual(result["candidate_ids"], ["session:phonics"])
        self.assertEqual(result["evidence"], [])

    def test_bounded_trigram_fts_does_not_wake_plain_same_name_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "source_index.sqlite"
            write_index(
                index,
                [
                    (1, "user", "Atlas dashboard layout sprint source context"),
                    (2, "assistant", "Atlas recall gate current-project boundary"),
                ],
            )
            result = run_hot_path_funnel(
                prompt="把 Atlas 这个模块接一下，先别改别的。",
                query_terms=["Atlas", "模块接一下"],
                candidate_indexes=[
                    {
                        "thread_key": "session:atlas",
                        "index_path": index,
                        "source_refs": [{"thread_key": "session:atlas", "line": 10}],
                    }
                ],
            )

        self.assertEqual(result["decision"], "skip")
        fts_stage = next(stage for stage in result["stages"] if stage["stage"] == "bounded_trigram_fts")
        self.assertEqual(fts_stage["status"], "skip")
        self.assertEqual(fts_stage["fallback_reason"], "prompt_lacks_memory_route_intent")

    def test_honest_no_op_skip_when_local_stages_have_no_cue(self) -> None:
        result = run_hot_path_funnel(
            prompt="把按钮 hover 样式调一下",
            query_terms=["按钮", "hover"],
            candidate_indexes=[],
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["stages"][-1]["stage"], "no_op")
        self.assertEqual(result["stages"][-1]["status"], "skip")
        self.assertEqual(result["stages"][-1]["fallback_reason"], "no_local_candidate")

    def test_continue_does_not_hit_arbitrary_registry_profile(self) -> None:
        result = run_hot_path_funnel(
            prompt="继续",
            query_terms=["继续"],
            candidate_indexes=[
                {
                    "thread_key": "session:old-profile",
                    "source_refs": [{"thread_key": "session:old-profile", "line": 10}],
                    "thread_profile": {
                        "terms": ["resume", "profile"],
                    },
                }
            ],
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["stages"][0]["stage"], "thread_profile")
        self.assertEqual(result["stages"][0]["status"], "skip")
        self.assertEqual(result["stages"][-1]["stage"], "no_op")

    def test_stale_cached_cue_is_navigation_only_not_evidence(self) -> None:
        result = run_hot_path_funnel(
            prompt="继续那个 profile 线索",
            query_terms=["profile"],
            candidate_indexes=[
                {
                    "thread_key": "session:stale",
                    "source_refs": [{"thread_key": "session:stale", "line": 30}],
                    "cue_cache": {
                        "query_aliases": ["profile"],
                        "state": "stale",
                    },
                }
            ],
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        living_stage = next(stage for stage in result["stages"] if stage["stage"] == "living_cue_cache")
        cue_stage = next(stage for stage in result["stages"] if stage["stage"] == "cue_cache")
        self.assertEqual(living_stage["status"], "skip")
        self.assertEqual(living_stage["fallback_reason"], "no_living_cue_match")
        self.assertEqual(cue_stage["status"], "hit")
        self.assertEqual(cue_stage["fallback_reason"], "stale_navigation_only")

    def test_query_pattern_routes_hit_before_cue_cache_without_evidence(self) -> None:
        result = run_hot_path_funnel(
            prompt="我们接着上次那个海马体预热走",
            query_terms=["海马体", "预热"],
            candidate_indexes=[],
            query_pattern_routes=[
                {
                    "query_aliases": ["上次那个海马体预热"],
                    "source_generation_digest": "gen-alpha-v2",
                    "thread_key_hash": "thread_alpha_hash",
                    "source_refs": [{"thread_key": "session:qp", "message_id": "msg-qp"}],
                    "created_unix": 1_800_000_000,
                    "ttl_seconds": 600,
                    "confidence": 0.93,
                }
            ],
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidate_ids"], ["session:qp"])
        self.assertEqual(result["candidate_reasons"]["session:qp"], "query_pattern_routes")
        self.assertEqual(result["evidence"], [])
        query_stage = next(stage for stage in result["stages"] if stage["stage"] == "query_pattern_routes")
        cue_stage = next(stage for stage in result["stages"] if stage["stage"] == "cue_cache")
        self.assertEqual(query_stage["status"], "hit")
        self.assertEqual(cue_stage["status"], "skip")
        self.assertEqual(cue_stage["fallback_reason"], "already_hit")
        self.assertEqual(result["query_pattern_routes"]["diagnostics"]["live_llm_call_count"], 0)

    def test_source_factual_alias_artifact_can_wake_basic_fact_route_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alias_path = root / "source-factual-aliases.jsonl"
            alias_path.write_text(
                "{"
                '"thread_key":"session:keepsake",'
                '"source_refs":[{"thread_key":"session:keepsake","message_id":"msg-2","line":20}],'
                '"query_aliases":["keepsake","souvenir","where"],'
                '"route_terms":["drawer","location","jade"]'
                "}\n",
                encoding="utf-8",
            )
            candidates = candidate_indexes_from_registry(
                {
                    "threads": [
                        {
                            "thread_key": "session:keepsake",
                            "paths": {"source_factual_aliases_jsonl": str(alias_path)},
                        }
                    ]
                }
            )
            result = run_hot_path_funnel(
                prompt="Where did I keep the jade keepsake?",
                query_terms=["jade", "keepsake", "where"],
                candidate_indexes=candidates,
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidate_ids"], ["session:keepsake"])
        self.assertEqual(result["candidate_reasons"]["session:keepsake"], "source_factual_aliases")
        self.assertEqual(result["evidence"], [])
        alias_stage = next(stage for stage in result["stages"] if stage["stage"] == "source_factual_aliases")
        self.assertEqual(alias_stage["status"], "hit")
        self.assertEqual(result["candidate_refs"][0]["line"], 20)
        self.assertTrue(result["source_boundary"]["source_reopen_required_for_facts"])

    def test_source_factual_alias_stage_does_not_wake_plain_same_name_work(self) -> None:
        result = run_hot_path_funnel(
            prompt="Rename the jade module and adjust imports.",
            query_terms=["jade", "module", "imports"],
            candidate_indexes=[
                {
                    "thread_key": "session:jade-fact",
                    "source_refs": [{"thread_key": "session:jade-fact", "line": 20}],
                    "source_factual_aliases": [
                        {
                            "query_aliases": ["jade", "keepsake", "where"],
                            "route_terms": ["drawer", "location"],
                            "source_refs": [{"thread_key": "session:jade-fact", "line": 20}],
                        }
                    ],
                }
            ],
        )

        alias_stage = next(stage for stage in result["stages"] if stage["stage"] == "source_factual_aliases")
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(alias_stage["status"], "skip")
        self.assertEqual(alias_stage["fallback_reason"], "prompt_lacks_factual_route_intent")


if __name__ == "__main__":
    unittest.main()
