from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import aippocampus_health as health  # noqa: E402


class AippocampusHealthTests(unittest.TestCase):
    def test_recommended_script_command_uses_posix_codex_home_on_macos(self) -> None:
        with mock.patch.object(health.os, "name", "posix"):
            command = health.recommended_script_command("build_index.py", Path("/tmp/work space"))

        self.assertEqual(
            command,
            'python "$CODEX_HOME/skills/aippocampus/scripts/build_index.py" --cwd "/tmp/work space"',
        )

    def test_recommended_script_command_keeps_powershell_shape_on_windows(self) -> None:
        with mock.patch.object(health.os, "name", "nt"):
            command = health.recommended_script_command("build_index.py", "C:/work")
        expected_cwd = "C:" + "\\work"

        self.assertEqual(
            command,
            f'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\build_index.py" --cwd "{expected_cwd}"',
        )

    def test_question_stats_are_fail_open_diagnostics(self) -> None:
        with mock.patch.object(
            health,
            "question_health_stats",
            side_effect=RuntimeError("bad local staging file"),
        ):
            payload = health.load_question_stats(
                jobs_path=Path("subconscious_jobs.jsonl"),
                registry_path=Path("threads.json"),
                resolve_registry_refs=True,
            )

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "question_health_error")
        self.assertEqual(payload["error_type"], "RuntimeError")

    def test_missing_question_jobs_are_unavailable_not_maintenance_blockers(self) -> None:
        payload = health.load_question_stats(
            jobs_path=Path("missing-subconscious-jobs.jsonl"),
            registry_path=None,
        )

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "jobs_missing")

    def test_question_stats_default_to_aggregate_with_registry_ref_resolution(self) -> None:
        with mock.patch.object(
            health,
            "question_health_stats",
            return_value={
                "available": True,
                "tracked_question_count": 1,
                "lifecycle": [{"title": "private question"}],
                "longest_running_open_question": {"title": "private question"},
            },
        ) as stats:
            payload = health.load_question_stats(
                jobs_path=Path("subconscious_jobs.jsonl"),
                registry_path=Path("threads.json"),
            )

        stats.assert_called_once_with(
            Path("subconscious_jobs.jsonl"),
            registry_path=Path("threads.json"),
            dormant_after_days=health.DEFAULT_DORMANT_AFTER_DAYS,
        )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["tracked_question_count"], 1)
        self.assertNotIn("lifecycle", payload)
        self.assertNotIn("longest_running_open_question", payload)

    def test_activity_diagnostics_are_advisory_not_threshold_replacements(self) -> None:
        self.assertEqual(
            health.activity_class(
                message_delta=30,
                byte_delta=0,
                stale_age_seconds=300,
                max_stale_messages=25,
                max_stale_bytes=5_000,
            ),
            "high_activity",
        )
        self.assertEqual(
            health.activity_class(
                message_delta=2,
                byte_delta=10,
                stale_age_seconds=2 * 24 * 3600,
                max_stale_messages=25,
                max_stale_bytes=5_000,
            ),
            "quiet",
        )

    def test_registry_wide_health_aggregates_without_default_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp)
            thread_dir = registry_dir / "threads" / "thread-1"
            (thread_dir / "index").mkdir(parents=True)
            (thread_dir / "clean-source").mkdir()
            (thread_dir / "index" / "manifest.json").write_text(
                json.dumps({"created_at": "2026-06-01T00:00:00Z", "message_count": 8}),
                encoding="utf-8",
            )
            (thread_dir / "clean-source" / "manifest.json").write_text("{}", encoding="utf-8")
            (thread_dir / "clean-source" / "messages.jsonl").write_text("one\n", encoding="utf-8")
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "provider:private-thread-title",
                                "message_count": 10,
                                "rollout_size": 2048,
                                "paths": {"registry_thread_store": "threads/thread-1"},
                                "health": {
                                    "ok": False,
                                    "recommended_actions": [
                                        {"id": "build_index", "severity": "warning"}
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = health.registry_health_report(registry_dir=registry_dir)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["thread_count"], 1)
        self.assertEqual(payload["recommended_action_counts"], {"build_index": 1})
        self.assertFalse(payload["privacy"]["message_bodies_read"])
        self.assertFalse(payload["privacy"]["paths_included"])
        thread = payload["top_threads"][0]
        self.assertIn("thread_ref", thread)
        self.assertNotIn("private-thread-title", json.dumps(payload))
        self.assertNotIn("thread_dir", thread)

    def test_registry_wide_cli_can_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "threads.json").write_text(json.dumps({"threads": []}), encoding="utf-8")
            with mock.patch("sys.stdout", new=StringIO()) as stdout:
                code = health.main(["--registry-wide", "--registry-dir", tmp, "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["thread_count"], 0)


if __name__ == "__main__":
    unittest.main()
