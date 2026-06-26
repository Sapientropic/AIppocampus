from __future__ import annotations

import unittest
from unittest import mock

from tests.aippocampus.import_path_helpers import import_tool_root_module

preflight = import_tool_root_module("changed_surface_preflight")


class ChangedSurfacePreflightTests(unittest.TestCase):
    def test_ruff_failure_stops_before_focused_tests(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            failed = command == preflight.test_plan.CI_RUFF_COMMAND
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="fail" if failed else "pass",
                returncode=1 if failed else 0,
                elapsed_ms=1,
                stdout="",
                stderr="import block is un-sorted" if failed else "",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tools/aippocampus/test_plan.py"],
                base="origin/main",
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["first_failure"]["command"], preflight.test_plan.CI_RUFF_COMMAND)
        self.assertIn(preflight.test_plan.GIT_DIFF_CHECK_COMMAND, seen)
        self.assertNotIn("python -m unittest tests.aippocampus.test_run_tests_tiers", "\n".join(seen))

    def test_git_diff_check_failure_stops_before_unit_tests(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            failed = command == preflight.test_plan.GIT_DIFF_CHECK_COMMAND
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="fail" if failed else "pass",
                returncode=1 if failed else 0,
                elapsed_ms=1,
                stdout="",
                stderr="file.py: trailing whitespace" if failed else "",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tests/aippocampus/test_test_plan.py"],
                base="origin/main",
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["ran_command_count"], 1)
        self.assertEqual(report["first_failure"]["command"], preflight.test_plan.GIT_DIFF_CHECK_COMMAND)
        self.assertFalse(any("unittest" in command for command in seen))

    def test_preflight_runs_slop_guard_before_focused_tests(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            failed = "tools/aippocampus/agent_slop_guard.py --json" in command
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="fail" if failed else "pass",
                returncode=1 if failed else 0,
                elapsed_ms=1,
                stdout='{"ok": false, "gate_status": "failed"}' if failed else "",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tools/aippocampus/agent_slop_guard.py"],
                base="origin/main",
            )

        self.assertFalse(report["ok"])
        self.assertIn("--fail-on-violations", report["first_failure"]["command"])
        focused_commands = [command for command in seen if "unittest" in command]
        self.assertEqual(focused_commands, [])

    def test_detail_full_preserves_command_stdout_for_diagnostics(self) -> None:
        def fake_command(command: str) -> preflight.CommandResult:
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="full diagnostic payload",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tools/aippocampus/changed_surface_preflight.py"],
                base="origin/main",
                detail="full",
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["commands"][0]["stdout"], "full diagnostic payload")


if __name__ == "__main__":
    unittest.main()
