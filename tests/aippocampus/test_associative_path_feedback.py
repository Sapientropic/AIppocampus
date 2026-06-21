from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall.associative_path_feedback import (
    append_followthrough_event,
    build_followthrough_event,
)
from aippocampus_runtime.recall.associative_path_walker import walk_associative_paths


def source_ref() -> dict[str, object]:
    return {"thread_key": "thread:apw", "source_id": "src", "message_id": "msg"}

def report_with_feedback(feedback: list[dict[str, object]]) -> dict[str, object]:
    return walk_associative_paths(
        query="slime mold exploratory recall",
        candidates=[
            {
                "route_id": "route:apw",
                "candidate_id": "route:apw",
                "route_terms": ["associative path walker", "routing exploration"],
                "thread_key": "thread:apw",
                "scope_bucket": "project",
            }
        ],
        bridge_rows=[
            {
                "candidate_id": "route:apw",
                "from_terms": ["slime mold", "exploratory recall"],
                "to_terms": ["associative path walker", "routing exploration"],
                "source_refs": [source_ref()],
                "scope_bucket": "project",
            }
        ],
        feedback_rows=feedback,
    )

class AssociativePathFeedbackTests(unittest.TestCase):
    def test_positive_followthrough_reinforces_only_same_scope(self) -> None:
        baseline = report_with_feedback([])
        same_scope = report_with_feedback(
            [
                build_followthrough_event(
                    route_id="route:apw",
                    outcome="source_helped_task",
                    scope_bucket="project",
                    source_refs=[source_ref()],
                )
            ]
        )
        cross_scope = report_with_feedback(
            [
                build_followthrough_event(
                    route_id="route:apw",
                    outcome="source_helped_task",
                    scope_bucket="user_private",
                    source_refs=[source_ref()],
                )
            ]
        )

        self.assertGreater(same_scope["candidates"][0]["score"], baseline["candidates"][0]["score"])
        self.assertEqual(cross_scope["candidates"][0]["score"], baseline["candidates"][0]["score"])
        self.assertIn("cross_scope_positive_feedback_ignored", cross_scope["reason_codes"])

    def test_negative_followthrough_dampens_repeated_wrong_hop(self) -> None:
        report = report_with_feedback(
            [
                build_followthrough_event(
                    route_id="route:apw",
                    outcome="wrong_hop",
                    scope_bucket="project",
                )
            ]
        )

        self.assertEqual(report["candidate_count"], 0)
        self.assertIn("negative_feedback_evaporated", report["reason_codes"])

    def test_ignored_and_stale_followthrough_are_negative_calibration_events(self) -> None:
        ignored = build_followthrough_event(
            route_id="route:apw",
            outcome="action_ignored",
            scope_bucket="project",
        )
        stale = build_followthrough_event(
            route_id="route:apw",
            outcome="stale_route",
            scope_bucket="project",
            freshness="stale",
        )

        self.assertEqual(ignored["signal"], "ignored")
        self.assertTrue(ignored["negative"])
        self.assertEqual(stale["signal"], "superseded")
        self.assertEqual(stale["freshness"], "stale")
        self.assertTrue(stale["negative"])

    def test_append_followthrough_event_writes_public_safe_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feedback.jsonl"
            event = build_followthrough_event(
                route_id="route:apw",
                outcome="manual_search_needed_first",
                scope_bucket="project",
                note="looked elsewhere before APW helped",
            )
            receipt = append_followthrough_event(path, event)

            row = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(receipt["ok"])
        self.assertFalse(receipt["path_written"])
        self.assertEqual(row["signal"], "wrong_route_drag")
        self.assertEqual(row["claim_boundary"], "feedback_is_not_source_truth")

if __name__ == "__main__":
    unittest.main()
