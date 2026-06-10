#!/usr/bin/env python3
"""Install or remove the ambient recall UserPromptSubmit hook."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.hooks.debug_log import prompt_hook_audit_status
from aippocampus_runtime.hooks.host_boundary import (
    add_host_integration,
    host_integration_text_lines,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_HOOK_MODULE = "aippocampus_runtime.hooks.prompt"
DEFAULT_HOOK_TIMEOUT_SECONDS = 5
PROVIDER_BRIDGE_MARKERS = (
    "aippocampus_provider_bridge_hook.py",
    "aippocampus_runtime.hooks.provider_bridge",
)
# Keep the internal Python budget below the host timeout. If a future installer
# raises the host timeout, this value can be raised deliberately; do not remove
# it, or slow semantic/API paths will be killed by Codex before they can
# fail-open and leave a sanitized diagnostic.
DEFAULT_HOOK_BUDGET_MS = 4300
DEFAULT_SEMANTIC_TIMEOUT_SECONDS = 2.5


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
    max_elapsed_ms: int = DEFAULT_HOOK_BUDGET_MS,
    semantic_timeout: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
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
    if max_elapsed_ms > 0:
        command += f" --max-elapsed-ms {int(max_elapsed_ms)}"
    if semantic_timeout > 0:
        command += f" --semantic-timeout {float(semantic_timeout):g}"
    if log:
        command += " --log"
    return command


def ambient_hook(
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    timeout: int,
    log: bool = False,
    max_elapsed_ms: int = DEFAULT_HOOK_BUDGET_MS,
    semantic_timeout: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return {
        "type": "command",
        "command": command_for(
            script,
            module=module,
            log=log,
            max_elapsed_ms=max_elapsed_ms,
            semantic_timeout=semantic_timeout,
        ),
        "timeout": timeout,
    }


def is_ambient_handler(
    handler: dict[str, Any],
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> bool:
    command = str(handler.get("command") or "")
    script_resolved = str(script.resolve()) if script is not None else ""
    # Match both the new AIppocampus handler and the old thread-memory handler
    # so reinstalling upgrades hooks in-place instead of leaving duplicate
    # UserPromptSubmit entries pointing at a renamed script.
    return (
        bool(module and module in command)
        or any(name in command for name in ("aippocampus_prompt_hook.py", "ambient_recall_hook.py"))
        or bool(script_resolved and script_resolved in command)
    )


def is_provider_bridge_handler(handler: dict[str, Any]) -> bool:
    command = str(handler.get("command") or "")
    return any(marker in command for marker in PROVIDER_BRIDGE_MARKERS)


def user_prompt_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(groups, list):
        groups = []
        hooks["UserPromptSubmit"] = groups
    return groups


def prune_direct_prompt_handlers(
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
                and is_ambient_handler(handler, script, module=module)
                and not is_provider_bridge_handler(handler)
            )
        ]
        if len(kept) != len(handlers):
            changed = True
        if kept:
            copy = dict(group)
            copy["hooks"] = kept
            out.append(copy)
    return out, changed


def provider_bridge_commands(groups: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if isinstance(handler, dict) and is_provider_bridge_handler(handler):
                commands.append(str(handler.get("command") or ""))
    return commands


def install(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    timeout: int = DEFAULT_HOOK_TIMEOUT_SECONDS,
    log: bool = False,
    max_elapsed_ms: int = DEFAULT_HOOK_BUDGET_MS,
    semantic_timeout: float = DEFAULT_SEMANTIC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    data = load_hooks(path)
    groups = user_prompt_groups(data)
    target = ambient_hook(
        script,
        module=module,
        timeout=timeout,
        log=log,
        max_elapsed_ms=max_elapsed_ms,
        semantic_timeout=semantic_timeout,
    )
    changed = False

    if script is None and module == DEFAULT_HOOK_MODULE:
        bridge_commands = provider_bridge_commands(groups)
        if bridge_commands:
            # The provider bridge delegates to this prompt module after setting
            # the provider env var, so a direct reinstall must keep the bridge
            # as the effective handler and only prune duplicate direct handlers.
            pruned, did_prune = prune_direct_prompt_handlers(groups, script, module=module)
            if did_prune or pruned != groups:
                data["hooks"]["UserPromptSubmit"] = pruned
                save_hooks(path, data)
                changed = True
            return add_host_integration(
                {
                    "changed": changed,
                    "installed": True,
                    "path": str(path),
                    "command": bridge_commands[0],
                    "provider_key_bridge_installed": True,
                }
            )

    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(handlers, list):
            continue
        existing = [
            handler
            for handler in handlers
            if isinstance(handler, dict) and is_ambient_handler(handler, script, module=module)
        ]
        if existing:
            if len(existing) == 1 and existing[0] == target:
                return add_host_integration(
                    {
                        "changed": False,
                        "installed": True,
                        "path": str(path),
                        "command": target["command"],
                    }
                )
            group["hooks"] = [
                handler
                for handler in handlers
                if not (
                    isinstance(handler, dict)
                    and is_ambient_handler(handler, script, module=module)
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
        {"changed": changed, "installed": True, "path": str(path), "command": target["command"]}
    )


def uninstall(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
) -> dict[str, Any]:
    data = load_hooks(path)
    hooks = data.setdefault("hooks", {})
    groups = hooks.get("UserPromptSubmit")
    if not isinstance(groups, list):
        return add_host_integration({"changed": False, "installed": False, "path": str(path)})

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
                and is_ambient_handler(handler, script, module=module)
            )
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
    return add_host_integration({"changed": changed, "installed": False, "path": str(path)})


def status(
    path: Path,
    script: Path | None = None,
    *,
    module: str = DEFAULT_HOOK_MODULE,
    include_last: bool = False,
    log_path: Path | None = None,
    status_path: Path | None = None,
) -> dict[str, Any]:
    data = load_hooks(path)
    groups = (data.get("hooks") or {}).get("UserPromptSubmit") or []
    commands: list[str] = []
    bridge_commands = (
        provider_bridge_commands(groups)
        if script is None and module == DEFAULT_HOOK_MODULE and isinstance(groups, list)
        else []
    )
    for group in groups if isinstance(groups, list) else []:
        for handler in group.get("hooks", []) if isinstance(group, dict) else []:
            if isinstance(handler, dict) and is_ambient_handler(handler, script, module=module):
                commands.append(str(handler.get("command") or ""))
    for command in bridge_commands:
        if command not in commands:
            commands.append(command)
    # Provider bridge wrappers are the effective default prompt hook: they set
    # provider credentials in the hook process and then delegate to this module.
    # Status must therefore match install/update readiness semantics instead of
    # reporting a healthy bridge-only setup as missing.
    installed = bool(commands)
    result: dict[str, Any] = add_host_integration(
        {
            "installed": installed,
            "path": str(path),
            "commands": commands,
            "provider_key_bridge_installed": bool(bridge_commands),
            "installed_via_provider_bridge": installed and bool(bridge_commands),
        }
    )
    if include_last:
        result["path"] = path.name
        result["path_redacted"] = True
        if commands:
            result["commands"] = ["<redacted:hook-command>" for _ in commands]
            result["commands_redacted"] = True
        result["last_prompt_hook"] = prompt_hook_audit_status(
            log_path=log_path,
            status_path=status_path,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["install", "uninstall", "status"], nargs="?", default="status"
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(codex_home()))
    parser.add_argument("--hooks-json")
    parser.add_argument("--script", help="Override hook command with an explicit Python file path.")
    parser.add_argument("--module", default=DEFAULT_HOOK_MODULE)
    parser.add_argument("--timeout", type=int, default=DEFAULT_HOOK_TIMEOUT_SECONDS)
    parser.add_argument("--max-elapsed-ms", type=int, default=DEFAULT_HOOK_BUDGET_MS)
    parser.add_argument(
        "--semantic-timeout", type=float, default=DEFAULT_SEMANTIC_TIMEOUT_SECONDS
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Ask the hook to write sanitized scent/evidence debug events.",
    )
    parser.add_argument(
        "--last",
        action="store_true",
        help="Include the latest sanitized prompt-hook memory injection audit summary in status output.",
    )
    parser.add_argument("--log-path", help="Prompt-hook debug JSONL path for --last status.")
    parser.add_argument("--status-path", help="Prompt-hook last-status JSON path for --last status.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    root = Path(args.codex_home).resolve()
    path = Path(args.hooks_json).resolve() if args.hooks_json else hooks_json_path(root)
    script = Path(args.script).resolve() if args.script else None
    if args.action == "install":
        result = install(
            path,
            script,
            module=args.module,
            timeout=args.timeout,
            log=args.log,
            max_elapsed_ms=args.max_elapsed_ms,
            semantic_timeout=args.semantic_timeout,
        )
    elif args.action == "uninstall":
        result = uninstall(path, script, module=args.module)
    else:
        result = status(
            path,
            script,
            module=args.module,
            include_last=args.last,
            log_path=Path(args.log_path).resolve() if args.log_path else None,
            status_path=Path(args.status_path).resolve() if args.status_path else None,
        )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Codex prompt hook {'installed' if result.get('installed') else 'not installed'}")
        print(f"hooks: {result.get('path')}")
        for line in host_integration_text_lines():
            print(line)
        if result.get("changed") is not None:
            print(f"changed: {result.get('changed')}")
        if result.get("command"):
            print(f"command: {result.get('command')}")
        raw_last = result.get("last_prompt_hook")
        last = raw_last if isinstance(raw_last, dict) else {}
        raw_latest = last.get("last_prompt_hook")
        latest = raw_latest if isinstance(raw_latest, dict) else {}
        if latest:
            print(
                "last prompt hook: "
                f"{latest.get('memory_surface')} "
                f"cards={latest.get('card_count')} "
                f"source_backed={latest.get('source_backed_count')} "
                f"cache={((latest.get('cache') or {}).get('status'))}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
