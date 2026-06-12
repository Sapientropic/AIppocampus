from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools" / "aippocampus"
sys.path.insert(0, str(TOOLS))

import test_plan  # noqa: E402


def commands_for(paths: list[str]) -> list[str]:
    payload = test_plan.build_test_plan(paths)
    return [str(command["command"]) for command in payload["commands"]]


class ChangedSurfaceTestPlanTests(unittest.TestCase):
    def test_docs_only_change_recommends_docs_health_without_pr_reflex(self) -> None:
        payload = test_plan.build_test_plan(["docs/guides/install-guide.md"])
        commands = [command["command"] for command in payload["commands"]]

        self.assertIn("docs", payload["categories"])
        self.assertEqual(commands, ["python tools/aippocampus/docs/check_docs_health.py --json"])

    def test_benchmark_change_recommends_public_fast_benchmark_smoke(self) -> None:
        commands = commands_for(["benchmarks/aippocampus/benchmark_longmemeval.py"])

        self.assertIn(
            "python tools/aippocampus/run_tests.py --tier benchmark-smoke "
            "--benchmark-suite-profile public-fast",
            commands,
        )

    def test_runtime_hook_change_recommends_hook_focus_and_pr_gate(self) -> None:
        commands = commands_for(
            ["skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"]
        )

        self.assertTrue(any("test_prompt_hook_hot_path" in command for command in commands))
        self.assertIn("python tools/aippocampus/run_tests.py --tier pr", commands)

    def test_mcp_change_recommends_mcp_contract_and_pr_gate(self) -> None:
        commands = commands_for(
            ["skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py"]
        )

        self.assertIn(
            "python -m unittest tests.aippocampus.test_aippocampus_mcp_server -v",
            commands,
        )
        self.assertIn("python tools/aippocampus/run_tests.py --tier pr", commands)

    def test_test_runner_change_recommends_tier_contract_and_report(self) -> None:
        payload = test_plan.build_test_plan(
            ["tools/aippocampus/run_tests.py", ".github/workflows/aippocampus-ci.yml"]
        )
        commands = [str(command["command"]) for command in payload["commands"]]

        self.assertIn("ci_workflow", payload["categories"])
        self.assertTrue(any("test_run_tests_tiers" in command for command in commands))
        self.assertTrue(any("test_test_plan" in command for command in commands))
        self.assertIn("python tools/aippocampus/run_tests.py --report-json", commands)

    def test_changed_tests_run_their_modules_first(self) -> None:
        commands = commands_for(
            [
                "tests\\aippocampus\\test_benchmark_longmemeval.py",
                "tests/aippocampus/test_run_tests_tiers.py",
            ]
        )

        self.assertEqual(
            commands[0],
            "python -m unittest "
            "tests.aippocampus.test_benchmark_longmemeval "
            "tests.aippocampus.test_run_tests_tiers -v",
        )

    def test_no_changes_recommends_quick_sanity(self) -> None:
        payload = test_plan.build_test_plan([])

        self.assertEqual(payload["changed_files"], [])
        self.assertEqual(
            payload["commands"][0]["command"],
            "python tools/aippocampus/run_tests.py --tier quick",
        )
        self.assertIn("does not replace", payload["boundary"])

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
