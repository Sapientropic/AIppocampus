from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import registry_search  # noqa: E402


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

    def _retrieval_module(self, captured: dict) -> types.ModuleType:
        module = types.ModuleType("retrieval")

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

        module.match_anchors = match_anchors
        module.expanded_terms_from_anchors = expanded_terms_from_anchors
        module.search_hybrid_index = search_hybrid_index
        return module

    def test_default_registry_search_budget_stays_bounded(self) -> None:
        captured: dict = {}

        with patch.dict(sys.modules, {"retrieval": self._retrieval_module(captured)}):
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

        with patch.dict(sys.modules, {"retrieval": self._retrieval_module(captured)}):
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


if __name__ == "__main__":
    unittest.main()
