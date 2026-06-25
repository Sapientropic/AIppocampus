from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import concept_graph as graph
from aippocampus_runtime.navigation import data_quality_guard as navigation_guard


class NavigationDataQualityGuardTests(unittest.TestCase):
    def test_association_quality_report_is_privacy_safe_and_av_bucketed(self) -> None:
        raw_fragment = "仍按新流程保持手动触发"
        associations = {
            "schema_version": 1,
            "terms": {
                raw_fragment: {
                    "term": raw_fragment,
                    "status": "staging",
                    "hit_count": 1,
                    "related_terms": ["动触发"],
                    "threads": [{"thread_key": "session:noise"}],
                    "term_quality": {
                        "left_accessor_variety": 1,
                        "right_accessor_variety": 1,
                        "document_count": 1,
                        "frequency": 1,
                        "score": 0.1,
                    },
                },
                "黏菌": {
                    "term": "黏菌",
                    "status": "verified",
                    "hit_count": 2,
                    "related_terms": ["海马体"],
                    "threads": [{"thread_key": "session:good"}],
                    "term_quality": {
                        "left_accessor_variety": 3,
                        "right_accessor_variety": 4,
                        "document_count": 2,
                        "frequency": 3,
                        "score": 12.0,
                    },
                },
            },
        }

        metrics = navigation_guard.association_quality_metrics(associations)
        encoded = json.dumps(metrics, ensure_ascii=False, sort_keys=True)

        self.assertEqual(metrics["term_count"], 2)
        self.assertGreaterEqual(metrics["low_value_cjk_rejection_count"], 1)
        self.assertIn("0-1", metrics["accessor_variety_buckets"])
        self.assertIn("4+", metrics["accessor_variety_buckets"])
        self.assertNotIn(raw_fragment, encoded)
        self.assertNotIn("黏菌", encoded)

    def test_cli_report_omits_raw_paths_and_labels_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            associations_path = root / "associations.json"
            graph_path = root / "missing.sqlite"
            associations_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "terms": {
                            "动触发": {
                                "term": "动触发",
                                "status": "staging",
                                "hit_count": 1,
                                "related_terms": [],
                                "threads": [{"thread_key": "session:noise"}],
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = navigation_guard.build_report(
                associations_path=associations_path,
                concept_graph_path=graph_path,
            )
            encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["mode"], "advisory")
        self.assertTrue(report["associations_path_present"])
        self.assertFalse(report["concept_graph_path_present"])
        self.assertNotIn(str(associations_path), encoded)
        self.assertNotIn("动触发", encoded)

    def test_graph_hub_collapse_report_is_privacy_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            associations_path = root / "associations.json"
            graph_path = root / "concept_index.sqlite"
            staging_path = root / "subconscious_edges.jsonl"
            associations_path.write_text(
                json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            rows = [
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "AIppocampus",
                    "dst": target,
                    "edge_type": "related",
                    "confidence": 0.92,
                    "source_refs": [
                        {"thread_key": "session:a", "assistant_line": index},
                        {"thread_key": "session:b", "assistant_line": index + 100},
                        {"thread_key": "session:c", "assistant_line": index + 200},
                    ],
                }
                for index, target in enumerate(
                    [
                        "memory report.md",
                        "Codex CLI",
                        "sync workflow",
                        "source boundary",
                        "Sapientropic/AIppocampus",
                        "release plan",
                        "operator dashboard",
                        "JSONL fixture",
                        "MCP compact surface",
                        "deployment pipeline",
                    ],
                    start=1,
                )
            ]
            staging_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            graph.build_concept_graph(
                associations_path,
                graph_path,
                subconscious_edges_path=staging_path,
            )

            report = navigation_guard.build_report(
                associations_path=associations_path,
                concept_graph_path=graph_path,
            )
            encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["advisory_status"], "warning")
        self.assertIn(
            "concept_graph_subconscious_hub_collapse",
            {item["kind"] for item in report["findings"]},
        )
        self.assertEqual(
            report["concept_graph"]["subconscious_hub_quality"]["parked_edge_group_count"],
            4,
        )
        self.assertNotIn("AIppocampus", encoded)
        self.assertNotIn("memory report.md", encoded)


if __name__ == "__main__":
    unittest.main()
