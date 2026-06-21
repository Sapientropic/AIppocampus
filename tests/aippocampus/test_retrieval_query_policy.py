from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import index_builder
from aippocampus_runtime.recall import query_policy as policy
from aippocampus_runtime.recall.query_expansion import (
    load_source_factual_alias_rows_diagnostics,
    plan_query_expansion,
)
from aippocampus_runtime.recall.retrieval import (
    extract_rag_terms,
    search_hybrid_index,
)


def _message(*, line: int, text: str) -> dict:
    return {
        "line": line,
        "timestamp": "",
        "role": "user",
        "kind": "message",
        "phase": "",
        "turn_index": line,
        "is_final": False,
        "sha1": f"sha-{line}",
        "text": text,
    }

class RetrievalQueryPolicyTests(unittest.TestCase):
    def test_semantic_trigger_terms_extract_multilingual_aliases_without_static_aliases(self) -> None:
        rows = [
            {
                "source": "semantic_cue_cache",
                "title": "External memory continuation",
                "aliases": ["memoria externa", "внешний гиппокамп", "ذاكرة سياقية"],
                "matched_terms": ["memoria externa"],
            },
            {
                "source": "semantic_triggers",
                "title": "Local path should be ignored",
                "aliases": [r"E:\\FAKE_TEST_LOCAL_PATH\\secret\\memory", "external hippocampus"],
            },
        ]

        terms = policy.semantic_trigger_terms(rows)

        self.assertIn("memoria externa", terms)
        self.assertIn("внешний гиппокамп", terms)
        self.assertIn("ذاكرة سياقية", terms)
        self.assertIn("external hippocampus", terms)
        self.assertNotIn(r"E:\\FAKE_TEST_LOCAL_PATH\\secret\\memory", terms)

    def test_domain_semantic_aliases_are_not_kept_in_static_alias_table(self) -> None:
        all_static_aliases = {
            str(alias).casefold()
            for aliases in policy.ALIASES.values()
            for alias in aliases
        }

        self.assertNotIn("external hippocampus", all_static_aliases)
        self.assertNotIn("active recall", all_static_aliases)
        self.assertIn(
            "external hippocampus",
            policy.semantic_trigger_terms(
                [
                    {
                        "source": "semantic_triggers",
                        "title": "External hippocampus recall continuity",
                        "aliases": ["external hippocampus", "active recall"],
                    }
                ]
            ),
        )

    def test_cjk_query_sidecar_terms_expand_compact_cues_without_generic_deictics(self) -> None:
        terms = policy.cjk_query_sidecar_terms("上次那个复开源头路线有界证据")

        self.assertIn("复开源头路线有界证据", terms)
        self.assertIn("源头路线", terms)
        self.assertIn("证据", terms)
        self.assertNotIn("上次", terms)
        self.assertNotIn("那个", terms)
        self.assertEqual(policy.cjk_query_sidecar_terms("之前 那个 记忆"), [])

    def test_cjk_retrieval_and_query_terms_share_extension_ranges(self) -> None:
        samples = [
            "项目㐀名支付接口",
            "项目𠀀名数据库迁移",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                rag_terms = extract_rag_terms(sample)
                query_terms = policy.cjk_query_sidecar_terms(sample)

                self.assertIn(sample, rag_terms)
                self.assertIn(sample, query_terms)
                self.assertTrue(any("支付接口" in term or "数据库迁移" in term for term in query_terms))

    def test_source_backed_alias_expansion_reaches_candidate_before_topk_truncation(self) -> None:
        alias_rows = [
            {
                "kind": "aippocampus_source_factual_alias",
                "row_id": "sfa_keepsake",
                "query_aliases": ["keepsake", "souvenir"],
                "route_terms": ["jade memento", "desk drawer"],
                "source_refs": [{"message_id": "msg-2", "line": 20}],
                "source_generation_digest": "gen-public-fixture",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            index_builder.make_sqlite(
                sqlite_path,
                [
                    _message(line=1, text="Unrelated release checklist and broad project notes."),
                    _message(line=2, text="The jade memento lives in the desk drawer."),
                ],
                [],
                [],
                rag_cache=False,
            )

            baseline = search_hybrid_index(
                sqlite_path,
                ["keepsake"],
                [],
                [],
                limit=1,
                candidate_limit=1,
                use_rag_chunks=False,
            )
            plan = plan_query_expansion(["keepsake"], source_alias_rows=alias_rows)
            expanded = search_hybrid_index(
                sqlite_path,
                ["keepsake"],
                plan["expanded_terms"],
                [],
                limit=1,
                candidate_limit=1,
                use_rag_chunks=False,
            )

        self.assertEqual(baseline, [])
        self.assertEqual(expanded[0]["id"], 2)
        self.assertIn("jade memento", plan["expanded_terms"])
        self.assertEqual(plan["diagnostics"]["expansion_sources"]["source_factual_alias"], 1)
        self.assertEqual(plan["diagnostics"]["boundary"], "navigation_only_source_reopen_required")
        self.assertNotIn("desk drawer", json.dumps(plan["diagnostics"], ensure_ascii=False))

    def test_source_factual_alias_loader_diagnostics_reports_jsonl_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-factual-aliases.jsonl"
            path.write_text(
                "{bad-json}\n"
                + json.dumps(
                    {
                        "kind": "aippocampus_source_factual_alias",
                        "row_id": "sfa_valid",
                        "query_aliases": ["keepsake"],
                        "route_terms": ["shelf"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            diagnostics = load_source_factual_alias_rows_diagnostics(path)

        self.assertEqual(diagnostics["row_count"], 1)
        self.assertEqual(diagnostics["jsonl_loss"]["invalid_json_line_count"], 1)

if __name__ == "__main__":
    unittest.main()
