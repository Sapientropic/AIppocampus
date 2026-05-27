#!/usr/bin/env python3
"""Install or remove thread-memory lifecycle maintenance hooks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampuslib import codex_home

SCRIPT_DIR = Path(__file__).resolve().parent
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


def command_for(script: Path, *, log: bool = False) -> str:
    command = f'"{Path(sys.executable).resolve()}" "{script.resolve()}"'
    if os.name == "nt":
        # Codex Desktop executes hook command strings through PowerShell on
        # Windows. A quoted executable at the start of the line is parsed as a
        # string expression and exits with code 1; the call operator keeps
        # paths-with-spaces safe and preserves the hook as fail-open glue.
        command = f"& {command}"
    if log:
        command += " --log"
    return command


def handler_for(script: Path, *, timeout: int, log: bool = False) -> dict[str, Any]:
    return {"type": "command", "command": command_for(script, log=log), "timeout": timeout}


def is_maintenance_handler(handler: dict[str, Any], script: Path) -> bool:
    command = str(handler.get("command") or "")
    script_resolved = str(script.resolve())
    # Match both the new AIppocampus handler and the old thread-memory handler
    # so reinstalling upgrades lifecycle hooks in-place instead of leaving
    # stale Stop/PreCompact/PostCompact commands behind.
    return (
        any(
            name in command
            for name in ("aippocampus_lifecycle_hook.py", "memory_maintenance_hook.py")
        )
        or script_resolved in command
    )


def groups_for(data: dict[str, Any], event: str) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        groups = []
        hooks[event] = groups
    return groups


def prune_event(groups: list[dict[str, Any]], script: Path) -> tuple[list[dict[str, Any]], bool]:
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
            if not (isinstance(handler, dict) and is_maintenance_handler(handler, script))
        ]
        if len(kept) != len(handlers):
            changed = True
        if kept:
            copy = dict(group)
            copy["hooks"] = kept
            out.append(copy)
    return out, changed


def install(
    path: Path, script: Path, *, timeout: int = DEFAULT_TIMEOUT_SECONDS, log: bool = False
) -> dict[str, Any]:
    data = load_hooks(path)
    changed = False
    target = handler_for(script, timeout=timeout, log=log)
    for event in EVENTS:
        groups = groups_for(data, event)
        pruned, did_prune = prune_event(groups, script)
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
    return {
        "changed": changed,
        "installed": True,
        "path": str(path),
        "events": list(EVENTS),
        "command": target["command"],
    }


def uninstall(path: Path, script: Path) -> dict[str, Any]:
    data = load_hooks(path)
    hooks = data.setdefault("hooks", {})
    changed = False
    for event in EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        pruned, did_prune = prune_event(groups, script)
        if did_prune:
            changed = True
            if pruned:
                hooks[event] = pruned
            else:
                hooks.pop(event, None)
    if changed:
        save_hooks(path, data)
    return {"changed": changed, "installed": False, "path": str(path), "events": list(EVENTS)}


def status(path: Path, script: Path) -> dict[str, Any]:
    data = load_hooks(path)
    installed_events: dict[str, list[str]] = {}
    for event in EVENTS:
        groups = (data.get("hooks") or {}).get(event) or []
        commands: list[str] = []
        for group in groups if isinstance(groups, list) else []:
            for handler in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(handler, dict) and is_maintenance_handler(handler, script):
                    commands.append(str(handler.get("command") or ""))
        if commands:
            installed_events[event] = commands
    return {
        "installed": set(installed_events) == set(EVENTS),
        "path": str(path),
        "events": installed_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["install", "uninstall", "status"], nargs="?", default="status"
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(codex_home()))
    parser.add_argument("--hooks-json")
    parser.add_argument("--script", default=str(SCRIPT_DIR / "aippocampus_lifecycle_hook.py"))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--log", action="store_true", help="Ask the hook to write sanitized lifecycle debug events."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    root = Path(args.codex_home).resolve()
    path = Path(args.hooks_json).resolve() if args.hooks_json else hooks_json_path(root)
    script = Path(args.script).resolve()
    if args.action == "install":
        result = install(path, script, timeout=args.timeout, log=args.log)
    elif args.action == "uninstall":
        result = uninstall(path, script)
    else:
        result = status(path, script)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"thread-memory maintenance hooks {'installed' if result.get('installed') else 'not installed'}"
        )
        print(f"hooks: {result.get('path')}")
        if result.get("changed") is not None:
            print(f"changed: {result.get('changed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
