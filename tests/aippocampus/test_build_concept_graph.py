from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import concept_graph as graph


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
                            "threads": [
                                {"thread_key": "session:a"},
                                {"thread_key": "session:b"},
                            ],
                        },
                        "Go runtime": {
                            "term": "Go runtime",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["gotd"],
                            "threads": [
                                {"thread_key": "session:a"},
                                {"thread_key": "session:b"},
                            ],
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

    def test_low_diversity_auto_cooccurs_is_parked_before_expansion(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "黏菌": {
                            "term": "黏菌",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 999,
                            "related_terms": ["探索算法"],
                            "threads": [{"thread_key": "session:single"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(self.associations, self.output)
        expansions = graph.expand_concepts(self.output, ["黏菌"], depth=1)

        self.assertEqual(expansions, [])
        self.assertEqual(
            result["quality_gate"]["reason_counts"]["low_source_diversity_auto_co_occurs"],
            1,
        )
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["parked"], 2)

    def test_cross_thread_auto_cooccurs_remains_navigation_expansion(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "黏菌": {
                            "term": "黏菌",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 4,
                            "related_terms": ["探索算法"],
                            "threads": [
                                {"thread_key": "session:a"},
                                {"thread_key": "session:b"},
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(self.associations, self.output)
        expansions = graph.expand_concepts(self.output, ["黏菌"], depth=1)

        self.assertEqual(expansions[0]["term"], "探索算法")
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["staging"], 2)
        self.assertNotIn("low_source_diversity_auto_co_occurs", result["quality_gate"]["reason_counts"])

    def test_query_gate_excludes_legacy_low_diversity_staging_cooccurs(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            src = graph.upsert_concept(
                con,
                "黏菌",
                status="staging",
                lifecycle_reason="legacy_staging",
                hit_count=999,
                thread_count=1,
            )
            dst = graph.upsert_concept(
                con,
                "探索算法",
                status="staging",
                lifecycle_reason="legacy_staging",
                hit_count=999,
                thread_count=1,
            )
            self.assertIsNotNone(src)
            self.assertIsNotNone(dst)
            graph.upsert_edge(
                con,
                str(src),
                str(dst),
                edge_type="co_occurs",
                confidence=1.0,
                status="staging",
                evidence_count=999,
                thread_count=1,
                lifecycle_reason="legacy_ungated_row",
            )
            con.commit()
        finally:
            con.close()

        self.assertEqual(graph.expand_concepts(self.output, ["黏菌"], depth=1), [])

    def test_graph_health_reports_quality_without_source_labels(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "黏菌": {
                            "term": "黏菌",
                            "status": "staging",
                            "confidence": 0.62,
                            "hit_count": 8,
                            "related_terms": ["探索算法"],
                            "threads": [{"thread_key": "session:single"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        graph.build_concept_graph(self.associations, self.output)

        health = graph.concept_graph_health(self.output)
        encoded = json.dumps(health, ensure_ascii=False, sort_keys=True)

        self.assertTrue(health["ok"])
        self.assertEqual(health["recall_useful_claimed"], False)
        self.assertEqual(health["edge_scope_key_distribution"]["global"], 2)
        self.assertIn("co_occurs", health["edge_type_status_counts"])
        self.assertIn("count_semantics", health)
        self.assertIn("statistical_unit_collapse", {item["code"] for item in health["warnings"]})
        self.assertNotIn("黏菌", encoded)
        self.assertNotIn("探索算法", encoded)
        self.assertNotIn(str(self.output), encoded)

    def test_concept_graph_schema_has_quality_indexes(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            edge_indexes = {
                row["name"] if isinstance(row, sqlite3.Row) else row[1]
                for row in con.execute("PRAGMA index_list(concept_edges)").fetchall()
            }
            concept_indexes = {
                row["name"] if isinstance(row, sqlite3.Row) else row[1]
                for row in con.execute("PRAGMA index_list(concepts)").fetchall()
            }
        finally:
            con.close()

        self.assertIn("idx_concept_edges_quality", edge_indexes)
        self.assertIn("idx_concepts_health", concept_indexes)

    def test_graph_rejects_sliding_window_cjk_fragments_from_association_input(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "机械飞升": {
                            "term": "机械飞升",
                            "status": "verified",
                            "confidence": 0.95,
                            "hit_count": 3,
                            "related_terms": ["海马体", "仍按新流程保持手动触发"],
                            "threads": [{"thread_key": "session:real"}],
                        },
                        "仍按新流程保持手动触发": {
                            "term": "仍按新流程保持手动触发",
                            "status": "verified",
                            "confidence": 0.99,
                            "hit_count": 99,
                            "related_terms": ["动触发"],
                            "threads": [{"thread_key": "session:noise"}],
                        },
                        "动触发": {
                            "term": "动触发",
                            "status": "verified",
                            "confidence": 0.99,
                            "hit_count": 99,
                            "related_terms": ["机械飞升"],
                            "threads": [{"thread_key": "session:noise"}],
                        },
                        "海马体": {
                            "term": "海马体",
                            "status": "verified",
                            "confidence": 0.9,
                            "hit_count": 2,
                            "related_terms": ["机械飞升"],
                            "threads": [{"thread_key": "session:real"}],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(self.associations, self.output)
        con = sqlite3.connect(self.output)
        try:
            labels = {row[0] for row in con.execute("SELECT label FROM concepts").fetchall()}
        finally:
            con.close()

        self.assertIn("机械飞升", labels)
        self.assertIn("海马体", labels)
        self.assertNotIn("仍按新流程保持手动触发", labels)
        self.assertNotIn("动触发", labels)
        self.assertGreaterEqual(result["concept_count"], 2)

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

    def test_lifecycle_promotes_repeated_cross_thread_source_backed_edges(self) -> None:
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
                    "confidence": 0.61,
                    "source_refs": [
                        {"thread_key": "session:a", "assistant_line": 10},
                        {"thread_key": "session:b", "assistant_line": 20},
                        {"thread_key": "session:b", "assistant_line": 24},
                    ],
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

        self.assertEqual(result["lifecycle"]["concept_status_counts"]["verified"], 2)
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["verified"], 2)
        self.assertEqual(result["lifecycle"]["promoted_count"], 4)
        self.assertIn("repeated_cross_thread_source_refs", result["lifecycle"]["reason_counts"])
        self.assertEqual(expansions[0]["term"], "Go runtime")
        self.assertEqual(expansions[0]["status"], "verified")
        self.assertTrue(result["source_boundary"]["graph_status_is_not_source_truth"])

    def test_lifecycle_parks_and_retires_noisy_edges_without_expansion(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        raw_private_reason = "private source excerpt should not serialize"
        staging.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "aippocampus_subconscious_edge",
                            "status": "staging",
                            "src": "本地底座",
                            "dst": "过期路线",
                            "edge_type": "related",
                            "confidence": 0.8,
                            "lifecycle_signal": "stale_without_reuse",
                            "source_refs": [{"thread_key": "session:old", "assistant_line": 1}],
                            "why": raw_private_reason,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "aippocampus_subconscious_edge",
                            "status": "staging",
                            "src": "本地底座",
                            "dst": "错误路线",
                            "edge_type": "related",
                            "confidence": 0.8,
                            "lifecycle_signal": "contradicted",
                            "source_refs": [{"thread_key": "session:correction", "assistant_line": 2}],
                            "why": raw_private_reason,
                        },
                        ensure_ascii=False,
                    ),
                ]
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
        encoded_result = json.dumps(result, ensure_ascii=False, sort_keys=True)

        self.assertEqual(expansions, [])
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["parked"], 2)
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["retired"], 2)
        self.assertEqual(result["lifecycle"]["suppressed_edge_count"], 4)
        self.assertIn("stale_without_reuse", result["lifecycle"]["reason_counts"])
        self.assertIn("contradicted_or_superseded", result["lifecycle"]["reason_counts"])
        self.assertNotIn(raw_private_reason, encoded_result)
        self.assertEqual(
            result["lifecycle"]["suppressed_reasons"]["related"]["parked"][
                "stale_without_reuse"
            ],
            2,
        )
        self.assertEqual(
            result["lifecycle"]["suppressed_reasons"]["related"]["retired"][
                "contradicted_or_superseded"
            ],
            2,
        )

    def test_lifecycle_does_not_promote_from_high_confidence_alone(self) -> None:
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
                    "dst": "gotd adapter",
                    "edge_type": "related",
                    "confidence": 0.99,
                    "source_refs": [{"thread_key": "session:single", "assistant_line": 1}],
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

        self.assertEqual(result["lifecycle"]["concept_status_counts"]["staging"], 2)
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["staging"], 2)
        self.assertEqual(result["lifecycle"]["promoted_count"], 0)
        self.assertEqual(expansions[0]["term"], "gotd adapter")
        self.assertEqual(expansions[0]["status"], "staging")

    def test_lifecycle_does_not_promote_verified_input_without_source_pattern(self) -> None:
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
                    "status": "verified",
                    "src": "本地底座",
                    "dst": "gotd adapter",
                    "edge_type": "related",
                    "confidence": 0.99,
                    "source_refs": [{"thread_key": "session:single", "assistant_line": 1}],
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

        self.assertEqual(result["lifecycle"]["promoted_count"], 0)
        self.assertEqual(expansions[0]["status"], "staging")

    def test_lifecycle_does_not_promote_duplicate_copies_of_same_source_ref(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        repeated_same_ref = {"thread_key": "session:single", "assistant_line": 1}
        staging = self.root / "subconscious_edges.jsonl"
        staging.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "本地底座",
                    "dst": "gotd adapter",
                    "edge_type": "related",
                    "confidence": 0.8,
                    "source_refs": [repeated_same_ref, repeated_same_ref, repeated_same_ref],
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

        self.assertEqual(result["lifecycle"]["promoted_count"], 0)
        self.assertEqual(expansions[0]["status"], "staging")
        self.assertEqual(result["lifecycle"]["oldest_staging_rows"][0]["evidence_count"], 1)

    def test_lifecycle_negative_signal_suppresses_matching_active_association_edge(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 2,
                            "related_terms": ["Go runtime"],
                            "threads": [{"thread_key": "session:assoc"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        staging.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "contradicted",
                    "src": "本地底座",
                    "dst": "Go runtime",
                    "edge_type": "co_occurs",
                    "confidence": 0.8,
                    "source_refs": [{"thread_key": "session:correction", "assistant_line": 1}],
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

        self.assertEqual(expansions, [])
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["retired"], 2)
        self.assertIn("contradicted_or_superseded", result["lifecycle"]["reason_counts"])

    def test_lifecycle_parks_low_confidence_source_backed_rows_for_diagnostics(self) -> None:
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
                    "dst": "低效路线",
                    "edge_type": "related",
                    "confidence": 0.33,
                    "source_refs": [{"thread_key": "session:weak", "assistant_line": 1}],
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

        self.assertEqual(expansions, [])
        self.assertEqual(result["lifecycle"]["concept_status_counts"]["parked"], 2)
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["parked"], 2)
        self.assertEqual(result["lifecycle"]["suppressed_edge_count"], 2)
        self.assertIn("low_confidence", result["lifecycle"]["reason_counts"])

    def test_lifecycle_suppressed_seed_concept_cannot_expand_even_with_active_edge(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            seed_id = graph.upsert_concept(
                con,
                "本地底座",
                status="parked",
                lifecycle_reason="low_utility",
                hit_count=1,
                thread_count=1,
            )
            dst_id = graph.upsert_concept(
                con,
                "Go runtime",
                status="staging",
                lifecycle_reason="staging_source_backed",
                hit_count=1,
                thread_count=1,
            )
            self.assertIsNotNone(seed_id)
            self.assertIsNotNone(dst_id)
            graph.upsert_edge(
                con,
                str(seed_id),
                str(dst_id),
                edge_type="related",
                confidence=0.9,
                status="staging",
                evidence_count=1,
                lifecycle_reason="staging_source_backed",
                thread_count=1,
            )
            con.commit()
        finally:
            con.close()

        self.assertEqual(graph.expand_concepts(self.output, ["本地底座"], depth=1), [])

    def test_lifecycle_diagnostics_do_not_emit_raw_staging_labels(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        raw_private_label = "private source excerpt should not serialize"
        staging = self.root / "subconscious_edges.jsonl"
        staging.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "本地底座",
                    "dst": raw_private_label,
                    "edge_type": raw_private_label,
                    "confidence": 0.8,
                    "source_refs": [{"thread_key": "session:single", "assistant_line": 1}],
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
        encoded_result = json.dumps(result, ensure_ascii=False, sort_keys=True)

        self.assertNotIn(raw_private_label, encoded_result)
        self.assertIn("label_hash", result["lifecycle"]["oldest_staging_rows"][0])

if __name__ == "__main__":
    unittest.main()
