"""Shared MCP launch-shape helpers for update/install surfaces."""

from __future__ import annotations

from pathlib import Path

FACADE_MCP_MODULE = "aippocampus_runtime.cli.facade"


def command_name(command: str) -> str:
    return Path(command or "").name.casefold()


def is_console_mcp_launch(command: str, args: list[str]) -> bool:
    return command_name(command) in {"aippocampus", "aippocampus.exe"} and args[:1] == [
        "mcp"
    ]


def is_facade_mcp_module_launch(args: list[str]) -> bool:
    return len(args) >= 3 and args[:3] == ["-m", FACADE_MCP_MODULE, "mcp"]


def is_current_mcp_host_launch(command: str, args: list[str]) -> bool:
    """Return whether a user/host MCP launch shape is current.

    The packaged and installed host path is the facade module because it owns
    runtime-floor handling, recovery cards, and future hot-reload probes before
    control reaches the MCP server. The server module still exists as an
    internal implementation and emergency operator fallback, but it should not
    make readiness green for host/package config.
    """

    return is_console_mcp_launch(command, args) or is_facade_mcp_module_launch(args)


def is_current_installed_python_mcp_launch(command: str, args: list[str]) -> bool:
    """Return whether an installed Codex cache launch should be preserved."""

    if command_name(command) in {"aippocampus", "aippocampus.exe"}:
        return False
    return is_facade_mcp_module_launch(args)


def portable_mcp_module_command(executable_name: str) -> str:
    return f"{executable_name} -m {FACADE_MCP_MODULE} mcp"


__all__ = [
    "FACADE_MCP_MODULE",
    "command_name",
    "is_console_mcp_launch",
    "is_current_installed_python_mcp_launch",
    "is_current_mcp_host_launch",
    "is_facade_mcp_module_launch",
    "portable_mcp_module_command",
]
