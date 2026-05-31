from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import coding_decision_events as decisions  # noqa: E402
import coding_rejected_route_probes as probes  # noqa: E402


def message(*, text: str, line: int, message_id: str = "m1") -> dict[str, object]:
    return {
        "message_id": message_id,
        "turn_id": f"t{line}",
        "source_id": "src-test",
        "clean_ordinal": line,
        "source_line": line,
        "role": "user",
        "timestamp": "2026-05-01T00:00:00Z",
        "text": text,
    }


def validation_row(target: str, status: str, *, created_at: str = "2026-05-20T00:00:00Z") -> dict[str, object]:
    return {
        "kind": "coding_decision_event",
        "event_type": "rejected_route_reopened",
        "target_finding_id": target,
        "validation_status": status,
        "created_at": created_at,
        "source_refs": [
            {
                "thread_key": f"session:{target}",
                "message_id": f"msg-{target}-{status}",
                "line": 30,
                "project_label": "AIppocampus",
            }
        ],
    }


def rejected_event(text: str, line: int, *, created_at: str = "2026-05-01T00:00:00Z") -> dict[str, object]:
    event = decisions.review_decision_candidates(
        decisions.extract_decision_candidates(
            [message(text=text, line=line, message_id=f"m{line}")],
            thread_key=f"session:decision-{line}",
            workspace="AIppocampus",
        )
    )[0]
    event["created_at"] = created_at
    return event


class CodingRejectedRouteProbeTests(unittest.TestCase):
    def test_rejected_route_event_creates_source_anchored_prospective_probe(self) -> None:
        event = rejected_event(
            "Do not replace source refs with summary-only retrieval in retrieval.py.",
            1,
        )

        probe = probes.build_rejected_route_probe(
            event,
            review_after_days=1,
            expiry_days=30,
        )
        encoded = json.dumps(probe, ensure_ascii=False)

        self.assertEqual(probe["finding_kind"], "dream_synthesized")
        self.assertEqual(probe["dream_function"], "prospective")
        self.assertEqual(probe["probe_family"], "coding_rejected_route")
        self.assertEqual(probe["review_state"], "needs_review")
        self.assertEqual(probe["adjudication_result"]["status"], "parked")
        self.assertFalse(probe["foreground_eligible"])
        self.assertFalse(probe["formal_memory_eligible"])
        self.assertTrue(probe["source_refs"])
        self.assertTrue(probe["bridge_claims"][0]["source_refs"])
        self.assertIn("what evidence would justify reopening", probe["summary"].casefold())
        self.assertNotIn("future_source", encoded)

    def test_fixture_replay_distinguishes_statuses_without_future_leakage(self) -> None:
        events = [
            rejected_event("Do not use route alpha.", 1),
            rejected_event("Do not use route beta.", 2),
            rejected_event("Do not use route gamma.", 3),
            rejected_event("Do not use route delta.", 4),
        ]
        generated = probes.build_rejected_route_probes(events, review_after_days=1, expiry_days=10)
        by_route = {probe["source_decision_id"]: probe["fingerprint"] for probe in generated}
        later_rows = [
            validation_row(by_route[str(events[0]["decision_id"])], "supported"),
            validation_row(by_route[str(events[1]["decision_id"])], "refuted"),
            validation_row(by_route[str(events[0]["decision_id"])], "supported", created_at="2026-06-30T00:00:00Z"),
            {
                "kind": "coding_decision_event",
                "title": "route delta appears as similar vocabulary only",
                "created_at": "2026-05-20T00:00:00Z",
                "source_refs": [{"thread_key": "session:overlap", "message_id": "msg-overlap", "line": 99}],
            },
        ]

        payload = probes.run_rejected_route_fixture(
            events,
            later_rows,
            now="2026-05-30T00:00:00Z",
            review_after_days=1,
            expiry_days=10,
        )
        summary = probes.public_fixture_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(
            payload["metrics"]["status_counts"],
            {"refuted": 1, "stale": 2, "supported": 1},
        )
        self.assertEqual(payload["metrics"]["ignored_after_now"], 1)
        self.assertGreaterEqual(payload["metrics"]["term_overlap_without_target"], 1)
        self.assertEqual(summary["status_counts"]["supported"], 1)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)

    def test_fixture_ignores_non_rejected_events(self) -> None:
        accepted = {
            "kind": decisions.DECISION_KIND,
            "finding_kind": "decision_event",
            "decision_id": "accepted_decision",
            "event_type": "accepted_decision",
            "rejected_paths": [],
            "source_refs": [
                {
                    "thread_key": "session:accepted",
                    "message_id": "msg-accepted",
                    "line": 5,
                    "project_label": "AIppocampus",
                }
            ],
        }

        generated = probes.build_rejected_route_probes([accepted])

        self.assertEqual(generated, [])


if __name__ == "__main__":
    unittest.main()
