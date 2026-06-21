from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.reflection import retrieval_lifecycle as lifecycle
from aippocampus_runtime.reflection import retrieval_reconsolidation as recon
from tests.aippocampus.redaction_fixtures import (
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

    def test_retrieval_reconsolidation_candidates_are_reviewable_not_memory_updates(self) -> None:
        superseded_retrieval = lifecycle.build_retrieval_event(
            event_id="retr_old_preference",
            thread_id="session:retrieval-test",
            workspace="AIppocampus",
            route="active_recall",
            action_grammar="reopenable_route",
            source_refs=[source_ref(60)],
        )
        refuted_retrieval = lifecycle.build_retrieval_event(
            event_id="retr_old_route",
            thread_id="session:retrieval-test",
            workspace="AIppocampus",
            route="prompt_hook_evidence",
            action_grammar="bounded_evidence",
            source_refs=[source_ref(70)],
            source_opened=True,
        )
        current_retrieval = lifecycle.build_retrieval_event(
            event_id="retr_current_constraint",
            thread_id="session:retrieval-test",
            workspace="AIppocampus",
            route="recall_deepen",
            action_grammar="source_open",
            source_refs=[source_ref(80)],
            source_opened=True,
        )
        events = [
            superseded_retrieval,
            lifecycle.build_outcome_event(
                retrieval_event_id="retr_old_preference",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                source_refs=[source_ref(61)],
                outcome_category="superseded",
            ),
            refuted_retrieval,
            lifecycle.build_outcome_event(
                retrieval_event_id="retr_old_route",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                source_refs=[source_ref(71)],
                outcome_category="refuted",
            ),
            current_retrieval,
            lifecycle.build_outcome_event(
                retrieval_event_id="retr_current_constraint",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                source_refs=[source_ref(81)],
                outcome_category="still_current",
            ),
        ]

        candidates = recon.build_reconsolidation_candidates(events)
        report = recon.reconsolidation_projection(events)

        self.assertEqual(
            {candidate["candidate_type"] for candidate in candidates},
            {
                "supersession_candidate",
                "refuted_recall_candidate",
                "still_current_candidate",
            },
        )
        self.assertEqual(report["reconsolidation_counts"]["activated"], 3)
        self.assertEqual(report["reconsolidation_counts"]["used"], 1)
        self.assertEqual(report["reconsolidation_counts"]["conflicted"], 2)
        self.assertEqual(report["reconsolidation_counts"]["superseded"], 1)
        self.assertEqual(report["reconsolidation_counts"]["refuted"], 1)
        self.assertEqual(report["reconsolidation_counts"]["still_current"], 1)
        for candidate in candidates:
            self.assertEqual(candidate["kind"], recon.RECONSOLIDATION_CANDIDATE_KIND)
            self.assertEqual(candidate["review_state"], "staging")
            self.assertEqual(candidate["truth_status"], "reviewable_candidate_not_memory_truth")
            self.assertEqual(candidate["formal_memory_promoted"], False)
            self.assertEqual(candidate["source_update_performed"], False)
            self.assertEqual(candidate["clean_source_mutated"], False)
            self.assertEqual(candidate["raw_rollout_mutated"], False)
            self.assertTrue(candidate["source_refs"])

    def test_revision_candidate_is_emitted_for_conflicted_old_recall(self) -> None:
        events = [
            lifecycle.build_retrieval_event(
                event_id="retr_stale_constraint",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                route="ambient_scent",
                action_grammar="direction_with_ref",
                source_refs=[source_ref(90)],
            ),
            lifecycle.build_outcome_event(
                retrieval_event_id="retr_stale_constraint",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                source_refs=[source_ref(91)],
                outcome_category="conflicted",
            ),
        ]

        [candidate] = recon.build_reconsolidation_candidates(events)

        self.assertEqual(candidate["candidate_type"], "revision_candidate")
        self.assertEqual(candidate["correction_adjudication_status"], "uncertain")
        self.assertEqual(candidate["correction_route"], "confirm_when_relevant")
        self.assertIn("retrieval_conflict_observed", candidate["reason_codes"])
        self.assertEqual(candidate["source_update_performed"], False)

    def test_reconsolidation_no_write_report_counts_without_writing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_path = root / "retrieval-lifecycle.jsonl"
            output_path = root / "retrieval-reconsolidation-candidates.jsonl"
            events = [
                lifecycle.build_retrieval_event(
                    event_id="retr_superseded",
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    route="active_recall",
                    action_grammar="reopenable_route",
                    source_refs=[source_ref(100)],
                ),
                lifecycle.build_outcome_event(
                    retrieval_event_id="retr_superseded",
                    thread_id="session:retrieval-test",
                    workspace="AIppocampus",
                    source_refs=[source_ref(101)],
                    outcome_category="superseded",
                ),
            ]
            lifecycle.append_events(events_path, events)

            report = recon.run_reconsolidation_review(
                events_path=events_path,
                output_path=output_path,
                no_write=True,
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = lifecycle.main(
                    [
                        "--events-input",
                        str(events_path),
                        "--output",
                        str(output_path),
                        "--reconsolidation-review",
                        "--no-write",
                        "--json",
                    ]
                )

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["wrote_count"], 0)
        self.assertEqual(report["no_write"], True)
        self.assertFalse(output_path.exists())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["reconsolidation_counts"]["superseded"], 1)
        self.assertIn("retrieval_reconsolidation_does_not_update_source_truth", report["cannot_claim"])

    def test_reconsolidation_candidates_require_source_refs_even_when_source_key_exists(self) -> None:
        events = [
            lifecycle.build_retrieval_event(
                event_id="retr_source_key_only",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                route="active_recall",
                action_grammar="reopenable_route",
                source_refs=[],
                source_key="source-key-only",
            ),
            lifecycle.build_outcome_event(
                retrieval_event_id="retr_source_key_only",
                thread_id="session:retrieval-test",
                workspace="AIppocampus",
                source_refs=[],
                source_key="source-key-only",
                outcome_category="superseded",
            ),
        ]

        candidates = recon.build_reconsolidation_candidates(events)
        report = recon.reconsolidation_projection(events)

        self.assertEqual(candidates, [])
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["reconsolidation_counts"]["blocked_missing_source_refs"], 1)

if __name__ == "__main__":
    unittest.main()
