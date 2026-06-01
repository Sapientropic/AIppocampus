from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.source.operation_integrity import diagnose_clean_source  # noqa: E402


class OperationIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.clean_source = Path(self.tmp.name) / "clean-source"
        self.clean_source.mkdir()
        (self.clean_source / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source_provider": "codex",
                    "source_id": "src_test",
                    "event_lane_policy": {
                        "status": "enabled_for_codex_rollouts",
                        "raw_payload_policy": "hash_only",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.clean_source / "events.jsonl").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_events(self, *rows: dict) -> None:
        (self.clean_source / "events.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def family(self, report: dict, name: str) -> dict:
        return next(item for item in report["families"] if item["family"] == name)

    def test_missing_event_family_reports_gap_without_blocking_recall(self) -> None:
        report = diagnose_clean_source(self.clean_source)

        self.assertTrue(report["ok"])
        self.assertFalse(report["contract_complete"])
        self.assertTrue(report["ordinary_recall_allowed"])
        self.assertEqual(
            self.family(report, "source_reopen_before_risky_action")["status"], "missing"
        )
        self.assertIn(
            {
                "family": "source_reopen_before_risky_action",
                "gap_kind": "missing_event_family",
                "message": "No source-reopen-before-risky-action events were found.",
                "ordinary_recall_allowed": True,
                "downstream_rule": "Do not claim this operation family is covered; reopen source or raw audit material before strong operation claims.",
            },
            report["gaps"],
        )

    def test_test_check_fact_report_is_source_backed_and_sanitized(self) -> None:
        self.write_events(
            {
                "event_id": "evt_test_failure",
                "source_id": "src_test",
                "source_ref": "codex:session:demo#L12",
                "source_line": 12,
                "timestamp": "2026-06-01T00:00:00Z",
                "turn_index": 3,
                "event_kind": "tool_call_observed",
                "hard_event_kind": "tool_call_failed",
                "tool_name": "functions.shell_command",
                "call_ref": "abc123",
                "command_class": "test",
                "exit_code": 1,
                "status": "failed",
                "behavior_backed": True,
                "input_sha256": "a" * 64,
                "observation_sha256": "b" * 64,
                "text": "python C:\\Users\\Administrator\\secret\\tests\\test_token.py",
                "raw_command": "python tests\\aippocampus\\test_secret.py",
                "stdout": "SECRET_TOKEN=abc123",
                "stderr": "private stack trace",
            }
        )

        report = diagnose_clean_source(self.clean_source)
        family = self.family(report, "test_check_command_result")
        self.assertEqual(family["status"], "covered")
        self.assertEqual(family["event_count"], 1)
        fact = family["facts"][0]
        self.assertEqual(fact["event_id"], "evt_test_failure")
        self.assertEqual(fact["source_ref"], "codex:session:demo#L12")
        self.assertEqual(fact["command_family"], "test")
        self.assertEqual(fact["target_class"], "unknown_test_target")
        self.assertEqual(fact["exit_status"], 1)
        self.assertEqual(fact["failure_family"], "nonzero_exit")
        self.assertEqual(fact["confidence"], "behavior_backed")
        self.assertEqual(fact["input_sha256"], "a" * 64)
        self.assertEqual(fact["observation_sha256"], "b" * 64)

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("C:\\Users", serialized)
        self.assertNotIn("SECRET_TOKEN", serialized)
        self.assertNotIn("test_token.py", serialized)
        self.assertNotIn("test_secret.py", serialized)
        self.assertNotIn("python tests", serialized)
        self.assertNotIn("raw_command", serialized)
        self.assertNotIn("stdout", serialized)
        self.assertNotIn("stderr", serialized)
        self.assertNotIn(str(self.clean_source), serialized)

    def test_explicit_file_edit_requires_safe_path_identity(self) -> None:
        self.write_events(
            {
                "event_id": "evt_file_edit",
                "source_id": "src_test",
                "source_ref": "codex:session:demo#L20",
                "critical_operation_family": "file_edit_write_attempt",
                "path_identity": "repo:skills/aippocampus/scripts/example.py",
                "generated_file": False,
                "status": "succeeded",
                "behavior_backed": True,
                "path": "C:\\Users\\Administrator\\repo\\skills\\aippocampus\\scripts\\example.py",
            }
        )

        report = diagnose_clean_source(self.clean_source)
        family = self.family(report, "file_edit_write_attempt")
        self.assertEqual(family["status"], "covered")
        self.assertEqual(
            family["facts"][0]["path_identity"], "repo:skills/aippocampus/scripts/example.py"
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("C:\\Users", serialized)
        self.assertEqual(report["privacy"]["issues"], [])


if __name__ == "__main__":
    unittest.main()
