from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import concept_graph as graph
from aippocampus_runtime.navigation import concept_graph_contributions as contributions
from aippocampus_runtime.navigation import data_quality_guard as navigation_guard
from aippocampus_runtime.navigation import trace_graph_ingress


class NavigationDataQualityGuardTests(unittest.TestCase):
    def test_trace_graph_ingress_owner_is_contribution_reexport(self) -> None:
        self.assertIs(
            contributions.trace_derived_graph_contribution_candidates,
            trace_graph_ingress.trace_derived_graph_contribution_candidates,
        )

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

    def test_trace_derived_graph_ingress_and_adoption_gate_use_source_open_lift(self) -> None:
        trace_rows = [
            {
                "trace_id": "positive",
                "trace_family": "successful_recall_deepen_source_open",
                "outcome": "source_reopen_success",
                "source_refs": [{"message_id": "msg-positive", "line": 1}],
                "opened_anchor_hits": 2,
            },
            {
                "trace_id": "negative",
                "trace_family": "repo_breadcrumb",
                "outcome": "wrong_route_drag",
                "safe_repo_relative": True,
                "route_id": "route:bad",
            },
            {
                "trace_id": "replay",
                "trace_family": "repo_breadcrumb",
                "outcome": "missed_opportunity",
                "safe_repo_relative": True,
            },
        ]

        candidates = contributions.trace_derived_graph_contribution_candidates(trace_rows)
        metrics = navigation_guard.trace_graph_adoption_metrics(candidates)
        report = navigation_guard.build_report(
            associations_path=None,
            concept_graph_path=None,
            trace_graph_candidates=candidates,
        )
        by_role = {row["training_role"]: row for row in candidates}
        encoded = json.dumps({"candidates": candidates, "metrics": metrics, "report": report}, ensure_ascii=False)

        self.assertEqual(by_role["positive_demo"]["edge_type"], "trace_positive_reopen")
        self.assertTrue(by_role["positive_demo"]["active_graph_edge"])
        self.assertEqual(by_role["hard_negative"]["status"], "parked")
        self.assertFalse(by_role["hard_negative"]["active_graph_edge"])
        self.assertEqual(by_role["replay_sample"]["status"], "eval_only")
        self.assertEqual(metrics["useful_source_open_hit_count"], 1)
        self.assertEqual(metrics["wrong_route_drag_count"], 1)
        self.assertEqual(metrics["false_accept_count"], 0)
        self.assertEqual(metrics["adoption_status"], "active_allowed")
        self.assertEqual(
            report["trace_graph_adoption"]["source_open_hits_by_training_role"]["positive_demo"],
            1,
        )
        self.assertNotIn("msg-positive", encoded)
        self.assertNotIn("route:bad", encoded)

    def test_semantic_cue_aliases_project_to_typed_graph_candidates(self) -> None:
        rows = [
            {
                "kind": "aippocampus_semantic_cue",
                "cue_id": "sc_active",
                "cue": "transport hot reload",
                "status": "active",
                "training_role": "positive_demo",
                "trace_admission_level": "reopenable_route",
                "candidate_lifecycle_state": "actionable_reopenable_route",
                "source_refs": [{"thread_key": "session:cue", "message_id": "msg-cue", "line": 4}],
            },
            {
                "kind": "aippocampus_semantic_cue",
                "cue_id": "sc_missing_admission",
                "cue": "missing admission cue",
                "status": "active",
                "source_refs": [{"thread_key": "session:cue", "message_id": "msg-missing", "line": 6}],
            },
            {
                "kind": "aippocampus_semantic_cue",
                "cue_id": "sc_suppressed",
                "cue": "wrong transport alias",
                "status": "suppressed_hard_negative",
                "training_role": "hard_negative",
                "trace_admission_level": "navigation_candidate",
                "candidate_lifecycle_state": "rejected_hard_negative",
                "source_refs": [{"thread_key": "session:cue", "message_id": "msg-bad", "line": 5}],
            },
        ]

        candidates = contributions.trace_derived_graph_contribution_candidates(rows)
        by_id = {row["signal_id"]: row for row in candidates}
        encoded = json.dumps(candidates, ensure_ascii=False)

        self.assertEqual(by_id["sc_active"]["edge_type"], "cue_alias_for_route")
        self.assertEqual(by_id["sc_active"]["status"], "verified")
        self.assertTrue(by_id["sc_active"]["active_graph_edge"])
        self.assertEqual(by_id["sc_missing_admission"]["admission_level"], "operator_only")
        self.assertTrue(by_id["sc_missing_admission"]["missing_trace_admission"])
        self.assertEqual(
            by_id["sc_missing_admission"]["lifecycle_reason"],
            "missing_trace_admission_metadata",
        )
        self.assertEqual(by_id["sc_missing_admission"]["status"], "staging")
        self.assertFalse(by_id["sc_missing_admission"]["active_graph_edge"])
        self.assertEqual(by_id["sc_suppressed"]["edge_type"], "cue_alias_for_route")
        self.assertEqual(by_id["sc_suppressed"]["status"], "parked")
        self.assertFalse(by_id["sc_suppressed"]["active_graph_edge"])
        self.assertNotIn("transport hot reload", encoded)
        self.assertNotIn("missing admission cue", encoded)
        self.assertNotIn("wrong transport alias", encoded)


if __name__ == "__main__":
    unittest.main()
