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
        ) -> dict:
            del entry, terms, max_hits, search_budget
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
        self.assertEqual(result["first_match_usefulness"]["status"], "query_anchor_missing")
        self.assertEqual(result["source_boundary"]["authority"], "direction_only")

if __name__ == "__main__":
    unittest.main()
