#!/usr/bin/env python3
"""Install or remove the ambient recall UserPromptSubmit hook."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampuslib import codex_home

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HOOK_TIMEOUT_SECONDS = 5


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


def ambient_hook(script: Path, *, timeout: int, log: bool = False) -> dict[str, Any]:
    return {
        "type": "command",
        "command": command_for(script, log=log),
        "timeout": timeout,
    }


def is_ambient_handler(handler: dict[str, Any], script: Path) -> bool:
    command = str(handler.get("command") or "")
    script_resolved = str(script.resolve())
    # Match both the new AIppocampus handler and the old thread-memory handler
    # so reinstalling upgrades hooks in-place instead of leaving duplicate
    # UserPromptSubmit entries pointing at a renamed script.
    return (
        any(name in command for name in ("aippocampus_prompt_hook.py", "ambient_recall_hook.py"))
        or script_resolved in command
    )


def user_prompt_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(groups, list):
        groups = []
        hooks["UserPromptSubmit"] = groups
    return groups


def install(
    path: Path, script: Path, *, timeout: int = DEFAULT_HOOK_TIMEOUT_SECONDS, log: bool = False
) -> dict[str, Any]:
    data = load_hooks(path)
    groups = user_prompt_groups(data)
    target = ambient_hook(script, timeout=timeout, log=log)
    changed = False

    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(handlers, list):
            continue
        existing = [
            handler
            for handler in handlers
            if isinstance(handler, dict) and is_ambient_handler(handler, script)
        ]
        if existing:
            if len(existing) == 1 and existing[0] == target:
                return {
                    "changed": False,
                    "installed": True,
                    "path": str(path),
                    "command": target["command"],
                }
            group["hooks"] = [
                handler
                for handler in handlers
                if not (isinstance(handler, dict) and is_ambient_handler(handler, script))
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
    return {"changed": changed, "installed": True, "path": str(path), "command": target["command"]}


def uninstall(path: Path, script: Path) -> dict[str, Any]:
    data = load_hooks(path)
    hooks = data.setdefault("hooks", {})
    groups = hooks.get("UserPromptSubmit")
    if not isinstance(groups, list):
        return {"changed": False, "installed": False, "path": str(path)}

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
            if not (isinstance(handler, dict) and is_ambient_handler(handler, script))
        ]
        if len(kept) != len(handlers):
            changed = True
        if kept:
            copy = dict(group)
            copy["hooks"] = kept
            kept_groups.append(copy)
    if kept_groups:
        hooks["UserPromptSubmit"] = kept_groups
    elif "UserPromptSubmit" in hooks:
        hooks.pop("UserPromptSubmit")
        changed = True
    if changed:
        save_hooks(path, data)
    return {"changed": changed, "installed": False, "path": str(path)}


def status(path: Path, script: Path) -> dict[str, Any]:
    data = load_hooks(path)
    groups = (data.get("hooks") or {}).get("UserPromptSubmit") or []
    installed = False
    commands: list[str] = []
    for group in groups if isinstance(groups, list) else []:
        for handler in group.get("hooks", []) if isinstance(group, dict) else []:
            if isinstance(handler, dict) and is_ambient_handler(handler, script):
                installed = True
                commands.append(str(handler.get("command") or ""))
    return {"installed": installed, "path": str(path), "commands": commands}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["install", "uninstall", "status"], nargs="?", default="status"
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(codex_home()))
    parser.add_argument("--hooks-json")
    parser.add_argument("--script", default=str(SCRIPT_DIR / "aippocampus_prompt_hook.py"))
    parser.add_argument("--timeout", type=int, default=DEFAULT_HOOK_TIMEOUT_SECONDS)
    parser.add_argument(
        "--log",
        action="store_true",
        help="Ask the hook to write sanitized scent/evidence debug events.",
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
        print(f"ambient recall hook {'installed' if result.get('installed') else 'not installed'}")
        print(f"hooks: {result.get('path')}")
        if result.get("changed") is not None:
            print(f"changed: {result.get('changed')}")
        if result.get("command"):
            print(f"command: {result.get('command')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
