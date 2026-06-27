from __future__ import annotations

import unittest
from unittest import mock

from tests.aippocampus.import_path_helpers import import_tool_root_module

preflight = import_tool_root_module("changed_surface_preflight")
test_plan_commands = import_tool_root_module("test_plan_commands")


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

    def test_tempdir_failure_does_not_create_changed_surface(self) -> None:
        expected_command = preflight.test_plan.py_script(
            "tools/aippocampus/run_tests.py",
            "--tier quick",
        )

        def fake_command(command: str) -> preflight.CommandResult:
            failed = command == expected_command
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="fail" if failed else "pass",
                returncode=2 if failed else 0,
                elapsed_ms=1,
                stdout="",
                stderr="No usable temporary directory for the test runner.",
            )

        with (
            mock.patch.object(preflight.test_plan, "collect_changed_files", return_value=[]),
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[],
                base="origin/main",
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["changed_file_count"], 0)
        self.assertEqual(report["changed_files"], [])
        self.assertEqual(report["first_failure"]["command"], expected_command)

    def test_default_preflight_uses_current_interpreter_when_python_alias_is_absent(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(test_plan_commands.shutil, "which", return_value=None),
            mock.patch.object(preflight.test_plan, "collect_changed_files", return_value=[]),
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            expected = test_plan_commands.py_script("tools/aippocampus/run_tests.py", "--tier quick")
            report = preflight.run_preflight(changed_files=[], base="origin/main")

        self.assertTrue(report["ok"])
        self.assertEqual(seen, [expected])
        self.assertFalse(expected.startswith("python "))
        self.assertFalse(report["detail_command"].startswith("python "))
        self.assertFalse(report["planner_detail_command"].startswith("python "))

    def test_detail_commands_open_full_operator_views(self) -> None:
        def fake_command(command: str) -> preflight.CommandResult:
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tools/aippocampus/changed_surface_preflight.py"],
                base="origin/main",
                local_executable=True,
            )

        self.assertIn("--detail full", report["detail_command"])
        self.assertIn("--local-executable", report["detail_command"])
        self.assertIn("--detail full", report["planner_detail_command"])
        self.assertIn("--local-executable", report["planner_detail_command"])

    def test_default_preflight_skips_explicit_pr_tier(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[
                    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py"
                ],
                base="origin/main",
            )

        self.assertEqual(report["mode"], "preflight")
        self.assertGreater(report["skipped_by_mode_count"], 0)
        self.assertTrue(
            any("run_tests.py --tier pr" in row["command"] for row in report["skipped_by_mode"])
        )
        self.assertFalse(any("run_tests.py --tier pr" in command for command in seen))
        self.assertIn("--mode closeout", report["closeout_command"])

    def test_default_preflight_skips_slow_focused_proof_slices(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[
                    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py",
                    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py",
                    "tests/aippocampus/test_agent_background.py",
                    "tests/aippocampus/test_agent_opt_in_cli_contracts.py",
                    "tests/aippocampus/test_agent_opt_in_recall_routes.py",
                    "tests/aippocampus/test_agent_recall_apw_fallback.py",
                    "tests/aippocampus/test_agent_recall_compact_projection.py",
                    "tests/aippocampus/test_changed_surface_preflight.py",
                ],
                base="origin/main",
            )

        skipped_scopes = {row["scope"] for row in report["skipped_by_mode"]}
        self.assertIn("focused:broad-runtime", skipped_scopes)
        self.assertIn("focused:apw-parity", skipped_scopes)
        self.assertIn("focused:recall-integration-readiness", skipped_scopes)
        self.assertTrue(
            any(row["scope"] == "focused" for row in report["skipped_by_mode"])
        )
        proof_commands = [
            command
            for command in seen
            if "-m unittest" in command or "recall_integration_readiness.py" in command
        ]
        joined = "\n".join(proof_commands)
        self.assertNotIn("test_aippocampus_mcp_server_recall", joined)
        self.assertNotIn("test_agent_recall_apw_fallback", joined)
        self.assertNotIn("recall_integration_readiness.py", joined)

    def test_default_preflight_allows_small_focused_unittest_probe(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=["tests/aippocampus/test_changed_surface_preflight.py"],
                base="origin/main",
            )

        self.assertEqual(report["mode"], "preflight")
        self.assertTrue(
            any("test_changed_surface_preflight" in command for command in seen)
        )

    def test_closeout_mode_runs_explicit_pr_tier(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[
                    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py"
                ],
                base="origin/main",
                mode="closeout",
            )

        self.assertEqual(report["mode"], "closeout")
        self.assertEqual(report["skipped_by_mode_count"], 0)
        self.assertTrue(any("run_tests.py --tier pr" in command for command in seen))

    def test_closeout_mode_runs_slow_focused_proof_slices(self) -> None:
        seen: list[str] = []

        def fake_command(command: str) -> preflight.CommandResult:
            seen.append(command)
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[
                    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py",
                    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py",
                    "tests/aippocampus/test_agent_background.py",
                    "tests/aippocampus/test_agent_opt_in_cli_contracts.py",
                    "tests/aippocampus/test_agent_opt_in_recall_routes.py",
                    "tests/aippocampus/test_agent_recall_apw_fallback.py",
                    "tests/aippocampus/test_agent_recall_compact_projection.py",
                    "tests/aippocampus/test_changed_surface_preflight.py",
                ],
                base="origin/main",
                mode="closeout",
            )

        joined = "\n".join(seen)
        self.assertEqual(report["mode"], "closeout")
        self.assertEqual(report["skipped_by_mode_count"], 0)
        self.assertIn("test_aippocampus_mcp_server_recall", joined)
        self.assertIn("test_agent_recall_apw_fallback", joined)
        self.assertIn("recall_integration_readiness.py", joined)

    def test_duplicate_focused_modules_are_reported(self) -> None:
        def fake_command(command: str) -> preflight.CommandResult:
            return preflight.CommandResult(
                command=command,
                scope="unknown",
                status="pass",
                returncode=0,
                elapsed_ms=1,
                stdout="",
                stderr="",
            )

        with (
            mock.patch.object(preflight.test_plan, "_debt_report_is_red", return_value=False),
            mock.patch.object(preflight, "run_shell_command", side_effect=fake_command),
        ):
            report = preflight.run_preflight(
                changed_files=[
                    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py"
                ],
                base="origin/main",
            )

        duplicate_modules = {
            row["module"]: row for row in report["duplicate_test_modules"]
        }
        self.assertIn(
            "tests.aippocampus.test_aippocampus_mcp_server_recall",
            duplicate_modules,
        )
        self.assertGreaterEqual(
            duplicate_modules[
                "tests.aippocampus.test_aippocampus_mcp_server_recall"
            ]["command_count"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
