from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(facade.SCRIPT_DIR, SCRIPTS)

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
