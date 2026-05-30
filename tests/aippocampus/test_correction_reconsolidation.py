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

import correction_reconsolidation as corr  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


def source_ref(line: int = 10) -> dict[str, object]:
    return {
        "thread_key": "session:correction-test",
        "message_id": f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-05-30T00:00:00Z",
    }


def activation_for(status: str) -> dict[str, object]:
    return corr.build_activation_event(
        event_id=f"act_{status}",
        thread_id="session:correction-test",
        workspace="AIppocampus",
        topic_epoch="epoch-1",
        correction_surface=f"Correction surface for {status}",
        source_refs=[source_ref(10)],
        target_type="route",
        provisional_importance="active_task",
    )


def outcome_for(status: str, *, activation_id: str | None = None) -> dict[str, object]:
    signal = {
        "valid_adopted": "adopted",
        "valid_ignored": "ignored",
        "refuted": "contradicted",
        "superseded": "unclear",
        "local_only": "adopted",
        "uncertain": "unclear",
    }[status]
    return corr.build_outcome_event(
        event_id=f"out_{status}",
        activation_event_id=activation_id or f"act_{status}",
        thread_id="session:correction-test",
        workspace="AIppocampus",
        topic_epoch="epoch-1",
        outcome_summary=f"Outcome evidence for {status}",
        source_refs=[source_ref(20)],
        adoption_signal=signal,
        adjudication_hint=status,
        changed_files=["docs/research/correction-reconsolidation.md"],
        verification_evidence=[{"kind": "test", "status": "passed", "summary": "fixture passed"}],
    )


