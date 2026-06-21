#!/usr/bin/env python3
"""Install or inspect the Codex PreToolUse action-hint hook."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.hooks.action_hint_cache import (
    DEFAULT_ACTION_HINT_CACHE_LABEL,
    action_hint_cache_resolution,
    default_action_hint_cache_path,
    load_action_hint_records_with_diagnostics,
)
from aippocampus_runtime.hooks.action_hint_cache_records import BLOCKED_STATES
from aippocampus_runtime.hooks.foreground_status import (
    action_hint_status_contract,
    compact_action_hint_status_result,
)
from aippocampus_runtime.hooks.host_boundary import add_host_integration
from aippocampus_runtime.hooks.install_action_hint_projection import (
    action_hint_frontstage_card,
    public_install_result,
    redact_public_result,
)
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
CACHE_ARG_RE = re.compile(r"""--cache-jsonl\s+(?:"([^"]+)"|'([^']+)'|(\S+))""")


def positive_timeout(value: str | int) -> int:
    timeout = int(value)
    if timeout < 1:
        raise argparse.ArgumentTypeError("--timeout must be at least 1 second")
    return timeout


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
    timeout = positive_timeout(timeout)
    return {
        "type": "command",
        "command": command_for(module=module, cache_jsonl=cache_jsonl),
        "timeout": timeout,
    }


def is_action_hint_handler(
    handler: Mapping[str, Any],
    *,
    module: str = DEFAULT_ACTION_HINT_MODULE,
) -> bool:
    command = str(handler.get("command") or "")
    return module in command or "aippocampus_runtime.hooks.action_hint" in command


def cache_path_from_command(command: str) -> Path | None:
    match = CACHE_ARG_RE.search(command)
    if not match:
        return None
    raw = next((group for group in match.groups() if group), "")
    if not raw:
        return None
    raw = raw.strip().strip('"').strip("'")
    return Path(raw)


def _cache_path_label(path: Path, *, codex_home_path: Path | None = None) -> dict[str, str]:
    default_path = default_action_hint_cache_path(Path.cwd(), home=codex_home_path)
    try:
        if path.resolve() == default_path.resolve():
            return {
                "cache_path_label": DEFAULT_ACTION_HINT_CACHE_LABEL,
                "cache_scope": "current_workspace",
                "cache_path_source": "default_registry",
            }
    except OSError:
        pass
    return {
        "cache_path_label": "explicit-cache-jsonl",
        "cache_scope": "explicit_override",
        "cache_path_source": "argument_or_existing_hook",
    }


