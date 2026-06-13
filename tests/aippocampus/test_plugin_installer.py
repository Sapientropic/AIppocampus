from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.update import codex_plugin_cli, plugin_installer  # noqa: E402


class FakeCodexRunner:
    def __init__(
        self,
        *,
        marketplace_add_returncode: int = 0,
        marketplace_add_stderr: str = "",
        marketplace_upgrade_returncode: int = 0,
        marketplace_upgrade_stderr: str = "",
    ) -> None:
        self.commands: list[list[str]] = []
        self.command_tails: list[list[str]] = []
        self.marketplace_add_returncode = marketplace_add_returncode
        self.marketplace_add_stderr = marketplace_add_stderr
        self.marketplace_upgrade_returncode = marketplace_upgrade_returncode
        self.marketplace_upgrade_stderr = marketplace_upgrade_stderr

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        executable = Path(command[0]).name.casefold() if command else ""
        tail = command[1:] if executable in {"codex", "codex.cmd", "codex.exe", "codex.bat"} else command
        self.command_tails.append(list(tail))
        if tail[:3] == ["plugin", "marketplace", "add"]:
            return subprocess.CompletedProcess(
                command,
                self.marketplace_add_returncode,
                "marketplace added",
                self.marketplace_add_stderr,
            )
        if tail[:3] == ["plugin", "marketplace", "upgrade"]:
            return subprocess.CompletedProcess(
                command,
                self.marketplace_upgrade_returncode,
                "marketplace upgraded",
                self.marketplace_upgrade_stderr,
            )
        if tail[:3] == ["plugin", "marketplace", "remove"]:
            return subprocess.CompletedProcess(command, 0, "marketplace removed", "")
        raise AssertionError(f"unexpected command: {command!r}")


def successful_probe() -> dict:
    return {
        "validation_ok": True,
        "mcp_status": {"tool_names": ["memory_health", "search_memory", "sync_status"]},
        "mcp_tool_is_error": False,
        "mcp_tool_payload": {
            "status": "available_requires_sync_dir",
            "backend": "local_folder",
        },
    }


class PluginInstallerTests(unittest.TestCase):
    def test_codex_install_builds_marketplace_refreshes_versioned_cache_and_verifies(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-install"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                codex_home = root / "codex-home"
                runner = FakeCodexRunner(
                    marketplace_upgrade_returncode=1,
                    marketplace_upgrade_stderr=(
                        "Error: marketplace `aippocampus-local` is not configured as a Git marketplace"
                    ),
                )

                result = plugin_installer.install_codex_plugin(
                    repo_root=REPO_ROOT,
                    codex_home_path=codex_home,
                    plugin_output=output,
                    verify=True,
                    runner=runner,
                    host_probe_runner=lambda **_: successful_probe(),
                )

                self.assertTrue(result["ok"])
                self.assertEqual(result["marketplace"]["name"], "aippocampus-local")
                marketplace_path = Path(result["marketplace"]["manifest"])
                self.assertTrue(marketplace_path.exists())
                marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
                self.assertEqual(marketplace["displayName"], "AIppocampus")
                self.assertEqual(
                    marketplace["plugins"][0]["source"]["path"],
                    "./plugins/aippocampus",
                )
                self.assertEqual(marketplace["plugins"][0]["policy"]["authentication"], "ON_USE")
                self.assertEqual(result["plugin"]["id"], "aippocampus@aippocampus-local")
                self.assertEqual(result["plugin"]["action"], "marketplace_refreshed")
                self.assertTrue(result["marketplace_upgrade"]["skipped_non_git"])
                self.assertEqual(result["agent_callable_status"], "host_live_probe_ok")
                self.assertFalse(result["hooks_auto_enabled"])
                installed_cache = (
                    codex_home
                    / "plugins"
                    / "cache"
                    / "aippocampus-local"
                    / "aippocampus"
                    / result["plugin"]["version"]
                )
                self.assertEqual(
                    Path(result["plugin"]["installed_cache"]).resolve(),
                    installed_cache.resolve(),
                )
                self.assertTrue((installed_cache / ".codex-plugin" / "plugin.json").exists())
                self.assertTrue(
                    result["cache_refresh"]["refreshed"]["installed_cache"]["target_path"],
                )
                self.assertIn(
                    [
                        "plugin",
                        "marketplace",
                        "add",
                        str(marketplace_path.parents[2]),
                    ],
                    runner.command_tails,
                )
                self.assertIn(
                    ["plugin", "marketplace", "upgrade", "aippocampus-local"],
                    runner.command_tails,
                )
                self.assertFalse(
                    any(command[:2] == ["plugin", "list"] for command in runner.command_tails)
                )
                self.assertFalse(
                    any(command[:2] == ["plugin", "add"] for command in runner.command_tails)
                )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_install_tolerates_existing_marketplace_and_still_upgrades(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-existing-marketplace"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runner = FakeCodexRunner(
                    marketplace_add_returncode=1,
                    marketplace_add_stderr="marketplace already configured",
                )

                result = plugin_installer.install_codex_plugin(
                    repo_root=REPO_ROOT,
                    codex_home_path=root / "codex-home",
                    plugin_output=output,
                    verify=True,
                    runner=runner,
                    host_probe_runner=lambda **_: successful_probe(),
                )

            self.assertTrue(result["ok"])
            self.assertTrue(result["marketplace_add"]["already_registered"])
            self.assertIn(
                ["plugin", "marketplace", "upgrade", "aippocampus-local"],
                runner.command_tails,
            )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_base_resolves_windows_launcher_before_extensionless_shim(self) -> None:
        with mock.patch.object(codex_plugin_cli.os, "name", "nt"):
            with mock.patch.object(
                codex_plugin_cli.shutil,
                "which",
                side_effect=lambda command: {
                    "codex.cmd": "C:\\Users\\Example\\AppData\\Roaming\\npm\\codex.cmd",
                    "codex.exe": "C:\\Program Files\\Codex\\codex.exe",
                }.get(command),
            ):
                self.assertEqual(
                    codex_plugin_cli.codex_base(),
                    ["C:\\Users\\Example\\AppData\\Roaming\\npm\\codex.cmd"],
                )

    def test_codex_base_keeps_explicit_command_list(self) -> None:
        self.assertEqual(codex_plugin_cli.codex_base(["custom-codex", "--flag"]), ["custom-codex", "--flag"])

    def test_codex_uninstall_removes_owned_marketplace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            marketplace_root = plugin_installer.default_marketplace_root(codex_home)
            package = root / "package"
            (package / ".codex-plugin").mkdir(parents=True)
            (package / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "aippocampus", "version": "0.2.0"}),
                encoding="utf-8",
            )
            plugin_installer.write_local_marketplace(
                marketplace_root,
                package_root=package,
                marketplace_name="aippocampus-local",
            )
            installed_cache = (
                codex_home
                / "plugins"
                / "cache"
                / "aippocampus-local"
                / "aippocampus"
                / "0.2.0"
            )
            plugin_installer.refresh_plugin_cache_layers(
                package_root=package,
                installed_dir=installed_cache,
            )
            runner = FakeCodexRunner()

            result = plugin_installer.uninstall_codex_plugin(
                codex_home_path=codex_home,
                runner=runner,
            )

        self.assertTrue(result["ok"])
        self.assertFalse(marketplace_root.exists())
        self.assertFalse(installed_cache.exists())
        self.assertTrue(result["removed_installed_cache"])
        self.assertIn(
            ["plugin", "marketplace", "remove", "aippocampus-local"],
            runner.command_tails,
        )
