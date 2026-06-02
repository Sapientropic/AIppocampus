from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import search_decision_adapter as adapter  # noqa: E402

SOURCE_BACKED_SEARCH_DECISION = {
    "title": "Local search-decision memory adapter",
    "matched_terms": ["search decision", "query expansion", "external search"],
    "query_aliases": [
        "local search-decision adapter",
        "搜索决策适配层",
        "source-backed query expansion",
        "before during after external search",
    ],
    "source_refs": [
        {
            "thread_key": "session:discussion-240",
            "message_id": "msg-search-decision",
            "line": 12,
        }
    ],
    "support_level": "candidate",
    "confidence": 0.86,
}


class SearchDecisionAdapterTests(unittest.TestCase):
    def test_degraded_search_cue_produces_source_backed_query_expansion_packet(self) -> None:
        prompt = "之前那个本地搜索决策适配层，怎么把旧上下文接到新 query 里？"

        decision = adapter.assess_before_search(prompt, [SOURCE_BACKED_SEARCH_DECISION])
        packet = adapter.query_expansion_packet(decision)
        raw = json.dumps(packet, ensure_ascii=False)

        self.assertEqual(decision["phase"], "before_search")
        self.assertEqual(decision["search_decision"], "degraded_cue_into_old_source")
        self.assertEqual(decision["support_level"], "candidate")
        self.assertEqual(packet["phase"], "during_search")
        self.assertEqual(packet["support_level"], "candidate")
        self.assertIn("local search-decision adapter", packet["query_terms"])
        self.assertIn("source-backed query expansion", packet["query_terms"])
        self.assertTrue(packet["source_boundary"]["source_refs_are_ids_only"])
        self.assertTrue(packet["source_boundary"]["expansion_terms_are_navigation_not_facts"])
        self.assertIn("H1_pattern_completion", packet["benchmark_links"])
        self.assertIn("H2_pattern_separation", packet["benchmark_links"])
        self.assertIn("H5_consolidation_handoff", packet["benchmark_links"])
        self.assertNotIn("old source said", raw)

    def test_prompt_that_only_looks_related_abstains_without_query_expansion(self) -> None:
        prompt = "帮我查一下 Chrome MV3 optional host permissions 的最新官方规则"
        browser_local_candidate = {
            "title": "Browser-local capture consent boundary",
            "matched_terms": ["browser", "local", "permission"],
            "query_aliases": ["browser-local memory search", "visible export boundary"],
            "source_refs": [{"thread_key": "session:browser-mvp", "message_id": "m-browser"}],
            "support_level": "candidate",
            "confidence": 0.72,
        }

        decision = adapter.assess_before_search(prompt, [browser_local_candidate])
        packet = adapter.query_expansion_packet(decision)

        self.assertEqual(decision["search_decision"], "new_query")
        self.assertEqual(decision["support_level"], "skip")
        self.assertEqual(decision["route_reason"], "insufficient_source_backed_overlap")
        self.assertEqual(packet["query_terms"], [])
        self.assertTrue(packet["source_boundary"]["abstained_instead_of_personalizing_search"])

    def test_after_search_classifies_result_without_making_it_long_term_truth(self) -> None:
        decision = adapter.assess_before_search(
            "搜索决策 adapter 跟外部搜索结果怎么回流？",
            [SOURCE_BACKED_SEARCH_DECISION],
        )

        result = adapter.classify_after_search(
            {
                "title": "New external search result",
                "relationship_hint": "correction",
                "source_url": "https://example.invalid/search-decision-update",
            },
            decision,
        )

        self.assertEqual(result["phase"], "after_search")
        self.assertEqual(result["classification"], "correction")
        self.assertFalse(result["long_term_truth_by_default"])
        self.assertEqual(result["next_memory_action"], "requires_explicit_import_or_review")
        self.assertTrue(result["source_boundary"]["external_result_is_not_memory_truth"])
        self.assertTrue(result["source_boundary"]["browser_or_search_trail_stays_private_by_default"])

    def test_cli_contract_outputs_before_during_after_envelope(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = adapter.main(
                [
                    "--prompt",
                    "之前那个本地搜索决策适配层怎么搜？",
                    "--candidates-json",
                    json.dumps([SOURCE_BACKED_SEARCH_DECISION]),
                    "--result-json",
                    json.dumps({"relationship_hint": "extension"}),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_search_decision_adapter")
        self.assertEqual(payload["before_search"]["phase"], "before_search")
        self.assertEqual(payload["during_search"]["phase"], "during_search")
        self.assertEqual(payload["after_search"]["phase"], "after_search")
        self.assertTrue(payload["source_boundary"]["local_first"])


if __name__ == "__main__":
    unittest.main()
