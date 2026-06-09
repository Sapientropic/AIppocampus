from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.reflection import consolidation_priority as priority  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


def source_ref(line: int = 10) -> dict[str, object]:
    return {
        "thread_key": "session:priority-test",
        "message_id": f"msg-{line}",
        "turn_id": f"turn-{line}",
        "source_line": line,
        "timestamp": "2026-06-09T02:00:00Z",
    }


class ConsolidationPriorityTests(unittest.TestCase):
    def test_event_requires_source_or_behavior_anchor_and_sanitizes_private_fields(self) -> None:
        event = priority.build_consolidation_priority_event(
            thread_id="session:priority-test",
            workspace=fake_test_windows_path("AIppocampus"),
            producer="correction",
            source_refs=[source_ref(11)],
            behavior_event_ids=["behavior-secret-id"],
            signals=[
                {
                    "signal_type": "correction",
                    "strength": 1.0,
                    "summary": (
                        f"Do not keep {FAKE_TEST_SECRET_VALUE} from "
                        f"{fake_test_windows_path('secret.txt')}"
                    ),
                }
            ],
            created_at="2026-06-09T02:10:00Z",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["kind"], priority.EVENT_KIND)
        self.assertEqual(event["producer"], "correction")
        self.assertGreaterEqual(event["effective_priority_score"], 0.8)
        self.assertEqual(event["review_queue_eligible"], True)
        self.assertEqual(event["formal_memory_promoted"], False)
        self.assertEqual(event["foreground_evidence"], False)
        self.assertIn("source_key", event)
        self.assertIn("workspace_sha1", event)
        self.assertTrue(event["privacy_scan"]["redacted"])
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

        with self.assertRaises(ValueError):
            priority.build_consolidation_priority_event(
                thread_id="session:missing-anchor",
                workspace="AIppocampus",
                producer="frontier_question",
                signals=[{"signal_type": "ordinary_turn", "strength": 0.1}],
            )

    def test_projection_prioritizes_high_value_awake_moments_and_skips_low_signal(self) -> None:
        high = priority.build_consolidation_priority_event(
            thread_id="session:priority-test",
            workspace="AIppocampus",
            producer="rejected_route",
            source_refs=[source_ref(20)],
            signals=[
                {"signal_type": "rejected_route", "strength": 1.0},
                {"signal_type": "failed_test", "strength": 0.6},
            ],
            created_at="2026-06-09T02:20:00Z",
        )
        medium = priority.build_consolidation_priority_event(
            thread_id="session:priority-test",
            workspace="AIppocampus",
            producer="cognitive_load",
            source_refs=[source_ref(21)],
            signals=[
                {"signal_type": "cognitive_load", "strength": 0.8},
                {"signal_type": "frontier_question", "strength": 0.5},
            ],
            created_at="2026-06-09T02:21:00Z",
        )
        low = priority.build_consolidation_priority_event(
            thread_id="session:priority-test",
            workspace="AIppocampus",
            producer="frontier_question",
            source_refs=[source_ref(22)],
            signals=[{"signal_type": "ordinary_turn", "strength": 0.2}],
            created_at="2026-06-09T02:22:00Z",
        )

        report = priority.priority_queue_projection([low, medium, high])
        queue = report["review_queue"]

        self.assertEqual(report["event_count"], 3)
        self.assertEqual([item["producer"] for item in queue], ["rejected_route", "cognitive_load"])
        self.assertGreater(queue[0]["effective_priority_score"], queue[1]["effective_priority_score"])
        self.assertEqual(report["producer_counts"]["frontier_question"], 1)
        self.assertIn("rejected_route", queue[0]["priority_reasons"])
        self.assertIn("failed_test", queue[0]["priority_reasons"])
        self.assertIn("cognitive_load", queue[1]["priority_reasons"])

    def test_stale_missing_superseded_or_blocked_sources_degrade_without_queueing(self) -> None:
        for state in ("stale", "missing", "superseded", "blocked"):
            event = priority.build_consolidation_priority_event(
                thread_id="session:priority-test",
                workspace="AIppocampus",
                producer="source_conflict",
                source_refs=[source_ref(30)],
                source_state=state,
                signals=[{"signal_type": "source_conflict", "strength": 1.0}],
            )
            self.assertEqual(event["degraded"], True)
            self.assertEqual(event["review_queue_eligible"], False)
            self.assertEqual(event["effective_priority_score"], 0.0)

        report = priority.priority_queue_projection(
            [
                priority.build_consolidation_priority_event(
                    thread_id="session:priority-test",
                    workspace="AIppocampus",
                    producer="source_conflict",
                    source_refs=[source_ref(31)],
                    source_state="blocked",
                    signals=[{"signal_type": "source_conflict", "strength": 1.0}],
                )
            ]
        )
        self.assertEqual(report["review_queue"], [])
        self.assertEqual(report["degraded_count"], 1)
        self.assertIn("priority_event_is_not_source_truth", report["cannot_claim"])

    def test_row_adapters_explain_priority_signal_families(self) -> None:
        rows = [
            {
                "kind": "behavior_event",
                "event_id": "evt-rejected",
                "event_type": "rejected_route",
                "source_refs": [source_ref(40)],
            },
            {
                "finding_kind": "frontier_marker",
                "source_refs": [source_ref(41)],
                "confidence": 0.9,
            },
            {
                "kind": "cognitive_load_signal",
                "signal_type": "failed_command",
                "load_score": 0.8,
                "source_refs": [source_ref(42)],
            },
        ]

        events = priority.events_from_candidate_rows(
            rows,
            thread_id="session:priority-test",
            workspace="AIppocampus",
            created_at="2026-06-09T02:30:00Z",
        )
        report = priority.priority_queue_projection(events)

        self.assertEqual(len(events), 3)
        self.assertEqual(
            [event["producer"] for event in events],
            ["rejected_route", "frontier_question", "failure"],
        )
        reasons = {reason for item in report["review_queue"] for reason in item["priority_reasons"]}
        self.assertIn("rejected_route", reasons)
        self.assertIn("frontier_question", reasons)
        self.assertIn("failed_command", reasons)

    def test_append_only_public_report_omits_raw_refs_and_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "consolidation-priority.jsonl"
            events = [
                priority.build_consolidation_priority_event(
                    thread_id="session:priority-test",
                    workspace=fake_test_windows_path("AIppocampus"),
                    producer="failure",
                    source_refs=[source_ref(50)],
                    signals=[
                        {
                            "signal_type": "failed_test",
                            "strength": 1.0,
                            "summary": f"{FAKE_TEST_SECRET_VALUE} raw prompt should not leak",
                        }
                    ],
                )
            ]
            events[0]["raw_prompt"] = f"persisting this would leak {FAKE_TEST_SECRET_VALUE}"
            events[0]["api_secret"] = FAKE_TEST_SECRET_VALUE
            priority.append_events(events_path, events)
            stored = events_path.read_text(encoding="utf-8")
            report = priority.priority_report(events_path=events_path)

        encoded = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["review_queue"][0]["producer"], "failure")
        self.assertNotIn('"raw_prompt":', stored)
        self.assertNotIn('"api_secret":', stored)
        self.assertNotIn("persisting this would leak", stored)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, stored)
        self.assertNotIn("msg-50", encoded)
        self.assertNotIn("turn-50", encoded)
        self.assertNotIn("session:priority-test", encoded)
        self.assertNotIn("raw prompt should not leak", encoded)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)


if __name__ == "__main__":
    unittest.main()
