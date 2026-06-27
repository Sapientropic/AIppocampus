from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.recall import retrieval as retrieval_impl
from aippocampus_runtime.registry import search as registry_search
from aippocampus_runtime.source import registry_search as source_registry_search


class RegistrySearchBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sqlite = self.root / "index.sqlite"
        self.sqlite.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _entry(self) -> dict:
        return {"paths": {"sqlite": str(self.sqlite)}}

    def _retrieval_replacements(self, captured: dict) -> dict:
        def match_anchors(anchors_path: Path | None, terms: list[str], limit: int) -> list[dict]:
            captured["anchor_limit"] = limit
            return []

        def expanded_terms_from_anchors(
            terms: list[str], anchors: list[dict], limit: int
        ) -> list[str]:
            captured["expanded_limit"] = limit
            return list(terms)

        def search_hybrid_index(
            index: Path,
            terms: list[str],
            expanded: list[str],
            anchors: list[dict],
            *,
            limit: int,
            candidate_limit: int,
            snippet_chars: int,
            context_radius: int,
        ) -> list[dict]:
            captured["search_kwargs"] = {
                "index": index,
                "terms": terms,
                "expanded": expanded,
                "anchors": anchors,
                "limit": limit,
                "candidate_limit": candidate_limit,
                "snippet_chars": snippet_chars,
                "context_radius": context_radius,
            }
            return [
                {
                    "line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 7,
                    "is_final": True,
                    "score": 11.0,
                    "snippet": "needle hit",
                }
            ]

        return {
            "match_anchors": match_anchors,
            "expanded_terms_from_anchors": expanded_terms_from_anchors,
            "search_hybrid_index": search_hybrid_index,
        }

    def test_default_registry_search_budget_stays_bounded(self) -> None:
        captured: dict = {}

        with patch.multiple(retrieval_impl, **self._retrieval_replacements(captured)):
            result = registry_search.deep_search_entry_result(
                self._entry(), ["needle"], max_hits=2
            )

        self.assertEqual(result["hits"][0]["snippet"], "needle hit")
        self.assertEqual(
            captured["search_kwargs"]["candidate_limit"],
            registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.candidate_limit,
        )
        self.assertEqual(
            captured["search_kwargs"]["snippet_chars"],
            registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.snippet_chars,
        )
        self.assertEqual(
            captured["search_kwargs"]["context_radius"],
            registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.context_radius,
        )
        self.assertEqual(registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.candidate_limit, 80)
        self.assertEqual(registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.snippet_chars, 260)
        self.assertEqual(registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET.context_radius, 0)

    def test_deep_registry_search_budget_can_request_more_context(self) -> None:
        captured: dict = {}

        with patch.multiple(retrieval_impl, **self._retrieval_replacements(captured)):
            registry_search.deep_search_entry_result(
                self._entry(),
                ["needle"],
                max_hits=2,
                search_budget=registry_search.REGISTRY_SEARCH_DEEP_BUDGET,
            )

        default = registry_search.REGISTRY_SEARCH_DEFAULT_BUDGET
        kwargs = captured["search_kwargs"]
        self.assertGreater(kwargs["candidate_limit"], default.candidate_limit)
        self.assertGreater(kwargs["snippet_chars"], default.snippet_chars)
        self.assertGreater(kwargs["context_radius"], default.context_radius)
        self.assertEqual(
            kwargs["candidate_limit"],
            registry_search.REGISTRY_SEARCH_DEEP_BUDGET.candidate_limit,
        )
        self.assertEqual(
            kwargs["snippet_chars"],
            registry_search.REGISTRY_SEARCH_DEEP_BUDGET.snippet_chars,
        )
        self.assertEqual(
            kwargs["context_radius"],
            registry_search.REGISTRY_SEARCH_DEEP_BUDGET.context_radius,
        )

    def test_deep_registry_search_demotes_process_notification_hits(self) -> None:
        clean_dir = self.root / "clean"
        clean_dir.mkdir()
        messages = clean_dir / "messages.jsonl"
        rows = [
            {
                "message_id": "msg_process",
                "source_line": 3,
                "role": "user",
                "text": "<subagent_notification> registry search source route wrapper echo",
            },
            {
                "message_id": "msg_real",
                "source_line": 4,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "registry search source route should prefer this final source-bearing note",
            },
        ]
        messages.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
            encoding="utf-8",
        )
        result = registry_search.deep_search_entry_result(
            {"paths": {"clean_source_messages_jsonl": str(messages)}},
            ["registry", "search", "source", "route"],
            max_hits=2,
        )

        self.assertEqual(result["hits"][0]["message_id"], "msg_real")
        self.assertTrue(result["hits"][1]["search_noise"])
        self.assertEqual(result["hits"][1]["noise_reason"], "process_notification")


class RegistrySourceSearchUsefulnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clean = self.root / "clean"
        self.clean.mkdir()
        self.messages = self.clean / "messages.jsonl"
        self.messages.write_text("", encoding="utf-8")
        (self.root / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:test",
                            "title": "continuity route",
                            "paths": {"clean_source_messages_jsonl": str(self.messages)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_useful_target_hit_requires_top_hit_query_anchor(self) -> None:
        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del entry, terms, max_hits, search_budget, deadline
            return {
                "hits": [
                    {
                        "message_id": "msg_nearby",
                        "line": 12,
                        "role": "assistant",
                        "phase": "final_answer",
                        "is_final": True,
                        "score": 10.0,
                        "snippet": "这是一条附近讨论，但没有用户正在找的罕见锚点。",
                    }
                ]
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["机械飞升 基因飞升"],
                registry_dir=self.root,
                cwd=self.root,
            )

        self.assertFalse(result["useful_target_hit"])
        self.assertEqual(result["status"], "matches_need_broadened_source_search")
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["suppressed_low_coverage_match_count"], 1)
        self.assertNotIn("first_match_usefulness", result)
        self.assertEqual(result["claim_boundary"], "search_miss_is_not_absence_of_memory")
        self.assertEqual(result["source_reopen_boundary"], "search_miss_is_not_absence_of_memory")
        self.assertEqual(result["suppression_boundary"], "low_coverage_matches_suppressed")
        self.assertEqual(
            result["foreground_action"]["id"],
            "broaden_registry_search_for_query_anchors",
        )
        self.assertNotEqual(
            result["foreground_action"]["id"],
            "open_registry_search_source_window",
        )

    def test_exact_session_identifier_does_not_promote_fuzzy_session_hits(self) -> None:
        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del entry, terms, max_hits, search_budget, deadline
            return {
                "hits": [
                    {
                        "message_id": "msg_session_decoy",
                        "line": 7,
                        "role": "assistant",
                        "phase": "final_answer",
                        "is_final": True,
                        "score": 50.0,
                        "snippet": "Generic session setup notes with no requested source identifier.",
                    }
                ]
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["session:00000000-0000-0000-0000-000000000000"],
                registry_dir=self.root,
                cwd=self.root,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["useful_target_hit"])
        self.assertEqual(result["status"], "identifier_not_found")
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["suppressed_low_coverage_match_count"], 1)
        self.assertNotEqual(
            result["foreground_action"]["id"],
            "open_registry_search_source_window",
        )

    def test_short_multi_anchor_partial_hits_are_suppressed_before_open(self) -> None:
        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del entry, terms, max_hits, search_budget, deadline
            return {
                "hits": [
                    {
                        "source": "sqlite",
                        "line": 135501,
                        "role": "assistant",
                        "phase": "commentary",
                        "score": 200.0,
                        "snippet": "开发者真实水平 这条只是搜索排名诊断，不含另一个锚点。",
                    }
                ]
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["开发者真实水平 小号"],
                registry_dir=self.root,
                cwd=self.root,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["useful_target_hit"])
        self.assertEqual(result["status"], "matches_need_broadened_source_search")
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["suppressed_low_coverage_match_count"], 1)
        self.assertEqual(
            result["foreground_action"]["id"],
            "broaden_registry_search_for_query_anchors",
        )
        self.assertEqual(result["claim_boundary"], "search_miss_is_not_absence_of_memory")
        self.assertEqual(result["source_reopen_boundary"], "search_miss_is_not_absence_of_memory")
        self.assertEqual(result["suppression_boundary"], "low_coverage_matches_suppressed")

    def test_sqlite_line_only_hit_does_not_emit_source_open_action(self) -> None:
        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del entry, terms, max_hits, search_budget, deadline
            return {
                "hits": [
                    {
                        "source": "sqlite",
                        "line": 135501,
                        "role": "assistant",
                        "phase": "commentary",
                        "score": 200.0,
                        "snippet": "开发者真实水平 和 小号 都在旧索引里，但没有 clean-source message id。",
                    }
                ]
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["开发者真实水平 小号"],
                registry_dir=self.root,
                cwd=self.root,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["useful_target_hit"])
        self.assertEqual(result["status"], "matches_need_broadened_source_search")
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(
            result["first_match_usefulness"]["status"],
            "source_route_not_reopenable",
        )
        self.assertNotIn("reopen_command", result["matches"][0])
        self.assertEqual(
            result["foreground_action"]["id"],
            "broaden_registry_search_for_reopenable_source",
        )
        self.assertEqual(result["claim_boundary"], "search_miss_is_not_absence_of_memory")
        self.assertEqual(result["source_reopen_boundary"], "search_miss_is_not_absence_of_memory")

    def test_partial_sqlite_hit_loses_to_reopenable_exact_clean_source(self) -> None:
        partial_clean = self.root / "partial-clean"
        exact_clean = self.root / "exact-clean"
        partial_clean.mkdir()
        exact_clean.mkdir()
        (partial_clean / "messages.jsonl").write_text("", encoding="utf-8")
        exact_text = "那开发者真实水平你怎么定，像谁的小号吗？"
        (exact_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_exact_user",
                    "message_id": "msg_exact_user",
                    "source_line": 42,
                    "role": "user",
                    "is_final": False,
                    "text": exact_text,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:partial",
                            "title": "partial diagnostic",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    partial_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:exact",
                            "title": "exact source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    exact_clean / "messages.jsonl"
                                )
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del terms, max_hits, search_budget, deadline
            path = str(((entry.get("paths") or {}).get("clean_source_messages_jsonl") or ""))
            if "partial-clean" in path:
                return {
                    "hits": [
                        {
                            "source": "sqlite",
                            "line": 135501,
                            "role": "assistant",
                            "phase": "commentary",
                            "score": 500.0,
                            "snippet": "开发者真实水平 ranking diagnostic only。",
                        }
                    ]
                }
            return {
                "hits": [
                    {
                        "source": "clean_source",
                        "message_id": "msg_exact_user",
                        "line": 42,
                        "role": "user",
                        "score": 1.0,
                        "snippet": exact_text,
                    }
                ]
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["开发者真实水平 小号"],
                registry_dir=self.root,
                cwd=self.root,
                record_last_search=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"][0]["thread"]["thread_key"], "session:exact")
        self.assertEqual(result["foreground_action"]["id"], "open_registry_search_source_window")

        reopened = source_registry_search.open_registry_source_window(
            registry_dir=self.root,
            hit_index=1,
            use_last_search=True,
        )
        opened = json.dumps(reopened["source_window"], ensure_ascii=False)

        self.assertTrue(reopened["ok"])
        self.assertEqual(reopened["source_boundary"]["authority"], "source_open")
        self.assertIn("开发者真实水平", opened)
        self.assertIn("小号", opened)

    def test_foreground_search_budget_returns_partial_with_precise_reopen(self) -> None:
        exact_clean = self.root / "exact-clean"
        slow_clean = self.root / "slow-clean"
        unsearched_clean = self.root / "unsearched-clean"
        exact_clean.mkdir()
        slow_clean.mkdir()
        unsearched_clean.mkdir()
        exact_text = "scarlet walnut source anchor survives bounded registry search"
        (exact_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_exact",
                    "message_id": "msg_exact",
                    "source_line": 17,
                    "role": "user",
                    "text": exact_text,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (slow_clean / "messages.jsonl").write_text("", encoding="utf-8")
        (unsearched_clean / "messages.jsonl").write_text("", encoding="utf-8")
        (self.root / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:exact",
                            "title": "exact source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    exact_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:slow",
                            "title": "slow source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    slow_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:unsearched",
                            "title": "unsearched source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    unsearched_clean / "messages.jsonl"
                                )
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_deep_search_entry_result(
            entry: dict,
            terms: list[str],
            *,
            max_hits: int,
            search_budget: object = None,
            deadline: object = None,
        ) -> dict:
            del terms, max_hits, search_budget, deadline
            thread_key = str(entry.get("thread_key") or "")
            if thread_key == "session:exact":
                return {
                    "hits": [
                        {
                            "source": "clean_source",
                            "message_id": "msg_exact",
                            "line": 17,
                            "role": "user",
                            "score": 20.0,
                            "snippet": exact_text,
                        }
                    ]
                }
            return {
                "hits": [],
                "budget_exhausted": True,
                "warnings": [
                    {
                        "stage": "registry_search",
                        "code": "foreground_search_time_budget_exhausted",
                    }
                ],
            }

        with patch.object(
            registry_search,
            "deep_search_entry_result",
            side_effect=fake_deep_search_entry_result,
        ):
            result = source_registry_search.search_registry_sources(
                ["scarlet walnut source anchor"],
                registry_dir=self.root,
                cwd=self.root,
                record_last_search=True,
                max_elapsed_ms=5000,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["degraded_reason"], "foreground_search_time_budget_exhausted")
        self.assertEqual(result["max_elapsed_ms"], 5000)
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertEqual(result["unsearched_entry_count"], 1)
        self.assertEqual(result["claim_boundary"], "source_reopen_required_before_claim")
        self.assertEqual(result["source_reopen_boundary"], "reopen_selected_registry_hit_before_claim")
        self.assertEqual(result["foreground_action"]["id"], "open_registry_search_source_window")
        self.assertIn("--open-source", result["foreground_action"]["command"])
        self.assertIn("--thread-key session:exact", result["foreground_action"]["command"])
        self.assertIn("--message-id msg_exact", result["foreground_action"]["command"])
        self.assertEqual(result["next_precise_reopen_command"], result["foreground_action"]["command"])

        reopened = source_registry_search.open_registry_source_window(
            registry_dir=self.root,
            hit_index=1,
            use_last_search=True,
        )
        self.assertTrue(reopened["ok"])
        self.assertIn("scarlet walnut", json.dumps(reopened["source_window"], ensure_ascii=False))

    def test_deep_search_ranks_exact_hit_after_public_snippet_cutoff_first(self) -> None:
        exact_clean = self.root / "exact-clean"
        partial_clean = self.root / "partial-clean"
        exact_clean.mkdir()
        partial_clean.mkdir()
        exact_phrase = "scarlet walnut cicada"
        long_prefix = "prefix filler " * 18
        long_suffix = " suffix filler" * 18
        (exact_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_exact_late",
                    "message_id": "msg_exact_late",
                    "source_line": 31,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": f"{long_prefix}{exact_phrase}{long_suffix}",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (partial_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_partial_loud",
                    "message_id": "msg_partial_loud",
                    "source_line": 9,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "scarlet scarlet scarlet walnut walnut walnut "
                        "nearby topic text without the requested adjacent phrase"
                    ),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:partial",
                            "title": "partial topic",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    partial_clean / "messages.jsonl"
                                )
                            },
                        },
                        {
                            "thread_key": "session:exact",
                            "title": "exact late source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    exact_clean / "messages.jsonl"
                                )
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = source_registry_search.search_registry_sources(
            [exact_phrase],
            registry_dir=self.root,
            cwd=self.root,
            search_budget="deep",
            record_last_search=True,
            limit=10,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"][0]["message_id"], "msg_exact_late")
        self.assertNotIn("_ranking_haystack", json.dumps(result, ensure_ascii=False))
        diagnostics = result["match_evidence_diagnostics"]
        self.assertEqual(diagnostics["exact_phrase_preserved_by_internal_context_count"], 1)

        reopened = source_registry_search.open_registry_source_window(
            registry_dir=self.root,
            hit_index=1,
            use_last_search=True,
        )

        self.assertTrue(reopened["ok"])
        self.assertIn(
            exact_phrase,
            json.dumps(reopened["source_window"], ensure_ascii=False),
        )

    def test_collapsed_duplicate_source_refs_are_directly_reopenable(self) -> None:
        duplicate_text = "registry duplicate alternate source window phrase"
        threads = []
        for index in range(1, 4):
            clean = self.root / f"duplicate-clean-{index}"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "id": f"msg_duplicate_{index}",
                        "message_id": f"msg_duplicate_{index}",
                        "source_line": 40 + index,
                        "role": "assistant",
                        "phase": "final_answer",
                        "is_final": True,
                        "text": duplicate_text,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:duplicate-{index}",
                    "title": f"Duplicate {index}",
                    "paths": {"clean_source_messages_jsonl": str(clean / "messages.jsonl")},
                }
            )
        (self.root / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
            encoding="utf-8",
        )

        result = source_registry_search.search_registry_sources(
            [duplicate_text],
            registry_dir=self.root,
            cwd=self.root,
            record_last_search=True,
            limit=10,
        )
        duplicate = result["matches"][0]

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(duplicate["source_count"], 3)
        self.assertEqual(
            [ref["source_ref_index"] for ref in duplicate["duplicate_source_refs"]],
            [1, 2, 3],
        )
        self.assertTrue(
            all(ref.get("source_window_command") for ref in duplicate["duplicate_source_refs"])
        )
        self.assertIn(
            "--source-ref-index 2",
            duplicate["duplicate_source_refs"][1]["last_search_reopen_command"],
        )

        representative = source_registry_search.open_registry_source_window(
            registry_dir=self.root,
            hit_index=1,
            use_last_search=True,
        )
        alternate = source_registry_search.open_registry_source_window(
            registry_dir=self.root,
            hit_index=1,
            source_ref_index=2,
            use_last_search=True,
        )

        self.assertTrue(representative["ok"])
        self.assertTrue(alternate["ok"])
        self.assertEqual(representative["source_route"]["thread_key"], "session:duplicate-1")
        self.assertEqual(alternate["source_route"]["thread_key"], "session:duplicate-2")
        self.assertIn(duplicate_text, json.dumps(alternate["source_window"], ensure_ascii=False))
        self.assertNotIn(str(self.root), json.dumps(alternate, ensure_ascii=False))

if __name__ == "__main__":
    unittest.main()
