from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.update import cli as update_cli  # noqa: E402
from aippocampus_runtime.update import plugin_installer  # noqa: E402

PROVIDER_ENV_NAMES = [
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
    "AIPPOCAMPUS_COGNITIVE_WORKER_MODE",
    "AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE",
    "AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE",
    "AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE",
    "AIPPOCAMPUS_FOREGROUND_KEY_TOOL_FAILURE",
]


@contextmanager
def provider_env(extra: dict[str, str] | None = None) -> Iterator[None]:
    old = {name: os.environ.get(name) for name in PROVIDER_ENV_NAMES}
    try:
        for name in PROVIDER_ENV_NAMES:
            os.environ.pop(name, None)
        if extra:
            os.environ.update(extra)
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def pushd(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_update(*args: str) -> tuple[int, dict]:
    stdout = StringIO()
    json_flag = "--json"
    if args and args[0] in {"status", "plan"}:
        # These tests inspect the full operator tree. Foreground `--json` is now
        # intentionally agent-sized, so keep the legacy diagnostic assertions on
        # the explicit operator surface.
        json_flag = "--operator-json"
    with redirect_stdout(stdout):
        code = update_cli.main([*args, json_flag])
    payload = json.loads(stdout.getvalue())
    return code, payload


def source_plugin_version() -> str:
    manifest = json.loads(
        (
            REPO_ROOT
            / "plugins"
            / "aippocampus"
            / ".codex-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    return str(manifest["version"])


def write_minimal_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    skill = repo / "skills" / "aippocampus"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# AIppocampus fixture\n", encoding="utf-8")
    (skill / "scripts" / "runtime.py").write_text("print('ok')\n", encoding="utf-8")


def init_git_fixture(repo: Path, *, message: str = "fixture") -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "aippocampus-test@example.invalid"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AIppocampus Test"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True, text=True)


def write_plugin_package(
    root: Path,
    *,
    version: str,
    mcp_command: str = "aippocampus",
    mcp_args: list[str] | None = None,
    include_skill: bool = True,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".codex-plugin").mkdir(exist_ok=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "aippocampus", "version": version, "mcpServers": "./.mcp.json"}),
        encoding="utf-8",
    )
    (root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "aippocampus": {
                        "command": mcp_command,
                        "args": mcp_args if mcp_args is not None else ["mcp"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    if include_skill:
        (root / "skills" / "aippocampus").mkdir(parents=True, exist_ok=True)
        (root / "skills" / "aippocampus" / "SKILL.md").write_text(
            "# AIppocampus fixture\n",
            encoding="utf-8",
        )


def aippocampus_hook_commands_by_event(hooks_path: Path) -> dict[str, list[str]]:
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    for event, groups in (data.get("hooks") or {}).items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for handler in group.get("hooks") or []:
                if not isinstance(handler, dict):
                    continue
                command = str(handler.get("command") or "")
                if any(
                    marker in command
                    for marker in (
                        "aippocampus_provider_bridge_hook.py",
                        "aippocampus_runtime.hooks.prompt",
                        "aippocampus_runtime.hooks.lifecycle",
                    )
                ):
                    result.setdefault(str(event), []).append(command)
    return result


def append_direct_aippocampus_hook_duplicates(hooks_path: Path) -> None:
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    hooks = data.setdefault("hooks", {})
    hooks.setdefault("UserPromptSubmit", []).append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": update_cli.install_prompt.command_for(),
                    "timeout": update_cli.install_prompt.DEFAULT_HOOK_TIMEOUT_SECONDS,
                }
            ]
        }
    )
    for event in update_cli.HOOK_EVENTS:
        hooks.setdefault(event, []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": update_cli.install_lifecycle.command_for(),
                        "timeout": update_cli.install_lifecycle.DEFAULT_TIMEOUT_SECONDS,
                    }
                ]
            }
        )
    hooks_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class UpdateSyncTests(unittest.TestCase):
    def test_json_error_output_does_not_echo_raw_exception_text(self) -> None:
        stdout = StringIO()
        with (
            patch.object(
                update_cli,
                "build_status",
                side_effect=RuntimeError(r"private path C:\Users\Name\secret.txt"),
            ),
            redirect_stdout(stdout),
        ):
            code = update_cli.main(["status", "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "update_failed")
        self.assertNotIn("C:\\Users\\Name\\secret.txt", encoded)
        self.assertNotIn("private path", encoded)

    def test_status_reports_surfaces_and_does_not_create_hook_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            codex_home = Path(tmp) / "codex-home"
            hooks_json = codex_home / "hooks.json"

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        surfaces = payload["surfaces"]
        self.assertEqual(payload["kind"], "aippocampus_update_status")
        self.assertIn("skill", surfaces)
        self.assertIn("hooks", surfaces)
        self.assertIn("llm", surfaces)
        self.assertIn("mcp", surfaces)
        self.assertIn("plugin", surfaces)
        self.assertIn("agent_callable", surfaces)
        self.assertIn(
            surfaces["agent_callable"]["status"],
            {"artifact_current_host_not_exposed", "host_not_exposed"},
        )
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertFalse(payload["summary"]["magic_ready"])
        self.assertEqual(surfaces["hooks"]["status"], "missing")
        self.assertEqual(surfaces["llm"]["status"], "missing_provider_env_var")
        self.assertFalse(hooks_json.exists())

    def test_status_splits_core_magic_optional_and_operator_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--skill-target",
                str(REPO_ROOT / "skills" / "aippocampus"),
                "--plugin-output",
                str(root / "missing-plugin-package"),
                "--hooks-json",
                str(hooks_json),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        summary = payload["summary"]
        self.assertTrue(summary["core_ready"])
        self.assertEqual(summary["core_blockers"], [])
        self.assertFalse(summary["magic_ready"])
        self.assertIn("llm", summary["magic_blockers"])
        self.assertIn("plugin", summary["optional_surfaces"])
        self.assertIn("mcp", summary["operator_surfaces"])
        self.assertNotIn("plugin", summary["core_blockers"])
        self.assertNotIn("plugin", summary["magic_blockers"])
        self.assertNotIn("llm", summary["optional_surfaces"])

    def test_windows_lifecycle_hooks_install_hidden_launcher_without_changing_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hooks_json = Path(tmp) / "hooks.json"
            with (
                patch.object(update_cli.install_lifecycle.os, "name", "nt"),
                patch.object(
                    update_cli.install_lifecycle,
                    "windows_pythonw_executable",
                    return_value=Path("C:/Python/pythonw.exe"),
                ),
            ):
                update_cli.install_lifecycle.install(hooks_json)
                status = update_cli.install_lifecycle.status(hooks_json)
                commands = aippocampus_hook_commands_by_event(hooks_json)
            prompt_command = update_cli.install_prompt.command_for()

        lifecycle_commands = [
            command
            for event, event_commands in commands.items()
            if event in update_cli.HOOK_EVENTS
            for command in event_commands
        ]
        self.assertTrue(lifecycle_commands)
        self.assertTrue(all("pythonw.exe" in command for command in lifecycle_commands))
        self.assertEqual(status["windows_hidden_launch"]["status"], "ready")
        self.assertNotIn("pythonw.exe", prompt_command.casefold())
        self.assertIn("aippocampus_runtime.hooks.prompt", prompt_command)

    def test_lifecycle_status_warns_about_visible_windows_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hooks_json = Path(tmp) / "hooks.json"
            visible_command = (
                '$env:PYTHONPATH="C:\\repo\\skills\\aippocampus\\scripts"; '
                '& "C:\\Python\\python.exe" -m aippocampus_runtime.hooks.lifecycle'
            )
            hooks_json.write_text(
                json.dumps(
                    {
                        "hooks": {
                            event: [{"hooks": [{"type": "command", "command": visible_command}]}]
                            for event in update_cli.HOOK_EVENTS
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = update_cli.install_lifecycle.status(hooks_json)

        hidden = status["windows_hidden_launch"]
        self.assertEqual(hidden["status"], "needs_reinstall")
        self.assertFalse(hidden["ready"])
        self.assertEqual(
            hidden["warning_code"],
            "windows_lifecycle_hook_may_show_console_window",
        )
        self.assertEqual(hidden["repair_command"], "aippocampus hooks lifecycle install")

    def test_status_reports_first_run_capability_ladder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--skill-target",
                str(REPO_ROOT / "skills" / "aippocampus"),
                "--hooks-json",
                str(hooks_json),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        ladder = payload["summary"]["capability_ladder"]
        by_id = {item["id"]: item for item in ladder}

        self.assertEqual(
            list(by_id),
            [
                "source_search_ready",
                "active_recall_ready",
                "ambient_hooks_ready",
                "semantic_provider_ready",
                "hook_provider_ready",
                "dream_or_subconscious_ready",
                "agent_fallback_ready",
            ],
        )
        self.assertEqual(by_id["source_search_ready"]["status"], "ready")
        self.assertIn(
            by_id["active_recall_ready"]["status"],
            {"artifact_current_host_not_exposed", "host_not_exposed"},
        )
        self.assertFalse(by_id["active_recall_ready"]["ready"])
        self.assertIn("foreground host", by_id["active_recall_ready"]["what_works"])
        self.assertEqual(by_id["ambient_hooks_ready"]["status"], "ready")
        self.assertEqual(
            by_id["semantic_provider_ready"]["status"], "missing_provider_env_var"
        )
        self.assertEqual(
            by_id["hook_provider_ready"]["status"], "missing_provider_env_var"
        )
        self.assertEqual(
            by_id["dream_or_subconscious_ready"]["status"], "needs_semantic_provider"
        )
        self.assertEqual(
            by_id["source_search_ready"]["next_command"],
            "aippocampus onboard --provider auto --status",
        )
        self.assertFalse(by_id["agent_fallback_ready"]["ready"])
        self.assertEqual(
            by_id["agent_fallback_ready"]["status"],
            "deterministic_only_missing_provider_and_agent",
        )

    def test_status_splits_mcp_artifact_from_foreground_agent_callable_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "aippocampus": {
                                "command": "python-definitely-missing-for-aippocampus-test",
                                "args": ["-m", "aippocampus_runtime.mcp.server"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--mcp-config",
                str(mcp_config),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        mcp = payload["surfaces"]["mcp"]
        agent = payload["surfaces"]["agent_callable"]
        self.assertEqual(mcp["status"], "current")
        self.assertTrue(mcp["package_artifact_current"])
        self.assertFalse(mcp["mcp_command_resolves"])
        self.assertEqual(agent["status"], "artifact_current_host_not_exposed")
        self.assertFalse(agent["ready"])
        self.assertFalse(agent["host_plugin_installed_or_enabled"])
        self.assertFalse(agent["host_mcp_registered"])

    def test_status_reports_mcp_repair_options_when_console_script_missing_but_python3_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "aippocampus": {
                                "command": "aippocampus",
                                "args": ["mcp"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            def fake_which(command: str) -> str | None:
                if command == "python3":
                    return "/usr/bin/python3"
                return None

            with patch.object(update_cli.shutil, "which", side_effect=fake_which):
                code, payload = run_update(
                    "status",
                    "--repo-root",
                    str(REPO_ROOT),
                    "--codex-home",
                    str(codex_home),
                    "--mcp-config",
                    str(mcp_config),
                    "--no-child-check",
                )

        self.assertEqual(code, 0)
        mcp = payload["surfaces"]["mcp"]
        agent = payload["surfaces"]["agent_callable"]
        self.assertEqual(mcp["status"], "current")
        self.assertFalse(mcp["mcp_command_resolves"])
        self.assertTrue(mcp["python3_available"])
        self.assertIn(
            "python3 -m aippocampus_runtime.cli.facade mcp",
            mcp["mcp_command_repair_options"],
        )
        self.assertEqual(agent["status"], "artifact_current_host_not_exposed")
        self.assertFalse(agent["ready"])

    def test_status_reports_plugin_marketplace_and_installed_cache_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            marketplace = root / "local-marketplace" / "aippocampus"
            installed = root / "codex-home" / "plugins" / "cache" / "aippocampus-local" / "aippocampus" / "0.1.0"
            write_plugin_package(marketplace, version="0.1.0")
            write_plugin_package(installed, version="0.1.0", mcp_command="python", mcp_args=["-m", "old"])

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(root / "codex-home"),
                "--plugin-marketplace-dir",
                str(marketplace),
                "--plugin-installed-dir",
                str(installed),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        plugin = payload["surfaces"]["plugin"]
        self.assertEqual(plugin["source_plugin_version"], source_plugin_version())
        self.assertEqual(plugin["local_marketplace"]["version"], "0.1.0")
        self.assertEqual(plugin["local_marketplace"]["status"], "stale_version")
        self.assertEqual(plugin["installed_cache"]["version"], "0.1.0")
        self.assertEqual(plugin["installed_cache"]["status"], "stale_version")
        self.assertTrue(plugin["cache_boundary"]["package_artifact_is_not_installed_cache"])
        self.assertTrue(plugin["plugin_cache_recommended_actions"])
        self.assertTrue(payload["summary"]["plugin_cache_needs_action"])
        self.assertIn("plugin_cache", payload["summary"]["needs_action"])
        self.assertIn("plugin", payload["summary"]["nested_action_surfaces"])

    def test_status_uses_configured_codex_marketplace_root_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            marketplace_root = root / "local-marketplace"
            write_minimal_repo(repo)
            write_plugin_package(
                repo / "plugins" / "aippocampus",
                version="0.2.0",
                include_skill=False,
            )
            write_plugin_package(
                marketplace_root / "plugins" / "aippocampus",
                version="0.1.0",
            )
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text(
                "[marketplaces.aippocampus-local]\n"
                f"source = '{marketplace_root.as_posix()}'\n",
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0, payload)
        plugin = payload["surfaces"]["plugin"]
        self.assertEqual(
            plugin["local_marketplace_source"],
            "configured_codex_marketplace",
        )
        self.assertEqual(plugin["local_marketplace"]["version"], "0.1.0")
        self.assertEqual(plugin["local_marketplace"]["status"], "stale_version")
        self.assertTrue(payload["summary"]["plugin_cache_needs_action"])

    def test_status_recommends_auto_for_unique_installed_plugin_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            installed = codex_home / "plugins" / "cache" / "aippocampus-local" / "aippocampus" / "0.1.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(installed, version="0.1.0")

            code, payload = run_update(
                "status",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0, payload)
        plugin_status = payload["surfaces"]["plugin"]
        self.assertEqual(
            plugin_status["installed_cache_auto_resolution"]["status"],
            "unique",
        )
        self.assertIn(
            "--plugin-installed-dir auto",
            plugin_status["plugin_cache_recommended_actions"][0],
        )

    def test_status_ignores_stale_cache_from_unconfigured_legacy_marketplace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            source = repo / "plugins" / "aippocampus"
            output = repo / "dist" / "aippocampus-plugin"
            current = (
                codex_home
                / "plugins"
                / "cache"
                / "aippocampus-local"
                / "aippocampus"
                / "0.2.0"
            )
            legacy = (
                codex_home
                / "plugins"
                / "cache"
                / "local"
                / "aippocampus"
                / "0.1.0-local"
            )
            write_plugin_package(source, version="0.2.0", include_skill=False)
            write_plugin_package(output, version="0.2.0", include_skill=False)
            write_plugin_package(current, version="0.2.0", include_skill=False)
            write_plugin_package(legacy, version="0.1.0", include_skill=False)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0, payload)
        plugin_status = payload["surfaces"]["plugin"]
        self.assertEqual(plugin_status["installed_cache"]["status"], "current")
        self.assertEqual(plugin_status["auto_detected_installed_cache_count"], 1)
        self.assertEqual(plugin_status["ignored_legacy_cache_count"], 1)
        self.assertEqual(plugin_status["plugin_cache_recommended_actions"], [])
        self.assertFalse(payload["summary"]["plugin_cache_needs_action"])

    def test_status_marks_successful_host_probe_as_current_thread_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": ["memory_health", "search_memory", "sync_status"]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {
                            "status": "available_requires_sync_dir",
                            "backend": "local_folder",
                        },
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        agent = payload["surfaces"]["agent_callable"]
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertEqual(
            payload["summary"]["agent_callable_status"],
            "host_live_probe_ok_foreground_probe_not_checked",
        )
        self.assertFalse(agent["ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok_foreground_probe_not_checked")
        self.assertIsNone(agent["foreground_tools_visible"])
        self.assertEqual(
            agent["foreground_tools_visibility_source"],
            "not_checked_in_this_status_call",
        )
        self.assertFalse(agent["foreground_probe_requested"])
        self.assertEqual(agent["foreground_probe_state"], "not_requested")
        self.assertEqual(agent["current_thread_tool_discovery"], "foreground_probe_not_checked")
        self.assertEqual(agent["host_live_probe"]["status"], "ok")
        self.assertEqual(agent["host_live_probe"]["source"], "codex_app_server_smoke")
        self.assertIn("--foreground-tools-visible", agent["next_command"])
        self.assertIn("--foreground-key-tools-callable", agent["next_command"])
        self.assertTrue(payload["summary"]["agent_callable_host_ready"])
        self.assertFalse(payload["summary"]["agent_callable_current_thread_visible"])
        self.assertNotIn("agent_callable", payload["summary"]["operator_blockers"])
        self.assertNotIn("agent_callable", payload["summary"]["needs_action"])
        by_id = {item["id"]: item for item in payload["summary"]["capability_ladder"]}
        self.assertFalse(by_id["active_recall_ready"]["ready"])
        self.assertEqual(
            by_id["active_recall_ready"]["status"],
            "host_live_probe_ok_foreground_probe_not_checked",
        )

    def test_status_keeps_visible_only_foreground_tools_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({"AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE": "1"}):
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": [
                                "agent_recall",
                                "agent_aippo",
                                "agent_background",
                                "agent_deepen",
                                "agent_explain",
                            ]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {"status": "available_requires_sync_dir"},
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        agent = payload["surfaces"]["agent_callable"]
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok_current_thread_unverified")
        self.assertEqual(agent["current_thread_tool_discovery"], "tools_visible_key_tools_unverified")
        self.assertEqual(agent["foreground_tools_visibility_source"], "env:AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE")
        self.assertTrue(agent["foreground_probe_requested"])
        self.assertEqual(agent["foreground_probe_state"], "tools_visible_key_tools_unverified")
        self.assertIn("--foreground-key-tools-callable", agent["next_command"])
        self.assertEqual(len(agent["host_probe_agent_native_tools"]), 5)

    def test_status_requires_current_thread_key_tool_calls_with_cli_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": ["agent_recall", "agent_aippo", "agent_deepen"]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {"status": "available_requires_sync_dir"},
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--foreground-tools-visible",
                "--foreground-key-tools-callable",
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        agent = payload["surfaces"]["agent_callable"]
        self.assertTrue(payload["summary"]["agent_callable_ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok_current_thread_verified")
        self.assertEqual(agent["foreground_tools_visibility_source"], "cli:--foreground-tools-visible")
        self.assertTrue(agent["current_foreground_key_tools_callable"])
        self.assertTrue(agent["foreground_probe_requested"])
        self.assertEqual(agent["foreground_probe_state"], "verified_by_current_foreground_key_tool_calls")
        self.assertEqual(
            agent["current_thread_tool_discovery"],
            "verified_by_current_foreground_key_tool_calls",
        )

    def test_status_reports_current_foreground_runtime_mismatch_after_key_tool_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": ["agent_recall", "agent_aippo", "agent_deepen"]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {"status": "available_requires_sync_dir"},
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--foreground-tools-visible",
                "--foreground-key-tool-failure",
                "ImportError: cannot import compact_aippo_guidance_card from E:\\private\\old.py",
                "--no-child-check",
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        agent = payload["surfaces"]["agent_callable"]
        card = next(
            item for item in payload["summary"]["capability_ladder"]
            if item["id"] == "active_recall_ready"
        )
        self.assertEqual(code, 0)
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertTrue(payload["summary"]["agent_callable_host_ready"])
        self.assertTrue(payload["summary"]["agent_callable_current_thread_visible"])
        self.assertEqual(agent["status"], "foreground_mcp_runtime_mismatch")
        self.assertEqual(agent["current_thread_tool_discovery"], "foreground_key_tool_call_failed")
        self.assertTrue(agent["foreground_probe_requested"])
        self.assertEqual(agent["foreground_probe_state"], "foreground_key_tool_call_failed")
        self.assertFalse(agent["current_foreground_key_tools_callable"])
        self.assertTrue(agent["live_host_schema_stale"])
        self.assertIn("aippocampus agent recall", agent["next_command"])
        self.assertEqual(card["status"], "foreground_mcp_runtime_mismatch")
        self.assertNotIn("E:\\private", encoded)

    def test_status_detects_stale_live_host_when_key_tool_smoke_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": False,
                        "mcp_status": {
                            "tool_names": [
                                "memory_health",
                                "search_memory",
                                "sync_status",
                                "agent_recall",
                                "agent_aippo",
                            ]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {
                            "status": "available_requires_sync_dir",
                            "backend": "local_folder",
                        },
                        "key_tool_smokes": [
                            {
                                "tool": "agent_recall",
                                "ok": False,
                                "is_error": True,
                                "error_code": "tool_failed",
                                "error_message": (
                                    "ImportError: cannot import name 'compact_aippo_guidance_card' "
                                    "from E:\\private\\plugin\\server.py"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--foreground-tools-visible",
                "--no-child-check",
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        agent = payload["surfaces"]["agent_callable"]
        self.assertEqual(code, 0)
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertFalse(payload["summary"]["agent_callable_host_ready"])
        self.assertEqual(agent["status"], "host_live_probe_key_tools_failed")
        self.assertTrue(agent["tools_visible"])
        self.assertFalse(agent["key_tools_callable"])
        self.assertTrue(agent["live_host_schema_stale"])
        self.assertEqual(agent["current_thread_tool_discovery"], "tools_visible_but_key_tools_failed")
        self.assertIn("reload Codex Desktop", agent["next_command"])
        self.assertEqual(payload["summary"]["host_conformance_label"], "cli_only")
        self.assertFalse(payload["surfaces"]["host_conformance"]["dimensions"]["live_schema_fresh"])
        self.assertNotIn("E:\\private", encoded)

    def test_status_reports_host_conformance_label_for_recall_deepen_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({
            "AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE": "1",
            "AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE": "1",
        }):
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": [
                                "memory_health",
                                "search_memory",
                                "sync_status",
                                "agent_recall",
                                "agent_deepen",
                            ]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {
                            "status": "available_requires_sync_dir",
                            "backend": "local_folder",
                        },
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--host-probe-report",
                str(probe),
                "--no-child-check",
            )

        conformance = payload["surfaces"]["host_conformance"]
        self.assertEqual(code, 0)
        self.assertEqual(payload["summary"]["host_conformance_label"], "recall_deepen")
        self.assertEqual(conformance["label"], "recall_deepen")
        self.assertTrue(conformance["dimensions"]["recall_callable"])
        self.assertTrue(conformance["dimensions"]["deepen_callable"])
        self.assertTrue(conformance["dimensions"]["first_magic_moment_path"])

    def test_status_uses_default_host_probe_cache_from_plugin_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = plugin_installer.default_host_probe_report_path(codex_home)
            probe.parent.mkdir(parents=True)
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {
                            "tool_names": ["memory_health", "search_memory", "sync_status"]
                        },
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {
                            "status": "available_requires_sync_dir",
                            "backend": "local_folder",
                        },
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        agent = payload["surfaces"]["agent_callable"]
        self.assertFalse(payload["summary"]["agent_callable_ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok_foreground_probe_not_checked")
        self.assertEqual(agent["host_live_probe"]["status"], "ok")
        self.assertEqual(agent["host_live_probe"]["source"], "codex_app_server_smoke")
        self.assertTrue(payload["summary"]["agent_callable_host_ready"])
        self.assertFalse(payload["summary"]["agent_callable_current_thread_visible"])
        self.assertNotIn("agent_callable", payload["summary"]["operator_blockers"])
        self.assertNotIn("agent_callable", payload["summary"]["needs_action"])

    def test_status_agent_json_is_compact_and_splits_host_from_current_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            probe = root / "codex-host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {"tool_names": ["memory_health", "search_memory"]},
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {"status": "available_requires_sync_dir"},
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "status",
                        "--repo-root",
                        str(REPO_ROOT),
                        "--codex-home",
                        str(codex_home),
                        "--host-probe-report",
                        str(probe),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )

        raw = stdout.getvalue()
        payload = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_update_status_agent_json")
        self.assertTrue(payload["summary"]["agent_callable_host_ready"])
        self.assertFalse(payload["summary"]["agent_callable_current_thread_visible"])
        self.assertIn(
            "current_thread_tool_discovery",
            payload["summary"]["foreground_actions"],
        )
        self.assertTrue(
            any(
                card["id"] == "current_thread_tool_discovery"
                for card in payload["foreground_status_cards"]
            )
        )
        current_thread_card = next(
            card
            for card in payload["foreground_status_cards"]
            if card["id"] == "current_thread_tool_discovery"
        )
        self.assertTrue(current_thread_card["command"].startswith("aippocampus "))
        self.assertIn("agent_recall", current_thread_card["manual_instruction"])
        self.assertNotIn("call agent_recall", current_thread_card["command"])
        self.assertNotIn("<summary>", json.dumps(current_thread_card, ensure_ascii=False))
        self.assertNotIn("agent_callable", payload["summary"]["needs_action"])
        self.assertEqual(
            payload["agent_callable"]["status"],
            "host_live_probe_ok_foreground_probe_not_checked",
        )
        self.assertTrue(payload["agent_callable"]["host_live_probe_ok"])
        self.assertFalse(payload["agent_callable"]["foreground_probe_requested"])
        self.assertEqual(payload["agent_callable"]["foreground_probe_state"], "not_requested")
        self.assertEqual(
            payload["agent_callable"]["current_thread_tool_discovery"],
            "foreground_probe_not_checked",
        )
        self.assertFalse(payload["summary"]["action_hints_ready"])
        self.assertFalse(payload["summary"]["action_hints_installed"])
        self.assertEqual(payload["summary"]["action_hints_status"], "not_installed")
        self.assertEqual(payload["action_hints"]["setup_role"], "recommended_for_trusted_codex")
        self.assertFalse(payload["action_hints"]["optional"])
        self.assertEqual(payload["action_hints"]["status"], "not_installed")
        self.assertIn(
            "action_hint_setup",
            payload["summary"]["foreground_actions"],
        )
        recommended = payload["action_hints"]["recommended_next_actions"]
        self.assertIn("install_action_hints", {item["id"] for item in recommended})
        self.assertIn("refresh_action_hints", {item["id"] for item in recommended})
        self.assertNotIn("action_hints", payload["summary"]["needs_action"])
        self.assertIsInstance(payload["next_actions"], list)
        agent_actions = [
            action for action in payload["next_actions"] if action.get("surface") == "agent_callable"
        ]
        self.assertTrue(agent_actions)
        self.assertTrue(agent_actions[0]["command"].startswith("aippocampus "))
        self.assertNotIn(str(codex_home), raw)
        self.assertNotIn(str(probe), raw)

    def test_status_agent_json_splits_action_hint_cache_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            cache_path = codex_home / "missing-action-hints.jsonl"
            update_cli.install_action_hint.install(hooks_json, cache_jsonl=cache_path)
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "status",
                        "--repo-root",
                        str(REPO_ROOT),
                        "--codex-home",
                        str(codex_home),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )

        raw = stdout.getvalue()
        payload = json.loads(raw)
        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["summary"]["action_hints_ready"])
        self.assertTrue(payload["summary"]["action_hints_installed"])
        self.assertEqual(payload["summary"]["action_hints_status"], "with_missing_cache_file")
        self.assertEqual(payload["action_hints"]["status"], "with_missing_cache_file")
        self.assertFalse(payload["action_hints"]["cache_exists"])
        self.assertIn("action_hints", {action["surface"] for action in payload["next_actions"]})
        self.assertNotIn(str(codex_home), raw)
        self.assertNotIn(str(cache_path), raw)

    def test_status_reports_staging_only_agent_fallback_when_host_capability_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({"AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE": "1"}):
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--skill-target",
                str(REPO_ROOT / "skills" / "aippocampus"),
                "--hooks-json",
                str(hooks_json),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        by_id = {item["id"]: item for item in payload["summary"]["capability_ladder"]}
        fallback = by_id["agent_fallback_ready"]
        self.assertTrue(fallback["ready"])
        self.assertEqual(fallback["status"], "agent_fallback_staging_only")
        self.assertEqual(fallback["diagnostic_status"], "agent_fallback_active")
        self.assertIn("staging-only", fallback["claim_boundary"])

    def test_status_does_not_claim_hook_provider_visibility_when_child_check_skipped(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({"DEEPSEEK_API_KEY": "test"}):
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--skill-target",
                str(REPO_ROOT / "skills" / "aippocampus"),
                "--hooks-json",
                str(hooks_json),
                "--no-child-check",
            )

        self.assertEqual(code, 0)
        by_id = {item["id"]: item for item in payload["summary"]["capability_ladder"]}
        self.assertEqual(by_id["semantic_provider_ready"]["status"], "ready")
        self.assertEqual(
            by_id["hook_provider_ready"]["status"], "child_process_not_checked"
        )
        self.assertFalse(by_id["hook_provider_ready"]["ready"])

    def test_status_marks_hook_provider_ready_when_child_process_inherits_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({"DEEPSEEK_API_KEY": "test"}):
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(REPO_ROOT),
                "--codex-home",
                str(codex_home),
                "--skill-target",
                str(REPO_ROOT / "skills" / "aippocampus"),
                "--hooks-json",
                str(hooks_json),
            )

        self.assertEqual(code, 0)
        by_id = {item["id"]: item for item in payload["summary"]["capability_ladder"]}
        self.assertEqual(by_id["semantic_provider_ready"]["status"], "ready")
        self.assertEqual(by_id["hook_provider_ready"]["status"], "ready")
        self.assertTrue(by_id["hook_provider_ready"]["ready"])
        self.assertEqual(
            by_id["hook_provider_ready"]["next_command"],
            "aippocampus hooks prompt status --last",
        )

    def test_status_text_leads_with_core_and_magic_not_generic_needs_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "status",
                        "--repo-root",
                        str(REPO_ROOT),
                        "--codex-home",
                        str(codex_home),
                        "--skill-target",
                        str(REPO_ROOT / "skills" / "aippocampus"),
                        "--plugin-output",
                        str(root / "missing-plugin-package"),
                        "--hooks-json",
                        str(hooks_json),
                        "--no-child-check",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Frontstage next:", output)
        self.assertIn("Core ready: true", output)
        self.assertIn("Magic ready: false", output)
        self.assertIn("Magic blockers: llm", output)
        self.assertIn("Optional surfaces: plugin", output)
        self.assertIn("Agent-callable surfaces:", output)
        self.assertIn("First-run readiness:", output)
        self.assertIn("source_search_ready: ready", output)
        self.assertIn("ambient_hooks_ready: ready", output)
        self.assertIn("semantic_provider_ready: missing_provider_env_var", output)
        self.assertIn(
            "agent_fallback_ready: deterministic_only_missing_provider_and_agent",
            output,
        )
        self.assertLess(output.index("Frontstage next:"), output.index("- skill:"))
        self.assertNotIn("Still needs action: plugin, llm", output)

    def test_apply_help_leads_with_mutating_surface_card(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            update_cli.build_parser().parse_args(["apply", "--help"])

        output = stdout.getvalue()
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage: aippocampus update apply [--surface SURFACE]", output)
        self.assertIn("Mutating surface decision card", output)
        self.assertIn("skill   replaces only the installable skill package", output)
        self.assertIn("hooks   writes/merges Codex hook entries", output)
        self.assertIn("rollback with matching hooks", output)
        self.assertIn("--all-local is a broad bootstrap/repair shortcut", output)

    def test_skill_apply_updates_stale_copy_and_excludes_distribution_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            skill = repo / "skills" / "aippocampus"
            (skill / ".ruff_cache").mkdir()
            (skill / ".ruff_cache" / "cache").write_text("noise", encoding="utf-8")
            (skill / "aippocampus_runtime.egg-info").mkdir()
            (skill / "aippocampus_runtime.egg-info" / "PKG-INFO").write_text(
                "noise", encoding="utf-8"
            )
            (skill / "scripts" / "__pycache__").mkdir()
            (skill / "scripts" / "__pycache__" / "runtime.pyc").write_bytes(b"noise")
            (skill / "scripts" / "runtime.pyo").write_bytes(b"noise")
            (skill / ".aippocampus").mkdir()
            (skill / ".aippocampus" / "index.json").write_text("{}", encoding="utf-8")
            target = codex_home / "skills" / "aippocampus"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("old\n", encoding="utf-8")

            code, payload = run_update(
                "apply",
                "--surface",
                "skill",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "# AIppocampus fixture\n")
            self.assertTrue((target / "scripts" / "runtime.py").exists())
            self.assertFalse((target / ".ruff_cache").exists())
            self.assertFalse((target / "aippocampus_runtime.egg-info").exists())
            self.assertFalse((target / "scripts" / "__pycache__").exists())
            self.assertFalse((target / "scripts" / "runtime.pyo").exists())
            self.assertFalse((target / ".aippocampus").exists())
            self.assertTrue(payload["applied_surfaces"][0]["ok"])

    def test_apply_blocks_dirty_git_source_before_replacing_skill_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            target = codex_home / "skills" / "aippocampus"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("old target stays\n", encoding="utf-8")
            init_git_fixture(repo)
            (repo / "skills" / "aippocampus" / "SKILL.md").write_text(
                "# dirty source\n",
                encoding="utf-8",
            )

            code, payload = run_update(
                "apply",
                "--surface",
                "skill",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            self.assertEqual(code, 2, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["status"], "blocked_dirty_worktree")
            self.assertTrue(payload["dirty_worktree_detected"])
            self.assertEqual(payload["surface"], "skill")
            self.assertIn("skills/aippocampus/SKILL.md", payload["dirty_paths"])
            self.assertIn("source_path", payload["would_write"])
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "old target stays\n")
            commands = {action["command"] for action in payload["safe_next_actions"]}
            self.assertIn("git status --short", commands)
            self.assertIn("aippocampus update plan --json", commands)

    def test_apply_allows_clean_git_source_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            init_git_fixture(repo)

            code, payload = run_update(
                "apply",
                "--surface",
                "skill",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["applied_surfaces"][0]["ok"])
            self.assertNotIn("dirty_worktree_override", payload["applied_surfaces"][0])

    def test_apply_blocks_dirty_git_target_without_auto_stashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            target_repo = root / "target-repo"
            write_minimal_repo(repo)
            target = target_repo / "skills" / "aippocampus"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("tracked target\n", encoding="utf-8")
            init_git_fixture(target_repo, message="target fixture")
            (target / "SKILL.md").write_text("dirty target\n", encoding="utf-8")

            code, payload = run_update(
                "apply",
                "--surface",
                "skill",
                "--repo-root",
                str(repo),
                "--skill-target",
                str(target),
                "--codex-home",
                str(root / "codex-home"),
                "--no-child-check",
            )

            self.assertEqual(code, 2, payload)
            self.assertEqual(payload["status"], "blocked_dirty_worktree")
            self.assertEqual(payload["surface"], "skill")
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "dirty target\n")
            self.assertFalse(payload["override_used"])
            self.assertIn("--force-dirty-worktree", payload["override"])

    def test_apply_force_dirty_worktree_override_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            init_git_fixture(repo)
            (repo / "skills" / "aippocampus" / "SKILL.md").write_text(
                "# dirty source but reviewed\n",
                encoding="utf-8",
            )

            code, payload = run_update(
                "apply",
                "--surface",
                "skill",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--force-dirty-worktree",
                "--no-child-check",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["applied_surfaces"][0]["ok"])
            self.assertTrue(payload["applied_surfaces"][0]["dirty_worktree_override"])
            self.assertEqual(
                (codex_home / "skills" / "aippocampus" / "SKILL.md").read_text(encoding="utf-8"),
                "# dirty source but reviewed\n",
            )

    def test_status_detects_stale_mcp_config_and_flat_script_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            (plugin / ".mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "aippocampus": {
                                "command": "python",
                                "args": ["skills/aippocampus/scripts/aippocampus_mcp_server.py"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            hooks = codex_home / "hooks.json"
            hooks.parent.mkdir(parents=True)
            hooks.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [
                                {"hooks": [{"type": "command", "command": "python aippocampus_prompt_hook.py"}]}
                            ],
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "python aippocampus_lifecycle_hook.py",
                                        }
                                    ]
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "plan",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            self.assertEqual(code, 0)
            self.assertEqual(payload["surfaces"]["mcp"]["status"], "stale")
            self.assertTrue(payload["surfaces"]["mcp"]["stale_flat_script"])
            self.assertEqual(payload["surfaces"]["hooks"]["status"], "stale")
            self.assertTrue(payload["surfaces"]["hooks"]["stale_flat_script_commands"])
            self.assertIn("hooks", payload["summary"]["needs_action"])

    def test_hooks_apply_replaces_old_flat_script_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            hooks = codex_home / "hooks.json"
            hooks.parent.mkdir(parents=True)
            hooks.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [
                                {"hooks": [{"type": "command", "command": "python ambient_recall_hook.py"}]}
                            ],
                            "Stop": [
                                {"hooks": [{"type": "command", "command": "python memory_maintenance_hook.py"}]}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            code, payload = run_update(
                "apply",
                "--surface",
                "hooks",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )
            data = hooks.read_text(encoding="utf-8")

            self.assertEqual(code, 0, payload)
            self.assertNotIn("ambient_recall_hook.py", data)
            self.assertNotIn("memory_maintenance_hook.py", data)
            self.assertIn("aippocampus_runtime.hooks.prompt", data)
            self.assertIn("aippocampus_runtime.hooks.lifecycle", data)
            self.assertTrue(payload["applied_surfaces"][0]["ok"])

    def test_update_status_treats_provider_bridge_wrapper_as_current_hooks(self) -> None:
        from aippocampus_runtime.ops import provider_key_bridge

        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            write_minimal_repo(repo)
            provider_env_var = "PROVIDER_UPDATE_BRIDGE_VALUE"
            fixture_prefix = "".join(chr(code) for code in (115, 107, 45))
            fixture_value = fixture_prefix + "FAKE_TEST_UPDATE_PROVIDER_BRIDGE_1234567890"
            dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")
            provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=provider_env_var,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )

            code, payload = run_update(
                "status",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["surfaces"]["hooks"]["status"], "current")
        self.assertTrue(payload["surfaces"]["hooks"]["provider_key_bridge_installed"])
        self.assertNotIn(fixture_value, json.dumps(payload, ensure_ascii=False))

    def test_update_status_reports_bridge_and_direct_duplicate_execution(self) -> None:
        from aippocampus_runtime.ops import provider_key_bridge

        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            dotenv = root / "provider.env"
            write_minimal_repo(repo)
            provider_env_var = "PROVIDER_UPDATE_BRIDGE_DUPLICATE"
            fixture_value = "sk-FAKE_TEST_UPDATE_PROVIDER_BRIDGE_DUPLICATE_1234567890"
            dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")
            provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=provider_env_var,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )
            append_direct_aippocampus_hook_duplicates(hooks_json)

            code, payload = run_update(
                "status",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        hooks = payload["surfaces"]["hooks"]
        self.assertEqual(code, 0, payload)
        self.assertEqual(hooks["status"], "duplicate_effective_hook_execution")
        self.assertTrue(hooks["provider_key_bridge_installed"])
        self.assertIn("duplicate_effective_hook_execution", hooks["reason_codes"])
        self.assertIn("aippocampus update apply --surface hooks", hooks["recommended_actions"])
        duplicate_events = {
            row["event"] for row in hooks["duplicate_effective_hook_execution"]
        }
        self.assertEqual(
            duplicate_events,
            {"UserPromptSubmit", "SessionStart", "Stop", "PreCompact", "PostCompact"},
        )
        for row in hooks["duplicate_effective_hook_execution"]:
            self.assertEqual(set(row["handler_kinds"]), {"bridge", "direct"})
        self.assertIn("hooks", payload["summary"]["needs_action"])
        self.assertNotIn(fixture_value, json.dumps(payload, ensure_ascii=False))

    def test_hooks_apply_normalizes_provider_bridge_and_direct_duplicates(self) -> None:
        from aippocampus_runtime.ops import provider_key_bridge

        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            dotenv = root / "provider.env"
            write_minimal_repo(repo)
            provider_env_var = "PROVIDER_UPDATE_BRIDGE_NORMALIZE"
            fixture_value = "sk-FAKE_TEST_UPDATE_PROVIDER_BRIDGE_NORMALIZE_1234567890"
            dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")
            provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=provider_env_var,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )
            append_direct_aippocampus_hook_duplicates(hooks_json)

            code, payload = run_update(
                "apply",
                "--surface",
                "hooks",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )
            commands = aippocampus_hook_commands_by_event(hooks_json)

        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["applied_surfaces"][0]["ok"])
        self.assertNotIn("hooks", payload["post_status"]["needs_action"])
        self.assertEqual(
            set(commands),
            {"UserPromptSubmit", "SessionStart", "Stop", "PreCompact", "PostCompact"},
        )
        for event, event_commands in commands.items():
            self.assertEqual(len(event_commands), 1, event)
            self.assertIn("aippocampus_provider_bridge_hook.py", event_commands[0])
            self.assertNotIn("aippocampus_runtime.hooks.prompt", event_commands[0])
            self.assertNotIn("aippocampus_runtime.hooks.lifecycle", event_commands[0])
        self.assertNotIn(fixture_value, json.dumps(payload, ensure_ascii=False))

    def test_provider_bridge_apply_replaces_existing_direct_hooks(self) -> None:
        from aippocampus_runtime.ops import provider_key_bridge

        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            hooks_json = codex_home / "hooks.json"
            dotenv = root / "provider.env"
            provider_env_var = "PROVIDER_UPDATE_BRIDGE_DIRECT_FIRST"
            fixture_value = "sk-FAKE_TEST_UPDATE_PROVIDER_BRIDGE_DIRECT_FIRST_1234567890"
            dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")
            update_cli.install_prompt.install(hooks_json)
            update_cli.install_lifecycle.install(hooks_json)

            report = provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=provider_env_var,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )
            commands = aippocampus_hook_commands_by_event(hooks_json)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            set(commands),
            {"UserPromptSubmit", "SessionStart", "Stop", "PreCompact", "PostCompact"},
        )
        for event, event_commands in commands.items():
            self.assertEqual(len(event_commands), 1, event)
            self.assertIn("aippocampus_provider_bridge_hook.py", event_commands[0])
            self.assertNotIn("aippocampus_runtime.hooks.prompt", event_commands[0])
            self.assertNotIn("aippocampus_runtime.hooks.lifecycle", event_commands[0])
        self.assertNotIn(fixture_value, json.dumps(report, ensure_ascii=False))

    def test_plugin_apply_rebuilds_staged_package_without_hook_or_cache_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            (plugin / ".mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "aippocampus": {
                                "command": "python",
                                "args": ["-m", "aippocampus_runtime.mcp.server"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (plugin / ".codex-plugin").mkdir()
            (plugin / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "aippocampus", "mcpServers": "./.mcp.json"}),
                encoding="utf-8",
            )
            (plugin / ".pytest_cache").mkdir()
            (plugin / ".pytest_cache" / "noise").write_text("noise", encoding="utf-8")
            (plugin / "plugin.egg-info").mkdir()
            (plugin / "plugin.egg-info" / "PKG-INFO").write_text("noise", encoding="utf-8")

            code, payload = run_update(
                "apply",
                "--surface",
                "plugin",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(root / "codex-home"),
                "--no-child-check",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue((output / ".mcp.json").exists())
            self.assertTrue((output / "skills" / "aippocampus" / "SKILL.md").exists())
            self.assertFalse((output / ".pytest_cache").exists())
            self.assertFalse((output / "plugin.egg-info").exists())
            self.assertFalse(payload["applied_surfaces"][0]["builder"]["hooks_auto_enabled"])
            self.assertTrue(payload["applied_surfaces"][0]["ok"])
            self.assertFalse(payload["applied_surfaces"][0]["cache_refresh"]["requested"])

    def test_plugin_apply_can_refresh_local_marketplace_and_installed_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            marketplace = root / "local-marketplace" / "aippocampus"
            installed = root / "codex-home" / "plugins" / "cache" / "aippocampus-local" / "aippocampus" / "0.1.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(marketplace, version="0.1.0")
            write_plugin_package(installed, version="0.1.0", mcp_command="python3", mcp_args=["-m", "aippocampus_runtime.mcp.server"])

            code, payload = run_update(
                "apply",
                "--surface",
                "plugin",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--plugin-marketplace-dir",
                str(marketplace),
                "--plugin-installed-dir",
                str(installed),
                "--codex-home",
                str(root / "codex-home"),
                "--no-child-check",
            )

            self.assertEqual(code, 0, payload)
            applied = payload["applied_surfaces"][0]
            self.assertTrue(applied["ok"])
            self.assertTrue(applied["cache_refresh"]["requested"])
            self.assertTrue(
                applied["cache_refresh"]["refreshed"]["installed_cache"][
                    "portable_mcp_config_preserved"
                ]
            )
            marketplace_manifest = json.loads(
                (marketplace / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            installed_manifest = json.loads(
                (installed / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            installed_mcp = json.loads((installed / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual(marketplace_manifest["version"], "0.2.0")
        self.assertEqual(installed_manifest["version"], "0.2.0")
        self.assertEqual(
            installed_mcp["mcpServers"]["aippocampus"]["command"],
            "python3",
        )

    def test_all_local_refreshes_configured_local_marketplace_without_extra_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            marketplace_root = root / "local-marketplace"
            marketplace_plugin = marketplace_root / "plugins" / "aippocampus"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(marketplace_plugin, version="0.1.0")
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text(
                "[marketplaces.aippocampus-local]\n"
                f"source = '{marketplace_root.as_posix()}'\n",
                encoding="utf-8",
            )

            code, payload = run_update(
                "apply",
                "--all-local",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )
            plugin_result = next(
                item for item in payload["applied_surfaces"] if item["surface"] == "plugin"
            )
            marketplace_manifest = json.loads(
                (marketplace_plugin / ".codex-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(code, 0, payload)
        self.assertTrue(plugin_result["ok"])
        self.assertEqual(marketplace_manifest["version"], "0.2.0")
        self.assertIn("local_marketplace", plugin_result["cache_refresh"]["refreshed"])

    def test_all_local_resolves_relative_marketplace_source_from_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            cwd = root / "agent-cwd"
            relative_source = Path("relative-marketplace")
            marketplace_plugin = codex_home / relative_source / "plugins" / "aippocampus"
            stray_cwd_marketplace = cwd / relative_source
            write_minimal_repo(repo)
            cwd.mkdir()
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(marketplace_plugin, version="0.1.0")
            codex_home.mkdir(parents=True, exist_ok=True)
            (codex_home / "config.toml").write_text(
                "[marketplaces.aippocampus-local]\n"
                "source = 'relative-marketplace'\n",
                encoding="utf-8",
            )

            with pushd(cwd):
                code, payload = run_update(
                    "apply",
                    "--all-local",
                    "--repo-root",
                    str(repo),
                    "--plugin-output",
                    str(output),
                    "--codex-home",
                    str(codex_home),
                    "--no-child-check",
                )
            plugin_result = next(
                item for item in payload["applied_surfaces"] if item["surface"] == "plugin"
            )
            marketplace_manifest = json.loads(
                (marketplace_plugin / ".codex-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                )
            )
            stray_created = stray_cwd_marketplace.exists()
            refreshed = plugin_result["cache_refresh"]["refreshed"]["local_marketplace"]

        self.assertEqual(code, 0, payload)
        self.assertTrue(plugin_result["ok"])
        self.assertEqual(marketplace_manifest["version"], "0.2.0")
        self.assertFalse(stray_created)
        self.assertTrue(refreshed["ok"])
        self.assertIn("<redacted:local-path>", refreshed["target_path"])

    def test_plugin_apply_auto_reports_requested_when_multiple_cache_candidates_block_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            cache_root = root / "codex-home" / "plugins" / "cache" / "aippocampus-local" / "aippocampus"
            first = cache_root / "0.1.0"
            second = cache_root / "0.1.1"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(first, version="0.1.0", mcp_command="python3")
            write_plugin_package(second, version="0.1.1", mcp_command="python3")

            code, payload = run_update(
                "apply",
                "--surface",
                "plugin",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--plugin-installed-dir",
                "auto",
                "--codex-home",
                str(root / "codex-home"),
                "--no-child-check",
            )

        applied = payload["applied_surfaces"][0]
        cache_refresh = applied["cache_refresh"]
        self.assertEqual(code, 1, payload)
        self.assertFalse(applied["ok"])
        self.assertTrue(cache_refresh["requested"])
        self.assertEqual(cache_refresh["requested_kind"], "installed_cache_auto")
        self.assertTrue(cache_refresh["auto_refresh_blocked"])
        self.assertEqual(cache_refresh["blocked_reason"], "multiple_candidates")
        self.assertEqual(cache_refresh["candidate_count"], 2)
        self.assertIn("plugin install --codex --verify --compact-json", cache_refresh["next_command"])
        self.assertIn("--plugin-installed-dir <path>", cache_refresh["manual_selection_command"])

    def test_apply_agent_json_reports_plugin_cache_failure_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            cache_root = codex_home / "plugins" / "cache" / "aippocampus-local" / "aippocampus"
            first = cache_root / "0.1.0"
            second = cache_root / "0.1.1"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(first, version="0.1.0", mcp_command="python3")
            write_plugin_package(second, version="0.1.1", mcp_command="python3")
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "apply",
                        "--all-local",
                        "--repo-root",
                        str(repo),
                        "--plugin-output",
                        str(output),
                        "--codex-home",
                        str(codex_home),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1, payload)
        self.assertEqual(payload["kind"], "aippocampus_update_apply_agent_json")
        self.assertFalse(payload["ok"])
        self.assertIn("plugin_cache", payload["summary"]["needs_action"])
        action = next(item for item in payload["next_actions"] if item["surface"] == "plugin_cache")
        self.assertIn("multiple_candidates", action["reason"])
        self.assertIn("2 candidates", action["reason"])
        self.assertIn("plugin install --codex --verify --compact-json", action["command"])

    def test_all_local_refreshes_matching_version_among_multiple_cache_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            cache_root = codex_home / "plugins" / "cache" / "aippocampus-local" / "aippocampus"
            old_cache = cache_root / "0.1.0"
            current_cache = cache_root / "0.2.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(old_cache, version="0.1.0", mcp_command="python3")
            write_plugin_package(current_cache, version="0.2.0", mcp_command="python3")

            code, payload = run_update(
                "apply",
                "--all-local",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            plugin_result = next(
                item for item in payload["applied_surfaces"] if item["surface"] == "plugin"
            )
            cache_refresh = plugin_result["cache_refresh"]

        self.assertEqual(code, 0, payload)
        self.assertTrue(plugin_result["ok"])
        self.assertTrue(cache_refresh["ok"])
        self.assertEqual(
            cache_refresh["installed_cache_auto_resolution"]["status"],
            "unique_version_match",
        )
        self.assertEqual(
            cache_refresh["installed_cache_auto_resolution"]["selection_basis"],
            "matching_plugin_version",
        )
        self.assertEqual(cache_refresh["installed_cache_status"], "current")

    def test_all_local_does_not_fail_when_multiple_cache_candidates_already_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            cache_root = codex_home / "plugins" / "cache" / "aippocampus-local" / "aippocampus"
            old_cache = cache_root / "0.1.0"
            current_cache = cache_root / "0.2.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(old_cache, version="0.1.0", mcp_command="python3")

            prep_code, prep_payload = run_update(
                "apply",
                "--surface",
                "plugin",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--plugin-installed-dir",
                str(current_cache),
                "--no-child-check",
            )
            self.assertEqual(prep_code, 0, prep_payload)

            code, payload = run_update(
                "apply",
                "--all-local",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            plugin_result = next(
                item for item in payload["applied_surfaces"] if item["surface"] == "plugin"
            )
            cache_refresh = plugin_result["cache_refresh"]

        self.assertEqual(code, 0, payload)
        self.assertTrue(plugin_result["ok"])
        self.assertTrue(cache_refresh["ok"])
        self.assertFalse(cache_refresh.get("auto_refresh_blocked", False))
        self.assertEqual(
            cache_refresh["installed_cache_auto_resolution"]["status"],
            "unique_version_match",
        )
        self.assertEqual(
            cache_refresh["installed_cache_auto_resolution"]["selection_basis"],
            "matching_plugin_version",
        )
        self.assertEqual(cache_refresh["installed_cache_status"], "current")

    def test_plugin_apply_can_refresh_unique_installed_cache_with_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            installed = root / "codex-home" / "plugins" / "cache" / "aippocampus-local" / "aippocampus" / "0.1.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(installed, version="0.1.0", mcp_command="python3")

            code, payload = run_update(
                "apply",
                "--surface",
                "plugin",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--plugin-installed-dir",
                "auto",
                "--codex-home",
                str(root / "codex-home"),
                "--no-child-check",
            )

            applied = payload["applied_surfaces"][0]
            installed_manifest = json.loads(
                (installed / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )

        self.assertEqual(code, 0, payload)
        self.assertTrue(applied["ok"])
        self.assertEqual(
            applied["cache_refresh"]["installed_cache_auto_resolution"]["status"],
            "unique",
        )
        self.assertEqual(installed_manifest["version"], "0.2.0")

    def test_all_local_refreshes_unique_installed_plugin_cache_without_extra_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            installed = codex_home / "plugins" / "cache" / "aippocampus-local" / "aippocampus" / "0.1.0"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            write_plugin_package(installed, version="0.1.0", mcp_command="python3")

            code, payload = run_update(
                "apply",
                "--all-local",
                "--repo-root",
                str(repo),
                "--plugin-output",
                str(output),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

            plugin_result = next(
                item for item in payload["applied_surfaces"] if item["surface"] == "plugin"
            )
            installed_manifest = json.loads(
                (installed / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )

        self.assertEqual(code, 0, payload)
        self.assertTrue(plugin_result["ok"])
        self.assertTrue(plugin_result["cache_refresh"]["requested"])
        self.assertEqual(
            plugin_result["cache_refresh"]["installed_cache_auto_resolution"]["status"],
            "unique",
        )
        self.assertEqual(installed_manifest["version"], "0.2.0")

    def test_all_local_agent_json_reports_host_reload_followup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            output = repo / "dist" / "aippocampus-plugin"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py", plugin)
            write_plugin_package(plugin, version="0.2.0", include_skill=False)
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "apply",
                        "--all-local",
                        "--repo-root",
                        str(repo),
                        "--plugin-output",
                        str(output),
                        "--codex-home",
                        str(codex_home),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["kind"], "aippocampus_update_apply_agent_json")
        action = next(
            item for item in payload["next_actions"] if item["surface"] == "agent_callable"
        )
        self.assertIn("Reload Codex Desktop", action["manual_instruction"])
        self.assertIn("--foreground-key-tools-callable --agent-json", action["command"])


if __name__ == "__main__":
    unittest.main()