class CorrectionReconsolidationTests(unittest.TestCase):
    def test_activation_event_is_source_backed_and_privacy_scanned(self) -> None:
        event = corr.build_activation_event(
            thread_id="session:correction-test",
            workspace=fake_test_windows_path("AIppocampus"),
            topic_epoch="epoch-1",
            correction_surface=(
                f"Use the docs route, not token={FAKE_TEST_SECRET_VALUE} "
                f"or {fake_test_windows_path('secret.txt')}"
            ),
            source_refs=[source_ref(11)],
            target_type="scope",
            provisional_importance="active_task",
        )

        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["kind"], corr.ACTIVATION_KIND)
        self.assertEqual(event["source_refs"][0]["thread_key"], "session:correction-test")
        self.assertEqual(event["formal_memory_promoted"], False)
        self.assertEqual(event["review_required"], True)
        self.assertTrue(event["privacy_scan"]["redacted"])
        self.assertEqual(event["privacy_scan"]["raw_text_stored"], False)
        self.assertIn("workspace_sha1", event)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_event_builders_require_source_refs(self) -> None:
        with self.assertRaises(ValueError):
            corr.build_activation_event(
                thread_id="session:missing-source",
                workspace="AIppocampus",
                topic_epoch="epoch-1",
                correction_surface="No source refs.",
                source_refs=[],
                target_type="claim",
            )

        with self.assertRaises(ValueError):
            corr.build_outcome_event(
                activation_event_id="act_missing",
                thread_id="session:missing-source",
                workspace="AIppocampus",
                topic_epoch="epoch-1",
                outcome_summary="No source refs.",
                source_refs=[],
                adoption_signal="unclear",
            )

    def test_outcome_event_sanitizes_evidence_and_changed_file_hints(self) -> None:
        event = corr.build_outcome_event(
            activation_event_id="act_one",
            thread_id="session:correction-test",
            workspace=r"E:\repo\AIppocampus",
            topic_epoch="epoch-1",
            outcome_summary=f"Final claim omitted Bearer {FAKE_TEST_BEARER_TOKEN}.",
            source_refs=[source_ref(21)],
            adoption_signal="adopted",
            changed_files=[
                r"E:\repo\AIppocampus\docs\research\correction-reconsolidation.md",
                fake_test_windows_path("outcome.txt"),
            ],
            verification_evidence=[
                {
                    "kind": "test",
                    "status": "passed",
                    "summary": f"pytest passed with Bearer {FAKE_TEST_BEARER_TOKEN}",
                }
            ],
            tool_evidence=[f"tool output used {fake_test_windows_path('tool.txt')}"],
        )

        encoded = json.dumps(event, ensure_ascii=False)
        file_kinds = {item["path_kind"] for item in event["changed_files"]}
        relative_paths = {item.get("path") for item in event["changed_files"]}

        self.assertIn("repo_relative", file_kinds)
        self.assertIn("redacted_local_path", file_kinds)
        self.assertIn("docs/research/correction-reconsolidation.md", relative_paths)
        self.assertTrue(event["privacy_scan"]["redacted"])
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_append_events_is_append_only(self) -> None:
        activation = activation_for("valid_adopted")
        outcome = outcome_for("valid_adopted")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "correction-events.jsonl"

            self.assertEqual(corr.append_events(path, [activation]), 1)
            first_snapshot = path.read_text(encoding="utf-8")
            self.assertEqual(corr.append_events(path, [outcome]), 1)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(first_snapshot.splitlines()[0], lines[0])
        self.assertEqual(json.loads(lines[0])["kind"], corr.ACTIVATION_KIND)
        self.assertEqual(json.loads(lines[1])["kind"], corr.OUTCOME_KIND)

    def test_adjudication_statuses_and_active_anchor_suppression(self) -> None:
        statuses = {
            "valid_adopted",
            "valid_ignored",
            "refuted",
            "superseded",
            "local_only",
            "uncertain",
        }
        events: list[dict[str, object]] = []
        for status in statuses:
            events.append(activation_for(status))
            events.append(outcome_for(status))

        candidates = corr.adjudicate_events(events)
        candidate_statuses = {candidate["adjudication_status"] for candidate in candidates}
        anchors = corr.render_active_task_anchors(candidates, context_state="horizon_lost")
        visible_anchors = corr.render_active_task_anchors(candidates, context_state="visible")
        repeated_anchors = corr.render_active_task_anchors(
            candidates,
            context_state="horizon_lost",
            already_injected_event_ids={"act_valid_adopted", "act_valid_ignored"},
        )

        self.assertLessEqual(statuses, candidate_statuses)
        self.assertEqual(
            {anchor["adjudication_status"] for anchor in anchors},
            {"valid_adopted", "valid_ignored"},
        )
        self.assertEqual(visible_anchors, [])
        self.assertEqual(repeated_anchors, [])
        self.assertTrue(corr.SUPPRESS_ANCHOR_STATUSES.isdisjoint({a["adjudication_status"] for a in anchors}))

    def test_run_adjudication_writes_candidate_hypotheses_without_promoting_memory(self) -> None:
        activation = corr.build_activation_event(
            event_id="act_candidate",
            thread_id="session:correction-test",
            workspace="AIppocampus",
            topic_epoch="epoch-1",
            correction_surface=f"Keep the correction but not token={FAKE_TEST_SECRET_VALUE}",
            source_refs=[source_ref(31)],
            target_type="handoff",
            provisional_importance="active_task",
        )
        outcome = corr.build_outcome_event(
            event_id="out_candidate",
            activation_event_id="act_candidate",
            thread_id="session:correction-test",
            workspace="AIppocampus",
            topic_epoch="epoch-1",
            outcome_summary="The final answer adopted the handoff correction.",
            source_refs=[source_ref(32)],
            adoption_signal="adopted",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_path = root / "events.jsonl"
            output_path = root / "adjudication.jsonl"
            corr.append_events(events_path, [activation, outcome])

            result = corr.run_adjudication(
                events_path=events_path,
                output_path=output_path,
                context_state="horizon_lost",
            )
            row = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

        encoded = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["wrote_count"], 1)
        self.assertEqual(row["kind"], corr.ADJUDICATION_KIND)
        self.assertEqual(row["truth_status"], "candidate_hypothesis_until_reviewed")
        self.assertEqual(row["formal_memory_promoted"], False)
        self.assertEqual(row["artifact_boundary"]["formal_memory"], False)
        self.assertEqual(result["anchors"][0]["kind"], corr.ACTIVE_ANCHOR_KIND)
        self.assertIn("live_hook_capture", result["cannot_claim"])
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)


if __name__ == "__main__":
    unittest.main()
