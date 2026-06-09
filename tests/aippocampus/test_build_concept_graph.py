from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.navigation import concept_graph as graph  # noqa: E402


class ConceptGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.associations = self.root / "associations.json"
        self.output = self.root / "concept_index.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_graph_and_expand_depth_two(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["Go runtime"],
                            "threads": [],
                        },
                        "Go runtime": {
                            "term": "Go runtime",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["gotd"],
                            "threads": [],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(self.associations, self.output)
        expansions = graph.expand_concepts(self.output, ["本地底座"], depth=2)

        self.assertGreaterEqual(result["concept_count"], 3)
        self.assertGreaterEqual(result["edge_count"], 4)
        self.assertEqual(expansions[0]["term"], "Go runtime")
        self.assertIn("gotd", [item["term"] for item in expansions])
        gotd = next(item for item in expansions if item["term"] == "gotd")
        self.assertEqual(gotd["depth"], 2)
        self.assertIn(gotd["score_bucket"], {"very_low", "low", "medium", "high", "very_high"})

    def test_build_graph_ingests_subconscious_staging_edges(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        staging.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "本地底座",
                    "dst": "Go runtime",
                    "edge_type": "same_decision_space",
                    "confidence": 0.92,
                    "source_refs": [{"thread_key": "session:test", "assistant_line": 1202}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["本地底座"], depth=1)

        self.assertEqual(result["subconscious_edge_count"], 2)
        self.assertEqual(expansions[0]["term"], "Go runtime")

    def test_multilingual_concept_kind_inference_is_conservative(self) -> None:
        cases = {
            "AIppocampus": "project",
            "sapientropic/aippocampus": "library",
            "Claude Code CLI": "tool",
            "数据管道": "workflow",
            "部署节奏": "workflow",
            "认证方案": "decision",
            "证据报告": "artifact",
            "未干的地图": "topic",
        }

        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(graph.infer_concept_kind(label), expected)

    def test_reviewed_supplied_kind_overrides_heuristic_with_diagnostics(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "杭州": {
                            "term": "杭州",
                            "status": "verified",
                            "confidence": 0.9,
                            "hit_count": 3,
                            "concept_kind": "place",
                            "concept_kind_status": "reviewed",
                            "related_terms": ["旅行路线"],
                            "threads": [{"thread_key": "session:place"}],
                        },
                        "用户画像": {
                            "term": "用户画像",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 2,
                            "concept_kind": "person",
                            "related_terms": ["杭州"],
                            "threads": [{"thread_key": "session:unreviewed"}],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(self.associations, self.output)
        expansions = graph.expand_concepts(self.output, ["杭州"], depth=1)

        self.assertEqual(result["concept_kind_counts"]["place"], 1)
        self.assertGreaterEqual(result["concept_kind_counts"]["topic"], 1)
        self.assertEqual(result["concept_kind_source_counts"]["supplied_reviewed"], 1)
        self.assertIn("fallback", result["concept_kind_source_counts"])
        self.assertTrue(result["source_boundary"]["concept_kind_is_navigation_only"])
        self.assertTrue(result["source_boundary"]["concept_kind_is_not_evidence"])
        first = expansions[0]
        self.assertEqual(first["term"], "旅行路线")
        self.assertEqual(first["concept_kind"], "workflow")
        self.assertEqual(first["concept_kind_source"], "deterministic")
        self.assertTrue(first["source_boundary"]["concept_kind_is_navigation_only"])

    def test_subconscious_source_backed_kind_hint_can_be_used(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        staging.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "部署节奏",
                    "src_concept_kind": "workflow",
                    "dst": "发布记录",
                    "dst_concept_kind": "artifact",
                    "edge_type": "related",
                    "confidence": 0.91,
                    "source_refs": [{"thread_key": "session:kinds", "assistant_line": 12}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["部署节奏"], depth=1)

        self.assertEqual(result["concept_kind_counts"]["workflow"], 1)
        self.assertEqual(result["concept_kind_counts"]["artifact"], 1)
        self.assertEqual(result["concept_kind_source_counts"]["supplied_source_backed"], 2)
        self.assertEqual(expansions[0]["term"], "发布记录")
        self.assertEqual(expansions[0]["concept_kind"], "artifact")


if __name__ == "__main__":
    unittest.main()
