from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import episode_arc_route_producer as route_producer  # noqa: E402


class EpisodeArcRouteProducerTests(unittest.TestCase):
    def test_public_route_producer_fixture_blocks_old_route_and_suppresses_wrong_order(self) -> None:
        report = route_producer.build_public_episode_arc_route_producer_report()

        self.assertEqual(report["kind"], route_producer.REPORT_KIND)
        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["episode_arc_count"], 7)
        self.assertGreaterEqual(metrics["repeated_wrong_route_prevented_count"], 2)
        self.assertGreaterEqual(metrics["unresolved_frontier_reopen_count"], 1)
        self.assertGreaterEqual(metrics["missing_middle_detected_count"], 1)
        self.assertGreaterEqual(metrics["wrong_order_suppressed_count"], 1)
        self.assertEqual(metrics["foreground_story_dump_count"], 0)
        self.assertEqual(metrics["sequence_route_claim_without_reopen_count"], 0)
        self.assertEqual(metrics["sequence_order_claim_requires_reopen_count"], metrics["sequence_route_count"])
        self.assertGreater(metrics["ordered_route_helpfulness_rate"], 0)

        rejected = [
            case
            for case in report["case_summaries"]
            if case["pathlet_kind"] == "rejected_route" and not case["sequence_gaps"]
        ]
        self.assertTrue(rejected)
        self.assertTrue(all(case["next_action"] == "prevent_repeated_wrong_route" for case in rejected))

        wrong_order = [
            case
            for case in report["case_summaries"]
            if "event_order_semantic_mismatch" in case["sequence_gaps"]
        ]
        self.assertTrue(wrong_order)
        self.assertTrue(all(case["next_action"] == "refresh_sources" for case in wrong_order))

    def test_report_is_public_safe_and_keeps_claim_boundaries(self) -> None:
        report = route_producer.build_public_episode_arc_route_producer_report()

        raw = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw_source_text", raw)
        self.assertNotIn("source_refs", raw)
        self.assertNotIn("thread_key", raw)
        self.assertNotIn("event_id", raw)
        self.assertNotIn("C:\\", raw)
        self.assertIn("source_reopen_required_before_claim", report["cannot_claim"])
        self.assertIn("live_host_behavior_lift", report["cannot_claim"])
        self.assertEqual(
            report["issue_readouts"]["github_1362"]["route_producer_fixture"],
            "measured_public_deterministic",
        )
        self.assertTrue(report["issue_readouts"]["github_1362"]["closeout_eligible"])
        self.assertEqual(
            report["issue_readouts"]["github_1363"]["public_vcs_hard_event_cohort"],
            "measured_public_deterministic",
        )
        self.assertFalse(report["issue_readouts"]["github_663"]["closeout_eligible"])

    def test_custom_unresolved_frontier_becomes_reopenable_route(self) -> None:
        report = route_producer.build_episode_arc_route_producer_report(
            [
                route_producer.public_event(
                    "custom-frontier",
                    "unresolved_frontier",
                    1,
                    family="custom_frontier",
                    sequence_index=0,
                ),
                route_producer.public_event(
                    "custom-frontier-source",
                    "source_reopen",
                    2,
                    family="custom_frontier",
                    sequence_index=1,
                ),
            ]
        )

        self.assertEqual(report["metrics"]["unresolved_frontier_reopen_count"], 1)
        case = report["case_summaries"][0]
        self.assertEqual(case["pathlet_kind"], "unresolved_frontier")
        self.assertEqual(case["action_grammar"], "reopenable_route")
        self.assertEqual(case["next_action"], "reopen_unresolved_frontier")
        self.assertTrue(case["source_reopen_required_before_claim"])


if __name__ == "__main__":
    unittest.main()
