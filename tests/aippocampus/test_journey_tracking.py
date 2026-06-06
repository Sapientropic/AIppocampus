from __future__ import annotations

import json
import sys
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

from aippocampus_runtime.journey import live as journey_live  # noqa: E402
from aippocampus_runtime.journey import tracking as journey  # noqa: E402


class JourneyTrackingTests(unittest.TestCase):
    def make_journey(self) -> journey.Journey:
        result = journey.create_journey(
            path_label="continuity after change",
            core_inquiry="How can continuity survive compaction without false memory claims?",
            waypoint_rows=journey.fixture_waypoints(),
            active_questions=["what survives compaction?"],
        )
        self.assertTrue(result.created, result.reason)
        self.assertIsNotNone(result.journey)
        return result.journey  # type: ignore[return-value]

    def test_creates_source_backed_journey_with_waypoint_boundaries(self) -> None:
        item = self.make_journey()
        payload = journey.journey_to_dict(item)

        self.assertEqual(payload["kind"], "aippocampus_journey")
        self.assertEqual(payload["status"], "traveling")
        self.assertEqual(len(payload["waypoints"]), 3)
        self.assertEqual(len({wp["thread_id"] for wp in payload["waypoints"]}), 3)
        self.assertTrue(payload["source_refs"])
        self.assertTrue(payload["current_frontier_source_refs"])
        self.assertEqual(payload["current_frontier_kind"], "journey_current_frontier")
        self.assertIn("navigation candidates", payload["truth_boundary"])

    def test_conservative_instantiation_gate_rejects_thin_or_unbacked_inputs(self) -> None:
        rows = journey.fixture_waypoints()

        too_few_threads = journey.create_journey(
            path_label="thin",
            core_inquiry="How can this source-backed question keep evolving across contexts?",
            waypoint_rows=[{**row, "thread_id": "session:one"} for row in rows],
        )
        self.assertFalse(too_few_threads.created)
        self.assertEqual(too_few_threads.reason, "not_enough_distinct_threads")

        unbacked = journey.create_journey(
            path_label="thin",
            core_inquiry="How can this source-backed question keep evolving across contexts?",
            waypoint_rows=[{**row, "source_refs": []} for row in rows],
        )
        self.assertFalse(unbacked.created)
        self.assertEqual(unbacked.reason, "not_enough_source_backed_waypoints")

        generic = journey.create_journey(
            path_label="generic",
            core_inquiry="coding",
            waypoint_rows=rows,
        )
        self.assertFalse(generic.created)
        self.assertEqual(generic.reason, "core_inquiry_not_specific")

    def test_expiration_and_dormancy_state_transitions(self) -> None:
        item = self.make_journey()

        camped = journey.refresh_journey_state(item, now="2026-07-10T00:00:00Z")
        self.assertEqual(camped.status, "camped")

        abandoned = journey.refresh_journey_state(item, now="2026-12-01T00:00:00Z")
        self.assertEqual(abandoned.status, "abandoned")

        arrived = journey.mark_arrived(item, timestamp="2026-05-21T00:00:00Z", note="Answered.")
        self.assertEqual(journey.refresh_journey_state(arrived, now="2026-12-01T00:00:00Z").status, "arrived")

    def test_appending_waypoint_is_append_only_and_extends_expiry(self) -> None:
        item = self.make_journey()
        old_ids = [waypoint.waypoint_id for waypoint in item.waypoints]
        old_expiry = item.expires_at

        updated = journey.append_waypoint(
            item,
            {
                "moment": "A later continuation tested the same source-ref boundary again.",
                "thread_id": "session:journey-d",
                "timestamp": "2026-06-01T00:00:00Z",
                "source_refs": [{"thread_key": "session:journey-d", "message_id": "msg-d"}],
                "frontier_hint": "Continue from the new boundary with source refs still attached.",
            },
        )

        self.assertEqual([waypoint.waypoint_id for waypoint in updated.waypoints[:3]], old_ids)
        self.assertEqual(len(updated.waypoints), 4)
        self.assertGreater(journey.parse_time(updated.expires_at), journey.parse_time(old_expiry))
        self.assertEqual(updated.status, "traveling")
        self.assertIn("new boundary", updated.current_frontier)

    def test_feedback_actions_confirm_correct_merge_abandon_and_revive(self) -> None:
        item = self.make_journey()
        confirmed = journey.apply_feedback(
            item,
            journey.JourneyFeedback(
                journey_id=item.journey_id,
                action="confirm",
                timestamp="2026-05-21T00:00:00Z",
            ),
        )
        self.assertEqual(confirmed.status, "traveling")
        self.assertEqual(confirmed.feedback_history[-1]["action"], "confirm")

        corrected = journey.apply_feedback(
            confirmed,
            journey.JourneyFeedback(
                journey_id=item.journey_id,
                action="correct",
                timestamp="2026-05-22T00:00:00Z",
                correction="The frontier is source survival, not generic memory anxiety.",
            ),
        )
        self.assertIn("source survival", corrected.current_frontier)

        merged = journey.apply_feedback(
            corrected,
            journey.JourneyFeedback(
                journey_id=item.journey_id,
                action="merge",
                timestamp="2026-05-23T00:00:00Z",
                merge_target="jr_target",
            ),
        )
        self.assertEqual(merged.status, "abandoned")
        self.assertEqual(merged.merged_into, "jr_target")

        abandoned = journey.apply_feedback(
            corrected,
            journey.JourneyFeedback(
                journey_id=item.journey_id,
                action="abandon",
                timestamp="2026-05-24T00:00:00Z",
            ),
        )
        self.assertEqual(abandoned.status, "abandoned")

        revived = journey.apply_feedback(
            abandoned,
            journey.JourneyFeedback(
                journey_id=item.journey_id,
                action="revive",
                timestamp="2026-05-25T00:00:00Z",
            ),
        )
        self.assertEqual(revived.status, "traveling")
        self.assertGreater(journey.parse_time(revived.expires_at), journey.parse_time(abandoned.expires_at))

    def test_replay_fixture_smoke_beats_plain_summary_baseline(self) -> None:
        payload = journey.run_replay_fixture_smoke()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertGreater(
            payload["metrics"]["journey_frontier_hits"],
            payload["metrics"]["plain_summary_hits"],
        )
        self.assertEqual(payload["journey"]["current_frontier_kind"], "journey_current_frontier")
        self.assertIn("live_model_behavioral_equivalence", payload["cannot_claim"])

    def test_live_theme_and_question_rows_create_journey_without_future_leakage(self) -> None:
        payload = journey_live.run_live_journey_time_sliced_replay_fixture(
            as_of="2026-06-03T23:59:00Z"
        )

        self.assertTrue(payload["ok"], json.dumps(payload, ensure_ascii=False, indent=2))
        self.assertEqual(payload["kind"], "aippocampus_live_journey_time_sliced_replay")
        self.assertEqual(payload["status"], "journey_candidate_created")
        self.assertEqual(payload["metrics"]["included_live_row_count"], 3)
        self.assertEqual(payload["metrics"]["future_row_excluded_count"], 1)
        self.assertFalse(payload["metrics"]["future_leakage_detected"])
        self.assertEqual(payload["journey"]["path_label"], "continuity after change")
        self.assertEqual(len(payload["journey"]["waypoints"]), 3)
        self.assertTrue(payload["journey"]["source_refs"])
        dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("FUTURE_LEAK_SENTINEL", dumped)
        self.assertNotIn("PRIVATE_SENTINEL_ROUTE_HANDLE", dumped)

    def test_foreground_journey_hint_timing_has_positive_and_negative_controls(self) -> None:
        replay = journey_live.run_live_journey_time_sliced_replay_fixture(
            as_of="2026-06-03T23:59:00Z"
        )
        live = replay["foreground_hint_replay"]

        self.assertEqual(live["positive"]["decision"], "agent_visible_hint")
        self.assertEqual(live["positive"]["agent_visible"]["visibility"], "gentle_nudge")
        self.assertIn("Journey hints are navigation", live["positive"]["agent_visible"]["truth_boundary"])
        self.assertNotIn("source_refs", live["positive"]["agent_visible"])
        self.assertTrue(live["positive"]["private_route_handle"].startswith("journey_route:"))

        self.assertEqual(live["source_visible_negative"]["decision"], "silent")
        self.assertEqual(live["unrelated_negative"]["decision"], "backstage_only")
        self.assertEqual(live["high_risk_negative"]["decision"], "source_reopen_required")
        encoded = json.dumps(live, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("PRIVATE_SENTINEL_ROUTE_HANDLE", encoded)
        self.assertNotIn("msg-live-a", live["positive"]["agent_visible"].get("frontier", ""))

    def test_content_light_cross_project_resonance_outputs_hypothesis_without_private_payload(self) -> None:
        current = journey.create_journey(
            path_label="PRIVATE_SENTINEL_CURRENT_PROJECT_GENERATED_ARTIFACTS",
            core_inquiry="How can migration cleanup avoid stale generated artifacts in private project alpha?",
            waypoint_rows=[
                {
                    "moment": "PRIVATE_SENTINEL_CURRENT_MOMENT stale build cache leaked into the patch.",
                    "thread_id": "current-a",
                    "timestamp": "2026-05-01T00:00:00Z",
                    "arc": "屯",
                    "labels": ["dynamics:stalled-start", "PRIVATE_SENTINEL_CURRENT_LABEL"],
                    "source_refs": [{"thread_key": "current-a", "message_id": "msg-current-a"}],
                },
                {
                    "moment": "PRIVATE_SENTINEL_CURRENT_MOMENT generated files needed a fresh source reopen.",
                    "thread_id": "current-b",
                    "timestamp": "2026-05-02T00:00:00Z",
                    "arc": "蒙",
                    "labels": ["dynamics:uncertain-route"],
                    "source_refs": [{"thread_key": "current-b", "message_id": "msg-current-b"}],
                },
                {
                    "moment": "PRIVATE_SENTINEL_CURRENT_MOMENT the route waited for source-backed validation.",
                    "thread_id": "current-c",
                    "timestamp": "2026-05-03T00:00:00Z",
                    "arc": "需",
                    "labels": ["dynamics:wait-for-evidence"],
                    "source_refs": [{"thread_key": "current-c", "message_id": "msg-current-c"}],
                },
            ],
        )
        candidate = journey.create_journey(
            path_label="PRIVATE_SENTINEL_OLD_PROJECT_REJECTED_ROUTE",
            core_inquiry="How can a rejected route be reopened only after its old source constraints change?",
            waypoint_rows=[
                {
                    "moment": "PRIVATE_SENTINEL_OLD_PROJECT old generated artifact was stale.",
                    "thread_id": "old-a",
                    "timestamp": "2026-04-01T00:00:00Z",
                    "arc": "屯",
                    "labels": ["dynamics:stalled-start"],
                    "source_refs": [
                        {
                            "thread_key": "old-a",
                            "message_id": "msg-old-a",
                            "source_line": "E:/PRIVATE/old-project/generated.py",
                        }
                    ],
                },
                {
                    "moment": "PRIVATE_SENTINEL_OLD_PROJECT old route was rejected for a now-uncertain constraint.",
                    "thread_id": "old-b",
                    "timestamp": "2026-04-02T00:00:00Z",
                    "arc": "蒙",
                    "labels": ["dynamics:uncertain-route"],
                    "source_refs": [{"thread_key": "old-b", "message_id": "msg-old-b"}],
                },
                {
                    "moment": "PRIVATE_SENTINEL_OLD_PROJECT old route waited for source-backed validation.",
                    "thread_id": "old-c",
                    "timestamp": "2026-04-03T00:00:00Z",
                    "arc": "需",
                    "labels": ["dynamics:wait-for-evidence"],
                    "source_refs": [{"thread_key": "old-c", "message_id": "msg-old-c"}],
                },
            ],
        )
        self.assertTrue(current.created, current.reason)
        self.assertTrue(candidate.created, candidate.reason)

        payload = journey.build_content_light_resonance(
            current_journey=journey.journey_to_dict(current.journey),
            candidate_journeys=[
                {
                    "project_key": "repo://PRIVATE_SENTINEL_OLD_PROJECT",
                    "journey": journey.journey_to_dict(candidate.journey),
                    "source_free_patterns": [
                        "stale_generated_artifact",
                        "rejected_route",
                        "E:/PRIVATE/old-project/generated.py",
                        "PRIVATE_SENTINEL_PATTERN_SHOULD_NOT_LEAK",
                    ],
                }
            ],
            current_project_key="repo://PRIVATE_SENTINEL_CURRENT_PROJECT",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_content_light_journey_resonance")
        self.assertEqual(payload["status"], "hypotheses_available")
        self.assertEqual(len(payload["matches"]), 1)
        match = payload["matches"][0]
        self.assertEqual(match["suggested_use"], "source_refresh_cue")
        self.assertEqual(match["candidate_patterns"], ["stale_generated_artifact", "rejected_route"])
        self.assertEqual(match["shared_structure"]["arc_sequence"], ["屯", "蒙", "需"])
        self.assertTrue(match["claim_boundary"]["hypothesis_not_fact"])
        self.assertTrue(match["privacy_boundary"]["content_light_only"])
        self.assertFalse(match["privacy_boundary"]["raw_source_refs_shared"])

        dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertIn("屯", dumped)
        for private_value in [
            "PRIVATE_SENTINEL_CURRENT_PROJECT",
            "PRIVATE_SENTINEL_CURRENT_MOMENT",
            "PRIVATE_SENTINEL_CURRENT_LABEL",
            "PRIVATE_SENTINEL_OLD_PROJECT",
            "msg-old-a",
            "E:/PRIVATE/old-project/generated.py",
            "PRIVATE_SENTINEL_PATTERN_SHOULD_NOT_LEAK",
        ]:
            self.assertNotIn(private_value, dumped)

    def test_content_light_resonance_degrades_when_journey_data_is_missing(self) -> None:
        payload = journey.build_content_light_resonance(
            current_journey=None,
            candidate_journeys=[],
            current_project_key="repo://PRIVATE_SENTINEL_CURRENT_PROJECT",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "skipped_missing_journey_data")
        self.assertEqual(payload["matches"], [])
        self.assertIn("source_text_comparison", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
