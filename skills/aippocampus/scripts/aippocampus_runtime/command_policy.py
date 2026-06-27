from __future__ import annotations

import os
import sys
from pathlib import PureWindowsPath


def quote_posix_double(value: object) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    )
    return f'"{escaped}"'


def current_python_command() -> str:
    """Return the active interpreter for foreground copy-paste commands."""

    if os.name == "nt":
        return f'& "{PureWindowsPath(sys.executable)}"'
    return quote_posix_double(sys.executable)


def current_python_module_command(module: str, args: str = "") -> str:
    suffix = f" {args}" if args else ""
    return f"{current_python_command()} -m {module}{suffix}"


def current_python_script_command(script: str, args: str = "") -> str:
    suffix = f" {args}" if args else ""
    return f"{current_python_command()} {script}{suffix}"
