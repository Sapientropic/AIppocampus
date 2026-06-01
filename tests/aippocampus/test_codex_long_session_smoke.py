from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
sys.path.insert(0, str(SMOKE))

import smoke_codex_long_session_continuity as live_smoke  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class CodexLongSessionSmokeTests(unittest.TestCase):
    def test_correction_survival_uses_hashes_without_raw_tokens(self) -> None:
        evidence = live_smoke.correction_survival_evidence(
            "The current route code is LIVEFIXABC12345.",
            "LIVEFIXABC12345",
            "LIVEOLDABC12345",
        )

        self.assertTrue(evidence["assistant_recalled_corrected_token"])
        self.assertTrue(evidence["assistant_avoided_obsolete_token"])
        self.assertNotIn("LIVEFIXABC12345", json.dumps(evidence))
        self.assertNotIn("LIVEOLDABC12345", json.dumps(evidence))

    def test_clean_source_evidence_detects_correction_and_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            turns = root / "turns.jsonl"
            messages.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "role": "user",
                                "text": (
                                    "Correction: LIVEOLD123 is stale. "
                                    "Use LIVEFIX123 instead."
                                ),
                            }
                        ),
                        json.dumps({"role": "assistant", "text": "LIVEFIX123"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            turns.write_text(json.dumps({"turn_id": "turn-1"}) + "\n", encoding="utf-8")
            manifest = {
                "message_count": 2,
                "turn_count": 1,
                "outputs": {
                    "messages_jsonl": str(messages),
                    "turns_jsonl": str(turns),
                },
            }

            evidence = live_smoke.clean_source_evidence(
                manifest,
                corrected_token="LIVEFIX123",
                obsolete_token="LIVEOLD123",
                target_pre_compact_turns=1,
            )

        self.assertTrue(evidence["built_from_real_rollout"])
        self.assertTrue(evidence["correction_message_found"])
        self.assertTrue(evidence["recall_answer_found"])
        self.assertFalse(evidence["stale_recall_answer_found"])

    def test_report_validation_requires_compaction_and_clean_source(self) -> None:
        report = live_smoke.result_skeleton("unit-run", 2)
        report["scenario"].update(
            {
                "completed_pre_compact_turn_count": 2,
                "completed_total_turn_count": 4,
                "correction_event_observed": True,
                "compaction_observed": True,
                "recall_turn_completed": True,
                "clean_source_verified": True,
            }
        )
        report["evidence"]["turn_count"].update(
            {"pre_compact_completed": 2, "total_completed": 4}
        )
        report["evidence"]["compaction_boundary"].update(
            {
                "compact_turn_completed": True,
                "context_compaction_item_observed": True,
                "pre_compact_hook_completed": True,
                "post_compact_hook_completed": True,
                "hook_events_observed": ["postCompact", "preCompact"],
            }
        )
        report["evidence"]["correction_survival"] = {
            "assistant_recalled_corrected_token": True,
            "assistant_avoided_obsolete_token": True,
        }
        report["evidence"]["clean_source"] = {
            "built_from_real_rollout": True,
            "correction_message_found": True,
            "recall_answer_found": True,
            "stale_recall_answer_found": False,
        }

        ok, failures = live_smoke.validate_report(report)

        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_public_payload_scan_catches_local_paths(self) -> None:
        synthetic_local_path = "E:" + r"\Private\rollout.jsonl"

        found = live_smoke.sensitive_string_issues({"value": synthetic_local_path})

        self.assertEqual(found[0]["code"], "local_path_in_public_payload")
        self.assertNotIn("Private", json.dumps(found))

    def test_run_id_segment_remains_filename_safe(self) -> None:
        segment = live_smoke.safe_run_id_segment(r"..\unsafe/private id")

        self.assertEqual(segment, "unsafe-private-id")

    def test_status_classifies_missing_codex_as_host_skip_before_thread_start(self) -> None:
        self.assertTrue(
            live_smoke.classify_unavailable(
                FileNotFoundError("could not find codex on PATH"),
                thread_started=False,
            )
        )
        self.assertFalse(
            live_smoke.classify_unavailable(
                RuntimeError("compaction did not preserve correction"),
                thread_started=True,
            )
        )

    def test_status_classifies_platform_file_not_found_as_host_skip(self) -> None:
        self.assertTrue(
            live_smoke.classify_unavailable(
                FileNotFoundError("[WinError 2] 系统找不到指定的文件。"),
                thread_started=False,
            )
        )

    def test_progress_jsonl_is_append_only_and_hash_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            first = live_smoke.ProgressRecorder(
                progress,
                run_id="raw-run-id-that-must-not-leak",
                target_turn_count=5,
            )
            first.record("host_initialized", phase="host_init", host_available=True)

            second = live_smoke.ProgressRecorder(
                progress,
                run_id="raw-run-id-that-must-not-leak",
                target_turn_count=5,
            )
            second.set_thread_id("raw-thread-id-that-must-not-leak")
            second.record("thread_started", phase="thread_start", thread_started=True)

            rows = read_jsonl(progress)

        self.assertEqual([row["event"] for row in rows], ["host_initialized", "thread_started"])
        self.assertEqual(rows[0]["thread_id_sha1"], None)
        self.assertEqual(rows[1]["thread_id_sha1"], live_smoke.sha1_text("raw-thread-id-that-must-not-leak")[:16])
        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertIn("run_id_sha1", serialized)
        self.assertIn("thread_id_sha1", serialized)
        self.assertNotIn("raw-run-id-that-must-not-leak", serialized)
        self.assertNotIn("raw-thread-id-that-must-not-leak", serialized)

    def test_progress_rows_drop_sensitive_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            recorder = live_smoke.ProgressRecorder(
                progress,
                run_id="raw-progress-run",
                target_turn_count=3,
            )
            recorder.set_thread_id("raw-thread-sensitive")
            recorder.record(
                "filler_turn_completed",
                phase=r"E:\Private\turn-phase",
                turn_index=2,
                completed_pre_compact_turn_count=3,
                prompt_text="RAW PROMPT SHOULD NOT LEAK",
                assistant_text="RAW ASSISTANT SHOULD NOT LEAK",
                rollout_path=r"E:\Private\rollout-raw-thread-sensitive.jsonl",
                credential="sk-test-secret-value-1234567890",
            )

            rows = read_jsonl(progress)

        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertEqual(live_smoke.sensitive_string_issues(rows), [])
        self.assertNotIn("RAW PROMPT SHOULD NOT LEAK", serialized)
        self.assertNotIn("RAW ASSISTANT SHOULD NOT LEAK", serialized)
        self.assertNotIn("Private", serialized)
        self.assertNotIn("rollout-raw-thread-sensitive", serialized)
        self.assertNotIn("sk-test-secret-value", serialized)
        self.assertNotIn("raw-thread-sensitive", serialized)

    def test_progress_records_host_skip_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.jsonl"
            with mock.patch.object(
                live_smoke.codex_host,
                "resolve_codex_command",
                side_effect=FileNotFoundError(r"could not find codex at E:\Private\codex.exe"),
            ):
                result = live_smoke.run_real_long_session_smoke(
                    root,
                    run_id="host-skip-run",
                    target_turn_count=2,
                    progress_jsonl=progress,
                )

            rows = read_jsonl(progress)

        self.assertEqual(result["status"], live_smoke.STATUS_SKIPPED)
        self.assertEqual(rows[-1]["event"], "smoke_skipped")
        self.assertEqual(rows[-1]["phase"], "host_init")
        self.assertEqual(rows[-1]["failure_code"], "FileNotFoundError")
        self.assertNotIn("Private", json.dumps(rows, ensure_ascii=False))

    def test_progress_records_compaction_failure_phase_without_message_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            recorder = live_smoke.ProgressRecorder(
                progress,
                run_id="failure-run",
                target_turn_count=50,
            )
            recorder.set_thread_id("raw-thread-for-compaction-failure")
            recorder.record_failure(
                "smoke_failed",
                phase="compaction",
                failure=live_smoke.SmokeFailure(
                    "compact_timeout",
                    r"raw-thread-for-compaction-failure timed out near E:\Private\rollout.jsonl",
                ),
            )

            rows = read_jsonl(progress)

        self.assertEqual(rows[-1]["event"], "smoke_failed")
        self.assertEqual(rows[-1]["phase"], "compaction")
        self.assertEqual(rows[-1]["failure_code"], "compact_timeout")
        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("raw-thread-for-compaction-failure", serialized)
        self.assertNotIn("Private", serialized)
        self.assertEqual(live_smoke.sensitive_string_issues(rows), [])


if __name__ == "__main__":
    unittest.main()
