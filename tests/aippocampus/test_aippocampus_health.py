from __future__ import annotations

import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
