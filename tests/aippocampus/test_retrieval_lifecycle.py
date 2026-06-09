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

from aippocampus_runtime.reflection import retrieval_lifecycle as lifecycle  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


def source_ref(line: int = 10) -> dict[str, object]:
    return {
        "thread_key": "session:retrieval-test",
        "message_id": f"msg-{line}",
        "turn_id": f"turn-{line}",
        "source_line": line,
        "timestamp": "2026-06-09T00:00:00Z",
    }


class RetrievalLifecycleTests(unittest.TestCase):
    def test_retrieval_event_requires_source_anchor_and_sanitizes_boundaries(self) -> None:
        event = lifecycle.build_retrieval_event(
            thread_id="session:retrieval-test",
            workspace=fake_test_windows_path("AIppocampus"),
            route="active_recall",
            action_grammar="reopenable_route",
            source_refs=[source_ref(11)],
            source_handle="active-lock-secret",
            retrieval_summary=(
                f"Recall {FAKE_TEST_SECRET_VALUE} from "
                f"{fake_test_windows_path('secret.txt')}"
            ),
            created_at="2026-06-09T01:00:00Z",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["kind"], lifecycle.RETRIEVAL_KIND)
        self.assertEqual(event["route"], "active_recall")
        self.assertEqual(event["source_confirmed_evidence"], False)
        self.assertEqual(event["formal_memory_promoted"], False)
        self.assertEqual(event["clean_source_mutated"], False)
        self.assertEqual(event["raw_rollout_mutated"], False)
        self.assertIn("source_key", event)
        self.assertIn("workspace_sha1", event)
        self.assertTrue(event["privacy_scan"]["redacted"])
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

        with self.assertRaises(ValueError):
            lifecycle.build_retrieval_event(
                thread_id="session:missing-source",
                workspace="AIppocampus",
                route="ambient_scent",
                action_grammar="direction_only",
                source_refs=[],
            )

    def test_append_only_projection_counts_retrievals_and_outcome_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "retrieval-lifecycle.jsonl"
            refs = [source_ref(20)]
            events = [
                lifecycle.build_retrieval_event(
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    route="active_recall",
                    action_grammar="reopenable_route",
                    source_refs=refs,
                    created_at="2026-06-09T01:00:00Z",
                ),
                lifecycle.build_retrieval_event(
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    route="source_reopen",
                    action_grammar="source_open",
                    source_refs=refs,
                    source_opened=True,
                    created_at="2026-06-09T01:03:00Z",
                ),
                lifecycle.build_outcome_event(
                    retrieval_event_id="retrieval-manual",
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    source_refs=refs,
                    outcome_category="pinned",
                    created_at="2026-06-09T01:05:00Z",
                ),
                lifecycle.build_outcome_event(
                    retrieval_event_id="retrieval-manual",
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    source_refs=refs,
                    outcome_category="superseded",
                    created_at="2026-06-09T01:06:00Z",
                ),
            ]

            lifecycle.append_events(events_path, events)
            report = lifecycle.lifecycle_report(events_path=events_path)

        source = report["sources"][0]
        self.assertEqual(source["retrieval_count"], 2)
        self.assertEqual(source["source_open_count"], 1)
        self.assertEqual(source["source_confirmed_evidence_count"], 1)
        self.assertEqual(source["last_retrieved_at"], "2026-06-09T01:03:00Z")
        self.assertEqual(source["outcome_categories"]["opened"], 1)
        self.assertEqual(source["outcome_categories"]["pinned"], 1)
        self.assertEqual(source["outcome_categories"]["superseded"], 1)
        self.assertIn("active_recall", source["routes"])
        self.assertIn("source_reopen", source["routes"])
        self.assertNotIn("source_refs", source)
        self.assertIn(
            "retrieval_count_is_not_memory_correctness",
            report["cannot_claim"],
        )

    def test_prompt_direction_only_scent_is_not_source_confirmed_evidence(self) -> None:
        prompt_result = {
            "decision": "scent",
            "semantic_source_reopen_route": True,
            "candidates": [
                {
                    "thread_key": "session:retrieval-test",
                    "title": "Navigation candidate",
                    "source_refs": [source_ref(30)],
                }
            ],
            "evidence": [],
        }

        events = lifecycle.events_from_prompt_recall_result(
            prompt_result,
            thread_id="session:retrieval-test",
            workspace="AIppocampus",
            created_at="2026-06-09T01:10:00Z",
        )
        report = lifecycle.lifecycle_projection(events)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["route"], "prompt_hook_scent")
        self.assertEqual(events[0]["action_grammar"], "direction_only")
        self.assertEqual(events[0]["source_opened"], False)
        self.assertEqual(events[0]["source_confirmed_evidence"], False)
        self.assertEqual(report["sources"][0]["source_confirmed_evidence_count"], 0)

    def test_active_and_mcp_adapters_mark_evidence_only_after_source_open(self) -> None:
        active_context = {
            "kind": "aippocampus_agent_initiated_recall_context",
            "source_reopen_routes": [source_ref(40)],
        }
        mcp_deepen = {
            "kind": "aippocampus_recall_deepen",
            "support_level": "evidence",
            "evidence_level": "source_backed",
            "source_refs": [source_ref(40)],
            "source_boundary": {"clean_source_reopened": True},
        }

        events = [
            *lifecycle.events_from_active_recall_result(
                active_context,
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                created_at="2026-06-09T01:20:00Z",
            ),
            *lifecycle.events_from_mcp_recall_result(
                "recall_deepen",
                mcp_deepen,
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                created_at="2026-06-09T01:21:00Z",
            ),
        ]
        report = lifecycle.lifecycle_projection(events)

        self.assertEqual([event["source_confirmed_evidence"] for event in events], [False, True])
        self.assertEqual(report["sources"][0]["retrieval_count"], 2)
        self.assertEqual(report["sources"][0]["source_open_count"], 1)

    def test_public_report_omits_private_refs_paths_and_raw_prompt_text(self) -> None:
        event = lifecycle.build_retrieval_event(
            thread_id="session:retrieval-test",
            workspace=fake_test_windows_path("AIppocampus"),
            route="ambient_scent",
            action_grammar="direction_only",
            source_refs=[source_ref(50)],
            retrieval_summary=(
                f"raw prompt should not leak {FAKE_TEST_SECRET_VALUE} "
                f"{fake_test_windows_path('secret.txt')}"
            ),
        )
        report = lifecycle.lifecycle_projection([event])
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("msg-50", encoded)
        self.assertNotIn("turn-50", encoded)
        self.assertNotIn("session:retrieval-test", encoded)
        self.assertNotIn("raw prompt should not leak", encoded)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)


if __name__ == "__main__":
    unittest.main()
