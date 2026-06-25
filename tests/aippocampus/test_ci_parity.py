from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from tools.aippocampus import run_ci_parity


class CiParityTests(unittest.TestCase):
    def test_candidate_python_commands_prefers_configured_and_bundled_runtime(self) -> None:
        bundled = r"C:\CodexRuntime\python.exe"
        with (
            mock.patch.dict(
                run_ci_parity.os.environ,
                {run_ci_parity.CI_PYTHON_ENV: r"C:\Python312\python.exe"},
            ),
            mock.patch.object(
                run_ci_parity,
                "_codex_bundled_python_commands",
                return_value=[[str(bundled)]],
            ),
        ):
            candidates = run_ci_parity._candidate_python_commands("3.12")

        self.assertEqual(candidates[0], [r"C:\Python312\python.exe"])
        self.assertEqual(candidates[1], [bundled])

    def test_find_python_for_minor_checks_candidates_before_selecting(self) -> None:
        with (
            mock.patch.object(
                run_ci_parity,
                "_candidate_python_commands",
                return_value=[["python"], ["py", "-3.12"]],
            ),
            mock.patch.object(
                run_ci_parity,
                "_command_minor",
                side_effect=["3.13", "3.12"],
            ) as command_minor,
        ):
            selected = run_ci_parity.find_python_for_minor("3.12")

        self.assertEqual(selected, ["py", "-3.12"])
        self.assertEqual(command_minor.call_count, 2)

    def test_missing_python_minor_returns_recovery_card_without_traceback(self) -> None:
        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_ci_parity, "find_python_for_minor", return_value=None),
        ):
            exit_code = run_ci_parity.main(["--python-minor", "3.12", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "python_minor_unavailable")
        self.assertIn("opt-in compatibility lane", payload["boundary"])
        self.assertIn("GitHub Actions", " ".join(payload["recovery_actions"]))

    def test_dry_run_prints_selected_pr_parity_command(self) -> None:
        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_ci_parity, "find_python_for_minor", return_value=["py", "-3.12"]),
        ):
            exit_code = run_ci_parity.main(["--tier", "pr", "--dry-run", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["command"][:2], ["py", "-3.12"])
        self.assertEqual(payload["command"][-2:], ["--tier", "pr"])

    def test_run_dispatches_without_shell_string(self) -> None:
        completed = mock.Mock(returncode=0)
        with (
            mock.patch.object(run_ci_parity, "find_python_for_minor", return_value=["py", "-3.12"]),
            mock.patch.object(run_ci_parity.subprocess, "run", return_value=completed) as run,
        ):
            exit_code = run_ci_parity.main(["--tier", "pr"])

        self.assertEqual(exit_code, 0)
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)
        self.assertEqual(args[0][:2], ["py", "-3.12"])


if __name__ == "__main__":
    unittest.main()
