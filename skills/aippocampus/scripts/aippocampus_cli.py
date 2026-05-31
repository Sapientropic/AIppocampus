#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus CLI facade."""

from __future__ import annotations

from aippocampus_runtime.cli.facade import COMMANDS as COMMANDS
from aippocampus_runtime.cli.facade import SCRIPT_DIR as SCRIPT_DIR
from aippocampus_runtime.cli.facade import CommandInvocation as CommandInvocation
from aippocampus_runtime.cli.facade import CommandSpec as CommandSpec
from aippocampus_runtime.cli.facade import main as main
from aippocampus_runtime.cli.facade import module_name_for_script as module_name_for_script
from aippocampus_runtime.cli.facade import print_help as print_help
from aippocampus_runtime.cli.facade import resolve_command as resolve_command
from aippocampus_runtime.cli.facade import run_hooks as run_hooks
from aippocampus_runtime.cli.facade import run_invocation as run_invocation
from aippocampus_runtime.cli.facade import run_module_main as run_module_main
from aippocampus_runtime.cli.facade import run_script as run_script

if __name__ == "__main__":
    raise SystemExit(main())
