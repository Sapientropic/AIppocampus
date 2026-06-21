from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import concept_edge_utility as utility
from aippocampus_runtime.navigation import concept_graph as graph


class ConceptEdgeUtilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.events = self.root / "concept-edge-utility-events.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_records_privacy_safe_event_and_report_groups_outcomes(self) -> None:
        raw_seed = "用户的家庭计划 private prompt text 123"
        raw_project = "AIppocampus private project label"
        raw_domain = "continuity design private domain"

        event = utility.record_edge_utility_event(
            self.events,
            seed_term=raw_seed,
            edge_type="project_topic",
            edge_status="staging",
            score=0.734,
            outcome="source_reopen_success",
            project_bucket=raw_project,
            domain_bucket=raw_domain,
            depth=1,
        )
        encoded_events = self.events.read_text(encoding="utf-8")
        report = utility.build_edge_utility_report(self.events)
        encoded_report = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(event["score_bucket"], "high")
        self.assertEqual(event["outcome"], "source_reopen_success")
        self.assertTrue(event["seed_term_hash"].startswith("sha256:"))
        self.assertNotIn(raw_seed, encoded_events)
        self.assertNotIn(raw_project, encoded_events)
        self.assertNotIn(raw_domain, encoded_events)
        self.assertNotIn(raw_seed, encoded_report)
        self.assertNotIn(raw_project, encoded_report)
        self.assertNotIn(raw_domain, encoded_report)
        self.assertEqual(report["by_edge_type"]["project_topic"]["event_count"], 1)
        self.assertEqual(
            report["by_edge_type"]["project_topic"]["source_reopen_success_count"],
            1,
        )
        self.assertEqual(report["by_status"]["staging"]["event_count"], 1)
        self.assertEqual(report["by_score_bucket"]["high"]["event_count"], 1)
        self.assertEqual(report["by_project_bucket"][event["project_bucket"]]["event_count"], 1)
        self.assertEqual(report["by_domain_bucket"][event["domain_bucket"]]["event_count"], 1)
        self.assertTrue(report["source_boundary"]["edge_utility_is_navigation_only"])
        self.assertTrue(report["source_boundary"]["edge_weights_are_ranking_priors"])
        self.assertFalse(report["policy"]["mutates_edge_type_multipliers"])

    def test_report_groups_failure_modes_without_changing_edge_priors(self) -> None:
        before = dict(graph.EDGE_TYPE_MULTIPLIER)
        utility.record_edge_utility_event(
            self.events,
            seed_term="部署节奏",
            edge_type="depends_on",
            edge_status="verified",
            score=0.32,
            outcome="skip",
            domain_bucket="workflow",
        )
        utility.record_edge_utility_event(
            self.events,
            seed_term="部署节奏",
            edge_type="depends_on",
            edge_status="verified",
            score=0.32,
            outcome="correction",
            domain_bucket="workflow",
        )

        report = utility.build_edge_utility_report(self.events)

        self.assertEqual(graph.EDGE_TYPE_MULTIPLIER, before)
        self.assertEqual(report["by_edge_type"]["depends_on"]["event_count"], 2)
        self.assertEqual(report["by_edge_type"]["depends_on"]["skip_count"], 1)
        self.assertEqual(report["by_edge_type"]["depends_on"]["correction_count"], 1)
        self.assertEqual(report["by_status"]["verified"]["event_count"], 2)
        self.assertEqual(report["by_score_bucket"]["low"]["event_count"], 2)
        self.assertEqual(report["failure_modes"]["skip"], 1)
        self.assertEqual(report["failure_modes"]["correction"], 1)
        low_bucket = report["edge_type_status_score_buckets"]["depends_on"]["verified"]["low"]
        self.assertEqual(low_bucket["event_count"], 2)
        self.assertEqual(low_bucket["skip_count"], 1)
        self.assertEqual(low_bucket["correction_count"], 1)

    def test_unknown_edge_type_is_hashed_instead_of_serialized(self) -> None:
        raw_edge_type = r"private\source.md"

        event = utility.record_edge_utility_event(
            self.events,
            seed_term="本地底座",
            edge_type=raw_edge_type,
            edge_status="staging",
            score=0.5,
            outcome="useful_match",
        )
        report = utility.build_edge_utility_report(self.events)
        encoded = self.events.read_text(encoding="utf-8") + json.dumps(
            report, ensure_ascii=False, sort_keys=True
        )

        self.assertTrue(event["edge_type"].startswith("custom:sha256:"))
        self.assertNotIn("private", encoded)
        self.assertNotIn("source.md", encoded)
        self.assertIn(event["edge_type"], report["by_edge_type"])

if __name__ == "__main__":
    unittest.main()
