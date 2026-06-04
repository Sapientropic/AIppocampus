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

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.update import cli as update_cli  # noqa: E402

PROVIDER_ENV_NAMES = [
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
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


class UpdateSyncTests(unittest.TestCase):
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
        self.assertFalse(payload["summary"]["magic_ready"])
        self.assertEqual(surfaces["hooks"]["status"], "missing")
        self.assertEqual(surfaces["llm"]["status"], "missing_provider_env_var")
        self.assertFalse(hooks_json.exists())

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


if __name__ == "__main__":
    unittest.main()
