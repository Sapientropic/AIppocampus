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
                "command_family": "python_pytest",
                "test_target_class": "focused_test_path",
                "exit_code": 1,
                "status": "failed",
                "failure_family": "assertion_failure",
                "behavior_backed": True,
                "input_sha256": "a" * 64,
                "observation_sha256": "b" * 64,
                "path_categories": ["test", "source"],
                "generated_file": False,
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
        self.assertEqual(fact["command_family"], "python_pytest")
        self.assertEqual(fact["target_class"], "focused_test_path")
        self.assertEqual(fact["exit_status"], 1)
        self.assertEqual(fact["failure_family"], "assertion_failure")
        self.assertEqual(fact["path_categories"], ["test", "source"])
        self.assertEqual(fact["generated_file"], False)
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

    def test_placeholder_event_id_becomes_weak_covered(self) -> None:
        self.write_events(
            {
                "event_id": "unknown",
                "source_ref": "codex:session:demo#L31",
                "source_line": 31,
                "critical_operation_family": "explicit_user_constraint",
                "constraint_kind": "do_not_touch_generated_files",
                "scope": "active_task",
                "expiry_or_supersession": "until_next_user_override",
                "status": "active",
            }
        )

        report = diagnose_clean_source(self.clean_source)
        family = self.family(report, "explicit_user_constraint")

        self.assertEqual(family["status"], "weak_covered")
        self.assertFalse(report["contract_complete"])
        self.assertTrue(report["ordinary_recall_allowed"])
        self.assertEqual(report["coverage_summary"]["weak_covered_family_count"], 1)
        self.assertIn(
            {"code": "placeholder_value", "field": "event_id", "event_id": "unknown"},
            family["facts"][0]["validation_reasons"],
        )

    def test_private_source_ref_becomes_weak_covered_without_leaking_value(self) -> None:
        self.write_events(
            {
                "event_id": "evt_private_source_ref",
                "source_ref": "C:\\Users\\Administrator\\secret\\thread.jsonl",
                "source_line": 34,
                "critical_operation_family": "test_check_command_result",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 0,
                "failure_family": "none",
                "status": "succeeded",
            }
        )

        report = diagnose_clean_source(self.clean_source)
        family = self.family(report, "test_check_command_result")
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertEqual(family["status"], "weak_covered")
        self.assertIn(
            {
                "code": "private_source_ref",
                "field": "source_ref",
                "event_id": "evt_private_source_ref",
            },
            family["facts"][0]["validation_reasons"],
        )
        self.assertEqual(report["privacy"]["issues"][0]["field"], "source_ref")
        self.assertNotIn("Administrator", serialized)
        self.assertNotIn("thread.jsonl", serialized)

    def test_implausible_exit_status_becomes_weak_covered(self) -> None:
        self.write_events(
            {
                "event_id": "evt_implausible_exit",
                "source_ref": "codex:session:demo#L36",
                "source_line": 36,
                "critical_operation_family": "test_check_command_result",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 9_999_999_999,
                "failure_family": "nonzero_exit",
                "status": "failed",
            }
        )

        report = diagnose_clean_source(self.clean_source)
        family = self.family(report, "test_check_command_result")

        self.assertEqual(family["status"], "weak_covered")
        self.assertEqual(family["facts"][0]["exit_status"], 9_999_999_999)
        self.assertIn(
            {
                "code": "implausible_exit_status",
                "field": "exit_status",
                "event_id": "evt_implausible_exit",
            },
            family["facts"][0]["validation_reasons"],
        )

    def test_explicit_file_edit_requires_safe_path_identity(self) -> None:
        self.write_events(
            {
                "event_id": "evt_file_edit",
                "source_id": "src_test",
                "source_ref": "codex:session:demo#L20",
                "critical_operation_family": "file_edit_write_attempt",
                "path_fingerprints": ["sha256:abc123def4567890"],
                "path_categories": ["source"],
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
            family["facts"][0]["path_fingerprints"], ["sha256:abc123def4567890"]
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("C:\\Users", serialized)
        self.assertEqual(report["privacy"]["issues"], [])

    def test_privacy_scan_checks_new_breadcrumb_lists(self) -> None:
        self.write_events(
            {
                "event_id": "evt_bad_breadcrumb",
                "source_id": "src_test",
                "source_ref": "codex:session:demo#L25",
                "critical_operation_family": "file_edit_write_attempt",
                "path_fingerprints": ["sha256:abc123def4567890", "C:\\Users\\Administrator\\secret.py"],
                "path_categories": ["source"],
                "generated_file": False,
                "status": "succeeded",
                "behavior_backed": True,
            }
        )

        report = diagnose_clean_source(self.clean_source)

        self.assertEqual(report["privacy"]["issues"][0]["field"], "path_fingerprints")
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("secret.py", serialized)


if __name__ == "__main__":
    unittest.main()
