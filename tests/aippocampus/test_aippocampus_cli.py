from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import types
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
        self.assertIn("doctor provider", proc.stdout)
        self.assertIn("mcp list-tools", proc.stdout)
        self.assertIn("smoke recall-funnel", proc.stdout)
        self.assertIn("storage gc", proc.stdout)
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

        export_invocation = facade.resolve_command(["export", "--cwd", "."])
        self.assertEqual(export_invocation.command, "export")
        self.assertEqual(export_invocation.module_name, "aippocampus_runtime.artifacts.export_bundle")
        self.assertEqual(export_invocation.script_name, "export_bundle.py")

        import_invocation = facade.resolve_command(["import", "bundle.zip"])
        self.assertEqual(import_invocation.command, "import")
        self.assertEqual(import_invocation.module_name, "aippocampus_runtime.artifacts.import_bundle")
        self.assertEqual(import_invocation.script_name, "import_bundle.py")

        doctor_invocation = facade.resolve_command(["doctor", "provider", "--json"])
        self.assertEqual(doctor_invocation.command, "doctor")
        self.assertEqual(doctor_invocation.module_name, "aippocampus_runtime.ops.provider_doctor")
        self.assertEqual(doctor_invocation.script_name, "provider_doctor.py")
        self.assertEqual(doctor_invocation.args, ["provider", "--json"])

        smoke_invocation = facade.resolve_command(
            ["smoke", "recall-funnel", "progressive recall", "--json"]
        )
        self.assertEqual(smoke_invocation.command, "smoke")
        self.assertEqual(
            smoke_invocation.module_name,
            "aippocampus_runtime.ops.recall_funnel_smoke",
        )
        self.assertEqual(smoke_invocation.script_name, "recall_funnel_smoke.py")
        self.assertEqual(
            smoke_invocation.args,
            ["recall-funnel", "progressive recall", "--json"],
        )

        storage_invocation = facade.resolve_command(["storage", "gc", "--dry-run", "--json"])
        self.assertEqual(storage_invocation.command, "storage")
        self.assertEqual(
            storage_invocation.module_name,
            "aippocampus_runtime.ops.storage_governance",
        )
        self.assertEqual(storage_invocation.script_name, "storage_governance.py")
        self.assertEqual(storage_invocation.args, ["gc", "--dry-run", "--json"])

        conversation_import = facade.resolve_command(
            [
                "import",
                "conversation",
                "--registry-dir",
                "registry",
                "--format",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ]
        )
        self.assertEqual(conversation_import.command, "import")
        self.assertEqual(conversation_import.module_name, "aippocampus_runtime.registry.api")
        self.assertEqual(conversation_import.script_name, "registry.py")
        self.assertEqual(
            conversation_import.args,
            [
                "--registry-dir",
                "registry",
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ],
        )

        prompt_hook_status = facade.resolve_command(
            ["hooks", "prompt", "status", "--last", "--json"]
        )
        self.assertEqual(prompt_hook_status.command, "hooks")
        self.assertEqual(
            prompt_hook_status.module_name,
            "aippocampus_runtime.hooks.install_prompt",
        )
        self.assertEqual(
            prompt_hook_status.script_name,
            "install_aippocampus_prompt_hook.py",
        )
        self.assertEqual(prompt_hook_status.args, ["status", "--last", "--json"])

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

    def test_package_facade_prefers_argv_aware_main_without_sys_argv_shim(self) -> None:
        from aippocampus_runtime.cli import facade

        module_name = "tests._fake_facade_argv_main"
        fake_module = types.ModuleType(module_name)
        seen: dict[str, object] = {}

        def main(argv: list[str] | None = None) -> int:
            seen["argv"] = list(argv or [])
            seen["sys_argv"] = list(sys.argv)
            return 7

        fake_module.main = main  # type: ignore[attr-defined]
        old_module = sys.modules.get(module_name)
        old_argv = sys.argv[:]
        sys.modules[module_name] = fake_module
        sys.argv = ["outer-host", "--keep"]
        try:
            code = facade.run_module_main(module_name, "fake_child.py", ["--flag", "value"])
        finally:
            sys.argv = old_argv
            if old_module is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = old_module

        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["--flag", "value"])
        self.assertEqual(seen["sys_argv"], ["outer-host", "--keep"])

    def test_package_facade_public_bundle_and_sync_commands_are_argv_aware(self) -> None:
        from aippocampus_runtime.artifacts import export_bundle, import_bundle
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.sync import bundle
        from aippocampus_runtime.sync.object_storage import cli as object_storage_cli

        self.assertTrue(facade.main_accepts_argv(export_bundle.main))
        self.assertTrue(facade.main_accepts_argv(import_bundle.main))
        self.assertTrue(facade.main_accepts_argv(bundle.main))
        self.assertTrue(facade.main_accepts_argv(object_storage_cli.main))

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
