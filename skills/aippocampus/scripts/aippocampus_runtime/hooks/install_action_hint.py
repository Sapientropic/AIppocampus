#!/usr/bin/env python3
"""Install or inspect the Codex PreToolUse action-hint hook."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.hooks.host_boundary import add_host_integration
from aippocampus_runtime.hooks.install_prompt import (
    load_hooks,
    quote_powershell_double,
    save_hooks,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ACTION_HINT_MODULE = "aippocampus_runtime.hooks.action_hint"
DEFAULT_ACTION_HINT_TIMEOUT_SECONDS = 3
ACTION_HINT_EVENT = "PreToolUse"
SUPPORTED_HOST = "codex"


def hooks_json_path(codex_home_path: Path | None = None) -> Path:
    return (codex_home_path or codex_home()) / "hooks.json"


def command_for(
    *,
    module: str = DEFAULT_ACTION_HINT_MODULE,
    cache_jsonl: Path | None = None,
) -> str:
    if os.name == "nt":
        command = (
            f"$env:PYTHONPATH={quote_powershell_double(SCRIPT_DIR)}; "
            f"& {quote_powershell_double(Path(sys.executable).resolve())} -m {module}"
        )
        if cache_jsonl is not None:
            command += f" --cache-jsonl {quote_powershell_double(cache_jsonl)}"
    else:
        command = (
            f"PYTHONPATH={shlex.quote(str(SCRIPT_DIR))} "
            f"{shlex.quote(str(Path(sys.executable).resolve()))} -m {module}"
        )
        if cache_jsonl is not None:
            command += f" --cache-jsonl {shlex.quote(str(cache_jsonl))}"
    return command


def action_hint_hook(
    *,
    module: str = DEFAULT_ACTION_HINT_MODULE,
    cache_jsonl: Path | None = None,
    timeout: int = DEFAULT_ACTION_HINT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return {
        "type": "command",
        "command": command_for(module=module, cache_jsonl=cache_jsonl),
        "timeout": int(timeout),
    }


def is_action_hint_handler(
    handler: Mapping[str, Any],
    *,
    module: str = DEFAULT_ACTION_HINT_MODULE,
) -> bool:
    command = str(handler.get("command") or "")
    return module in command or "aippocampus_runtime.hooks.action_hint" in command


def event_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault(ACTION_HINT_EVENT, [])
    if not isinstance(groups, list):
        groups = []
        hooks[ACTION_HINT_EVENT] = groups
    return groups


def _unsupported(path: Path, *, host: str) -> dict[str, Any]:
    return add_host_integration(
        {
            "installed": False,
            "changed": False,
            "path": str(path),
            "surface_event": ACTION_HINT_EVENT,
            "event_supported": False,
            "support_status": f"unsupported_host:{host}",
        }
    )


def install(
    path: Path,
    *,
    host: str = SUPPORTED_HOST,
    module: str = DEFAULT_ACTION_HINT_MODULE,
    cache_jsonl: Path | None = None,
    timeout: int = DEFAULT_ACTION_HINT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if host != SUPPORTED_HOST:
        return _unsupported(path, host=host)
    data = load_hooks(path)
    groups = event_groups(data)
    target = action_hint_hook(module=module, cache_jsonl=cache_jsonl, timeout=timeout)
    changed = False
    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(handlers, list):
            continue
        existing = [
            handler
            for handler in handlers
            if isinstance(handler, dict) and is_action_hint_handler(handler, module=module)
        ]
        if existing:
            if len(existing) == 1 and existing[0] == target:
                return add_host_integration(
                    {
                        "changed": False,
                        "installed": True,
                        "path": str(path),
                        "surface_event": ACTION_HINT_EVENT,
                        "event_supported": True,
                        "support_status": "supported_by_codex_hooks_json",
                        "command": target["command"],
                    }
                )
            group["hooks"] = [
                handler
                for handler in handlers
                if not (
                    isinstance(handler, dict)
                    and is_action_hint_handler(handler, module=module)
                )
            ]
            changed = True
    if not groups:
        groups.append({"hooks": []})
        changed = True
    group = groups[0]
    if not isinstance(group, dict):
        groups[0] = {"hooks": []}
        group = groups[0]
        changed = True
    handlers = group.setdefault("hooks", [])
    if not isinstance(handlers, list):
        group["hooks"] = []
        handlers = group["hooks"]
        changed = True
    handlers.append(target)
    changed = True
    save_hooks(path, data)
    return add_host_integration(
        {
            "changed": changed,
            "installed": True,
            "path": str(path),
            "surface_event": ACTION_HINT_EVENT,
            "event_supported": True,
            "support_status": "supported_by_codex_hooks_json",
            "command": target["command"],
        }
    )


def uninstall(
    path: Path,
    *,
    module: str = DEFAULT_ACTION_HINT_MODULE,
) -> dict[str, Any]:
    data = load_hooks(path)
    hooks = data.setdefault("hooks", {})
    groups = hooks.get(ACTION_HINT_EVENT)
    if not isinstance(groups, list):
        return add_host_integration(
            {
                "changed": False,
                "installed": False,
                "path": str(path),
                "surface_event": ACTION_HINT_EVENT,
                "event_supported": True,
                "support_status": "supported_by_codex_hooks_json",
            }
        )
    changed = False
    kept_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            kept_groups.append(group)
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            kept_groups.append(group)
            continue
        kept = [
            handler
            for handler in handlers
            if not (
                isinstance(handler, dict)
                and is_action_hint_handler(handler, module=module)
            )
        ]
        if len(kept) != len(handlers):
            changed = True
        if kept:
            kept_group = dict(group)
            kept_group["hooks"] = kept
            kept_groups.append(kept_group)
    if kept_groups:
        hooks[ACTION_HINT_EVENT] = kept_groups
    elif ACTION_HINT_EVENT in hooks:
        hooks.pop(ACTION_HINT_EVENT)
        changed = True
    if changed:
        save_hooks(path, data)
    return add_host_integration(
        {
            "changed": changed,
            "installed": False,
            "path": str(path),
            "surface_event": ACTION_HINT_EVENT,
            "event_supported": True,
            "support_status": "supported_by_codex_hooks_json",
        }
    )


def status(
    path: Path,
    *,
    host: str = SUPPORTED_HOST,
    module: str = DEFAULT_ACTION_HINT_MODULE,
    include_private_paths: bool = False,
) -> dict[str, Any]:
    if host != SUPPORTED_HOST:
        result = _unsupported(path, host=host)
    else:
        data = load_hooks(path)
        groups = (data.get("hooks") or {}).get(ACTION_HINT_EVENT) or []
        commands: list[str] = []
        for group in groups if isinstance(groups, list) else []:
            for handler in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(handler, dict) and is_action_hint_handler(handler, module=module):
                    commands.append(str(handler.get("command") or ""))
        result = add_host_integration(
            {
                "installed": bool(commands),
                "path": str(path),
                "surface_event": ACTION_HINT_EVENT,
                "event_supported": True,
                "support_status": "supported_by_codex_hooks_json",
                "commands": commands,
            }
        )
    if not include_private_paths:
        result["path"] = path.name
        result["path_redacted"] = True
        raw_commands = result.get("commands")
        if isinstance(raw_commands, list) and raw_commands:
            result["commands"] = ["<redacted:hook-command>" for _ in raw_commands]
            result["commands_redacted"] = True
        else:
            result["commands_redacted"] = False
        result.pop("command", None)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["install", "uninstall", "status"],
        nargs="?",
        default="status",
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(codex_home()))
    parser.add_argument("--hooks-json")
    parser.add_argument("--host", default=SUPPORTED_HOST)
    parser.add_argument("--cache-jsonl")
    parser.add_argument("--timeout", type=int, default=DEFAULT_ACTION_HINT_TIMEOUT_SECONDS)
    parser.add_argument("--include-private-paths", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    root = Path(args.codex_home).resolve()
    path = Path(args.hooks_json).resolve() if args.hooks_json else hooks_json_path(root)
    cache_jsonl = Path(args.cache_jsonl).resolve() if args.cache_jsonl else None
    if args.action == "install":
        result = install(path, host=args.host, cache_jsonl=cache_jsonl, timeout=args.timeout)
    elif args.action == "uninstall":
        result = uninstall(path)
    else:
        result = status(path, host=args.host, include_private_paths=args.include_private_paths)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Codex action hint hook {'installed' if result.get('installed') else 'not installed'}"
        )
        print(f"event: {ACTION_HINT_EVENT}")
        print(f"support: {result.get('support_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
