"""Unified AIppocampus command facade over packaged runtime entrypoints."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.cli.command_registry import (
    COMMANDS as COMMANDS,
)
from aippocampus_runtime.cli.command_registry import (
    CommandInvocation as CommandInvocation,
)
from aippocampus_runtime.cli.command_registry import (
    CommandSpec as CommandSpec,
)
from aippocampus_runtime.cli.command_registry import (
    invocation_from_spec as invocation_from_spec,
)
from aippocampus_runtime.cli.command_registry import (
    module_name_for_script as module_name_for_script,
)
from aippocampus_runtime.cli.command_registry import (
    resolve_command as resolve_command,
)
from aippocampus_runtime.cli.errors import cli_error_object
from aippocampus_runtime.cli.facade_help import print_help
from aippocampus_runtime.cli.frontdoor_dispatch import dispatch_frontdoor
from aippocampus_runtime.cli.human_io import emit_json, exit_code_for_payload
from aippocampus_runtime.cli.recovery import handle_module_exception
from aippocampus_runtime.cli.runtime_floor import (
    emit_python_runtime_floor,
    python_runtime_floor_payload,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]

__all__ = [
    "COMMANDS",
    "CommandInvocation",
    "CommandResult",
    "CommandSpec",
    "dispatch",
    "invocation_from_spec",
    "main",
    "module_name_for_script",
    "resolve_command",
    "run_command",
    "run_hooks",
    "run_invocation",
    "run_module_main",
    "run_script",
]


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    invocation: CommandInvocation | None
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

def run_script(script_name: str, args: list[str]) -> int:
    return run_module_main(module_name_for_script(script_name), script_name, args)


def _coerce_exit_code(result: Any) -> int:
    return int(result or 0)


def _system_exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _system_exit_status(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def main_accepts_argv(main_func: Callable[..., Any]) -> bool:
    """Return whether a command main can be called as `main(argv)`.

    The facade should prefer package APIs over script emulation. Some older
    entrypoints still only expose a no-argument `main()` that reads `sys.argv`;
    those stay on the compatibility path until their owner grows an argv-aware
    API. Do not simplify this to "always pass argv": it would break legacy
    public scripts that are intentionally still script-shaped.
    """
    try:
        signature = inspect.signature(main_func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        }:
            return True
    return False


def run_module_main(module_name: str, script_name: str, args: list[str]) -> int:
    """Run a packaged command main in-process.

    Argv-aware package owners are called directly as Python APIs. Legacy
    no-argument mains still get a temporary script-shaped `sys.argv` so old
    direct-entrypoint semantics remain intact while the runtime is migrated.
    """
    module = importlib.import_module(module_name)
    main_func = getattr(module, "main", None)
    if not callable(main_func):
        raise RuntimeError(f"module {module_name} has no callable main()")

    if main_accepts_argv(main_func):
        stderr = StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                code = _coerce_exit_code(main_func(list(args)))
        except SystemExit as exc:
            if _system_exit_status(exc) == 0:
                print(stderr.getvalue(), end="", file=sys.stderr)
                return 0
            return handle_module_exception(
                script_name,
                args,
                exc,
                stderr_text=stderr.getvalue(),
            )
        except Exception as exc:
            return handle_module_exception(
                script_name,
                args,
                exc,
                stderr_text=stderr.getvalue(),
            )
        print(stderr.getvalue(), end="", file=sys.stderr)
        return code

    old_argv = sys.argv[:]
    sys.argv = [str(SCRIPT_DIR / script_name), *args]
    stderr = StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            code = _coerce_exit_code(main_func())
    except SystemExit as exc:
        if _system_exit_status(exc) == 0:
            print(stderr.getvalue(), end="", file=sys.stderr)
            return 0
        return handle_module_exception(
            script_name,
            args,
            exc,
            stderr_text=stderr.getvalue(),
        )
    except Exception as exc:
        return handle_module_exception(
            script_name,
            args,
            exc,
            stderr_text=stderr.getvalue(),
        )
    else:
        print(stderr.getvalue(), end="", file=sys.stderr)
        return code
    finally:
        sys.argv = old_argv


def run_invocation(invocation: CommandInvocation) -> int:
    return run_script(invocation.script_name, invocation.args)


def dispatch(argv: list[str]) -> tuple[CommandInvocation | None, int]:
    args = list(argv)
    if (runtime_floor := python_runtime_floor_payload()) is not None:
        emit_python_runtime_floor(runtime_floor, args)
        return None, 2
    frontdoor = dispatch_frontdoor(args, run_invocation=run_invocation)
    if frontdoor.handled:
        return frontdoor.invocation, frontdoor.exit_code

    invocation = resolve_command(args)
    if invocation is not None:
        return invocation, run_invocation(invocation)

    if "--json" in args:
        payload = {
            "kind": "aippocampus_cli_error",
            "ok": False,
            "error": cli_error_object(
                "unsupported_operation",
                f"unknown command: {args[0]}",
            ),
            "safe_next_actions": [
                {
                    "id": "show_help",
                    "label": "Show AIppocampus commands",
                    "command": "aippocampus --help",
                    "mutation_risk": "read_only",
                }
            ],
        }
        emit_json(payload)
        return None, exit_code_for_payload(payload)
    print(f"unknown command: {args[0]}", file=sys.stderr)
    print_help(file=sys.stderr)
    return None, 2


def run_command(argv: list[str] | None = None, *, capture_output: bool = False) -> CommandResult:
    args = list(sys.argv[1:] if argv is None else argv)
    if not capture_output:
        invocation, code = dispatch(args)
        return CommandResult(tuple(args), invocation, code)

    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        invocation, code = dispatch(args)
    return CommandResult(tuple(args), invocation, code, stdout.getvalue(), stderr.getvalue())


def main(argv: list[str] | None = None) -> int:
    return run_command(argv).exit_code


def run_hooks(args: list[str]) -> int:
    invocation = resolve_command(["hooks", *args])
    if invocation is None:
        return 2
    return run_invocation(invocation)


if __name__ == "__main__":
    raise SystemExit(main())
