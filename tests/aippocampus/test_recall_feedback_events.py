from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import feedback_events as feedback  # noqa: E402


class RecallFeedbackEventTests(unittest.TestCase):
    def test_public_safe_feedback_report_groups_by_context_and_signal_family(self) -> None:
        events = [
            feedback.recall_feedback_event(
                candidate_id="candidate:exact",
                source_id="source:exact",
                blend_context="exact_quote",
                signal_family="text",
                outcome="candidate_delivered",
                route_kind="active_path",
            ),
            feedback.recall_feedback_event(
                candidate_id="candidate:exact",
                source_id="source:exact",
                blend_context="exact_quote",
                signal_family="text",
                outcome="source_reopen_success",
                route_kind="active_path",
            ),
            feedback.recall_feedback_event(
                candidate_id="candidate:graph",
                source_id="source:graph",
                blend_context="theme_emergence",
                signal_family="graph",
                outcome="ignored",
                route_kind="continuity_domain",
            ),
        ]

        report = feedback.recall_feedback_report(events)

        exact_text = report["by_blend_context"]["exact_quote"]["signal_families"]["text"]
        theme_graph = report["by_blend_context"]["theme_emergence"]["signal_families"]["graph"]
        self.assertEqual(exact_text["candidate_delivered_count"], 1)
        self.assertEqual(exact_text["source_reopen_success_count"], 1)
        self.assertEqual(theme_graph["ignored_count"], 1)
        self.assertEqual(report["policy_boundary"]["telemetry_is_calibration_evidence"], True)
        self.assertEqual(report["privacy_boundary"]["stores_raw_prompt_text"], False)
        self.assertEqual(report["privacy_boundary"]["stores_private_source_excerpt"], False)
        self.assertNotIn("raw_prompt", events[0])

    def test_active_flow_reducer_promotes_reopen_success_and_demotes_blocked_routes(self) -> None:
        events = [
            feedback.active_flow_event(
                route_id="pathlet:helpful",
                route_kind="pathlet",
                signal="source_reopen_success",
                source_id="source:helpful",
                weight_delta=0.4,
            ),
            feedback.active_flow_event(
                route_id="pathlet:helpful",
                route_kind="pathlet",
                signal="user_confirmed",
                source_id="source:helpful",
                weight_delta=0.2,
            ),
            feedback.active_flow_event(
                route_id="domain:blocked",
                route_kind="continuity_domain",
                signal="blocked",
                source_id="source:blocked",
                reason="private route blocked",
            ),
            feedback.active_flow_event(
                route_id="domain:blocked",
                route_kind="continuity_domain",
                signal="wrong_route_drag",
                source_id="source:blocked",
            ),
        ]

        report = feedback.active_flow_activation_report(events)
        by_route = {row["route_id"]: row for row in report["routes"]}

        self.assertGreater(by_route["pathlet:helpful"]["activation_score"], 0)
        self.assertEqual(by_route["pathlet:helpful"]["foreground_eligible"], True)
        self.assertLess(by_route["domain:blocked"]["activation_score"], 0)
        self.assertEqual(by_route["domain:blocked"]["foreground_eligible"], False)
        self.assertIn("blocked_route_not_foreground_eligible", by_route["domain:blocked"]["reason_codes"])
        self.assertEqual(report["metrics"]["source_reopen_success_count"], 1)
        self.assertEqual(report["metrics"]["wrong_route_drag_count"], 1)
        self.assertEqual(report["metrics"]["blocked_count"], 1)
        self.assertEqual(report["policy_boundary"]["activation_weights_are_not_source_truth"], True)

    def test_public_fixture_covers_positive_and_negative_route_feedback(self) -> None:
        report = feedback.public_route_feedback_fixture_report()

        self.assertEqual(report["fixture"]["kind"], "public_route_feedback_fixture")
        self.assertGreaterEqual(report["metrics"]["source_reopen_success_count"], 1)
        self.assertGreaterEqual(report["metrics"]["wrong_route_drag_count"], 1)
        self.assertGreaterEqual(report["metrics"]["blocked_count"], 1)
        self.assertEqual(report["privacy_boundary"]["public_replayable_events_only"], True)
        self.assertEqual(report["policy_boundary"]["default_route_weighting_unchanged"], True)

    def test_public_route_feedback_fixture_file_is_replayable(self) -> None:
        fixture_path = REPO_ROOT / "benchmark_corpus" / "route_feedback" / "fixture.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        events = [
            feedback.active_flow_event(
                route_id=row["route_id"],
                route_kind=row["route_kind"],
                signal=row["signal"],
                source_id=row["source_id"],
                weight_delta=row.get("weight_delta"),
                reason=row.get("reason", ""),
            )
            for row in payload["events"]
        ]
        report = feedback.active_flow_activation_report(events)

        self.assertEqual(payload["kind"], "public_route_feedback_fixture")
        self.assertEqual(payload["privacy_boundary"]["public_replayable_events_only"], True)
        self.assertGreaterEqual(report["metrics"]["source_reopen_success_count"], 1)
        self.assertGreaterEqual(report["metrics"]["wrong_route_drag_count"], 1)
        self.assertGreaterEqual(report["metrics"]["blocked_count"], 1)

    def test_wrong_route_alias_stays_negative_and_unknown_route_kind_is_rejected(self) -> None:
        event = feedback.active_flow_event(
            route_id="route:test",
            route_kind="continuity_domain",
            signal="wrong_route",
            source_id="source:test",
        )

        self.assertEqual(event["signal"], "wrong_route_drag")
        self.assertEqual(event["weight_delta"], -1.0)

        with self.assertRaises(feedback.InvalidFeedbackValue) as context:
            feedback.active_flow_event(
                route_id="route:test",
                route_kind="recall_context",
                signal="wrong_route_drag",
                source_id="source:test",
            )
        self.assertEqual(context.exception.field, "route_kind")


if __name__ == "__main__":
    unittest.main()