def _cache_status(commands: list[str], *, codex_home_path: Path | None = None) -> dict[str, Any]:
    paths = [cache_path_from_command(command) for command in commands]
    valid_paths = [path for path in paths if path is not None]
    if not valid_paths:
        return {
            "cache_status": "with_missing_cache_file",
            "cache_path_configured": False,
            "cache_exists": False,
            "cache_record_count": 0,
            "fresh_record_count": 0,
            "expired_record_count": 0,
            "malformed_cache_line_count": 0,
            "provider_counts": {},
            "cache_path": "",
            "cache_path_label": DEFAULT_ACTION_HINT_CACHE_LABEL,
            "cache_scope": "not_configured",
            "cache_path_source": "missing_hook_argument",
            "next_command": "aippocampus hooks action refresh-cache --write --json",
        }
    path = valid_paths[0]
    path_meta = _cache_path_label(path, codex_home_path=codex_home_path)
    if not path.exists():
        return {
            "cache_status": "with_missing_cache_file",
            "cache_path_configured": True,
            "cache_exists": False,
            "cache_record_count": 0,
            "fresh_record_count": 0,
            "expired_record_count": 0,
            "malformed_cache_line_count": 0,
            "provider_counts": {},
            "cache_path": str(path),
            **path_meta,
            "next_command": "aippocampus hooks action refresh-cache --write --json",
        }
    cache = load_action_hint_records_with_diagnostics(path)
    records = [row for row in cache.get("records") or [] if isinstance(row, Mapping)]
    now_unix = time.time()
    provider_counts: dict[str, int] = {}
    fresh_count = 0
    expired_count = 0
    for record in records:
        provider = str(record.get("provider_family") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        freshness = str(record.get("freshness") or "").casefold()
        try:
            expires_at = float(record.get("expires_at_unix") or 0)
        except (TypeError, ValueError):
            expires_at = 0.0
        if freshness in BLOCKED_STATES or (expires_at and expires_at <= now_unix):
            expired_count += 1
        else:
            fresh_count += 1
    count = len(records)
    if count == 0:
        cache_status = "with_empty_cache"
    elif fresh_count:
        cache_status = "with_fresh_records"
    else:
        cache_status = "with_expired_records"
    return {
        "cache_status": cache_status,
        "cache_path_configured": True,
        "cache_exists": True,
        "cache_record_count": count,
        "fresh_record_count": fresh_count,
        "expired_record_count": expired_count,
        "malformed_cache_line_count": int(cache.get("malformed_cache_line_count") or 0),
        "provider_counts": provider_counts,
        "cache_path": str(path),
        **path_meta,
        "next_command": "aippocampus hooks action refresh-cache --write --json",
    }


def event_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault(ACTION_HINT_EVENT, [])
    if not isinstance(groups, list):
        groups = []
        hooks[ACTION_HINT_EVENT] = groups
    return groups


def _unsupported(path: Path, *, host: str) -> dict[str, Any]:
    result = add_host_integration(
        {
            "installed": False,
            "changed": False,
            "path": str(path),
            "surface_event": ACTION_HINT_EVENT,
            "event_supported": False,
            "support_status": f"unsupported_host:{host}",
            "requested_host": host,
            "effective_host": SUPPORTED_HOST,
        }
    )
    result["host_integration"] = {
        **dict(result.get("host_integration") or {}),
        "status": f"unsupported_host:{host}",
        "requested_host": host,
        "effective_host": SUPPORTED_HOST,
    }
    return result


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
    if cache_jsonl is None:
        cache_jsonl = default_action_hint_cache_path(Path.cwd(), home=path.parent)
        cache_meta = action_hint_cache_resolution(cwd=Path.cwd(), home=path.parent)
    else:
        cache_meta = action_hint_cache_resolution(cache_jsonl, cwd=Path.cwd(), home=path.parent)
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
                        "cache_path_label": cache_meta["path_label"],
                        "cache_scope": cache_meta["scope"],
                        "cache_path_source": cache_meta["path_source"],
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
            "cache_path_label": cache_meta["path_label"],
            "cache_scope": cache_meta["scope"],
            "cache_path_source": cache_meta["path_source"],
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
                **(
                    _cache_status(commands, codex_home_path=path.parent)
                    if commands
                    else {
                        "cache_status": "not_installed",
                        "cache_path_configured": False,
                        "cache_exists": False,
                        "cache_record_count": 0,
                        "fresh_record_count": 0,
                        "expired_record_count": 0,
                        "malformed_cache_line_count": 0,
                        "provider_counts": {},
                        "cache_path": "",
                        "cache_path_label": DEFAULT_ACTION_HINT_CACHE_LABEL,
                        "cache_scope": "not_configured",
                        "cache_path_source": "missing_hook_argument",
                        "next_command": "aippocampus hooks action refresh-cache --write --json",
                    }
                ),
            }
        )
    result["frontstage_card"] = action_hint_frontstage_card(result)
    result["hot_path_active"] = bool(result["frontstage_card"].get("hot_path_active"))
    result["warning_state"] = str(result["frontstage_card"].get("warning_state") or "")
    result["setup_role"] = str(result["frontstage_card"].get("setup_role") or "")
    result.update(action_hint_status_contract(result["frontstage_card"]))
    return (
        result
        if include_private_paths
        else compact_action_hint_status_result(result, event=ACTION_HINT_EVENT)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        epilog=(
            "Refresh prepared cache through the facade with: "
            "aippocampus hooks action refresh-cache --write --json"
        )
    )
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
    parser.add_argument("--timeout", type=positive_timeout, default=DEFAULT_ACTION_HINT_TIMEOUT_SECONDS)
    parser.add_argument("--include-private-paths", action="store_true")
    parser.add_argument(
        "--operator-json",
        action="store_true",
        dest="operator_json",
        help="Emit raw local hooks.json path and hook command for local diagnostics.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    root = Path(args.codex_home).resolve()
    path = Path(args.hooks_json).resolve() if args.hooks_json else hooks_json_path(root)
    cache_jsonl = Path(args.cache_jsonl).resolve() if args.cache_jsonl else None
    if args.action == "install":
        install_result = install(path, host=args.host, cache_jsonl=cache_jsonl, timeout=args.timeout)
        status_result = status(path, host=args.host, include_private_paths=True)
        result = {
            **status_result,
            "changed": bool(install_result.get("changed")),
            "install_action": "install",
        }
    elif args.action == "uninstall":
        result = uninstall(path)
    else:
        result = status(path, host=args.host, include_private_paths=True)
    include_private_paths = args.include_private_paths or args.operator_json
    if args.action == "install" and not include_private_paths:
        result = public_install_result(result, path=path)
    elif args.action == "status" and not include_private_paths:
        result = compact_action_hint_status_result(result, event=ACTION_HINT_EVENT)
    elif not include_private_paths:
        result = redact_public_result(result, path=path)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Action-time hints: {result.get('status') or 'unknown'}")
        print("optional: true; fail-open: true; authority: navigation_only")
        print(f"event: {ACTION_HINT_EVENT}")
        print(f"support: {result.get('support_status')}")
        steps = [result.get("foreground_action"), *(result.get("safe_next_actions") or [])]
        if steps:
            installed = bool(result.get("installed"))
            preferred_labels = (
                {"review guidance", "install action hint hook", "refresh action hint cache"}
                if not installed
                else {"refresh action hint cache", "install action hint hook"}
            )
            preferred = next(
                (
                    step
                    for step in steps
                    if str(step.get("label") or "").casefold() in preferred_labels
                ),
                next(
                    (
                        step
                        for step in steps
                        if str(step.get("label") or "").casefold().startswith("check")
                    ),
                    steps[0],
                ),
            )
            print(f"next: {preferred.get('command')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
