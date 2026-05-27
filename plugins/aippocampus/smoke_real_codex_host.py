#!/usr/bin/env python3
"""Real Codex app-server plugin manager and MCP host smoke for AIppocampus.

This smoke intentionally uses the Codex app-server JSON protocol instead of
calling the plugin's MCP process directly. It is heavier than
``smoke_plugin_install.py`` because it mutates the user's real Codex plugin
state briefly. All mutations use a run-id-scoped local marketplace and are
removed in ``finally``.
"""

from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import build_plugin_package
from smoke_plugin_install import default_build_output, safe_build_output


PLUGIN_NAME = "aippocampus"
REQUIRED_MCP_TOOLS = {
    "search_memory",
    "sync_status",
    "memory_health",
}


class AppServerError(RuntimeError):
    """Raised when the real Codex app-server returns an RPC error."""


class CodexAppServerClient:
    """Small newline-delimited JSON client for ``codex app-server``.

    The current Codex app-server stdio transport speaks one JSON object per
    line, not LSP-style Content-Length frames. Keeping this client local to the
    smoke makes that host contract explicit and easy to update if Codex changes
    its transport.
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
            raise AppServerError(f"codex app-server exited before {method}: {self._proc.returncode}")
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
                        f"codex app-server exited while waiting for {method}: {self._proc.returncode}"
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


def resolve_codex_command(codex_command: str | None = None) -> list[str]:
    if codex_command:
        path = Path(codex_command)
        if path.suffix.casefold() == ".ps1":
            return ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
        return [str(path)]
    # On Windows, npm also creates an extensionless shell script named ``codex``.
    # Python may try that first and fail with WinError 5, so prefer codex.cmd.
    for candidate in ("codex.cmd", "codex.exe", "codex"):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    raise FileNotFoundError("could not find codex on PATH")


def path_is_within(root: Path, target: Path) -> bool:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    return resolved_target == resolved_root or resolved_root in resolved_target.parents


def safe_remove_tree(root: Path, target: Path) -> bool:
    if not target.exists():
        return False
    if not path_is_within(root, target):
        raise ValueError(f"refusing to remove outside expected root: {target}")
    shutil.rmtree(target)
    return True


def prepare_local_marketplace(repo_root: Path, build_output: Path, run_id: str) -> tuple[str, Path, Path]:
    marketplace_name = f"aippocampus-real-smoke-{run_id}"
    marketplace_root = repo_root / ".tmp" / f"aippocampus-real-codex-marketplace-{run_id}"
    if marketplace_root.exists():
        safe_remove_tree(repo_root, marketplace_root)
    plugin_root = marketplace_root / ".agents" / "plugins"
    plugin_dir = marketplace_root / "plugins" / PLUGIN_NAME
    plugin_root.mkdir(parents=True)
    plugin_dir.parent.mkdir(parents=True)
    shutil.copytree(build_output, plugin_dir)
    marketplace = {
        "name": marketplace_name,
        "displayName": "AIppocampus real Codex smoke",
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{PLUGIN_NAME}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_USE",
                },
            }
        ],
    }
    (plugin_root / "marketplace.json").write_text(
        json.dumps(marketplace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return marketplace_name, marketplace_root, plugin_dir


def summarize_plugin(plugin: dict[str, Any]) -> dict[str, Any]:
    summary = plugin.get("summary") or {}
    return {
        "id": summary.get("id"),
        "name": summary.get("name"),
        "installed": summary.get("installed"),
        "enabled": summary.get("enabled"),
        "authPolicy": summary.get("authPolicy"),
        "installPolicy": summary.get("installPolicy"),
        "marketplaceName": plugin.get("marketplaceName"),
        "marketplacePath": plugin.get("marketplacePath"),
        "mcpServers": plugin.get("mcpServers") or [],
        "skills": [item.get("name") for item in plugin.get("skills") or []],
        "hooks": plugin.get("hooks") or [],
        "apps": plugin.get("apps") or [],
    }


def extract_sync_status_payload(tool_response: dict[str, Any]) -> dict[str, Any]:
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


def find_mcp_server(status_response: dict[str, Any], name: str) -> dict[str, Any] | None:
    result = status_response.get("result") or {}
    for server in result.get("data") or []:
        if isinstance(server, dict) and server.get("name") == name:
            return server
    return None


def mcp_tool_names(server: dict[str, Any] | None) -> list[str]:
    if not server:
        return []
    tools = server.get("tools") or {}
    if isinstance(tools, dict):
        return sorted(str(name) for name in tools)
    return []


def validate_smoke(result: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    before = result.get("plugin_read_before") or {}
    after = result.get("plugin_read_after_install") or {}
    status = result.get("mcp_status") or {}
    tool_payload = result.get("mcp_tool_payload") or {}
    cleanup = result.get("cleanup") or {}

    if before.get("installed"):
        failures.append("plugin unexpectedly installed before smoke install")
    if after.get("installed") is not True or after.get("enabled") is not True:
        failures.append("plugin was not installed and enabled through Codex plugin manager")
    if PLUGIN_NAME not in after.get("mcpServers", []):
        failures.append("installed plugin did not expose the aippocampus MCP server")
    if not any(str(name).endswith(":aippocampus") or str(name) == "aippocampus" for name in after.get("skills", [])):
        failures.append("installed plugin did not expose the aippocampus skill")

    tool_names = set(status.get("tool_names") or [])
    missing_tools = sorted(REQUIRED_MCP_TOOLS - tool_names)
    if missing_tools:
        failures.append(f"Codex MCP host did not list required tools: {', '.join(missing_tools)}")

    if result.get("mcp_tool_is_error"):
        failures.append("Codex MCP host returned isError=true for sync_status")
    if tool_payload.get("status") != "available_requires_sync_dir":
        failures.append("sync_status payload did not report available_requires_sync_dir")
    if tool_payload.get("backend") != "local_folder":
        failures.append("sync_status payload did not report local_folder backend")
    expected_commands = {"status", "push", "pull", "repair"}
    if not expected_commands.issubset(set(tool_payload.get("commands") or [])):
        failures.append("sync_status payload did not expose status/push/pull/repair commands")

    if cleanup.get("plugin_uninstall_ok") is not True:
        failures.append("plugin uninstall cleanup did not succeed")
    if cleanup.get("marketplace_remove_ok") is not True:
        failures.append("marketplace remove cleanup did not succeed")
    if cleanup.get("marketplace_root_exists"):
        failures.append("temporary local marketplace directory still exists")
    return not failures, failures


def run_real_codex_host_smoke(
    repo_root: str | Path,
    *,
    codex_command: str | None = None,
    build_output: str | Path | None = None,
    keep_artifacts: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    run_id = run_id or uuid.uuid4().hex[:10]
    output = safe_build_output(repo_root, build_output or default_build_output(repo_root))
    codex = resolve_codex_command(codex_command)
    app_server_cmd = [*codex, "app-server", "--listen", "stdio://"]

    marketplace_name = ""
    marketplace_root: Path | None = None
    installed_plugin_id: str | None = None
    marketplace_added = False
    codex_home: Path | None = None
    client: CodexAppServerClient | None = None
    thread_id: str | None = None
    cleanup: dict[str, Any] = {
        "thread_archive_ok": None,
        "plugin_uninstall_ok": None,
        "marketplace_remove_ok": None,
        "removed_build_output": False,
        "removed_marketplace_root": False,
        "removed_codex_cache_root": False,
        "marketplace_root_exists": None,
    }
    result: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "codex_command": app_server_cmd,
        "build_output": str(output),
        "marketplace_name": None,
        "marketplace_root": None,
        "codex_user_agent": None,
        "codex_home": None,
        "plugin_read_before": {},
        "plugin_install": {},
        "plugin_read_after_install": {},
        "mcp_refresh": {},
        "mcp_status": {},
        "thread_id": None,
        "mcp_tool_payload": {},
        "mcp_tool_is_error": True,
        "notifications": [],
        "protocol_noise": [],
        "cleanup": cleanup,
        "failures": [],
        "stderr_tail": "",
    }

    try:
        build_plugin_package.build_package(repo_root, output)
        marketplace_name, marketplace_root, plugin_dir = prepare_local_marketplace(repo_root, output, run_id)
        result["marketplace_name"] = marketplace_name
        result["marketplace_root"] = str(marketplace_root)
        result["marketplace_plugin_dir"] = str(plugin_dir)

        client = CodexAppServerClient(app_server_cmd, repo_root)
        init = client.request(
            "initialize",
            {"clientInfo": {"name": "aippocampus-real-codex-smoke", "version": "0.1.0"}},
            timeout=90,
        )
        init_result = init.get("result") or {}
        result["codex_user_agent"] = init_result.get("userAgent")
        if init_result.get("codexHome"):
            codex_home = Path(str(init_result["codexHome"]))
            result["codex_home"] = str(codex_home)

        add = client.request("marketplace/add", {"source": str(marketplace_root)}, timeout=120)
        add_result = add.get("result") or {}
        marketplace_added = True
        result["marketplace_add"] = add_result
        marketplace_path = str(Path(str(add_result.get("installedRoot") or marketplace_root)) / ".agents" / "plugins" / "marketplace.json")
        plugin_params = {"pluginName": PLUGIN_NAME, "marketplacePath": marketplace_path}

        before = client.request("plugin/read", plugin_params, timeout=60)
        result["plugin_read_before"] = summarize_plugin((before.get("result") or {}).get("plugin") or {})

        install = client.request("plugin/install", plugin_params, timeout=120)
        result["plugin_install"] = install.get("result") or {}

        after = client.request("plugin/read", plugin_params, timeout=60)
        after_summary = summarize_plugin((after.get("result") or {}).get("plugin") or {})
        result["plugin_read_after_install"] = after_summary
        installed_plugin_id = str(after_summary.get("id") or "")

        refresh = client.request("config/mcpServer/reload", {}, timeout=90, raise_on_error=False)
        result["mcp_refresh"] = {
            "ok": "result" in refresh and not refresh.get("error"),
            "error": refresh.get("error"),
        }

        status_response = client.request("mcpServerStatus/list", {"detail": "full"}, timeout=120)
        server = find_mcp_server(status_response, PLUGIN_NAME)
        result["mcp_status"] = {
            "found": server is not None,
            "authStatus": (server or {}).get("authStatus"),
            "tool_names": mcp_tool_names(server),
            "resource_count": len((server or {}).get("resources") or []),
            "resource_template_count": len((server or {}).get("resourceTemplates") or []),
        }

        thread = client.request(
            "thread/start",
            {
                "cwd": str(repo_root),
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
                "ephemeral": True,
                "threadSource": "user",
                "sessionStartSource": "startup",
            },
            timeout=120,
        )
        thread_result = thread.get("result") or {}
        thread_obj = thread_result.get("thread") or {}
        thread_id = str(thread_obj.get("id") or "")
        result["thread_id"] = thread_id

        tool = client.request(
            "mcpServer/tool/call",
            {
                "server": PLUGIN_NAME,
                "threadId": thread_id,
                "tool": "sync_status",
                "arguments": {},
            },
            timeout=120,
        )
        tool_result = tool.get("result") or {}
        result["mcp_tool_is_error"] = bool(tool_result.get("isError"))
        result["mcp_tool_payload"] = extract_sync_status_payload(tool)

        result["notifications"] = [item.get("method") for item in client.notifications[:40]]
        result["protocol_noise"] = client.protocol_noise[:20]
        return result
    except Exception as exc:
        result["ok"] = False
        result["exception"] = f"{type(exc).__name__}: {exc}"
        result["failures"] = [*result.get("failures", []), result["exception"]]
        return result
    finally:
        if client is not None:
            try:
                if thread_id:
                    try:
                        archive = client.request(
                            "thread/archive",
                            {"threadId": thread_id},
                            timeout=60,
                            raise_on_error=False,
                        )
                        archive_error = archive.get("error")
                        archive_message = str((archive_error or {}).get("message") or "")
                        cleanup["thread_archive_ok"] = "result" in archive or "no rollout found" in archive_message
                        cleanup["thread_archive_error"] = archive_error
                    except Exception as exc:
                        cleanup["thread_archive_ok"] = False
                        cleanup["thread_archive_error"] = f"{type(exc).__name__}: {exc}"
                if installed_plugin_id:
                    try:
                        uninstall = client.request(
                            "plugin/uninstall",
                            {"pluginId": installed_plugin_id},
                            timeout=120,
                            raise_on_error=False,
                        )
                        cleanup["plugin_uninstall_ok"] = "result" in uninstall and not uninstall.get("error")
                        cleanup["plugin_uninstall_error"] = uninstall.get("error")
                    except Exception as exc:
                        cleanup["plugin_uninstall_ok"] = False
                        cleanup["plugin_uninstall_error"] = f"{type(exc).__name__}: {exc}"
                if marketplace_added and marketplace_name:
                    try:
                        remove = client.request(
                            "marketplace/remove",
                            {"marketplaceName": marketplace_name},
                            timeout=120,
                            raise_on_error=False,
                        )
                        cleanup["marketplace_remove_ok"] = "result" in remove and not remove.get("error")
                        cleanup["marketplace_remove_error"] = remove.get("error")
                    except Exception as exc:
                        cleanup["marketplace_remove_ok"] = False
                        cleanup["marketplace_remove_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                result["stderr_tail"] = client.stderr_tail
                client.close()
        if marketplace_root is not None:
            if keep_artifacts:
                cleanup["marketplace_root_exists"] = marketplace_root.exists()
            else:
                cleanup["removed_marketplace_root"] = safe_remove_tree(repo_root, marketplace_root)
                cleanup["marketplace_root_exists"] = marketplace_root.exists()
        if not keep_artifacts and output.exists():
            cleanup["removed_build_output"] = safe_remove_tree(repo_root / "dist", output)
        if not keep_artifacts and codex_home is not None and marketplace_name:
            cache_root = codex_home / "plugins" / "cache"
            cache_target = cache_root / marketplace_name
            if cache_target.exists():
                cleanup["removed_codex_cache_root"] = safe_remove_tree(cache_root, cache_target)
        if client is not None:
            result["notifications"] = [item.get("method") for item in client.notifications[:40]]
            result["protocol_noise"] = client.protocol_noise[:20]
        validation_ok, validation_failures = validate_smoke(result)
        exception = result.get("exception")
        result["failures"] = ([exception] if exception else []) + validation_failures
        result["ok"] = validation_ok and exception is None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--codex-command")
    parser.add_argument("--build-output")
    parser.add_argument("--run-id")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_real_codex_host_smoke(
        args.repo_root,
        codex_command=args.codex_command,
        build_output=args.build_output,
        keep_artifacts=args.keep_artifacts,
        run_id=args.run_id,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"real Codex host smoke: {'ok' if result.get('ok') else 'failed'}")
        print(f"Codex: {result.get('codex_user_agent')}")
        print(f"MCP tools: {', '.join((result.get('mcp_status') or {}).get('tool_names') or [])}")
        for failure in result.get("failures") or []:
            print(f"- {failure}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
