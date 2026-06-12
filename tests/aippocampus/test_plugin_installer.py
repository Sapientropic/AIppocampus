from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.update import plugin_installer  # noqa: E402


class FakeCodexRunner:
    def __init__(self, list_payload: dict | None = None) -> None:
        self.commands: list[list[str]] = []
        self.list_payload = list_payload or {"installed": [], "available": []}

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        if command[:3] == ["codex", "plugin", "list"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.list_payload), "")
        if command[:4] == ["codex", "plugin", "marketplace", "add"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"marketplaceName": "aippocampus-local", "alreadyAdded": False}),
                "",
            )
        if command[:3] == ["codex", "plugin", "add"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "pluginId": "aippocampus@aippocampus-local",
                        "version": "0.2.0",
                        "installedPath": "/tmp/fake-installed-aippocampus",
                    }
                ),
                "",
            )
        if command[:3] == ["codex", "plugin", "remove"]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"removed": True}), "")
        if command[:4] == ["codex", "plugin", "marketplace", "remove"]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"removed": True}), "")
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
    def test_codex_install_builds_marketplace_installs_and_verifies(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-install"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runner = FakeCodexRunner()

                result = plugin_installer.install_codex_plugin(
                    repo_root=REPO_ROOT,
                    codex_home_path=root / "codex-home",
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
                self.assertEqual(
                    marketplace["plugins"][0]["source"]["path"],
                    "./plugins/aippocampus",
                )
                self.assertEqual(marketplace["plugins"][0]["policy"]["authentication"], "ON_USE")
                self.assertEqual(result["plugin"]["id"], "aippocampus@aippocampus-local")
                self.assertEqual(result["agent_callable_status"], "host_live_probe_ok")
                self.assertFalse(result["hooks_auto_enabled"])
                self.assertIn(
                    [
                        "codex",
                        "plugin",
                        "marketplace",
                        "add",
                        str(marketplace_path.parents[2]),
                        "--json",
                    ],
                    runner.commands,
                )
                self.assertIn(
                    ["codex", "plugin", "add", "aippocampus@aippocampus-local", "--json"],
                    runner.commands,
                )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_install_is_idempotent_when_plugin_is_already_installed(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-idempotent"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runner = FakeCodexRunner(
                    {
                        "installed": [
                            {
                                "pluginId": "aippocampus@aippocampus-local",
                                "version": "0.2.0",
                                "installed": True,
                                "enabled": True,
                            }
                        ],
                        "available": [],
                    }
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
            self.assertEqual(result["plugin"]["action"], "already_current")
            self.assertNotIn(
                ["codex", "plugin", "add", "aippocampus@aippocampus-local", "--json"],
                runner.commands,
            )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_install_replaces_stale_installed_plugin(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-stale"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runner = FakeCodexRunner(
                    {
                        "installed": [
                            {
                                "pluginId": "aippocampus@aippocampus-local",
                                "version": "0.1.0",
                                "installed": True,
                                "enabled": True,
                            }
                        ],
                        "available": [],
                    }
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
            self.assertEqual(result["plugin"]["action"], "reinstalled")
            self.assertLess(
                runner.commands.index(
                    ["codex", "plugin", "remove", "aippocampus@aippocampus-local", "--json"]
                ),
                runner.commands.index(
                    ["codex", "plugin", "add", "aippocampus@aippocampus-local", "--json"]
                ),
            )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_install_replaces_same_version_when_source_path_is_missing(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-same-version-missing-source"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runner = FakeCodexRunner(
                    {
                        "installed": [
                            {
                                "pluginId": "aippocampus@aippocampus-local",
                                "version": "0.2.0",
                                "installed": True,
                                "enabled": True,
                                "source": {
                                    "source": "local",
                                    "path": str(root / "missing-marketplace-plugin"),
                                },
                            }
                        ],
                        "available": [],
                    }
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
            self.assertEqual(result["plugin"]["action"], "reinstalled")
        finally:
            shutil.rmtree(output, ignore_errors=True)

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
            runner = FakeCodexRunner()

            result = plugin_installer.uninstall_codex_plugin(
                codex_home_path=codex_home,
                runner=runner,
            )

        self.assertTrue(result["ok"])
        self.assertFalse(marketplace_root.exists())
        self.assertIn(
            ["codex", "plugin", "remove", "aippocampus@aippocampus-local", "--json"],
            runner.commands,
        )
        self.assertIn(
            ["codex", "plugin", "marketplace", "remove", "aippocampus-local", "--json"],
            runner.commands,
        )
