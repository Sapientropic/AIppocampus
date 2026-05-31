from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
CLI = SCRIPTS / "aippocampus_cli.py"
sys.path.insert(0, str(SCRIPTS))


class AippocampusCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_help_lists_common_operator_flows(self) -> None:
        proc = self.run_cli("--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("health", proc.stdout)
        self.assertIn("mcp list-tools", proc.stdout)
        self.assertIn("hooks", proc.stdout)

    def test_top_level_script_is_compatibility_shim_for_package_facade(self) -> None:
        import aippocampus_cli
        from aippocampus_runtime.cli import facade

        self.assertIs(aippocampus_cli.main, facade.main)
        self.assertIs(aippocampus_cli.run_script, facade.run_script)
        self.assertIs(aippocampus_cli.run_command, facade.run_command)
        self.assertIs(aippocampus_cli.resolve_command, facade.resolve_command)
        self.assertIs(aippocampus_cli.CommandInvocation, facade.CommandInvocation)
        self.assertIs(aippocampus_cli.CommandResult, facade.CommandResult)
        self.assertEqual(facade.SCRIPT_DIR, SCRIPTS)

    def test_package_facade_resolves_commands_without_running_child_processes(self) -> None:
        from aippocampus_runtime.cli import facade

        invocation = facade.resolve_command(["mcp", "list-tools", "--json"])

        self.assertEqual(invocation.command, "mcp")
        self.assertEqual(invocation.module_name, "aippocampus_runtime.mcp.server")
        self.assertEqual(invocation.script_name, "aippocampus_mcp_server.py")
        self.assertEqual(invocation.args, ["--list-tools", "--json"])

        search_invocation = facade.resolve_command(["search", "source", "--json"])
        self.assertEqual(search_invocation.command, "search")
        self.assertEqual(search_invocation.module_name, "aippocampus_runtime.source.search")
        self.assertEqual(search_invocation.script_name, "search_clean_source.py")

    def test_package_facade_default_runner_is_in_process(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = facade.main(["mcp", "list-tools"])

        self.assertEqual(code, 0)
        tools = json.loads(stdout.getvalue())["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))

    def test_package_facade_exposes_captureable_python_api(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as ambient_stdout,
            patch("sys.stderr", new=StringIO()) as ambient_stderr,
        ):
            result = facade.run_command(["mcp", "list-tools"], capture_output=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.invocation.command, "mcp")
        tools = json.loads(result.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))
        self.assertEqual(result.stderr, "")
        self.assertEqual(ambient_stdout.getvalue(), "")
        self.assertEqual(ambient_stderr.getvalue(), "")

    def test_package_facade_capture_api_handles_usage_and_unknown_commands(self) -> None:
        from aippocampus_runtime.cli import facade

        help_result = facade.run_command(["--help"], capture_output=True)
        unknown_result = facade.run_command(["nope"], capture_output=True)

        self.assertTrue(help_result.ok)
        self.assertIn("Commands:", help_result.stdout)
        self.assertIsNone(help_result.invocation)
        self.assertFalse(unknown_result.ok)
        self.assertEqual(unknown_result.exit_code, 2)
        self.assertIn("unknown command: nope", unknown_result.stderr)
        self.assertIn("Commands:", unknown_result.stderr)

    def test_mcp_list_tools_preserves_json_stdout(self) -> None:
        proc = self.run_cli("mcp", "list-tools")

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        tools = json.loads(proc.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))

    def test_sync_status_preserves_child_exit_code_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("sync", "status", "--sync-dir", tmp, "--json")

        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertFalse(data["manifest_exists"])


if __name__ == "__main__":
    unittest.main()
