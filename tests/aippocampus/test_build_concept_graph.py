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
        self.assertIn("idx_concept_edges_expand", edge_indexes)

    def test_graph_health_quality_buckets_group_by_count_values(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            src_id = graph.upsert_concept(
                con,
                "Source topic",
                status="verified",
                lifecycle_reason="fixture",
                hit_count=12,
                thread_count=8,
            )
            one_id = graph.upsert_concept(
                con,
                "One thread",
                status="verified",
                lifecycle_reason="fixture",
                hit_count=1,
                thread_count=1,
            )
            many_id = graph.upsert_concept(
                con,
                "Many threads",
                status="verified",
                lifecycle_reason="fixture",
                hit_count=9,
                thread_count=8,
            )
            assert src_id and one_id and many_id
            graph.upsert_edge(
                con,
                src_id,
                one_id,
                edge_type="verified_related",
                confidence=0.9,
                status="verified",
                evidence_count=1,
                thread_count=1,
                lifecycle_reason="fixture",
            )
            graph.upsert_edge(
                con,
                src_id,
                many_id,
                edge_type="verified_related",
                confidence=0.9,
                status="verified",
                evidence_count=8,
                thread_count=8,
                lifecycle_reason="fixture",
            )
            con.commit()
        finally:
            con.close()

        health = graph.concept_graph_health(self.output)

        self.assertEqual(health["source_diversity_buckets"]["1"], 1)
        self.assertEqual(health["source_diversity_buckets"]["8+"], 1)
        self.assertEqual(health["evidence_count_buckets"]["1"], 1)
        self.assertEqual(health["evidence_count_buckets"]["8+"], 1)

    def test_build_aggregates_repeated_concept_upserts_by_unique_label(self) -> None:
        related_terms = [f"Route shard {idx:02d}" for idx in range(30)]
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.92,
                            "hit_count": 100,
                            "related_terms": related_terms,
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

        result = graph.build_concept_graph(self.associations, self.output, max_related_per_term=30)
        diagnostics = result["build_diagnostics"]

        self.assertEqual(result["build_mode"], "full_rebuild")
        self.assertEqual(diagnostics["edge_upsert_attempts"], 60)
        self.assertGreater(diagnostics["concept_resolve_requests"], diagnostics["unique_concept_labels"])
        self.assertLessEqual(
            diagnostics["concept_db_upsert_attempts"],
            diagnostics["unique_concept_labels"],
        )
        self.assertGreaterEqual(diagnostics["concept_cache_hits"], 30)

    def test_build_skips_unchanged_input_manifest_without_resetting_graph(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 4,
                            "related_terms": ["Go runtime"],
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

        first = graph.build_concept_graph(self.associations, self.output)
        second = graph.build_concept_graph(self.associations, self.output)

        self.assertEqual(first["build_mode"], "full_rebuild")
        self.assertEqual(second["build_mode"], "skipped_unchanged_inputs")
        self.assertEqual(second["previous_graph"]["concept_count"], first["concept_count"])
        self.assertEqual(second["previous_graph"]["edge_count"], first["edge_count"])
        self.assertEqual(second["build_diagnostics"]["build_mode"], "skipped_unchanged_inputs")
        self.assertEqual(second["build_diagnostics"]["previous_build_mode"], "full_rebuild")
        self.assertFalse(second["build_diagnostics"]["reset_graph_called"])
        self.assertEqual(second["build_diagnostics"]["concept_db_upsert_attempts"], 0)

        payload = json.loads(self.associations.read_text(encoding="utf-8"))
        payload["terms"]["本地底座"]["related_terms"].append("gotd")
        self.associations.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        rebuilt = graph.build_concept_graph(self.associations, self.output)

        self.assertEqual(rebuilt["build_mode"], "incremental_update")
        self.assertFalse(rebuilt["build_diagnostics"]["reset_graph_called"])
        self.assertEqual(rebuilt["build_diagnostics"]["changed_families"], ["associations"])
        self.assertGreater(rebuilt["build_diagnostics"]["edge_contribution_rows_updated"], 0)
        self.assertGreater(rebuilt["edge_count"], second["edge_count"])

    def test_incremental_association_slice_replaces_stale_related_edges(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 4,
                            "related_terms": ["Go runtime"],
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
        graph.build_concept_graph(self.associations, self.output)
        payload = json.loads(self.associations.read_text(encoding="utf-8"))
        payload["terms"]["本地底座"]["related_terms"] = ["gotd adapter"]
        self.associations.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        result = graph.build_concept_graph(self.associations, self.output)
        expansions = graph.expand_concepts(self.output, ["本地底座"], depth=1)
        con = sqlite3.connect(self.output)
        try:
            labels = {row[0] for row in con.execute("SELECT label FROM concepts").fetchall()}
        finally:
            con.close()

        self.assertEqual(result["build_mode"], "incremental_update")
        self.assertFalse(result["build_diagnostics"]["reset_graph_called"])
        self.assertEqual(result["build_diagnostics"]["changed_families"], ["associations"])
        self.assertGreaterEqual(result["build_diagnostics"]["read_model_edge_keys_deleted"], 2)
        self.assertIn("gotd adapter", [item["term"] for item in expansions])
        self.assertNotIn("Go runtime", [item["term"] for item in expansions])
        self.assertNotIn("Go runtime", labels)

    def test_incremental_timeline_turn_replaces_stale_topic_edges(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        timeline = self.root / "project_timeline.json"
        timeline.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": {
                        "p": {
                            "project_label": "AIppocampus",
                            "project_tags": ["黏菌"],
                            "latest_turns": [
                                {
                                    "thread_key": "session:timeline",
                                    "turn_id": "turn:1",
                                    "topic_terms": ["生命周期", "证据缺口"],
                                    "source_refs": [
                                        {"thread_key": "session:timeline", "source_line": 10}
                                    ],
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        graph.build_concept_graph(
            self.associations,
            self.output,
            project_timeline_path=timeline,
        )
        payload = json.loads(timeline.read_text(encoding="utf-8"))
        payload["projects"]["p"]["latest_turns"][0]["topic_terms"] = [
            "source boundary",
            "registry search",
        ]
        timeline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            project_timeline_path=timeline,
        )
        con = sqlite3.connect(self.output)
        try:
            labels = {row[0] for row in con.execute("SELECT label FROM concepts").fetchall()}
        finally:
            con.close()

        self.assertEqual(result["build_mode"], "incremental_update")
        self.assertFalse(result["build_diagnostics"]["reset_graph_called"])
        self.assertEqual(result["build_diagnostics"]["changed_families"], ["project_timeline"])
        self.assertIn("source boundary", labels)
        self.assertIn("registry search", labels)
        self.assertNotIn("生命周期", labels)
        self.assertNotIn("证据缺口", labels)

    def test_incremental_subconscious_negative_deletion_restores_association_edge(
        self,
    ) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 3,
                            "related_terms": ["Go runtime"],
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
        first = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        self.assertEqual(first["lifecycle"]["edge_status_counts"]["retired"], 2)
        self.assertEqual(graph.expand_concepts(self.output, ["本地底座"], depth=1), [])

        staging.write_text("", encoding="utf-8")
        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["本地底座"], depth=1)

        self.assertEqual(result["build_mode"], "incremental_update")
        self.assertFalse(result["build_diagnostics"]["reset_graph_called"])
        self.assertEqual(result["build_diagnostics"]["changed_families"], ["subconscious_edges"])
        self.assertGreaterEqual(result["build_diagnostics"]["edge_contribution_rows_deleted"], 2)
        self.assertEqual(result["lifecycle"]["edge_status_counts"].get("retired", 0), 0)
        self.assertEqual(expansions[0]["term"], "Go runtime")

    def test_graph_health_reports_build_manifest_without_private_paths(self) -> None:
        self.associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 4,
                            "related_terms": ["Go runtime"],
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
        graph.build_concept_graph(self.associations, self.output)

        health = graph.concept_graph_health(self.output)
        encoded = json.dumps(health, ensure_ascii=False, sort_keys=True)

        self.assertIn("input_manifest", health)
        self.assertIn("build_diagnostics", health)
        self.assertEqual(
            health["build_diagnostics"]["schema_version"],
            "concept_graph_build_diagnostics_v1",
        )
        self.assertNotIn(str(self.associations), encoded)
        self.assertNotIn(str(self.output), encoded)

    def test_hub_neighbor_query_plan_avoids_temp_sort(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            seed_id = graph.upsert_concept(
                con,
                "AIppocampus",
                status="verified",
                lifecycle_reason="fixture_seed",
                hit_count=100,
                thread_count=5,
            )
            self.assertIsNotNone(seed_id)
            for idx in range(300):
                dst_id = graph.upsert_concept(
                    con,
                    f"Specific route {idx:03d}",
                    status="verified",
                    lifecycle_reason="fixture_neighbor",
                    hit_count=idx + 1,
                    thread_count=5,
                )
                self.assertIsNotNone(dst_id)
                graph.upsert_edge(
                    con,
                    str(seed_id),
                    str(dst_id),
                    edge_type="verified_related",
                    confidence=0.95 - (idx * 0.0001),
                    status="verified",
                    evidence_count=idx + 1,
                    thread_count=5,
                    lifecycle_reason="fixture_edge",
                )
            con.commit()
            plan = graph.edge_query_plan(con, str(seed_id), status="verified", max_degree=12)
        finally:
            con.close()

        self.assertTrue(plan["uses_expand_index"], plan["plan"])
        self.assertFalse(plan["uses_temp_btree"], plan["plan"])

    def test_expansion_reports_depth_downgrade_when_neighbor_budget_is_exhausted(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            seed_id = graph.upsert_concept(
                con,
                "本地底座",
                status="verified",
                lifecycle_reason="fixture_seed",
                hit_count=100,
                thread_count=5,
            )
            self.assertIsNotNone(seed_id)
            for idx in range(8):
                mid_id = graph.upsert_concept(
                    con,
                    f"Bridge route {idx}",
                    status="verified",
                    lifecycle_reason="fixture_mid",
                    hit_count=10,
                    thread_count=5,
                )
                leaf_id = graph.upsert_concept(
                    con,
                    f"Leaf route {idx}",
                    status="verified",
                    lifecycle_reason="fixture_leaf",
                    hit_count=10,
                    thread_count=5,
                )
                self.assertIsNotNone(mid_id)
                self.assertIsNotNone(leaf_id)
                graph.upsert_edge(
                    con,
                    str(seed_id),
                    str(mid_id),
                    edge_type="verified_related",
                    confidence=0.95,
                    status="verified",
                    evidence_count=10,
                    thread_count=5,
                    lifecycle_reason="fixture_edge",
                )
                graph.upsert_edge(
                    con,
                    str(mid_id),
                    str(leaf_id),
                    edge_type="verified_related",
                    confidence=0.95,
                    status="verified",
                    evidence_count=10,
                    thread_count=5,
                    lifecycle_reason="fixture_edge",
                )
            con.commit()
        finally:
            con.close()

        rows, diagnostics = graph.expand_concepts_with_diagnostics(
            self.output,
            ["本地底座"],
            depth=2,
            max_degree=8,
            max_neighbor_fetches=1,
        )

        self.assertTrue(rows)
        self.assertEqual(diagnostics["budget_state"], "depth_downgraded")
        self.assertEqual(diagnostics["neighbor_fetches"], 1)
        self.assertLess(diagnostics["depth_used"], diagnostics["depth_requested"])

    def test_expansion_reports_truncated_budget_when_depth_two_is_partial(self) -> None:
        con = graph.connect(self.output)
        try:
            graph.init_schema(con)
            labels = ["seed", "child_a", "child_b", "grand_a", "grand_b"]
            ids = {
                label: graph.upsert_concept(
                    con,
                    label,
                    status="verified",
                    lifecycle_reason="fixture",
                    hit_count=10,
                    thread_count=5,
                )
                for label in labels
            }
            for src, dst in [
                ("seed", "child_a"),
                ("seed", "child_b"),
                ("child_a", "grand_a"),
                ("child_b", "grand_b"),
            ]:
                graph.upsert_edge(
                    con,
                    str(ids[src]),
                    str(ids[dst]),
                    edge_type="verified_related",
                    confidence=1.0,
                    status="verified",
                    evidence_count=5,
                    thread_count=5,
                    lifecycle_reason="fixture",
                )
            con.commit()
        finally:
            con.close()

        rows, diagnostics = graph.expand_concepts_with_diagnostics(
            self.output,
            ["seed"],
            depth=2,
            max_degree=12,
            max_terms=10,
            max_neighbor_fetches=2,
        )

        self.assertIn("grand_a", [row["term"] for row in rows])
        self.assertNotIn("grand_b", [row["term"] for row in rows])
        self.assertEqual(diagnostics["depth_used"], diagnostics["depth_requested"])
        self.assertEqual(diagnostics["neighbor_fetches"], 2)
        self.assertGreater(diagnostics["neighbor_fetches_skipped_due_to_budget"], 0)
        self.assertEqual(diagnostics["budget_state"], "truncated_by_neighbor_budget")

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
        term_quality = result["quality_gate"]["term_quality"]
        self.assertGreaterEqual(
            term_quality["rejected_counts_by_ingress"]["association"],
            2,
        )
        self.assertGreaterEqual(
            term_quality["rejected_counts_by_ingress"]["related_term"],
            1,
        )
        encoded_quality = json.dumps(term_quality, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("仍按新流程保持手动触发", encoded_quality)
        self.assertNotIn("动触发", encoded_quality)

    def test_graph_rejects_low_value_cjk_fragments_from_timeline_ingress(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        timeline = self.root / "project_timeline.json"
        timeline.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": {
                        "p": {
                            "project_label": "AIppocampus",
                            "project_tags": ["黏菌"],
                            "latest_turns": [
                                {
                                    "thread_key": "session:timeline",
                                    "topic_terms": [
                                        "仍按新流程保持手动触发",
                                        "动触发",
                                        "生命周期",
                                        "证据缺口",
                                    ],
                                    "source_refs": [
                                        {"thread_key": "session:timeline", "source_line": 10}
                                    ],
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            project_timeline_path=timeline,
        )
        health = graph.concept_graph_health(self.output)
        con = sqlite3.connect(self.output)
        try:
            labels = {row[0] for row in con.execute("SELECT label FROM concepts").fetchall()}
        finally:
            con.close()

        self.assertIn("黏菌", labels)
        self.assertIn("生命周期", labels)
        self.assertIn("证据缺口", labels)
        self.assertNotIn("仍按新流程保持手动触发", labels)
        self.assertNotIn("动触发", labels)
        self.assertGreaterEqual(
            result["quality_gate"]["term_quality"]["rejected_counts_by_ingress"]["timeline"],
            2,
        )
        self.assertEqual(
            health["term_quality_gate"]["rejected_counts_by_ingress"]["timeline"],
            result["quality_gate"]["term_quality"]["rejected_counts_by_ingress"]["timeline"],
        )
        encoded_health = json.dumps(health, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("生命周期", encoded_health)
        self.assertNotIn("证据缺口", encoded_health)
        self.assertNotIn("仍按新流程保持手动触发", encoded_health)

    def test_graph_rejects_low_value_cjk_fragments_from_subconscious_ingress(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        rows = [
            {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_edge",
                "status": "staging",
                "src": "仍按新流程保持手动触发",
                "dst": "生命周期",
                "edge_type": "related",
                "confidence": 0.9,
                "source_refs": [{"thread_key": "session:noise", "assistant_line": 10}],
            },
            {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_edge",
                "status": "staging",
                "src": "黏菌",
                "dst": "海马体",
                "edge_type": "related",
                "confidence": 0.9,
                "source_refs": [{"thread_key": "session:good", "assistant_line": 20}],
            },
            {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_edge",
                "status": "staging",
                "src": "动触发",
                "dst": "海马体",
                "edge_type": "related",
                "confidence": 0.9,
                "source_refs": [{"thread_key": "session:noise", "assistant_line": 30}],
            },
        ]
        staging.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["黏菌"], depth=1)
        con = sqlite3.connect(self.output)
        try:
            labels = {row[0] for row in con.execute("SELECT label FROM concepts").fetchall()}
        finally:
            con.close()

        self.assertEqual(result["subconscious_edge_count"], 2)
        self.assertEqual(expansions[0]["term"], "海马体")
        self.assertIn("黏菌", labels)
        self.assertIn("海马体", labels)
        self.assertNotIn("仍按新流程保持手动触发", labels)
        self.assertNotIn("动触发", labels)
        self.assertGreaterEqual(
            result["quality_gate"]["term_quality"]["rejected_counts_by_ingress"][
                "subconscious"
            ],
            2,
        )

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

    def test_subconscious_project_hub_collapse_parks_overflow_edges(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        targets = [
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
        ]
        rows = []
        for index, target in enumerate(targets):
            rows.append(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_edge",
                    "status": "staging",
                    "src": "AIppocampus",
                    "dst": target,
                    "edge_type": "related",
                    "confidence": 0.93,
                    "source_refs": [
                        {"thread_key": "session:a", "assistant_line": 100 + index},
                        {"thread_key": "session:b", "assistant_line": 200 + index},
                        {"thread_key": "session:c", "assistant_line": 300 + index},
                    ],
                }
            )
        staging.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["AIppocampus"], depth=1, max_degree=20)
        health = graph.concept_graph_health(self.output)
        encoded_health = json.dumps(health, ensure_ascii=False, sort_keys=True)

        hub_quality = result["quality_gate"]["subconscious_hub_quality"]
        self.assertEqual(hub_quality["collapsed_hub_count"], 1)
        self.assertEqual(hub_quality["parked_edge_group_count"], 4)
        self.assertEqual(hub_quality["active_capped_edge_group_count"], 6)
        self.assertLessEqual(len(expansions), 6)
        self.assertEqual(result["lifecycle"]["edge_status_counts"]["parked"], 8)
        self.assertIn("subconscious_hub_collapse", {item["code"] for item in health["warnings"]})
        self.assertEqual(health["subconscious_hub_quality"]["parked_edge_group_count"], 4)
        self.assertNotIn("AIppocampus", encoded_health)
        self.assertNotIn("memory report.md", encoded_health)

    def test_subconscious_small_project_hub_remains_navigation_usable(self) -> None:
        self.associations.write_text(
            json.dumps({"schema_version": 1, "terms": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        staging = self.root / "subconscious_edges.jsonl"
        rows = [
            {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_edge",
                "status": "staging",
                "src": "AIppocampus",
                "dst": target,
                "edge_type": edge_type,
                "confidence": 0.91,
                "source_refs": [{"thread_key": "session:overview", "assistant_line": index}],
            }
            for index, (target, edge_type) in enumerate(
                [
                    ("source IO kernel", "decision_about"),
                    ("MCP compact surface", "same_decision_space"),
                    ("agent recall", "project_topic"),
                    ("sync workflow", "depends_on"),
                ],
                start=1,
            )
        ]
        staging.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

        result = graph.build_concept_graph(
            self.associations,
            self.output,
            subconscious_edges_path=staging,
        )
        expansions = graph.expand_concepts(self.output, ["AIppocampus"], depth=1, max_degree=10)
        health = graph.concept_graph_health(self.output)

        self.assertEqual(result["quality_gate"]["subconscious_hub_quality"]["collapsed_hub_count"], 0)
        self.assertEqual(result["quality_gate"]["subconscious_hub_quality"]["parked_edge_group_count"], 0)
        self.assertGreaterEqual(len(expansions), 3)
        self.assertEqual(result["lifecycle"]["edge_status_counts"].get("parked", 0), 0)
        self.assertNotIn("subconscious_hub_collapse", {item["code"] for item in health["warnings"]})

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
