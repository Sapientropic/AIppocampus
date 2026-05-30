#!/usr/bin/env python3
"""Unified AIppocampus command facade over the existing script-first runtime."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMMANDS = {
    "health": ("aippocampus_health.py", ()),
    "onboard": ("onboard.py", ()),
    "search": ("search_clean_source.py", ()),
}


def run_script(script_name: str, args: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script_name), *args],
        text=False,
        check=False,
    )
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print_help()
        return 0
    command, rest = args[0], args[1:]

    if command in COMMANDS:
        script_name, prefix = COMMANDS[command]
        return run_script(script_name, [*prefix, *rest])
    if command == "mcp":
        if rest and rest[0] == "list-tools":
            return run_script("aippocampus_mcp_server.py", ["--list-tools", *rest[1:]])
        return run_script("aippocampus_mcp_server.py", rest)
    if command == "sync":
        return run_script("sync_bundle.py", rest)
    if command == "object-sync":
        return run_script("sync_object_storage.py", rest)
    if command == "hooks":
        return run_hooks(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    print_help(file=sys.stderr)
    return 2


def run_hooks(args: list[str]) -> int:
    hook_kind = "prompt"
    rest = list(args)
    if rest and rest[0] in {"prompt", "lifecycle"}:
        hook_kind = rest.pop(0)
    script = (
        "install_aippocampus_lifecycle_hook.py"
        if hook_kind == "lifecycle"
        else "install_aippocampus_prompt_hook.py"
    )
    return run_script(script, rest)


def print_help(*, file=sys.stdout) -> None:
    parser = argparse.ArgumentParser(
        prog="aippocampus",
        description="Unified facade for AIppocampus operator commands.",
        add_help=False,
    )
    parser.print_usage(file)
    print("", file=file)
    print("Commands:", file=file)
    print("  health              Run runtime health checks", file=file)
    print("  onboard             Register/build provider-backed clean source", file=file)
    print("  search              Search clean-source memory", file=file)
    print("  mcp list-tools      List MCP tool schemas", file=file)
    print("  sync                Local-folder sync status/push/pull/repair", file=file)
    print("  object-sync         Object-storage sync status/push/pull/repair", file=file)
    print("  hooks [kind]        Prompt or lifecycle hook status/install/uninstall", file=file)
    print("", file=file)
    print("All commands delegate to existing scripts and preserve their output and exit code.", file=file)


if __name__ == "__main__":
    raise SystemExit(main())
