#!/usr/bin/env python3
"""One-command Codex plugin install, verification, and rollback flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.update.cli import (
    DEFAULT_PLUGIN_OUTPUT,
    _load_plugin_builder,
    find_repo_root,
)
from aippocampus_runtime.update.plugin_cache import refresh_plugin_cache_layers

PLUGIN_NAME = "aippocampus"
MARKETPLACE_NAME = "aippocampus-local"
MARKETPLACE_RELATIVE_MANIFEST = Path(".agents") / "plugins" / "marketplace.json"
MARKETPLACE_MARKER = ".aippocampus-owned-marketplace.json"
REQUIRED_HOST_TOOLS = {"memory_health", "search_memory", "sync_status"}
IGNORED_TREE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".eggs"}
IGNORED_TREE_SUFFIXES = (".pyc", ".pyo")

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
HostProbeRunner = Callable[..., dict[str, Any]]


class AppServerError(RuntimeError):
    """Raised when the Codex app-server JSON protocol cannot complete."""


class CodexAppServerClient:
    """Small newline-delimited JSON client for ``codex app-server``.

    This duplicates only the host-facing probe client needed by the install
    command. The plugin smoke script has cleanup-heavy test behavior; this
    runtime path needs a stable verification probe without mutating plugin state.
    """

    def __init__(self, command: list[str], cwd: Path) -> None:
        self._stdout: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._notifications: list[dict[str, Any]] = []
        self._protocol_noise: list[str] = []
        self._next_id = 1
        self._proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    @property
    def notifications(self) -> list[dict[str, Any]]:
        return list(self._notifications)

    @property
    def protocol_noise(self) -> list[str]:
        return list(self._protocol_noise)

    @property
    def stderr_tail(self) -> str:
        return "".join(self._stderr_lines)[-4000:]

    def _read_stdout(self) -> None:
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._stdout.put(line)
        finally:
            self._stdout.put(None)

    def _read_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr_lines.append(line)
            if len(self._stderr_lines) > 200:
                self._stderr_lines = self._stderr_lines[-200:]

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 60.0,
        raise_on_error: bool = True,
    ) -> dict[str, Any]:
        if self._proc.poll() is not None:
            raise AppServerError(
                f"codex app-server exited before {method}: {self._proc.returncode}"
            )
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {method}")
            try:
                line = self._stdout.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise AppServerError(
                        "codex app-server exited while waiting for "
                        f"{method}: {self._proc.returncode}"
                    ) from None
                continue
            if line is None:
                raise AppServerError(f"codex app-server closed stdout while waiting for {method}")
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                self._protocol_noise.append(line[:240])
                if len(self._protocol_noise) > 20:
                    self._protocol_noise = self._protocol_noise[-20:]
                continue
            if response.get("id") != request_id:
                self._notifications.append(response)
                continue
            if raise_on_error and response.get("error"):
                raise AppServerError(f"{method} failed: {response['error']}")
            return response

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)


def default_marketplace_root(codex_home_path: Path | None = None) -> Path:
    return Path(codex_home_path or codex_home()).expanduser() / "aippocampus-marketplace"


def marketplace_manifest_path(marketplace_root: Path) -> Path:
    return marketplace_root / MARKETPLACE_RELATIVE_MANIFEST


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _redact_local_paths(text: str, paths: list[Path]) -> str:
    redacted = text
    path_texts = {str(item.expanduser().resolve()) for item in paths if item}
    for path in sorted(path_texts, key=len, reverse=True):
        redacted = redacted.replace(path, "<local-path-redacted>")
    return redacted


def _codex_base(codex_command: str | list[str] | None = None) -> list[str]:
    if codex_command is None:
        return ["codex"]
    if isinstance(codex_command, list):
        return list(codex_command)
    return [str(codex_command)]


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _load_json_text(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    data = json.loads(value)
    return data if isinstance(data, dict) else {"data": data}


def _run_json(runner: CommandRunner, command: list[str]) -> dict[str, Any]:
    proc = runner(command)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(command[:4])}; {tail}"
        )
    try:
        return _load_json_text(proc.stdout or "")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command returned non-json output: {' '.join(command[:4])}"
        ) from exc


def _read_manifest(root: Path) -> dict[str, Any]:
    manifest = root / ".codex-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _ignored_tree_name(name: str) -> bool:
    return (
        name in IGNORED_TREE_NAMES
        or name.endswith(".egg-info")
        or name.endswith(IGNORED_TREE_SUFFIXES)
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_fingerprint(root: Path) -> str:
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(_ignored_tree_name(part) for part in rel.parts):
            continue
        rows.append(f"{rel.as_posix()}:{_file_hash(path)}")
    digest = hashlib.sha256("\n".join(rows).encode("utf-8"))
    return digest.hexdigest()


def _resolve_manifest_root(path: Path) -> Path:
    if (path / ".codex-plugin" / "plugin.json").exists():
        return path
    candidate = path / "plugins" / PLUGIN_NAME
    if (candidate / ".codex-plugin" / "plugin.json").exists():
        return candidate
    return path


def _plugin_version(root: Path) -> str:
    return str(_read_manifest(root).get("version") or "")


def _write_owner_marker(marketplace_root: Path, marketplace_name: str) -> None:
    marker = {
        "owner": "aippocampus",
        "marketplace_name": marketplace_name,
        "plugin": PLUGIN_NAME,
        "safe_to_remove": True,
    }
    (marketplace_root / MARKETPLACE_MARKER).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_replace_tree(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target or _path_is_under(source, target):
        raise ValueError("refusing unsafe plugin marketplace refresh path")
    if len(target.parts) <= 2:
        raise ValueError("refusing shallow plugin marketplace refresh path")
    tmp = target.parent / f".{target.name}.tmp-aippocampus-install"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(source, tmp)
    if target.exists():
        shutil.rmtree(target)
    tmp.replace(target)


def write_local_marketplace(
    marketplace_root: Path,
    *,
    package_root: Path,
    marketplace_name: str = MARKETPLACE_NAME,
) -> dict[str, Any]:
    marketplace_root = Path(marketplace_root).expanduser().resolve()
    package_root = Path(package_root).resolve()
    if not (package_root / ".codex-plugin" / "plugin.json").exists():
        raise FileNotFoundError("plugin package root does not contain .codex-plugin/plugin.json")

    plugin_dir = marketplace_root / "plugins" / PLUGIN_NAME
    plugin_dir.parent.mkdir(parents=True, exist_ok=True)
    _safe_replace_tree(package_root, plugin_dir)
    manifest_root = marketplace_manifest_path(marketplace_root).parent
    manifest_root.mkdir(parents=True, exist_ok=True)
    marketplace = {
        "name": marketplace_name,
        "displayName": "AIppocampus local",
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                "category": "Productivity",
            }
        ],
    }
    manifest = marketplace_manifest_path(marketplace_root)
    manifest.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_owner_marker(marketplace_root, marketplace_name)
    return {
        "name": marketplace_name,
        "root": str(marketplace_root),
        "manifest": str(manifest),
        "plugin_dir": str(plugin_dir),
    }


def _plugin_item_id(item: dict[str, Any]) -> str:
    raw_summary = item.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    return str(item.get("pluginId") or item.get("id") or summary.get("id") or "")


def _plugin_item_version(item: dict[str, Any]) -> str:
    raw_summary = item.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    return str(item.get("version") or summary.get("version") or "")


def _plugin_item_enabled(item: dict[str, Any]) -> bool:
    raw_summary = item.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    value = item.get("enabled", summary.get("enabled", True))
    return bool(value)


def _plugin_item_source_path(item: dict[str, Any]) -> Path | None:
    raw_source = item.get("source")
    source: dict[str, Any] = raw_source if isinstance(raw_source, dict) else {}
    path = source.get("path")
    return Path(str(path)).expanduser() if path else None


def _installed_source_current(item: dict[str, Any], package_root: Path) -> bool | None:
    source_path = _plugin_item_source_path(item)
    if source_path is None:
        return None
    source_root = _resolve_manifest_root(source_path)
    if not source_root.exists():
        return False
    try:
        return _tree_fingerprint(source_root) == _tree_fingerprint(package_root)
    except Exception:
        return False


def _find_installed_plugin(payload: dict[str, Any], selector: str) -> dict[str, Any] | None:
    for item in payload.get("installed") or []:
        if not isinstance(item, dict):
            continue
        if _plugin_item_id(item) == selector:
            return item
    return None


def _extract_sync_status_payload(tool_response: dict[str, Any]) -> dict[str, Any]:
    result = tool_response.get("result") or {}
    content = result.get("content") or []
    if not content:
        return {}
    first = content[0] if isinstance(content[0], dict) else {}
    text = str(first.get("text") or "")
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _find_mcp_server(status_response: dict[str, Any], name: str) -> dict[str, Any] | None:
    result = status_response.get("result") or {}
    for server in result.get("data") or []:
        if isinstance(server, dict) and server.get("name") == name:
            return server
    return None


def _mcp_tool_names(server: dict[str, Any] | None) -> list[str]:
    if not server:
        return []
    tools = server.get("tools") or {}
    if isinstance(tools, dict):
        return sorted(str(name) for name in tools)
    return []


def _validate_host_probe(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    tools = set((result.get("mcp_status") or {}).get("tool_names") or [])
    missing = sorted(REQUIRED_HOST_TOOLS - tools)
    if missing:
        failures.append(f"Codex MCP host did not list required tools: {', '.join(missing)}")
    if result.get("mcp_tool_is_error"):
        failures.append("Codex MCP host returned isError=true for sync_status")
    payload = result.get("mcp_tool_payload") or {}
    if payload.get("status") != "available_requires_sync_dir":
        failures.append("sync_status did not report available_requires_sync_dir")
    if payload.get("backend") != "local_folder":
        failures.append("sync_status did not report local_folder backend")
    return failures


def run_codex_host_probe(
    *,
    repo_root: Path,
    codex_command: str | list[str] | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    app_server_cmd = [*_codex_base(codex_command), "app-server", "--listen", "stdio://"]
    client: CodexAppServerClient | None = None
    thread_id: str | None = None
    result: dict[str, Any] = {
        "validation_ok": False,
        "codex_command": app_server_cmd,
        "mcp_refresh": {},
        "mcp_status": {},
        "thread_id": None,
        "mcp_tool_payload": {},
        "mcp_tool_is_error": True,
        "notifications": [],
        "protocol_noise": [],
        "failures": [],
        "stderr_tail": "",
    }
    try:
        client = CodexAppServerClient(app_server_cmd, Path(repo_root).resolve())
        init = client.request(
            "initialize",
            {"clientInfo": {"name": "aippocampus-plugin-install", "version": "0.1.0"}},
            timeout=timeout_seconds,
        )
        result["codex_user_agent"] = (init.get("result") or {}).get("userAgent")
        refresh = client.request(
            "config/mcpServer/reload",
            {},
            timeout=timeout_seconds,
            raise_on_error=False,
        )
        result["mcp_refresh"] = {
            "ok": "result" in refresh and not refresh.get("error"),
            "error": refresh.get("error"),
        }
        status = client.request("mcpServerStatus/list", {"detail": "full"}, timeout=timeout_seconds)
        server = _find_mcp_server(status, PLUGIN_NAME)
        result["mcp_status"] = {
            "found": server is not None,
            "authStatus": (server or {}).get("authStatus"),
            "tool_names": _mcp_tool_names(server),
        }
        thread = client.request(
            "thread/start",
            {
                "cwd": str(Path(repo_root).resolve()),
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
                "ephemeral": True,
                "threadSource": "user",
                "sessionStartSource": "startup",
            },
            timeout=timeout_seconds,
        )
        thread_id = str(((thread.get("result") or {}).get("thread") or {}).get("id") or "")
        result["thread_id"] = thread_id
        tool = client.request(
            "mcpServer/tool/call",
            {
                "server": PLUGIN_NAME,
                "threadId": thread_id,
                "tool": "sync_status",
                "arguments": {},
            },
            timeout=timeout_seconds,
        )
        result["mcp_tool_is_error"] = bool((tool.get("result") or {}).get("isError"))
        result["mcp_tool_payload"] = _extract_sync_status_payload(tool)
        failures = _validate_host_probe(result)
        result["failures"] = failures
        result["validation_ok"] = not failures
        return result
    except Exception as exc:
        result["exception"] = f"{type(exc).__name__}: {exc}"
        result["failures"] = [result["exception"]]
        return result
    finally:
        if client is not None:
            try:
                if thread_id:
                    client.request(
                        "thread/archive",
                        {"threadId": thread_id},
                        timeout=60,
                        raise_on_error=False,
                    )
            finally:
                result["stderr_tail"] = _redact_local_paths(
                    client.stderr_tail,
                    [Path(repo_root), Path.home()],
                )
                result["notifications"] = [item.get("method") for item in client.notifications[:40]]
                result["protocol_noise"] = client.protocol_noise[:20]
                client.close()


def _agent_callable_status(probe: dict[str, Any] | None, verify: bool) -> str:
    if not verify:
        return "not_verified"
    if probe and probe.get("validation_ok"):
        return "host_live_probe_ok"
    return "host_live_probe_failed"


def install_codex_plugin(
    *,
    repo_root: Path | str | None = None,
    codex_home_path: Path | str | None = None,
    plugin_output: Path | str | None = None,
    marketplace_root: Path | str | None = None,
    marketplace_name: str = MARKETPLACE_NAME,
    codex_command: str | list[str] | None = None,
    verify: bool = False,
    runner: CommandRunner | None = None,
    host_probe_runner: HostProbeRunner | None = None,
) -> dict[str, Any]:
    repo = find_repo_root(Path(repo_root).resolve() if repo_root else None)
    codex_home_resolved = (
        Path(codex_home_path).expanduser().resolve() if codex_home_path else codex_home()
    )
    output = Path(plugin_output).resolve() if plugin_output else repo / DEFAULT_PLUGIN_OUTPUT
    marketplace = (
        Path(marketplace_root).expanduser().resolve()
        if marketplace_root
        else default_marketplace_root(codex_home_resolved)
    )
    runner = runner or _default_runner
    host_probe_runner = host_probe_runner or run_codex_host_probe

    builder = _load_plugin_builder(repo)
    if builder is None or not hasattr(builder, "build_package"):
        raise RuntimeError("plugin package builder is not available")

    build_result = builder.build_package(repo, output)
    package_root = Path(str(build_result["output_dir"])).resolve()
    marketplace_result = write_local_marketplace(
        marketplace,
        package_root=package_root,
        marketplace_name=marketplace_name,
    )
    cache_refresh = refresh_plugin_cache_layers(
        package_root=package_root,
        marketplace_dir=Path(marketplace_result["plugin_dir"]),
        installed_dir=None,
    )

    codex = _codex_base(codex_command)
    marketplace_add = _run_json(
        runner,
        [*codex, "plugin", "marketplace", "add", str(marketplace), "--json"],
    )
    list_payload = _run_json(
        runner,
        [*codex, "plugin", "list", "--marketplace", marketplace_name, "--available", "--json"],
    )
    expected_version = _plugin_version(package_root)
    installed = _find_installed_plugin(list_payload, f"{PLUGIN_NAME}@{marketplace_name}")
    source_current = _installed_source_current(installed, package_root) if installed else None
    version_current = installed is not None and _plugin_item_version(installed) == expected_version
    installed_current = (
        installed is not None
        and version_current
        and _plugin_item_enabled(installed)
        and (source_current if source_current is not None else True)
    )
    if installed_current:
        plugin_result = {
            "id": f"{PLUGIN_NAME}@{marketplace_name}",
            "version": expected_version,
            "action": "already_current",
            "installed": True,
            "enabled": True,
            "source": "codex_plugin_list",
        }
    else:
        stale_remove = None
        action = "installed"
        if installed is not None:
            stale_remove = _run_json(
                runner,
                [*codex, "plugin", "remove", f"{PLUGIN_NAME}@{marketplace_name}", "--json"],
            )
            action = "reinstalled"
        add = _run_json(
            runner,
            [*codex, "plugin", "add", f"{PLUGIN_NAME}@{marketplace_name}", "--json"],
        )
        plugin_result = {
            "id": str(add.get("pluginId") or f"{PLUGIN_NAME}@{marketplace_name}"),
            "version": str(add.get("version") or expected_version),
            "action": action,
            "installed": True,
            "enabled": True,
            "raw": add,
            "stale_remove": stale_remove,
        }

    probe = (
        host_probe_runner(repo_root=repo, codex_command=codex_command)
        if verify
        else None
    )
    agent_status = _agent_callable_status(probe, verify)
    return {
        "kind": "aippocampus_plugin_install",
        "ok": agent_status != "host_live_probe_failed",
        "repo_root": str(repo),
        "codex_home": str(codex_home_resolved),
        "plugin_package": build_result,
        "marketplace": marketplace_result,
        "marketplace_add": marketplace_add,
        "plugin": plugin_result,
        "cache_refresh": cache_refresh,
        "host_probe": probe,
        "agent_callable_status": agent_status,
        "hooks_auto_enabled": False,
        "rollback_command": "aippocampus plugin uninstall --codex",
    }


def _owned_marketplace_manifest(marketplace_root: Path) -> bool:
    marker = marketplace_root / MARKETPLACE_MARKER
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            return False
        return data.get("owner") == "aippocampus" and data.get("safe_to_remove") is True
    manifest = marketplace_manifest_path(marketplace_root)
    if not manifest.exists():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return False
    plugins = data.get("plugins")
    return (
        data.get("name") == MARKETPLACE_NAME
        and isinstance(plugins, list)
        and len(plugins) == 1
        and isinstance(plugins[0], dict)
        and plugins[0].get("name") == PLUGIN_NAME
        and (plugins[0].get("source") or {}).get("path") == f"./plugins/{PLUGIN_NAME}"
    )


def _remove_owned_marketplace(marketplace_root: Path, codex_home_path: Path) -> bool:
    marketplace_root = marketplace_root.resolve()
    codex_home_path = codex_home_path.resolve()
    if not marketplace_root.exists():
        return False
    if not _path_is_under(marketplace_root, codex_home_path):
        raise ValueError("refusing to remove marketplace outside Codex home")
    if not _owned_marketplace_manifest(marketplace_root):
        raise ValueError("refusing to remove marketplace without AIppocampus ownership marker")
    shutil.rmtree(marketplace_root)
    return True


def uninstall_codex_plugin(
    *,
    codex_home_path: Path | str | None = None,
    marketplace_root: Path | str | None = None,
    marketplace_name: str = MARKETPLACE_NAME,
    codex_command: str | list[str] | None = None,
    keep_marketplace: bool = False,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    codex_home_resolved = (
        Path(codex_home_path).expanduser().resolve() if codex_home_path else codex_home()
    )
    marketplace = (
        Path(marketplace_root).expanduser().resolve()
        if marketplace_root
        else default_marketplace_root(codex_home_resolved)
    )
    runner = runner or _default_runner
    codex = _codex_base(codex_command)
    plugin_remove = _run_json(
        runner,
        [*codex, "plugin", "remove", f"{PLUGIN_NAME}@{marketplace_name}", "--json"],
    )
    marketplace_remove = _run_json(
        runner,
        [*codex, "plugin", "marketplace", "remove", marketplace_name, "--json"],
    )
    removed_marketplace_root = False
    if not keep_marketplace:
        removed_marketplace_root = _remove_owned_marketplace(marketplace, codex_home_resolved)
    return {
        "kind": "aippocampus_plugin_uninstall",
        "ok": True,
        "codex_home": str(codex_home_resolved),
        "plugin_remove": plugin_remove,
        "marketplace_remove": marketplace_remove,
        "removed_marketplace_root": removed_marketplace_root,
        "marketplace_root": str(marketplace),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus plugin",
        description="Install, verify, or remove the AIppocampus Codex plugin.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install the Codex plugin")
    install.add_argument("--codex", action="store_true", help="Use the Codex plugin manager")
    install.add_argument("--verify", "--verify-host", action="store_true", dest="verify")
    install.add_argument("--repo-root")
    install.add_argument("--codex-home")
    install.add_argument("--plugin-output")
    install.add_argument("--marketplace-root")
    install.add_argument("--marketplace-name", default=MARKETPLACE_NAME)
    install.add_argument("--codex-command")
    install.add_argument("--json", action="store_true", dest="json_output")

    uninstall = subparsers.add_parser(
        "uninstall",
        help="Remove the Codex plugin and owned marketplace",
    )
    uninstall.add_argument("--codex", action="store_true", help="Use the Codex plugin manager")
    uninstall.add_argument("--codex-home")
    uninstall.add_argument("--marketplace-root")
    uninstall.add_argument("--marketplace-name", default=MARKETPLACE_NAME)
    uninstall.add_argument("--codex-command")
    uninstall.add_argument("--keep-marketplace", action="store_true")
    uninstall.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _emit_result(result: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
        return
    if result["kind"] == "aippocampus_plugin_install":
        print(f"plugin: {result['plugin']['action']} {result['plugin']['id']}")
        print(f"marketplace: {result['marketplace']['name']}")
        print(f"agent callable: {result['agent_callable_status']}")
        print(f"rollback: {result['rollback_command']}")
    else:
        print("plugin: removed")
        print(f"marketplace removed: {result['removed_marketplace_root']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.codex:
        parser.error("this command currently requires --codex")
    try:
        if args.command == "install":
            result = install_codex_plugin(
                repo_root=args.repo_root,
                codex_home_path=args.codex_home,
                plugin_output=args.plugin_output,
                marketplace_root=args.marketplace_root,
                marketplace_name=args.marketplace_name,
                codex_command=args.codex_command,
                verify=args.verify,
            )
        else:
            result = uninstall_codex_plugin(
                codex_home_path=args.codex_home,
                marketplace_root=args.marketplace_root,
                marketplace_name=args.marketplace_name,
                codex_command=args.codex_command,
                keep_marketplace=args.keep_marketplace,
            )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        error = {
            "ok": False,
            "error": {
                "code": "plugin_command_failed",
                "message": error_message,
            },
        }
        if getattr(args, "json_output", False):
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(error_message)
        return 1
    _emit_result(result, json_output=args.json_output)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
