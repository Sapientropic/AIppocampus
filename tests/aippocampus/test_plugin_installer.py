from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.update import (  # noqa: E402
    codex_plugin_cli,
    host_probe_warnings,
    plugin_installer,
)


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
        "mcp_status": {
            "tool_names": [
                "memory_health",
                "search_memory",
                "sync_status",
                "agent_recall",
                "agent_aippo",
                "agent_background",
                "agent_deepen",
                "agent_explain",
            ]
        },
        "mcp_tool_is_error": False,
        "mcp_tool_payload": {
            "status": "available_requires_sync_dir",
            "backend": "local_folder",
        },
    }


def successful_probe_with_noisy_stderr() -> dict:
    result = successful_probe()
    result["stderr_tail"] = "\n".join(
        [
            "ignoring interface.defaultPrompt[0]: prompt must be at most 128 characters in other/plugin.json",
            "Failed to list resource templates for MCP server 'aippocampus': Method not found: resources/templates/list",
            "Failed to list resources for MCP server 'aippocampus': Method not found: resources/list",
            "Failed to kill MCP process group 12345: No such process",
            "state db discrepancy during find_thread_path_by_id_str_in_subdir: falling_back",
        ]
    )
    return result


class PluginInstallerTests(unittest.TestCase):
    def test_plugin_install_summary_surfaces_mcp_command_path_repair(self) -> None:
        summary = plugin_installer.public_install_summary(
            {
                "ok": True,
                "agent_callable_status": "host_live_probe_ok",
                "plugin": {
                    "id": "aippocampus@aippocampus-local",
                    "version": "0.3.3",
                    "action": "marketplace_refreshed",
                    "installed": True,
                    "enabled": True,
                },
                "host_probe": {
                    "validation_ok": True,
                    "mcp_status": {"tool_names": ["agent_recall", "agent_background"]},
                    "key_tool_smokes": [{"tool": "agent_recall", "ok": True}],
                    "warning_summary": {"validation_ok": True},
                },
                "mcp_command_preflight": {
                    "command": "aippocampus",
                    "resolves": False,
                    "status": "console_script_not_resolvable",
                    "primary_repair_command": (
                        "python -m aippocampus_runtime.cli.facade mcp"
                    ),
                    "repair_options": [
                        "python -m aippocampus_runtime.cli.facade mcp",
                    ],
                },
            }
        )

        self.assertTrue(summary["ok"])
        self.assertTrue(summary["aippocampus_action_required"])
        self.assertEqual(
            summary["next_action"],
            "python -m aippocampus_runtime.cli.facade mcp",
        )
        self.assertFalse(summary["mcp_command_preflight"]["resolves"])
        self.assertFalse(summary["mcp_command_preflight"]["resolved_path_emitted"])

    def test_plugin_install_and_uninstall_help_show_rollback_and_dry_run_paths(self) -> None:
        install = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "plugin",
                "install",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        uninstall = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "plugin",
                "uninstall",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertIn("writes local plugin files only", install.stdout)
        self.assertIn("Rollback:", install.stdout)
        self.assertIn("--dry-run --json", install.stdout)
        self.assertIn("Use --dry-run first", uninstall.stdout)
        self.assertIn("Safe preview:", uninstall.stdout)

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
                self.assertEqual(result["host_probe_report"]["status"], "written")
                cached_probe = plugin_installer.default_host_probe_report_path(codex_home)
                self.assertTrue(cached_probe.exists())
                self.assertEqual(
                    json.loads(cached_probe.read_text(encoding="utf-8"))["validation_ok"],
                    True,
                )
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

    def test_codex_install_refreshes_existing_configured_marketplace_root(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-configured-marketplace"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                codex_home = root / "codex-home"
                configured_marketplace = root / "old-local-marketplace"
                codex_home.mkdir()
                (codex_home / "config.toml").write_text(
                    "[marketplaces.aippocampus-local]\n"
                    f"source = '{configured_marketplace}'\n",
                    encoding="utf-8",
                )
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
                    verify=False,
                    runner=runner,
                )

                self.assertTrue(result["ok"])
                self.assertEqual(result["marketplace_source"], "configured_codex_marketplace")
                self.assertEqual(Path(result["marketplace"]["root"]), configured_marketplace)
                self.assertTrue(
                    (
                        configured_marketplace
                        / "plugins"
                        / "aippocampus"
                        / ".codex-plugin"
                        / "plugin.json"
                    ).exists()
                )
                self.assertIn(
                    [
                        "plugin",
                        "marketplace",
                        "add",
                        str(configured_marketplace),
                    ],
                    runner.command_tails,
                )
                self.assertFalse((codex_home / "aippocampus-marketplace").exists())
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_interrupted_plugin_install_tmp_can_be_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marketplace_root = root / "marketplace"
            target = marketplace_root / "plugins" / "aippocampus"
            tmp_install = target.parent / ".aippocampus.tmp-aippocampus-install"
            tmp_install.mkdir(parents=True)
            (tmp_install / ".codex-plugin").mkdir()
            (tmp_install / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "aippocampus", "version": "0.0.1"}),
                encoding="utf-8",
            )

            report = plugin_installer.recover_interrupted_plugin_install(target)

            self.assertTrue(report["interrupted_install_found"])
            self.assertIn("published_tmp_install", report["recovered"])
            self.assertTrue((target / ".codex-plugin" / "plugin.json").exists())
            self.assertFalse(tmp_install.exists())
            self.assertTrue(report["write_boundary"]["written"])

    def test_codex_install_buckets_nonfatal_host_probe_stderr_after_success(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-stderr-summary"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = plugin_installer.install_codex_plugin(
                    repo_root=REPO_ROOT,
                    codex_home_path=root / "codex-home",
                    plugin_output=output,
                    verify=True,
                    runner=FakeCodexRunner(),
                    host_probe_runner=lambda **_: successful_probe_with_noisy_stderr(),
                )

            summary = result["host_probe"]["warning_summary"]
            self.assertTrue(result["ok"])
            self.assertEqual(result["agent_callable_status"], "host_live_probe_ok")
            self.assertEqual(summary["status"], "verification_passed_with_nonfatal_host_warnings")
            self.assertEqual(summary["fatal_failures"], [])
            self.assertEqual(summary["aippocampus_actionable_warnings"], [])
            self.assertGreaterEqual(len(summary["benign_host_probe_warnings"]), 4)
            self.assertEqual(len(summary["unrelated_host_or_plugin_noise"]), 1)
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_codex_host_probe_calls_key_agent_tools_not_only_sync_status(self) -> None:
        calls: list[str] = []

        class FakeAppServerClient:
            notifications: list[dict[str, str]]
            protocol_noise: list[str]
            stderr_tail: str

            def __init__(self, _command: list[str], _cwd: Path) -> None:
                self.notifications = []
                self.protocol_noise = []
                self.stderr_tail = ""

            def request(
                self,
                method: str,
                params: dict | None = None,
                *,
                timeout: float = 60.0,
                raise_on_error: bool = True,
            ) -> dict:
                del timeout, raise_on_error
                if method == "initialize":
                    return {"result": {"userAgent": "fake-codex"}}
                if method == "config/mcpServer/reload":
                    return {"result": {"ok": True}}
                if method == "mcpServerStatus/list":
                    return {
                        "result": {
                            "data": [
                                {
                                    "name": "aippocampus",
                                    "tools": {
                                        "memory_health": {},
                                        "search_memory": {},
                                        "sync_status": {},
                                        "agent_recall": {},
                                        "agent_aippo": {},
                                        "agent_background": {},
                                    },
                                }
                            ]
                        }
                    }
                if method == "thread/start":
                    return {"result": {"thread": {"id": "thread-1"}}}
                if method == "mcpServer/tool/call":
                    tool = str((params or {}).get("tool") or "")
                    calls.append(tool)
                    if tool == "sync_status":
                        payload = {
                            "status": "available_requires_sync_dir",
                            "backend": "local_folder",
                        }
                    else:
                        payload = {"kind": f"{tool}_smoke", "ok": True}
                    return {
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(payload),
                                }
                            ]
                        }
                    }
                if method == "thread/archive":
                    return {"result": {"ok": True}}
                raise AssertionError(f"unexpected app-server method: {method}")

            def close(self) -> None:
                return None

        with mock.patch.object(plugin_installer, "CodexAppServerClient", FakeAppServerClient):
            result = plugin_installer.run_codex_host_probe(
                repo_root=REPO_ROOT,
                codex_command="codex",
            )

        self.assertTrue(result["validation_ok"], result)
        self.assertEqual(calls, ["sync_status", "agent_recall", "agent_aippo", "agent_background"])
        self.assertEqual(
            [item["tool"] for item in result["key_tool_smokes"]],
            ["agent_recall", "agent_aippo", "agent_background"],
        )
        self.assertTrue(all(item["ok"] for item in result["key_tool_smokes"]))

    def test_public_install_summary_omits_paths_and_raw_host_noise(self) -> None:
        output = REPO_ROOT / "dist" / "test-plugin-installer-public-summary"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = plugin_installer.install_codex_plugin(
                    repo_root=REPO_ROOT,
                    codex_home_path=root / "codex-home",
                    plugin_output=output,
                    verify=True,
                    runner=FakeCodexRunner(),
                    host_probe_runner=lambda **_: successful_probe_with_noisy_stderr(),
                )

                summary = plugin_installer.public_install_summary(result)

            encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)
            warnings = summary["host_probe"]["warning_summary"]

            self.assertEqual(summary["kind"], "aippocampus_plugin_install_public_summary")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["agent_callable_status"], "host_live_probe_ok")
            self.assertEqual(summary["tool_count"], 8)
            self.assertGreaterEqual(summary["nonfatal_host_warning_count"], 1)
            self.assertFalse(summary["aippocampus_action_required"])
            self.assertIn("review trusted Codex action hints", summary["next_action"])
            trusted_commands = {
                action["command"] for action in summary["trusted_codex_next_actions"]
            }
            self.assertIn("aippocampus hooks action status --json", trusted_commands)
            self.assertIn("aippocampus hooks action install --json", trusted_commands)
            self.assertIn("agent_recall", summary["host_probe"]["key_tools_present"])
            self.assertIn("agent_background", summary["host_probe"]["key_tools_present"])
            self.assertEqual(summary["rollback_command"], "aippocampus plugin uninstall --codex")
            self.assertGreaterEqual(warnings["warning_count"], 1)
            self.assertGreaterEqual(
                warnings["bucket_counts"]["benign_host_probe_warnings"],
                1,
            )
            self.assertNotIn(str(root), encoded)
            self.assertNotIn(str(output), encoded)
            self.assertNotIn("stderr_tail", encoded)
            self.assertNotIn("other/plugin.json", encoded)
            self.assertNotIn("state db discrepancy", encoded)
            self.assertNotIn("marketplace_add", encoded)
            self.assertNotIn("marketplace_upgrade", encoded)
            self.assertNotIn("command_tails", encoded)
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_compact_json_is_public_summary_alias(self) -> None:
        args = plugin_installer.build_parser().parse_args(
            ["install", "--codex", "--verify", "--compact-json"]
        )

        self.assertTrue(args.public_summary)
        self.assertFalse(args.operator_json)

    def test_install_json_defaults_to_compact_success_summary(self) -> None:
        probe = plugin_installer.attach_host_probe_warning_summary(
            successful_probe_with_noisy_stderr()
        )
        result = {
            "kind": "aippocampus_plugin_install",
            "ok": True,
            "plugin": {
                "id": "aippocampus@aippocampus-local",
                "version": "0.3.2",
                "action": "marketplace_refreshed",
                "installed": True,
                "enabled": True,
            },
            "host_probe": probe,
            "agent_callable_status": "host_live_probe_ok",
            "rollback_command": "aippocampus plugin uninstall --codex",
        }

        with (
            mock.patch.object(plugin_installer, "install_codex_plugin", return_value=result),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = plugin_installer.main(["install", "--codex", "--verify", "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_plugin_install_public_summary")
        self.assertEqual(payload["agent_callable_status"], "host_live_probe_ok")
        self.assertFalse(payload["aippocampus_action_required"])
        self.assertGreaterEqual(payload["nonfatal_host_warning_count"], 1)
        self.assertNotIn("stderr_tail", encoded)
        self.assertNotIn("other/plugin.json", encoded)
        self.assertNotIn("marketplace_add", encoded)

    def test_install_permission_failure_returns_path_safe_recovery_card(self) -> None:
        raw_path = "X:" + "\\synthetic-private\\dist\\aippocampus-plugin\\.codex-plugin\\plugin.json"
        with (
            mock.patch.object(
                plugin_installer,
                "install_codex_plugin",
                side_effect=PermissionError(5, "Access denied", raw_path),
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = plugin_installer.main(["install", "--codex", "--verify", "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "aippocampus_plugin_install_recovery")
        self.assertEqual(payload["error"]["code"], "plugin_package_write_denied")
        self.assertIn("redacted", payload["error"]["path"])
        self.assertTrue(payload["privacy_boundary"]["no_private_memory_copied"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_serialized"])
        self.assertIn("operator-json", encoded)
        self.assertNotIn("PermissionError", encoded)
        self.assertNotIn(raw_path, encoded)

    def test_install_permission_failure_human_and_operator_json_stay_path_safe(self) -> None:
        raw_path = "X:" + "\\synthetic-private\\dist\\aippocampus-plugin\\.codex-plugin\\plugin.json"
        with (
            mock.patch.object(
                plugin_installer,
                "install_codex_plugin",
                side_effect=PermissionError(5, "Access denied", raw_path),
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = plugin_installer.main(["install", "--codex", "--verify"])
        human = stdout.getvalue()

        self.assertEqual(code, 1)
        self.assertIn("plugin install needs attention", human)
        self.assertIn("plugin_package_write_denied", human)
        self.assertNotIn("PermissionError", human)
        self.assertNotIn(raw_path, human)

        with (
            mock.patch.object(
                plugin_installer,
                "install_codex_plugin",
                side_effect=PermissionError(5, "Access denied", raw_path),
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = plugin_installer.main(["install", "--codex", "--verify", "--operator-json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_plugin_install_recovery")
        self.assertEqual(payload["error"]["code"], "plugin_package_write_denied")
        self.assertTrue(payload["privacy_boundary"]["operator_json_requested"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_serialized"])
        self.assertTrue(payload["operator_diagnostics"]["raw_stdout_disabled"])
        self.assertNotIn("PermissionError", encoded)
        self.assertNotIn(raw_path, encoded)

    def test_operator_json_marks_boundary_without_raw_install_report(self) -> None:
        probe = plugin_installer.attach_host_probe_warning_summary(
            successful_probe_with_noisy_stderr()
        )
        result = {
            "kind": "aippocampus_plugin_install",
            "ok": True,
            "plugin": {
                "id": "aippocampus@aippocampus-local",
                "version": "0.3.2",
                "action": "marketplace_refreshed",
                "installed": True,
                "enabled": True,
            },
            "marketplace_add": {"stdout": "added"},
            "host_probe": probe,
            "agent_callable_status": "host_live_probe_ok",
            "rollback_command": "aippocampus plugin uninstall --codex",
        }

        with (
            mock.patch.object(plugin_installer, "install_codex_plugin", return_value=result),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = plugin_installer.main(["install", "--codex", "--verify", "--operator-json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_plugin_install_public_summary")
        self.assertTrue(payload["privacy_boundary"]["operator_json_requested"])
        self.assertTrue(payload["operator_diagnostics"]["raw_stdout_disabled"])
        self.assertNotIn("stderr_tail", encoded)
        self.assertNotIn("marketplace_add", encoded)

    def test_host_probe_warning_summary_does_not_downgrade_failed_probe_noise(self) -> None:
        summary = host_probe_warnings.summarize_host_probe_warnings(
            {
                "validation_ok": False,
                "stderr_tail": "\n".join(
                    [
                        "Failed to list resources for MCP server 'aippocampus': Method not found: resources/list",
                        "Failed to kill MCP process group 12345: No such process",
                        "state db discrepancy during find_thread_path_by_id_str_in_subdir: falling_back",
                    ]
                ),
            }
        )

        self.assertEqual(summary["status"], "probe_failed_or_has_fatal_stderr")
        self.assertEqual(summary["benign_host_probe_warnings"], [])
        self.assertGreaterEqual(len(summary["aippocampus_actionable_warnings"]), 1)
        self.assertGreaterEqual(len(summary["unclassified_stderr"]), 1)

    def test_host_probe_warning_summary_keeps_true_errors_fatal_after_success(self) -> None:
        summary = host_probe_warnings.summarize_host_probe_warnings(
            {
                "validation_ok": True,
                "stderr_tail": "\n".join(
                    [
                        "Traceback (most recent call last): plugin background worker crashed",
                        "Fatal host probe invariant failed",
                        "other plugin completed background refresh",
                    ]
                ),
            }
        )

        self.assertEqual(summary["status"], "probe_failed_or_has_fatal_stderr")
        self.assertEqual(len(summary["fatal_failures"]), 2)
        self.assertEqual(len(summary["unrelated_host_or_plugin_noise"]), 1)

    def test_host_probe_warning_summary_keeps_unrelated_auth_fatal_noise_nonfatal_after_success(
        self,
    ) -> None:
        summary = host_probe_warnings.summarize_host_probe_warnings(
            {
                "validation_ok": True,
                "stderr_tail": "\n".join(
                    [
                        "Token refresh not possible, re-authorization required.",
                        "worker quit with fatal: Transport channel closed, when Auth(AuthorizationRequired)",
                        "worker quit with fatal: Client error: HTTP request failed: error sending request for url (https://chatgpt.com/backend-api/wham/apps), when send initialized notification",
                    ]
                ),
            }
        )

        self.assertEqual(summary["status"], "verification_passed_with_nonfatal_host_warnings")
        self.assertEqual(summary["fatal_failures"], [])
        self.assertEqual(len(summary["unrelated_host_or_plugin_noise"]), 3)

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
        cmd_path = "C:" + "\\Users\\Example\\AppData\\Roaming\\npm\\codex.cmd"
        exe_path = "C:" + "\\Program Files\\Codex\\codex.exe"
        with mock.patch.object(codex_plugin_cli.os, "name", "nt"):
            with mock.patch.object(
                codex_plugin_cli.shutil,
                "which",
                side_effect=lambda command: {
                    "codex.cmd": cmd_path,
                    "codex.exe": exe_path,
                }.get(command),
            ):
                self.assertEqual(
                    codex_plugin_cli.codex_base(),
                    [cmd_path],
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

    def test_codex_uninstall_dry_run_reports_plan_without_removing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            marketplace_root = plugin_installer.default_marketplace_root(codex_home)
            package = root / "package"
            (package / ".codex-plugin").mkdir(parents=True)
            (package / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "aippocampus", "version": "0.3.2"}),
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
                / "0.3.2"
            )
            plugin_installer.refresh_plugin_cache_layers(
                package_root=package,
                installed_dir=installed_cache,
            )

            result = plugin_installer.uninstall_codex_plugin_preview(
                codex_home_path=codex_home,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertTrue(result["would_remove_installed_cache"])
            self.assertTrue(result["would_remove_marketplace_root"])
            self.assertTrue(result["marketplace_owned_by_aippocampus"])
            self.assertEqual(result["execute_command"], "aippocampus plugin uninstall --codex")
            self.assertTrue(marketplace_root.exists())
            self.assertTrue(installed_cache.exists())

    def test_plugin_uninstall_cli_json_redacts_local_paths_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "plugin",
                    "uninstall",
                    "--codex",
                    "--codex-home",
                    str(codex_home),
                    "--dry-run",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            operator = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "plugin",
                    "uninstall",
                    "--codex",
                    "--codex-home",
                    str(codex_home),
                    "--dry-run",
                    "--json",
                    "--operator-json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(
            payload["kind"],
            "aippocampus_plugin_uninstall_preview_public_summary",
        )
        self.assertIn("agent_next_action", payload)
        self.assertFalse(payload["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn(str(codex_home), encoded)
        self.assertEqual(operator.returncode, 0, operator.stderr)
        operator_payload = json.loads(operator.stdout)
        operator_encoded = json.dumps(operator_payload, ensure_ascii=False)
        self.assertEqual(
            operator_payload["kind"],
            "aippocampus_plugin_uninstall_preview_public_summary",
        )
        self.assertTrue(operator_payload["privacy_boundary"]["operator_json_requested"])
        self.assertFalse(operator_payload["privacy_boundary"]["local_paths_serialized"])
        self.assertTrue(operator_payload["operator_diagnostics"]["raw_stdout_disabled"])
        self.assertNotIn(str(codex_home), operator_encoded)
