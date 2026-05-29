#!/usr/bin/env python3
"""Package-level install/uninstall smoke for the AIppocampus plugin."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import build_plugin_package

PLUGIN_NAME = "aippocampus"

ALTERNATE_CLIENT_SURFACE = {
    "kind": "standalone_mcp_stdio_jsonrpc_client",
    "config_source": "installed_plugin_mcp_json",
    "headless_codex_app_server": False,
    "interactive_desktop_ui": False,
    "operations": [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call:sync_status",
    ],
}


def default_build_output(repo_root: Path) -> Path:
    return repo_root / "dist" / f"aippocampus-plugin-smoke-{uuid.uuid4().hex[:10]}"


def safe_build_output(repo_root: Path, build_output: str | Path | None) -> Path:
    output = Path(build_output) if build_output else default_build_output(repo_root)
    if not output.is_absolute():
        output = repo_root / output
    resolved = output.resolve()
    dist_root = (repo_root / "dist").resolve()
    forbidden = {
        repo_root.resolve(),
        Path(__file__).resolve().parent,
        (repo_root / "skills" / "aippocampus").resolve(),
    }
    if resolved in forbidden or resolved == dist_root or dist_root not in resolved.parents:
        raise ValueError(f"unsafe plugin smoke build output directory: {resolved}")
    return resolved


def safe_install_target(install_root: str | Path, plugin_name: str = PLUGIN_NAME) -> Path:
    if Path(plugin_name).name != plugin_name:
        raise ValueError(f"invalid plugin name: {plugin_name}")
    root = Path(install_root).resolve()
    target = (root / plugin_name).resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"unsafe plugin install target: {target}")
    if target.exists():
        raise ValueError(f"refusing to overwrite existing plugin install: {target}")
    return target


def mcp_command_from_config(plugin_dir: Path) -> list[str]:
    config = json.loads((plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    server = (config.get("mcpServers") or {}).get(PLUGIN_NAME) or {}
    command = str(server.get("command") or "")
    args = [str(arg) for arg in server.get("args") or []]
    if not command or not args:
        raise ValueError("plugin MCP config must declare command and args")
    executable = sys.executable if command in {"python", "python3"} else command
    return [executable, *args]


def run_mcp_jsonrpc_smoke(plugin_dir: Path) -> dict[str, Any]:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "sync_status", "arguments": {}},
        },
    ]
    stdin = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"
    proc = subprocess.run(
        mcp_command_from_config(plugin_dir),
        cwd=plugin_dir,
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=10,
        check=False,
    )
    responses = (
        [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode == 0
        else []
    )
    tool_names = []
    tool_payload: dict[str, Any] = {}
    tool_is_error = True
    if len(responses) >= 3:
        tool_names = [
            str(item.get("name") or "") for item in responses[1].get("result", {}).get("tools", [])
        ]
        tool_result = responses[2].get("result", {})
        tool_is_error = bool(tool_result.get("isError"))
        content = tool_result.get("content") or []
        if content:
            tool_payload = json.loads(str(content[0].get("text") or "{}"))
    ok = (
        proc.returncode == 0
        and [item.get("id") for item in responses] == [1, 2, 3]
        and "sync_status" in tool_names
        and not tool_is_error
        and tool_payload.get("status") == "available_requires_sync_dir"
    )
    return {
        "ok": ok,
        "alternate_client_surface": ALTERNATE_CLIENT_SURFACE,
        "response_ids": [item.get("id") for item in responses],
        "request_methods": [str(item.get("method") or "") for item in requests],
        "tools": tool_names,
        "tool_payload": tool_payload,
        "tool_is_error": tool_is_error,
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-1000:],
    }


def smoke_plugin_install(
    repo_root: str | Path,
    install_root: str | Path,
    *,
    build_output: str | Path | None = None,
    keep_build: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    output = safe_build_output(repo_root, build_output)
    install_dir = safe_install_target(install_root)

    build_result: dict[str, Any] | None = None
    installed = False
    uninstalled = False
    mcp_tools: list[str] = []
    mcp_smoke_ok = False
    mcp_jsonrpc: dict[str, Any] = {
        "ok": False,
        "alternate_client_surface": ALTERNATE_CLIENT_SURFACE,
        "response_ids": [],
        "tools": [],
        "tool_payload": {},
        "tool_is_error": True,
    }
    result: dict[str, Any] = {
        "ok": False,
        "build_output": str(output),
        "install_dir": str(install_dir),
        "installed": False,
        "mcp_smoke_ok": False,
        "mcp_tools": [],
        "mcp_jsonrpc_smoke_ok": False,
        "mcp_jsonrpc_request_methods": [],
        "mcp_jsonrpc_response_ids": [],
        "mcp_jsonrpc_tools": [],
        "mcp_jsonrpc_tool_payload": {},
        "mcp_jsonrpc_tool_is_error": True,
        "alternate_client_surface": ALTERNATE_CLIENT_SURFACE,
        "hooks_auto_enabled": False,
        "uninstalled": False,
    }
    try:
        build_result = build_plugin_package.build_package(repo_root, output)
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, install_dir)
        installed = True

        manifest = json.loads(
            (install_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        hooks_auto_enabled = "hooks" in manifest or bool(
            (build_result or {}).get("hooks_auto_enabled")
        )

        proc = subprocess.run(
            [*mcp_command_from_config(install_dir), "--list-tools"],
            cwd=install_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            payload = json.loads(proc.stdout)
            mcp_tools = [str(item.get("name") or "") for item in payload.get("tools") or []]
            mcp_smoke_ok = "search_memory" in mcp_tools
        mcp_jsonrpc = run_mcp_jsonrpc_smoke(install_dir)
        mcp_smoke_ok = mcp_smoke_ok and bool(mcp_jsonrpc.get("ok"))

        result.update(
            {
                "ok": installed and mcp_smoke_ok and not hooks_auto_enabled,
                "build_output": str(output),
                "install_dir": str(install_dir),
                "installed": installed,
                "mcp_smoke_ok": mcp_smoke_ok,
                "mcp_tools": mcp_tools,
                "mcp_jsonrpc_smoke_ok": bool(mcp_jsonrpc.get("ok")),
                "mcp_jsonrpc_request_methods": mcp_jsonrpc.get("request_methods", []),
                "mcp_jsonrpc_response_ids": mcp_jsonrpc.get("response_ids", []),
                "mcp_jsonrpc_tools": mcp_jsonrpc.get("tools", []),
                "mcp_jsonrpc_tool_payload": mcp_jsonrpc.get("tool_payload", {}),
                "mcp_jsonrpc_tool_is_error": bool(mcp_jsonrpc.get("tool_is_error", True)),
                "alternate_client_surface": mcp_jsonrpc.get(
                    "alternate_client_surface", ALTERNATE_CLIENT_SURFACE
                ),
                "hooks_auto_enabled": hooks_auto_enabled,
                "uninstalled": False,
            }
        )
    finally:
        if install_dir.exists():
            shutil.rmtree(install_dir)
            uninstalled = True
        if not keep_build and build_result is not None:
            shutil.rmtree(output, ignore_errors=True)
        if build_result is not None:
            build_result["uninstalled"] = uninstalled
        result["uninstalled"] = uninstalled
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--install-root")
    parser.add_argument("--build-output")
    parser.add_argument("--keep-build", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        install_root = (
            Path(args.install_root).resolve() if args.install_root else Path(tmp) / "plugins"
        )
        result = smoke_plugin_install(
            args.repo_root,
            install_root,
            build_output=args.build_output,
            keep_build=args.keep_build,
        )
        result["uninstalled"] = not Path(result["install_dir"]).exists()
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"plugin install smoke ok: {result['ok']}")
            print(f"mcp tools: {', '.join(result['mcp_tools'])}")
    return 0 if result.get("ok") and result.get("uninstalled") else 1


if __name__ == "__main__":
    raise SystemExit(main())
