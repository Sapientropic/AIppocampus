from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.update import cli as update_cli

PROVIDER_ENV_NAMES = [
    "AIPPOCAMPUS_DEEPSEEK_API_KEY",
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
def update_workspace(extra_env: dict[str, str] | None = None) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp, provider_env(extra_env):
        yield Path(tmp)

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

@dataclass(frozen=True)
class PluginUpdateScenario:
    root: Path
    repo: Path
    codex_home: Path
    plugin_output: Path

    @property
    def source_plugin(self) -> Path:
        return self.repo / "plugins" / "aippocampus"

    @property
    def local_marketplace_root(self) -> Path:
        return self.root / "local-marketplace"

    @property
    def local_marketplace_plugin(self) -> Path:
        return self.local_marketplace_root / "plugins" / "aippocampus"

    @property
    def installed_cache_root(self) -> Path:
        return (
            self.codex_home
            / "plugins"
            / "cache"
            / "aippocampus-local"
            / "aippocampus"
        )

    def installed_cache(self, version: str) -> Path:
        return self.installed_cache_root / version

    def write_current_source_plugin(self, *, version: str = "0.2.0") -> Path:
        self.source_plugin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            REPO_ROOT / "plugins" / "aippocampus" / "build_plugin_package.py",
            self.source_plugin,
        )
        write_plugin_package(self.source_plugin, version=version, include_skill=False)
        return self.source_plugin

    def write_installed_cache(
        self,
        version: str,
        *,
        mcp_command: str = "python3",
        mcp_args: list[str] | None = None,
    ) -> Path:
        cache = self.installed_cache(version)
        write_plugin_package(
            cache,
            version=version,
            mcp_command=mcp_command,
            mcp_args=mcp_args,
        )
        return cache

    def write_local_marketplace_plugin(self, version: str = "0.1.0") -> Path:
        write_plugin_package(self.local_marketplace_plugin, version=version)
        return self.local_marketplace_plugin

    def configure_local_marketplace(self, source: str | Path | None = None) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        source_text = (
            source.as_posix()
            if isinstance(source, Path)
            else str(source or self.local_marketplace_root.as_posix())
        )
        (self.codex_home / "config.toml").write_text(
            "[marketplaces.aippocampus-local]\n"
            f"source = '{source_text}'\n",
            encoding="utf-8",
        )

@contextmanager
def plugin_update_scenario() -> Iterator[PluginUpdateScenario]:
    with update_workspace() as root:
        scenario = PluginUpdateScenario(
            root=root,
            repo=root / "repo",
            codex_home=root / "codex-home",
            plugin_output=root / "repo" / "dist" / "aippocampus-plugin",
        )
        write_minimal_repo(scenario.repo)
        yield scenario

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
