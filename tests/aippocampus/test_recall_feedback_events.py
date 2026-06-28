from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.recall.feedback import events as feedback


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
                source_ref={"thread_key": "thread-helpful", "message_id": "msg-helpful"},
                weight_delta=0.4,
            ),
            feedback.active_flow_event(
                route_id="pathlet:helpful",
                route_kind="pathlet",
                signal="user_confirmed",
                source_id="source:helpful",
                source_ref={"thread_key": "thread-helpful", "message_id": "msg-helpful"},
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
        self.assertEqual(
            report["training_signal_summary"]["training_role_counts"]["positive_demo"],
            2,
        )
        self.assertEqual(
            report["training_signal_summary"]["training_role_counts"]["hard_negative"],
            2,
        )
        self.assertEqual(report["suppression_lifecycle"]["hard_negative_count"], 1)
        self.assertEqual(report["policy_boundary"]["activation_weights_are_not_source_truth"], True)
        self.assertEqual(
            report["policy_boundary"]["default_route_weighting_consumer"],
            "bounded_route_activation_metadata",
        )
        self.assertEqual(report["calibration"]["consumer"], "bounded_route_activation_metadata")

    def test_public_fixture_covers_positive_and_negative_route_feedback(self) -> None:
        report = feedback.public_route_feedback_fixture_report()

        self.assertEqual(report["fixture"]["kind"], "public_route_feedback_fixture")
        self.assertGreaterEqual(report["metrics"]["source_reopen_success_count"], 1)
        self.assertGreaterEqual(report["metrics"]["wrong_route_drag_count"], 1)
        self.assertGreaterEqual(report["metrics"]["blocked_count"], 1)
        self.assertEqual(report["privacy_boundary"]["public_replayable_events_only"], True)
        self.assertEqual(
            report["policy_boundary"]["default_route_weighting_consumer"],
            "bounded_route_activation_metadata",
        )

    def test_feedback_training_signals_are_contrastive_and_suppression_is_reversible(self) -> None:
        positive = feedback.active_flow_event(
            route_id="route:good",
            route_kind="pathlet",
            signal="source_reopen_success",
            source_id="source:good",
            source_ref={"thread_key": "thread-good", "message_id": "msg-good"},
        )
        negative = feedback.active_flow_event(
            route_id="route:bad",
            route_kind="pathlet",
            signal="wrong_route_drag",
            source_id="source:bad",
        )
        negative["cue_hash"] = "cue-shared"
        negative["preferred_route_id"] = "route:good"
        negative["rejected_route_ids"] = ["route:bad"]
        reopen = feedback.active_flow_event(
            route_id="route:bad",
            route_kind="pathlet",
            signal="source_reopen_success",
            source_id="source:bad",
        )

        signals = feedback.feedback_training_signal_rows([positive, negative])
        by_role = {row["training_role"]: row for row in signals}
        lifecycle = feedback.suppression_lifecycle_report([negative, reopen], detail="operator")
        compact = feedback.suppression_lifecycle_report([negative], detail="compact")
        encoded = json.dumps({"signals": signals, "lifecycle": lifecycle, "compact": compact}, ensure_ascii=False)

        self.assertEqual(by_role["positive_demo"]["training_role"], "positive_demo")
        self.assertEqual(by_role["hard_negative"]["training_role"], "hard_negative")
        self.assertTrue(by_role["hard_negative"]["contrastive_pair"])
        self.assertEqual(lifecycle["overridden_by_positive_count"], 1)
        self.assertEqual(compact["hard_negative_count"], 1)
        self.assertNotIn("source:good", encoded)
        self.assertNotIn("source:bad", encoded)

    def test_suppression_lifecycle_maps_dismiss_park_expiry_and_positive_override(self) -> None:
        dismissed = feedback.active_flow_event(
            route_id="route:dismissed",
            route_kind="active_path",
            signal="dismiss",
            source_id="source:dismissed",
        )
        parked = feedback.active_flow_event(
            route_id="route:parked",
            route_kind="active_path",
            signal="PARK",
            source_id="source:parked",
        )
        expired = feedback.active_flow_event(
            route_id="route:expired",
            route_kind="active_path",
            signal="expired",
            source_id="source:expired",
        )
        negative_then_positive = [
            feedback.active_flow_event(
                route_id="route:recovered",
                route_kind="active_path",
                signal="manual_search_after_route",
                source_id="source:recovered",
            ),
            feedback.active_flow_event(
                route_id="route:recovered",
                route_kind="active_path",
                signal="source_reopen_success",
                source_id="source:recovered",
                weight_delta=1.25,
            ),
        ]

        lifecycle = feedback.suppression_lifecycle_report(
            [dismissed, parked, expired, *negative_then_positive],
            detail="operator",
        )
        compact = feedback.suppression_lifecycle_report([dismissed, parked], detail="compact")
        activation = feedback.active_flow_activation_report(negative_then_positive)
        by_route = {row["route_id"]: row for row in lifecycle["routes"]}

        self.assertEqual(dismissed["signal"], "dismissed")
        self.assertEqual(parked["signal"], "parked")
        self.assertEqual(by_route["route:dismissed"]["status"], "suppressed_hard_negative")
        self.assertEqual(by_route["route:parked"]["status"], "parked_recheck")
        self.assertEqual(by_route["route:expired"]["status"], "expired_recheck")
        self.assertEqual(
            by_route["route:recovered"]["status"],
            "overridden_by_positive_source_open",
        )
        self.assertEqual(compact["hard_negative_count"], 1)
        self.assertNotIn("routes", compact)
        self.assertTrue(activation["routes"][0]["foreground_eligible"])
        self.assertEqual(
            activation["routes"][0]["current_feedback_state"],
            "overridden_by_positive_source_open",
        )

    def test_suppression_lifecycle_uses_cumulative_score_for_foreground_eligibility(self) -> None:
        events = [
            feedback.active_flow_event(
                route_id="route:reflap",
                route_kind="active_path",
                signal="wrong_route_drag",
                source_id="source:reflap",
            )
            for _ in range(5)
        ]
        events.append(
            feedback.active_flow_event(
                route_id="route:reflap",
                route_kind="active_path",
                signal="source_reopen_success",
                source_id="source:reflap",
            )
        )

        lifecycle = feedback.suppression_lifecycle_report(events, detail="operator")
        activation = feedback.active_flow_activation_report(events)
        lifecycle_route = lifecycle["routes"][0]
        activation_route = activation["routes"][0]

        self.assertEqual(lifecycle_route["status"], "overridden_by_positive_source_open")
        self.assertEqual(lifecycle_route["activation_score"], -4.0)
        self.assertFalse(lifecycle_route["foreground_eligible"])
        self.assertFalse(activation_route["foreground_eligible"])
        self.assertEqual(
            lifecycle_route["foreground_eligible"],
            activation_route["foreground_eligible"],
        )
        self.assertIn("wrong_route_drag_demoted", lifecycle_route["reason_codes"])
        self.assertIn("source_reopen_success_promoted", lifecycle_route["reason_codes"])
        self.assertEqual(lifecycle["foreground_ineligible_count"], 1)

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

    def test_exact_stale_signal_and_custom_weight_calibration_are_preserved(self) -> None:
        stale = feedback.active_flow_event(
            route_id="route:stale",
            route_kind="active_path",
            signal="stale",
        )
        expired = feedback.active_flow_event(
            route_id="route:expired",
            route_kind="active_path",
            signal="expired",
        )
        custom_weight_events = [
            feedback.active_flow_event(
                route_id="route:custom-weight",
                route_kind="active_path",
                signal="source_reopen_success",
                source_ref={"thread_key": "thread-custom", "message_id": f"msg-{index}"},
                weight_delta=-0.2,
            )
            for index in range(2)
        ]

        activation = feedback.active_flow_activation_report(custom_weight_events)
        calibration = feedback.recall_feedback_calibration_report(custom_weight_events)

        self.assertEqual(stale["signal"], "stale")
        self.assertEqual(stale["weight_delta"], -0.35)
        self.assertEqual(expired["signal"], "expired")
        self.assertEqual(expired["weight_delta"], -0.4)
        self.assertEqual(activation["routes"][0]["activation_score"], -0.4)
        self.assertFalse(activation["routes"][0]["foreground_eligible"])
        self.assertEqual(calibration["deltas"][0]["route_weight_delta"], -0.2)
        self.assertFalse(calibration["deltas"][0]["foreground_eligible"])

    def test_active_flow_source_refs_are_preserved_for_training_admission(self) -> None:
        sourced = feedback.active_flow_event(
            route_id="route:sourced",
            route_kind="pathlet",
            signal="source_reopen_success",
            source_ref={"thread_key": "thread-sourced", "message_id": "msg-sourced"},
        )
        unsourced = feedback.active_flow_event(
            route_id="route:unsourced",
            route_kind="pathlet",
            signal="source_reopen_success",
            source_id="source:unsourced",
        )

        sourced_signal, unsourced_signal = feedback.feedback_training_signal_rows(
            [sourced, unsourced]
        )

        self.assertEqual(sourced["source_ref_count"], 1)
        self.assertEqual(sourced_signal["source_ref_count"], 1)
        self.assertEqual(sourced_signal["training_role"], "positive_demo")
        self.assertEqual(unsourced_signal["source_ref_count"], 0)
        self.assertEqual(unsourced_signal["training_role"], "none")

    def test_alias_and_context_feedback_events_are_navigation_only_and_public_safe(self) -> None:
        alias_event = feedback.alias_merge_event(
            route_id="route:test",
            route_kind="active_path",
            aliases=["外置海马体", r"C:\Users\someone\secret.txt"],
            source_id="source:test",
        )
        suppress_event = feedback.suppress_context_event(
            route_id="route:test",
            route_kind="active_path",
            context_cues=["普通数据库选型", "/tmp/private-source.txt"],
            source_id="source:test",
        )

        self.assertEqual(alias_event["aliases"], ["外置海马体"])
        self.assertEqual(suppress_event["context_cues"], ["普通数据库选型"])
        self.assertTrue(alias_event["policy_boundary"]["alias_feedback_is_navigation_only"])
        self.assertTrue(suppress_event["policy_boundary"]["context_feedback_is_navigation_only"])
        self.assertFalse(alias_event["privacy_boundary"]["stores_private_source_excerpt"])
        self.assertFalse(suppress_event["privacy_boundary"]["stores_local_path"])

    def test_feedback_calibration_report_lifts_demotes_and_falls_back_on_sparse_conflict(self) -> None:
        events = [
            feedback.active_flow_event(
                route_id="route:helpful",
                route_kind="pathlet",
                signal="source_reopen_success",
                source_id="source:1",
            ),
            feedback.active_flow_event(
                route_id="route:helpful",
                route_kind="pathlet",
                signal="user_confirmed",
                source_id="source:1",
            ),
            feedback.active_flow_event(
                route_id="route:wrong",
                route_kind="active_path",
                signal="wrong_route_drag",
                source_id="source:2",
            ),
            feedback.active_flow_event(
                route_id="route:conflict",
                route_kind="active_path",
                signal="source_reopen_success",
                source_id="source:3",
            ),
            feedback.active_flow_event(
                route_id="route:conflict",
                route_kind="active_path",
                signal="wrong_route_drag",
                source_id="source:3",
            ),
        ]

        report = feedback.recall_feedback_calibration_report(events)
        by_route = {row["route_id"]: row for row in report["deltas"]}

        self.assertGreater(by_route["route:helpful"]["route_weight_delta"], 0)
        self.assertEqual(by_route["route:wrong"]["route_weight_delta"], 0.0)
        self.assertTrue(by_route["route:wrong"]["sparse_feedback_fallback"])
        self.assertEqual(by_route["route:conflict"]["route_weight_delta"], 0.0)
        self.assertTrue(by_route["route:conflict"]["conflicting_feedback_fallback"])
        self.assertFalse(report["policy_boundary"]["clean_source_mutation_allowed"])
        self.assertIn("feedback_calibration_can_emit_source_open", report["cannot_claim"])

if __name__ == "__main__":
    unittest.main()
