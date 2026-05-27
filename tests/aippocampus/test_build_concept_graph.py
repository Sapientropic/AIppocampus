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

import build_concept_graph as graph  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
