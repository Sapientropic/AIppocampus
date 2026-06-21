from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.reflection import host_capture
from aippocampus_runtime.reflection import reconsolidation as corr
from tests.aippocampus.redaction_fixtures import (
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

    def test_texture_evidence_enriches_outcome_reconstruction_without_raw_payloads(self) -> None:
        activation = corr.build_activation_event(
            event_id="act_texture",
            thread_id="session:correction-test",
            workspace="AIppocampus",
            topic_epoch="epoch-1",
            correction_surface="The rejected route should stay visible as a correction boundary.",
            source_refs=[source_ref(30)],
            target_type="route",
            provisional_importance="active_task",
        )
        outcome = corr.build_outcome_event(
            event_id="out_texture",
            activation_event_id="act_texture",
            thread_id="session:correction-test",
            workspace="AIppocampus",
            topic_epoch="epoch-1",
            outcome_summary="The later outcome still needs adjudication.",
            source_refs=[source_ref(31)],
            adoption_signal="unclear",
            texture_evidence=[
                {
                    "kind": "aippocampus_source_texture",
                    "texture_id": "tex_tool_failure",
                    "signal_kind": "tool_failure_texture",
                    "signal_detail": "verification_failure",
                    "signal_labels": [
                        "tool_failure",
                        fake_test_windows_path("texture.txt"),
                        f"Bearer {FAKE_TEST_BEARER_TOKEN}",
                    ],
                    "truth_boundary": "texture_signal_not_source_fact",
                    "source_refs": [source_ref(32)],
                    "event_refs": [
                        {
                            "event_id": "evt-texture",
                            "status": "failed",
                            "command_class": "test",
                            "stdout": "raw stdout should not be stored",
                        }
                    ],
                }
            ],
        )
        candidate = corr.build_adjudication_candidate(activation, outcome)
        encoded = json.dumps({"outcome": outcome, "candidate": candidate}, ensure_ascii=False)

        self.assertEqual(outcome["source_texture_consumption"]["selected_count"], 1)
        self.assertEqual(candidate["adjudication_status"], "uncertain")
        self.assertEqual(candidate["evidence"]["texture_evidence_count"], 1)
        self.assertEqual(candidate["evidence"]["texture_signal_kinds"], ["tool_failure_texture"])
        self.assertIn("msg-32", {ref.get("message_id") for ref in candidate["source_refs"]})
        self.assertNotIn("raw stdout", encoded)
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
        irrelevant_anchors = corr.render_active_task_anchors(
            candidates,
            context_state="horizon_lost",
            action_relevant=False,
        )

        self.assertLessEqual(statuses, candidate_statuses)
        self.assertEqual(
            {anchor["adjudication_status"] for anchor in anchors},
            {"valid_adopted", "valid_ignored"},
        )
        self.assertEqual(visible_anchors, [])
        self.assertEqual(repeated_anchors, [])
        self.assertEqual(irrelevant_anchors, [])
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

    def test_host_prompt_payload_creates_sanitized_activation_event_when_source_backed(self) -> None:
        result = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session:live-correction",
                "cwd": fake_test_windows_path("AIppocampus"),
                "topic_epoch": "epoch-live",
                "prompt": (
                    "Correction: use the source-backed route, not "
                    f"token={FAKE_TEST_SECRET_VALUE} or {fake_test_windows_path('private.txt')}."
                ),
                "source_refs": [source_ref(40)],
                "target_type": "route",
                "provisional_importance": "active_task",
            }
        )

        encoded = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["created"])
        self.assertEqual(result["event_kind"], corr.ACTIVATION_KIND)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["kind"], corr.ACTIVATION_KIND)
        self.assertEqual(event["hook_stage"], "UserPromptSubmit")
        self.assertEqual(event["source"], "live_host_event_capture")
        self.assertEqual(event["host_event_name"], "UserPromptSubmit")
        self.assertEqual(event["target_type"], "route")
        self.assertEqual(event["provisional_importance"], "active_task")
        self.assertTrue(event["privacy_scan"]["redacted"])
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_host_payload_without_source_refs_is_blocked_instead_of_written(self) -> None:
        result = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session:missing-source",
                "cwd": "AIppocampus",
                "prompt": "Correction: follow the newer source route.",
            }
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["reason"], "missing_source_refs")
        self.assertEqual(result["events"], [])
        self.assertIn("host_payload_without_source_refs", result["cannot_claim"])

    def test_host_stop_payload_creates_outcome_and_aggregate_buckets_without_private_text(self) -> None:
        activation_result = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session:live-correction",
                "cwd": "AIppocampus",
                "topic_epoch": "epoch-live",
                "prompt": "Correction: keep the route source-backed.",
                "source_refs": [source_ref(50)],
                "target_type": "route",
            }
        )
        activation = activation_result["events"][0]
        outcome_result = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "Stop",
                "session_id": "session:live-correction",
                "cwd": fake_test_windows_path("AIppocampus"),
                "topic_epoch": "epoch-live",
                "activation_event_id": activation["event_id"],
                "final_response": (
                    "Adopted the correction and omitted "
                    f"Bearer {FAKE_TEST_BEARER_TOKEN}."
                ),
                "source_refs": [source_ref(51)],
                "adoption_signal": "adopted",
                "changed_files": [fake_test_windows_path("secret.txt"), "docs/research/correction-reconsolidation.md"],
                "verification_evidence": [
                    {"kind": "test", "status": "passed", "summary": "targeted correction test passed"}
                ],
            }
        )
        outcome = outcome_result["events"][0]
        candidates = corr.adjudicate_events([activation, outcome])
        report = host_capture.aggregate_private_history_adjudication([activation, outcome], candidates)
        encoded = json.dumps({"outcome": outcome, "report": report}, ensure_ascii=False)

        self.assertTrue(outcome_result["created"])
        self.assertEqual(outcome["kind"], corr.OUTCOME_KIND)
        self.assertEqual(outcome["source"], "live_host_event_capture")
        self.assertEqual(outcome["host_event_name"], "Stop")
        self.assertEqual(outcome["adoption_signal"], "adopted")
        self.assertEqual(report["kind"], "aippocampus_correction_real_history_adjudication_report")
        self.assertEqual(report["privacy_boundary"]["aggregate_only"], True)
        self.assertEqual(report["privacy_boundary"]["raw_correction_text_emitted"], False)
        self.assertEqual(report["buckets"]["valid_adopted"]["count"], 1)
        self.assertEqual(report["metrics"]["activation_event_count"], 1)
        self.assertEqual(report["metrics"]["outcome_event_count"], 1)
        self.assertEqual(report["metrics"]["candidate_count"], 1)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_host_post_tool_use_failure_creates_learning_activation_when_source_backed(self) -> None:
        result = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "session:tool-failure",
                "cwd": fake_test_windows_path("AIppocampus"),
                "topic_epoch": "epoch-live",
                "tool_name": "shell_command",
                "tool_input": {"command": f"pytest {fake_test_windows_path('private_test.py')}"},
                "exit_code": 1,
                "tool_response": f"AssertionError with token {FAKE_TEST_SECRET_VALUE}",
                "source_refs": [source_ref(60)],
                "scope": "project:AIppocampus",
                "workspace_or_environment_profile": "public-ci-windows",
            }
        )
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["created"], result)
        self.assertEqual(result["event_kind"], "aippocampus_learning_activation")
        activation = result["events"][0]
        self.assertEqual(activation["activation_kind"], "tool_failure_activation")
        self.assertTrue(activation["durable_activation"])
        self.assertEqual(activation["host_event_name"], "PostToolUse")
        self.assertTrue(activation["source_reopen_required_before_claim"])
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_host_post_tool_use_expected_red_is_review_only_and_missing_source_blocks(self) -> None:
        expected_red = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "session:tool-failure",
                "tool_name": "shell_command",
                "tool_input": {"command": "pytest tests/public_fixture.py"},
                "exit_code": 1,
                "tool_response": "AssertionError",
                "expected_local_red": True,
                "source_refs": [source_ref(61)],
            }
        )
        missing_source = host_capture.capture_host_correction_event(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "session:tool-failure",
                "tool_name": "shell_command",
                "exit_code": 1,
                "tool_response": "AssertionError",
            }
        )

        self.assertTrue(expected_red["created"])
        self.assertFalse(expected_red["events"][0]["durable_activation"])
        self.assertEqual(expected_red["events"][0]["activation_status"], "review_only_expected_red")
        self.assertFalse(missing_source["created"])
        self.assertEqual(missing_source["reason"], "missing_source_refs")

if __name__ == "__main__":
    unittest.main()
