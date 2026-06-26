from __future__ import annotations

import sys
from pathlib import Path

PORTABLE_PYTHON_COMMAND = "python"


def local_python_command() -> str:
    """Return the interpreter that is running the planner, shell-quoted."""
    executable = str(Path(sys.executable).resolve())
    return '"' + executable.replace('"', '\\"') + '"'


def python_command(*, local_executable: bool = False) -> str:
    """Return a copy-pasteable Python command."""
    return local_python_command() if local_executable else PORTABLE_PYTHON_COMMAND


def py_command(args: str, *, local_executable: bool = False) -> str:
    return f"{python_command(local_executable=local_executable)} {args}"


def py_script(script: str, args: str = "", *, local_executable: bool = False) -> str:
    suffix = f" {args}" if args else ""
    return f"{python_command(local_executable=local_executable)} {script}{suffix}"


def shell_arg(value: str) -> str:
    if not value or any(char.isspace() or char in {'"', "'"} for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value
