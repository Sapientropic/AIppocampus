#!/usr/bin/env python3
"""Install or remove thread-memory lifecycle maintenance hooks."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.hooks.host_boundary import (
    add_host_integration,
    host_integration_text_lines,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_HOOK_MODULE = "aippocampus_runtime.hooks.lifecycle"
DEFAULT_TIMEOUT_SECONDS = 20
EVENTS = ("SessionStart", "Stop", "PreCompact", "PostCompact")


def hooks_json_path(codex_home_path: Path | None = None) -> Path:
    return (codex_home_path or codex_home()) / "hooks.json"


def load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        data["hooks"] = {}
    return data


def save_hooks(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def quote_powershell_double(value: str | Path) -> str:
    text = str(value)
    escaped = text.replace("`", "``").replace('"', '`"').replace("$", "`$")
    return f'"{escaped}"'


def command_for(
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    log: bool = False,
) -> str:
    if script is None:
        if os.name == "nt":
            command = (
                f"$env:PYTHONPATH={quote_powershell_double(SCRIPT_DIR)}; "
                f"& {quote_powershell_double(Path(sys.executable).resolve())} -m {module}"
            )
        else:
            command = (
                f"PYTHONPATH={shlex.quote(str(SCRIPT_DIR))} "
                f"{shlex.quote(str(Path(sys.executable).resolve()))} -m {module}"
            )
    else:
        command = f'"{Path(sys.executable).resolve()}" "{script.resolve()}"'
    if os.name == "nt" and script is not None:
        # Codex Desktop executes hook command strings through PowerShell on
        # Windows. A quoted executable at the start of the line is parsed as a
        # string expression and exits with code 1; the call operator keeps
        # paths-with-spaces safe and preserves the hook as fail-open glue.
        command = f"& {command}"
    if log:
        command += " --log"
    return command


def handler_for(
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    timeout: int,
    log: bool = False,
) -> dict[str, Any]:
    return {
        "type": "command",
        "command": command_for(script, module=module, log=log),
        "timeout": timeout,
    }


def is_maintenance_handler(
    handler: dict[str, Any],
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> bool:
    command = str(handler.get("command") or "")
    script_resolved = str(script.resolve()) if script is not None else ""
    # Match both the new AIppocampus handler and the old thread-memory handler
    # so reinstalling upgrades lifecycle hooks in-place instead of leaving
    # stale Stop/PreCompact/PostCompact commands behind.
    return (
        bool(module and module in command)
        or any(
            name in command
            for name in ("aippocampus_lifecycle_hook.py", "memory_maintenance_hook.py")
        )
        or bool(script_resolved and script_resolved in command)
    )


def groups_for(data: dict[str, Any], event: str) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        groups = []
        hooks[event] = groups
    return groups


def prune_event(
    groups: list[dict[str, Any]],
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> tuple[list[dict[str, Any]], bool]:
    changed = False
    out: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            out.append(group)
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            out.append(group)
            continue
        kept = [
            handler
            for handler in handlers
            if not (
                isinstance(handler, dict)
                and is_maintenance_handler(handler, script, module=module)
            )
        ]
        if len(kept) != len(handlers):
            changed = True
        if kept:
            copy = dict(group)
            copy["hooks"] = kept
            out.append(copy)
    return out, changed


def install(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    log: bool = False,
) -> dict[str, Any]:
    data = load_hooks(path)
    changed = False
    target = handler_for(script, module=module, timeout=timeout, log=log)
    for event in EVENTS:
        groups = groups_for(data, event)
        pruned, did_prune = prune_event(groups, script, module=module)
        if did_prune:
            changed = True
        event_changed = did_prune or pruned != groups
        pruned.append({"hooks": [target]})
        data["hooks"][event] = pruned
        changed = True if event_changed or not did_prune else changed
    before_normalized = json.dumps(load_hooks(path), ensure_ascii=False, sort_keys=True)
    after_normalized = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before_normalized != after_normalized:
        save_hooks(path, data)
        changed = True
    else:
        changed = False
    return add_host_integration(
        {
            "changed": changed,
            "installed": True,
            "path": str(path),
            "events": list(EVENTS),
            "command": target["command"],
        }
    )


def uninstall(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> dict[str, Any]:
    data = load_hooks(path)
    hooks = data.setdefault("hooks", {})
    changed = False
    for event in EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        pruned, did_prune = prune_event(groups, script, module=module)
        if did_prune:
            changed = True
            if pruned:
                hooks[event] = pruned
            else:
                hooks.pop(event, None)
    if changed:
        save_hooks(path, data)
    return add_host_integration(
        {"changed": changed, "installed": False, "path": str(path), "events": list(EVENTS)}
    )


def status(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> dict[str, Any]:
    data = load_hooks(path)
    installed_events: dict[str, list[str]] = {}
    for event in EVENTS:
        groups = (data.get("hooks") or {}).get(event) or []
        commands: list[str] = []
        for group in groups if isinstance(groups, list) else []:
            for handler in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(handler, dict) and is_maintenance_handler(handler, script, module=module):
                    commands.append(str(handler.get("command") or ""))
        if commands:
            installed_events[event] = commands
    return add_host_integration(
        {
            "installed": set(installed_events) == set(EVENTS),
            "path": str(path),
            "events": installed_events,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["install", "uninstall", "status"], nargs="?", default="status"
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(codex_home()))
    parser.add_argument("--hooks-json")
    parser.add_argument("--script", help="Override hook command with an explicit Python file path.")
    parser.add_argument("--module", default=DEFAULT_HOOK_MODULE)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--log", action="store_true", help="Ask the hook to write sanitized lifecycle debug events."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    root = Path(args.codex_home).resolve()
    path = Path(args.hooks_json).resolve() if args.hooks_json else hooks_json_path(root)
    script = Path(args.script).resolve() if args.script else None
    if args.action == "install":
        result = install(path, script, module=args.module, timeout=args.timeout, log=args.log)
    elif args.action == "uninstall":
        result = uninstall(path, script, module=args.module)
    else:
        result = status(path, script, module=args.module)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Codex lifecycle hooks {'installed' if result.get('installed') else 'not installed'}"
        )
        print(f"hooks: {result.get('path')}")
        for line in host_integration_text_lines():
            print(line)
        if result.get("changed") is not None:
            print(f"changed: {result.get('changed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
