from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import log_retention  # noqa: E402


class LogRetentionTests(unittest.TestCase):
    def test_rotate_log_compresses_current_file_and_keeps_recent_backups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "logs" / "build_associations_hook.log"
            log.parent.mkdir()
            log.write_bytes(b"old diagnostic bytes" * 8)
            (log.parent / "build_associations_hook.log.1.gz").write_bytes(b"stale")

            report = log_retention.rotate_log_if_needed(log, max_bytes=20, backups=2)

            self.assertTrue(report["rotated"])
            self.assertFalse(log.exists())
            first = log.parent / "build_associations_hook.log.1.gz"
            second = log.parent / "build_associations_hook.log.2.gz"
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertIn(b"old diagnostic bytes", gzip.decompress(first.read_bytes()))
            self.assertEqual(second.read_bytes(), b"stale")

    def test_public_log_health_report_does_not_emit_log_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "logs" / "subconscious_scheduler_hook.log"
            log.parent.mkdir()
            log.write_text(
                "private prompt text and source snippet should stay local\n",
                encoding="utf-8",
            )

            report = log_retention.log_health_report(root, max_bytes=10)
            rendered = str(report)

            self.assertTrue(report["oversized"])
            self.assertEqual(report["kind"], "aippocampus_logs_status_card")
            self.assertEqual(report["surface"], "foreground_decision_card")
            self.assertEqual(report["items"][0]["artifact_name"], log.name)
            self.assertEqual(report["remediation_command"], "aippocampus logs rotate --dry-run")
            self.assertEqual(report["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", report)
            self.assertNotIn(report["foreground_action"], report["safe_next_actions"])
            self.assertEqual(report["foreground_action"]["id"], "plan_log_rotation")
            self.assertEqual(
                report["foreground_action"]["command"],
                "aippocampus logs rotate --dry-run --json",
            )
            self.assertIn("subconscious_scheduler_hook.log", rendered)
            self.assertNotIn("private prompt text", rendered)
            self.assertNotIn("source snippet", rendered)

    def test_rotate_dry_run_reports_plan_without_touching_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "logs" / "build_associations_hook.log"
            log.parent.mkdir()
            log.write_bytes(b"oversized diagnostic bytes" * 8)

            with mock.patch("sys.stdout", new=StringIO()) as stdout:
                code = log_retention.main(
                    [
                        "rotate",
                        "--registry-dir",
                        str(root),
                        "--max-bytes",
                        "20",
                        "--dry-run",
                        "--json",
                    ]
                )
            cli_payload = json.loads(stdout.getvalue())

            # Re-run the pure function for explicit shape assertions; the CLI
            # path above is what protects the no-write surface.
            plan = log_retention.rotation_plan(root, max_bytes=20)

            self.assertEqual(code, 0)
            self.assertEqual(cli_payload["kind"], "aippocampus_logs_rotation_plan")
            self.assertEqual(cli_payload["foreground_action_contract"], "foreground-action-v2")
            self.assertTrue(log.exists())
            self.assertEqual(plan["kind"], "aippocampus_logs_rotation_plan")
            self.assertTrue(plan["read_only"])
            self.assertEqual(plan["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", plan)
            self.assertNotIn(plan["foreground_action"], plan["safe_next_actions"])
            self.assertEqual(plan["would_rotate_count"], 1)
            self.assertEqual(plan["apply_command"], "aippocampus logs rotate --apply")
            self.assertEqual(plan["foreground_action"]["id"], "apply_log_rotation")
            self.assertEqual(plan["foreground_action"]["command"], "aippocampus logs rotate --apply")

    def test_healthy_logs_do_not_suggest_cleanup_or_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "logs" / "build_associations_hook.log"
            log.parent.mkdir()
            log.write_bytes(b"small")

            status = log_retention.log_health_report(root, max_bytes=20)
            plan = log_retention.rotation_plan(root, max_bytes=20)

            self.assertFalse(status["oversized"])
            self.assertEqual(status["kind"], "aippocampus_logs_status_card")
            self.assertEqual(status["surface"], "foreground_decision_card")
            self.assertEqual(status["oversized_count"], 0)
            self.assertEqual(status["status"], "healthy")
            self.assertNotIn("remediation_command", status)
            self.assertEqual(status["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", status)
            self.assertNotIn(status["foreground_action"], status["safe_next_actions"])
            self.assertEqual(status["foreground_action"]["id"], "no_cleanup_needed")
            self.assertEqual(status["foreground_action"]["mutation_risk"], "read_only")
            self.assertTrue(status["foreground_action"]["continue_without_command"])
            self.assertTrue(status["foreground_action"]["no_op"])
            self.assertNotIn("command", status["foreground_action"])
            self.assertEqual(plan["would_rotate_count"], 0)
            self.assertEqual(plan["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", plan)
            self.assertNotIn(plan["foreground_action"], plan["safe_next_actions"])
            self.assertEqual(plan["foreground_action"]["id"], "no_cleanup_needed")
            self.assertEqual(plan["foreground_action"]["mutation_risk"], "read_only")
            self.assertTrue(plan["foreground_action"]["continue_without_command"])
            self.assertNotIn("command", plan["foreground_action"])
            self.assertNotIn("apply_command", plan)

    def test_rotate_json_defaults_to_plan_and_requires_explicit_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "logs" / "build_associations_hook.log"
            log.parent.mkdir()
            log.write_bytes(b"oversized diagnostic bytes" * 8)

            with mock.patch("sys.stdout", new=StringIO()) as stdout:
                code = log_retention.main(
                    [
                        "rotate",
                        "--registry-dir",
                        str(root),
                        "--max-bytes",
                        "20",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertTrue(log.exists())
            self.assertFalse((log.parent / "build_associations_hook.log.1.gz").exists())
            self.assertEqual(payload["kind"], "aippocampus_logs_rotation_plan")
            self.assertTrue(payload["read_only"])
            self.assertTrue(payload["apply_required"])
            self.assertFalse(payload["privacy_boundary"]["writes_performed"])

    def test_streaming_append_keeps_current_file_under_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "subconscious_scheduler.log"

            result = log_retention.append_bytes_with_rotation(
                log,
                b"x" * 35,
                max_bytes=10,
                backups=3,
            )

            self.assertEqual(result["written_bytes"], 35)
            self.assertLessEqual(log.stat().st_size, 10)
            backups = sorted(log.parent.glob("subconscious_scheduler.log.*.gz"))
            self.assertLessEqual(len(backups), 3)

    def test_rotate_known_logs_does_not_trim_source_staging_queues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "subconscious_jobs.jsonl"
            queue.write_text("source-backed staging row\n" * 20, encoding="utf-8")

            result = log_retention.rotate_known_logs(root, max_bytes=10, backups=2)

            self.assertEqual(result["rotated_count"], 0)
            self.assertTrue(queue.exists())
            self.assertFalse((root / "subconscious_jobs.jsonl.1.gz").exists())

    def test_run_command_with_rotating_log_caps_single_child_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "logs" / "build_associations_hook.log"

            code = log_retention.run_command_with_rotating_log(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 35)"],
                log=log,
                max_bytes=10,
                backups=2,
            )

            self.assertEqual(code, 0)
            self.assertLessEqual(log.stat().st_size, 10)
            backups = sorted(log.parent.glob("build_associations_hook.log.*.gz"))
            self.assertLessEqual(len(backups), 2)


if __name__ == "__main__":
    unittest.main()
