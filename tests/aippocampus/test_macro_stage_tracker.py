from __future__ import annotations

import json
import unittest

from aippocampus_runtime.macro import stage_tracker


def _source_event(
    event_id: str,
    target: str,
    *,
    event_type: str = "roadmap_shift",
    signal_scale: str = "project_event",
    support_delta: float = 1.0,
    route_success_delta: float = 0.0,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "target_hexagram": target,
        "source_lane": "integration_worker",
        "signal_scale": signal_scale,
        "source_refs": [{"source_id": f"source-{event_id}", "raw_text": "PRIVATE"}],
        "support_delta": support_delta,
        "route_success_delta": route_success_delta,
        "local_path": "C:\\private\\stage.json",
    }

class MacroStageTrackerTests(unittest.TestCase):
    def test_king_wen_adjacency_classifies_project_movement_states(self) -> None:
        advanced = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[_source_event("advanced", "解")],
        )
        stalled = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[_source_event("stalled", "蹇")],
        )
        reversed_update = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="解",
            source_events=[_source_event("reversed", "蹇")],
        )
        jumped = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[_source_event("jumped", "益")],
        )
        forked = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[
                _source_event("fork-a", "解"),
                _source_event("fork-b", "损"),
            ],
        )

        self.assertEqual(advanced["sequence"]["movement_state"], "advanced")
        self.assertEqual(stalled["sequence"]["movement_state"], "stalled")
        self.assertEqual(reversed_update["sequence"]["movement_state"], "reversed")
        self.assertEqual(jumped["sequence"]["movement_state"], "jumped")
        self.assertEqual(forked["sequence"]["movement_state"], "forked")
        self.assertEqual(advanced["sequence"]["previous"], "蹇")
        self.assertEqual(advanced["sequence"]["current"], "解")
        self.assertEqual(advanced["sequence"]["track"], "king_wen")
        self.assertEqual(advanced["sequence"]["pair_transition"], "pair_internal")
        self.assertEqual(advanced["sequence"]["king_wen_pair"]["relation"], "reverse")
        self.assertIn("king_wen_pair_internal_perspective_shift", advanced["diagnostics"])
        self.assertEqual(jumped["sequence"]["pair_transition"], "cross_pair")
        self.assertIn("king_wen_cross_pair_transition", jumped["diagnostics"])
        self.assertEqual(advanced["authority_level"], "navigation_only")
        self.assertEqual(advanced["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(advanced["fact_claim_allowed"])

    def test_stage_update_preserves_review_state_and_public_safe_source_refs(self) -> None:
        update = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[_source_event("bench", "解", event_type="benchmark_result")],
            review_state="machine_checked",
            report_only=True,
        )
        encoded = json.dumps(update, ensure_ascii=False, sort_keys=True)

        self.assertEqual(update["review_state"], "machine_checked")
        self.assertEqual(update["source_refs"], [{"source_id": "source-bench"}])
        self.assertTrue(update["report_only"])
        self.assertEqual(update["write_effect"], "none")
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertIn("benchmark_result", update["event_types"])

    def test_later_contradiction_marks_stage_update_stale_for_recheck(self) -> None:
        update = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[_source_event("advanced", "解")],
            review_state="machine_checked",
        )
        stale = stage_tracker.recheck_stage_update(
            update,
            later_events=[
                _source_event(
                    "correction",
                    "损",
                    event_type="user_correction",
                    support_delta=0.0,
                )
            ],
        )

        self.assertEqual(stale["review_state"], "stale")
        self.assertTrue(stale["diagnostic_only"])
        self.assertIn("later_source_contradicts_stage", stale["diagnostics"])
        self.assertIn("source_contradiction_recheck", stale["recheck_on"])

    def test_unpromoted_journey_signal_cannot_move_project_stage(self) -> None:
        update = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[
                _source_event(
                    "journey",
                    "解",
                    signal_scale="journey",
                    event_type="journey_waypoint",
                )
            ],
        )

        self.assertEqual(update["sequence"]["current"], "蹇")
        self.assertEqual(update["sequence"]["movement_state"], "stalled")
        self.assertEqual(update["review_state"], "needs_review")
        self.assertIn(
            "journey_signal_ignored_without_project_promotion",
            update["diagnostics"],
        )

    def test_fixture_report_covers_worker_lane_momentum_and_no_write_mode(self) -> None:
        report = stage_tracker.build_stage_tracker_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["schema_version"], "macro-stage-tracker-v0")
        self.assertEqual(report["metrics"]["movement_state_coverage_count"], 5)
        self.assertEqual(report["metrics"]["claim_ready_stage_updates"], 0)
        self.assertEqual(report["metrics"]["write_effect_count"], 0)
        self.assertIn("integration_worker", report["worker_lanes"])
        self.assertIn(report["momentum_summary"]["phase_hint"], {"rising", "peaking"})
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_user_correction_delta_shapes_momentum_summary(self) -> None:
        event = _source_event("correction", "蹇", support_delta=0.0)
        event["user_correction_delta"] = 1.0

        update = stage_tracker.build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[event],
        )

        momentum = update["momentum"]
        self.assertEqual(momentum["phase_hint"], "declining")
        self.assertEqual(momentum["basis"]["user_correction_delta"], 1.0)
        self.assertEqual(momentum["trend"]["friction_delta"], 1.0)
        self.assertEqual(momentum["trend"]["net_delta"], -1.0)
        self.assertNotEqual(momentum["phase_hint"], "hibernating")

if __name__ == "__main__":
    unittest.main()
