from __future__ import annotations

import json
import os
import shutil
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


def run_update(*args: str) -> tuple[int, dict]:
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = update_cli.main([*args, "--json"])
    payload = json.loads(stdout.getvalue())
    return code, payload


def write_minimal_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    skill = repo / "skills" / "aippocampus"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# AIppocampus fixture\n", encoding="utf-8")
    (skill / "scripts" / "runtime.py").write_text("print('ok')\n", encoding="utf-8")


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
        self.assertEqual(plugin["source_plugin_version"], "0.2.0")
        self.assertEqual(plugin["local_marketplace"]["version"], "0.1.0")
        self.assertEqual(plugin["local_marketplace"]["status"], "stale_version")
        self.assertEqual(plugin["installed_cache"]["version"], "0.1.0")
        self.assertEqual(plugin["installed_cache"]["status"], "stale_version")
        self.assertTrue(plugin["cache_boundary"]["package_artifact_is_not_installed_cache"])
        self.assertTrue(plugin["plugin_cache_recommended_actions"])

    def test_status_uses_successful_host_probe_report_for_agent_callable_ready(self) -> None:
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
        self.assertTrue(payload["summary"]["agent_callable_ready"])
        self.assertEqual(payload["summary"]["agent_callable_status"], "host_live_probe_ok")
        self.assertTrue(agent["ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok")
        self.assertEqual(agent["foreground_tools_visible"], True)
        self.assertEqual(agent["foreground_tools_visibility_source"], "host_probe_report")
        self.assertEqual(agent["host_live_probe"]["status"], "ok")
        self.assertEqual(agent["host_live_probe"]["source"], "codex_app_server_smoke")
        self.assertEqual(agent["next_command"], "aippocampus update status --json")
        by_id = {item["id"]: item for item in payload["summary"]["capability_ladder"]}
        self.assertTrue(by_id["active_recall_ready"]["ready"])
        self.assertEqual(by_id["active_recall_ready"]["status"], "ready")

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
        self.assertTrue(payload["summary"]["agent_callable_ready"])
        self.assertEqual(agent["status"], "host_live_probe_ok")
        self.assertEqual(agent["host_live_probe"]["status"], "ok")
        self.assertEqual(agent["host_live_probe"]["source"], "codex_app_server_smoke")

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
        self.assertNotIn("Still needs action: plugin, llm", output)

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


if __name__ == "__main__":
    unittest.main()
