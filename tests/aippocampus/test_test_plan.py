from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from tests.aippocampus.import_path_helpers import import_tool_root_module

test_plan = import_tool_root_module("test_plan")

def commands_for(paths: list[str]) -> list[str]:
    payload = test_plan.build_test_plan(paths)
    return [str(command["command"]) for command in payload["commands"]]

def py_command(args: str) -> str:
    return test_plan.py_command(args)

def py_script(script: str, args: str = "") -> str:
    return test_plan.py_script(script, args)

class ChangedSurfaceTestPlanTests(unittest.TestCase):
    def test_docs_only_change_recommends_docs_health_without_pr_reflex(self) -> None:
        with mock.patch.object(test_plan, "_debt_report_is_red", return_value=False):
            payload = test_plan.build_test_plan(["docs/guides/install-guide.md"])
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("docs", payload["categories"])
        self.assertEqual(
            commands,
            [py_script("tools/aippocampus/docs/check_docs_health.py", "--json")],
        )

    def test_architecture_debt_tracked_change_recommends_headroom_preflight(self) -> None:
        payload = test_plan.build_test_plan(
            ["skills/aippocampus/scripts/aippocampus_runtime/cli/facade.py"]
        )
        commands = [command["command"] for command in payload["commands"]]
        reasons = [command["reason"] for command in payload["commands"]]

        self.assertIn("architecture_debt", payload["categories"])
        self.assertIn("changed_surface_debt", payload["categories"])
        self.assertIn("static_gates", payload["categories"])
        self.assertIn("type_check", payload["categories"])
        self.assertIn(test_plan.CI_RUFF_COMMAND, commands)
        self.assertIn(test_plan.CI_MYPY_COMMAND, commands)
        self.assertIn(
            py_script("tools/aippocampus/docs/debt_report.py", "--headroom-only --json"),
            commands,
        )
        self.assertIn(
            py_script(
                "tools/aippocampus/docs/debt_report.py",
                "--changed-surface-only --json "
                "--changed-file skills/aippocampus/scripts/aippocampus_runtime/cli/facade.py",
            ),
            commands,
        )
        self.assertTrue(any("headroom preflight" in reason for reason in reasons))
        self.assertTrue(any("count refresh" in reason for reason in reasons))
        self.assertTrue(any("not a substitute for functional tests" in reason for reason in reasons))
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--tier pr"), commands)

    def test_low_margin_architecture_debt_touch_names_guard_pressure(self) -> None:
        changed = "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py"
        with mock.patch.object(
            test_plan,
            "architecture_debt_low_margin_paths",
            return_value={changed},
        ):
            payload = test_plan.build_test_plan([changed])
        reasons = [command["reason"] for command in payload["commands"]]

        self.assertIn("architecture_debt", payload["categories"])
        self.assertTrue(any("Low-margin guard pressure touched" in reason for reason in reasons))
        self.assertTrue(any("split/trim decision" in reason for reason in reasons))

    def test_red_debt_report_surfaces_even_for_untracked_changes(self) -> None:
        with mock.patch.object(test_plan, "_debt_report_is_red", return_value=True):
            payload = test_plan.build_test_plan(["docs/guides/install-guide.md"])
        commands = [command["command"] for command in payload["commands"]]
        reasons = [command["reason"] for command in payload["commands"]]

        self.assertIn("architecture_debt", payload["categories"])
        self.assertIn(
            py_script("tools/aippocampus/docs/debt_report.py", "--headroom-only --json"),
            commands,
        )
        self.assertTrue(any("already red" in reason for reason in reasons))
        self.assertTrue(any("count-only drift" in reason for reason in reasons))
        self.assertIn(py_script("tools/aippocampus/docs/check_docs_health.py", "--json"), commands)

    def test_benchmark_change_recommends_public_fast_benchmark_smoke(self) -> None:
        commands = commands_for(["benchmarks/aippocampus/benchmark_longmemeval.py"])

        self.assertIn(
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier benchmark-smoke --benchmark-suite-profile public-fast",
            ),
            commands,
        )

    def test_python_change_gets_changed_surface_debt_gate(self) -> None:
        with mock.patch.object(test_plan, "_debt_report_is_red", return_value=False):
            payload = test_plan.build_test_plan(
                ["skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"]
            )
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("changed_surface_debt", payload["categories"])
        self.assertIn(
            py_script(
                "tools/aippocampus/docs/debt_report.py",
                "--changed-surface-only --json "
                "--changed-file skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py",
            ),
            commands,
        )

    def test_runtime_hook_change_recommends_hook_focus_and_pr_gate(self) -> None:
        commands = commands_for(
            ["skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"]
        )

        self.assertIn(test_plan.CI_RUFF_COMMAND, commands)
        self.assertIn(test_plan.CI_MYPY_COMMAND, commands)
        self.assertTrue(any("test_prompt_hook_hot_path" in command for command in commands))
        self.assertTrue(any("test_prompt_hook_anti_nag_behavior" in command for command in commands))
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--tier pr"), commands)

    def test_mcp_change_recommends_mcp_contract_and_pr_gate(self) -> None:
        commands = commands_for(
            ["skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py"]
        )

        self.assertTrue(
            any(
                "test_aippocampus_mcp_server_catalog" in command
                and "test_aippocampus_mcp_server_recall" in command
                and "test_aippocampus_mcp_server_ops" in command
                for command in commands
            )
        )
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--tier pr"), commands)

    def test_recall_integration_surface_recommends_readiness_gate(self) -> None:
        commands = commands_for(
            ["tools/aippocampus/smoke/known_artifact_recall_dogfood.py"]
        )

        self.assertIn(
            py_script("tools/aippocampus/recall_integration_readiness.py", "--json"),
            commands,
        )

    def test_test_runner_change_recommends_tier_contract_and_report(self) -> None:
        payload = test_plan.build_test_plan(
            [
                "tools/aippocampus/run_tests.py",
                "tools/aippocampus/run_ci_parity.py",
                ".github/workflows/aippocampus-ci.yml",
            ]
        )
        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertIn("ci_workflow", payload["categories"])
        self.assertIn("static_gates", payload["categories"])
        self.assertIn("type_check", payload["categories"])
        self.assertIn(test_plan.CI_RUFF_COMMAND, commands)
        self.assertIn(test_plan.CI_MYPY_COMMAND, commands)
        self.assertTrue(any("test_run_tests_tiers" in command for command in commands))
        self.assertTrue(any("test_test_plan" in command for command in commands))
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--report-json"), commands)

    def test_test_only_change_frontloads_ruff_without_unneeded_mypy(self) -> None:
        commands = commands_for(["tests/aippocampus/test_test_plan.py"])

        self.assertEqual(commands[0], test_plan.CI_RUFF_COMMAND)
        self.assertNotIn(test_plan.CI_MYPY_COMMAND, commands)
        self.assertTrue(any("tests.aippocampus.test_test_plan" in command for command in commands))

    def test_ci_workflow_change_frontloads_static_parity_gates(self) -> None:
        payload = test_plan.build_test_plan([".github/workflows/aippocampus-ci.yml"])
        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertIn("ci_workflow", payload["categories"])
        self.assertIn(test_plan.CI_RUFF_COMMAND, commands)
        self.assertIn(test_plan.CI_MYPY_COMMAND, commands)
        self.assertLess(
            commands.index(test_plan.CI_RUFF_COMMAND),
            next(index for index, command in enumerate(commands) if "test_test_plan" in command),
        )

    def test_default_commands_are_portable_and_do_not_leak_user_home_python(self) -> None:
        fake_home = chr(67) + ":" + "\\Users\\Example"
        fake_python = fake_home + "\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
        with (
            mock.patch.object(
                test_plan.sys,
                "executable",
                fake_python,
            ),
            mock.patch.object(test_plan, "_debt_report_is_red", return_value=False),
        ):
            payload = test_plan.build_test_plan(["tools/aippocampus/test_plan.py"])

        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertEqual(payload["command_mode"], "portable")
        self.assertTrue(any(command.startswith("python ") for command in commands))
        self.assertFalse(any(fake_home in command for command in commands))

    def test_local_executable_mode_is_explicit(self) -> None:
        with (
            mock.patch.object(test_plan.sys, "executable", r"C:\Python313\python.exe"),
            mock.patch.object(test_plan, "_debt_report_is_red", return_value=False),
        ):
            payload = test_plan.build_test_plan(
                ["tools/aippocampus/test_plan.py"],
                local_executable=True,
            )

        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertEqual(payload["command_mode"], "local_executable")
        self.assertTrue(any("python.exe" in command for command in commands))

    def test_python_minor_match_has_no_warning(self) -> None:
        with (
            mock.patch.object(test_plan, "_local_python_version_parts", return_value=(3, 12, 9)),
            mock.patch.object(test_plan, "canonical_ci_python_version", return_value="3.12"),
        ):
            payload = test_plan.build_test_plan(["tools/aippocampus/test_plan.py"])

        self.assertTrue(payload["python_environment"]["minor_matches_ci"])
        self.assertEqual(payload["warnings"], [])

    def test_python_minor_mismatch_warns_without_adding_matrix_gate(self) -> None:
        with (
            mock.patch.object(test_plan, "_local_python_version_parts", return_value=(3, 13, 1)),
            mock.patch.object(test_plan, "canonical_ci_python_version", return_value="3.12"),
        ):
            payload = test_plan.build_test_plan(["tools/aippocampus/test_plan.py"])

        warnings = payload["warnings"]
        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertFalse(payload["python_environment"]["minor_matches_ci"])
        self.assertEqual(warnings[0]["kind"], "python_minor_mismatch")
        self.assertIn("run_ci_parity.py --tier pr --json", warnings[0]["next_action"])
        self.assertIn("do not run a broad matrix", warnings[0]["next_action"])
        self.assertFalse(any("3.12" in command and "broad-pr" in command for command in commands))

    def test_release_tool_change_recommends_release_contracts_and_boundary_scan(self) -> None:
        payload = test_plan.build_test_plan(["tools/aippocampus/release/check_public_boundary.py"])
        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertIn("release_tool", payload["categories"])
        self.assertTrue(any("test_agent_discovery_release_check" in command for command in commands))
        self.assertTrue(any("test_public_boundary_check" in command for command in commands))
        self.assertIn(
            py_script("tools/aippocampus/release/check_public_boundary.py", "--json"),
            commands,
        )

    def test_changed_tests_run_their_modules_first(self) -> None:
        commands = commands_for(
            [
                "tests\\aippocampus\\test_benchmark_longmemeval.py",
                "tests/aippocampus/test_run_tests_tiers.py",
            ]
        )

        self.assertEqual(commands[0], test_plan.CI_RUFF_COMMAND)
        self.assertEqual(
            commands[1],
            py_command(
                "-m unittest "
                "tests.aippocampus.test_benchmark_longmemeval "
                "tests.aippocampus.test_run_tests_tiers -v"
            ),
        )

    def test_large_changed_test_surface_is_grouped_into_copy_pasteable_slices(self) -> None:
        payload = test_plan.build_test_plan(
            [
                "tests/aippocampus/test_active_recall.py",
                "tests/aippocampus/test_active_path_packet.py",
                "tests/aippocampus/test_agent_background.py",
                "tests/aippocampus/test_benchmark_entrypoints.py",
                "tests/aippocampus/test_benchmark_graph_extraction_boundary.py",
                "tests/aippocampus/test_query_profile.py",
                "tests/aippocampus/test_run_tests_tiers.py",
                "tests/aippocampus/test_test_plan.py",
            ]
        )

        warnings = payload["warnings"]
        groups = payload["changed_test_groups"]
        commands = [command["command"] for command in payload["commands"]]
        grouped_commands = [
            group["command"]
            for group in groups
        ]

        self.assertEqual(warnings[-1]["kind"], "large_dirty_surface")
        self.assertIn("pick the slice", warnings[-1]["next_action"])
        self.assertGreaterEqual(len(groups), 2)
        self.assertEqual(grouped_commands, sorted(grouped_commands))
        self.assertEqual(len(grouped_commands), len(set(grouped_commands)))
        self.assertTrue(all(command in commands for command in grouped_commands))
        self.assertFalse(
            any(
                "debt_report.py" not in command
                and "test_active_recall" in command
                and "test_agent_background" in command
                and "test_benchmark_graph_extraction_boundary" in command
                for command in commands
            )
        )
        self.assertTrue(
            any(
                group["group"] == "quick"
                and "tests.aippocampus.test_active_path_packet" in group["modules"]
                and "tests.aippocampus.test_query_profile" in group["modules"]
                for group in groups
            )
        )
        self.assertTrue(
            any(
                group["group"] == "broad-runtime"
                and "tests.aippocampus.test_active_recall" in group["modules"]
                and "tests.aippocampus.test_agent_background" in group["modules"]
                for group in groups
            )
        )
        self.assertTrue(
            any(
                group["group"] == "broad-benchmark-guard"
                and group["modules"] == [
                    "tests.aippocampus.test_benchmark_graph_extraction_boundary"
                ]
                for group in groups
            )
        )
        self.assertTrue(
            any(
                group["group"] == "broad-test-tooling"
                and group["module_count"] >= 1
                for group in groups
            )
        )

    def test_benchmark_fast_lane_guard_does_not_force_benchmark_smoke(self) -> None:
        payload = test_plan.build_test_plan(
            ["tests/aippocampus/test_benchmark_graph_extraction_boundary.py"]
        )
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("benchmark_fast_lane_guard", payload["categories"])
        self.assertNotIn("benchmark", payload["categories"])
        self.assertFalse(any("--tier benchmark-smoke" in command for command in commands))

    def test_benchmark_evidence_change_still_recommends_benchmark_smoke(self) -> None:
        payload = test_plan.build_test_plan(
            ["tests/aippocampus/test_benchmark_longmemeval.py"]
        )
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("benchmark", payload["categories"])
        self.assertIn(
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier benchmark-smoke --benchmark-suite-profile public-fast",
            ),
            commands,
        )

    def test_apw_fallback_changes_name_real_clean_source_parity_gate(self) -> None:
        payload = test_plan.build_test_plan(
            [
                "skills/aippocampus/scripts/aippocampus_runtime/recall/"
                "associative_path_fallback.py"
            ]
        )
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("apw_parity", payload["categories"])
        self.assertTrue(
            any(
                "test_agent_recall_apw_fallback" in command
                and "test_benchmark_associative_path_walker" in command
                for command in commands
            )
        )

    def test_no_changes_recommends_quick_sanity(self) -> None:
        payload = test_plan.build_test_plan([])

        self.assertEqual(payload["changed_files"], [])
        self.assertEqual(
            payload["commands"][0]["command"],
            py_script("tools/aippocampus/run_tests.py", "--tier quick"),
        )
        self.assertIn("does not replace", payload["boundary"])

    def test_release_preflight_plan_keeps_local_gate_lean(self) -> None:
        payload = test_plan.build_release_preflight_plan()

        local_required = [command["command"] for command in payload["local_required"]]
        fallback = [
            command["command"]
            for command in payload["local_if_ci_unavailable_or_changed_after_ci"]
        ]
        fallback_reasons = [
            command["reason"]
            for command in payload["local_if_ci_unavailable_or_changed_after_ci"]
        ]
        ci_owned = payload["ci_owned_do_not_repeat_locally_by_default"]

        self.assertEqual(payload["kind"], "aippocampus_release_preflight_plan")
        self.assertTrue(payload["gate_policy"]["do_not_stack_quick_before_pr"])
        self.assertIn(
            py_script("tools/aippocampus/run_tests.py", "--tier pr"),
            payload["local_closeout_sequence"],
        )
        self.assertIn(
            py_script(
                "tools/aippocampus/release/check_agent_discovery_release.py",
                "--offline --json",
            ),
            local_required,
        )
        self.assertIn(
            py_script("tools/aippocampus/release/check_public_boundary.py", "--json"),
            local_required,
        )
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--tier pr"), fallback)
        self.assertIn(py_script("tools/aippocampus/run_tests.py", "--tier full"), ci_owned)
        self.assertTrue(any("`pr` includes `quick`" in reason for reason in fallback_reasons))
        self.assertIn(py_command('-m pip install -e ".[release]"'), payload["publish_workflow_owned"])
        self.assertTrue(any("PyPI publish" in command for command in payload["publish_workflow_owned"]))
        self.assertTrue(
            any(
                "--wait-ready" in command["command"]
                for command in payload["post_publish_required"]
            )
        )
        self.assertTrue(
            any(
                "pip install aippocampus" in command["command"]
                for command in payload["post_publish_required"]
            )
        )

    def test_release_preflight_cli_emits_json_without_changed_file_scan(self) -> None:
        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(test_plan, "collect_changed_files") as collect_changed_files,
        ):
            exit_code = test_plan.main(["--release-preflight", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["kind"], "aippocampus_release_preflight_plan")
        collect_changed_files.assert_not_called()

    def test_collect_changed_files_includes_untracked_files(self) -> None:
        def fake_git(args: list[str]) -> list[str]:
            if args[:3] == ["diff", "--name-only", "--diff-filter=ACMRTUXB"]:
                return []
            if args == ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"]:
                return []
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return ["tools/aippocampus/test_plan.py"]
            return []

        with mock.patch.object(test_plan, "_run_git_name_only", side_effect=fake_git):
            changed = test_plan.collect_changed_files(base="origin/main")

        self.assertEqual(changed, ["tools/aippocampus/test_plan.py"])

if __name__ == "__main__":
    unittest.main()
