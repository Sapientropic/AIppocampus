#!/usr/bin/env python3
"""Runtime scan for compact/frontstage JSON surfaces.

This is a low-noise regression guard for the recurring agent failure where a
new status or recovery path hand-rolls compact output and leaks operator proof
fields. It runs representative real CLI commands, then checks one MCP runtime
recovery response through the MCP profile renderer so `structuredContent` stays
the product card instead of a pretty JSON wall.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

try:
    from repo_paths import ensure_repo_imports
except ModuleNotFoundError:  # pragma: no cover - package import path
    from tools.aippocampus.repo_paths import ensure_repo_imports

PATHS = ensure_repo_imports(Path(__file__))

SCHEMA_VERSION = 1

DEFAULT_PROBE_TIMEOUT_SECONDS = 10.0
DEFAULT_SCAN_BUDGET_SECONDS = 30.0
DEFAULT_SLOW_PROBE_MS = 3000.0


@dataclass(frozen=True)
class SurfaceProbe:
    command: str
    profile: str = "foreground_compact"
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS


CLI_PROBES = (
    SurfaceProbe("aippocampus hooks prompt status --last --json"),
    SurfaceProbe("aippocampus hooks lifecycle status --json"),
    SurfaceProbe("aippocampus hooks action status --json"),
    SurfaceProbe("aippocampus hooks claude-code status --json"),
    SurfaceProbe("aippocampus agent background --json"),
    SurfaceProbe('aippocampus agent background "compact foreground audit" --json'),
    SurfaceProbe('aippocampus agent aippo --task "AIppocampus host probe schema freshness" --json'),
    SurfaceProbe("aippocampus warm status --json"),
    SurfaceProbe("aippocampus dream status --json"),
    SurfaceProbe("aippocampus update status --json"),
    SurfaceProbe('aippocampus search --all "compact foreground audit" --json --max 5'),
    SurfaceProbe(
        'aippocampus search --all "compact foreground audit" '
        "--search-budget deep --json --max-elapsed-ms 15000 --max 5",
        profile="detail_or_full",
    ),
    SurfaceProbe("aippocampus doctor provider --json"),
    SurfaceProbe("aippocampus storage gc --dry-run --summary-json --cwd ."),
    SurfaceProbe("aippocampus storage gc --dry-run --json --top 1 --cwd ."),
)

CLI_COMMANDS = tuple(probe.command for probe in CLI_PROBES)

MAX_SAFE_ACTIONS = 1


def denied_keys() -> frozenset[str]:
    from aippocampus_runtime.foreground_compact_language import (
        COMPACT_CONTROL_SURFACE_FIELD_DENYLIST,
        COMPACT_POLICY_FIELD_DENYLIST,
    )

    return (
        COMPACT_POLICY_FIELD_DENYLIST
        | COMPACT_CONTROL_SURFACE_FIELD_DENYLIST
        | frozenset(
            {
                "operator_json_available",
                "operator_detail_available",
                "operator_detail_fields",
            }
        )
    )


def _format_path(path: Sequence[str | int]) -> str:
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered = f"{rendered}[{part}]"
        elif rendered:
            rendered = f"{rendered}.{part}"
        else:
            rendered = part
    return rendered


def denied_field_paths(value: Any, path: tuple[str | int, ...] = ()) -> list[str]:
    denied = denied_keys()
    if isinstance(value, Mapping):
        paths: list[str] = []
        for key, child in value.items():
            child_path = (*path, str(key))
            if str(key) in denied:
                paths.append(_format_path(child_path))
            paths.extend(denied_field_paths(child, child_path))
        return paths
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        paths = []
        for index, child in enumerate(value):
            paths.extend(denied_field_paths(child, (*path, index)))
        return paths
    return []


def safe_action_count(value: Any) -> int:
    if not isinstance(value, Mapping):
        return 0
    actions = value.get("safe_next_actions")
    return len(actions) if isinstance(actions, list) else 0


def _load_json(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        raise ValueError("command produced no stdout")
    return json.loads(text)


def _command_surface(command: str | Sequence[str]) -> str:
    if isinstance(command, str):
        return command
    return shlex.join([str(item) for item in command])


def _command_argv(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        raw = shlex.split(command)
    else:
        raw = [str(item) for item in command]
    if raw and raw[0] == "aippocampus":
        return [sys.executable, "-m", "aippocampus_runtime.cli.facade", *raw[1:]]
    return raw


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    parts = [str(PATHS.skill_scripts)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def scan_cli_command(
    command: str | Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    profile: str = "foreground_compact",
) -> dict[str, Any]:
    surface = _command_surface(command)
    argv = _command_argv(command)
    started_at = perf_counter()
    if timeout_seconds <= 0:
        clamped_timeout_seconds = max(0.0, timeout_seconds)
        return {
            "surface": surface,
            "kind": "cli",
            "profile": profile,
            "ok": False,
            "exit_code": None,
            "elapsed_ms": 0.0,
            "timeout_seconds": clamped_timeout_seconds,
            "error": "scan_budget_exhausted",
            "stderr_preview": "",
        }
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_subprocess_env(),
            **_popen_kwargs(),
        )
    except OSError as exc:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        return {
            "surface": surface,
            "kind": "cli",
            "profile": profile,
            "ok": False,
            "exit_code": None,
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": timeout_seconds,
            "error": f"process_start_failed:{type(exc).__name__}",
            "stderr_preview": str(exc)[:240],
        }
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        return {
            "surface": surface,
            "kind": "cli",
            "profile": profile,
            "ok": False,
            "exit_code": None,
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": timeout_seconds,
            "error": "timeout",
            "stdout_preview": stdout.strip()[:240],
            "stderr_preview": stderr.strip()[:240],
        }
    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
    try:
        payload = _load_json(stdout)
    except Exception as exc:
        return {
            "surface": surface,
            "kind": "cli",
            "profile": profile,
            "ok": False,
            "exit_code": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": timeout_seconds,
            "error": f"json_parse_failed:{type(exc).__name__}",
            "stderr_preview": stderr.strip()[:240],
        }
    leaks = denied_field_paths(payload)
    safe_count = safe_action_count(payload)
    if profile == "detail_or_full":
        return {
            "surface": surface,
            "kind": "cli",
            "profile": profile,
            "ok": True,
            "exit_code": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": timeout_seconds,
            "diagnostic_field_paths": leaks,
            "safe_action_count": safe_count,
        }
    return {
        "surface": surface,
        "kind": "cli",
        "profile": profile,
        "ok": not leaks and safe_count <= MAX_SAFE_ACTIONS,
        "exit_code": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "timeout_seconds": timeout_seconds,
        "denied_field_paths": leaks,
        "safe_action_count": safe_count,
    }


def scan_mcp_runtime_recovery() -> dict[str, Any]:
    from aippocampus_runtime.mcp.result_profile import render_profiled_result
    from aippocampus_runtime.mcp.runtime_recovery import (
        foreground_mcp_runtime_recovery_payload,
    )

    started_at = perf_counter()
    payload = foreground_mcp_runtime_recovery_payload(
        "agent_recall",
        TypeError("agent_recall() got an unexpected keyword argument 'cue'"),
    )
    result = render_profiled_result(
        {"detail": "compact"},
        payload,
        is_error=True,
        full_output_boundary="foreground_mcp_runtime_recovery",
    )
    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    leaks = denied_field_paths(structured)
    safe_count = safe_action_count(structured)
    return {
        "surface": "mcp_runtime_recovery:agent_recall",
        "kind": "mcp",
        "profile": "foreground_compact",
        "ok": isinstance(structured, Mapping) and not leaks and safe_count <= MAX_SAFE_ACTIONS,
        "elapsed_ms": elapsed_ms,
        "has_structured_content": isinstance(structured, Mapping),
        "text_item_count": len(result.get("content") or []) if isinstance(result, dict) else 0,
        "denied_field_paths": leaks,
        "safe_action_count": safe_count,
    }


def _mcp_tool_structured_content_check(
    surface: str,
    result: dict[str, Any],
    *,
    elapsed_ms: float,
) -> dict[str, Any]:
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    leaks = denied_field_paths(structured)
    safe_count = safe_action_count(structured)
    return {
        "surface": surface,
        "kind": "mcp",
        "profile": "foreground_compact",
        "ok": isinstance(structured, Mapping) and not leaks and safe_count <= MAX_SAFE_ACTIONS,
        "elapsed_ms": elapsed_ms,
        "has_structured_content": isinstance(structured, Mapping),
        "text_item_count": len(result.get("content") or []) if isinstance(result, dict) else 0,
        "denied_field_paths": leaks,
        "safe_action_count": safe_count,
    }


def scan_mcp_key_tool_compact_cards(*, cwd: Path) -> list[dict[str, Any]]:
    """Scan representative MCP compact tools that bypass recall projection.

    `agent_recall` and `agent_deepen` have dedicated compact projection tests.
    These key tools caught a real regression where the host probe passed schema
    discovery while AIppo/background compact output still leaked source-boundary
    vocabulary. Keep them here as an executable surface inventory, not another
    prose contract.
    """

    from aippocampus_runtime.mcp import tool_handlers

    checks: list[dict[str, Any]] = []
    for surface, call in (
        (
            "mcp_tool:agent_aippo",
            lambda: tool_handlers.call_agent_aippo(
                {
                    "task": "AIppocampus host probe schema freshness",
                    "cwd": str(cwd),
                }
            ),
        ),
        (
            "mcp_tool:agent_background",
            lambda: tool_handlers.call_agent_background(
                {
                    "cue": "AIppocampus reviewed background findings smoke",
                    "limit": 1,
                    "cwd": str(cwd),
                }
            ),
        ),
        (
            "mcp_tool:agent_background_missing_input",
            lambda: tool_handlers.call_agent_background({}),
        ),
    ):
        started_at = perf_counter()
        result = call()
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        checks.append(_mcp_tool_structured_content_check(surface, result, elapsed_ms=elapsed_ms))
    return checks


def _first_slow_check(
    checks: Sequence[Mapping[str, Any]],
    *,
    slow_probe_ms: float,
) -> Mapping[str, Any] | None:
    for check in checks:
        if check.get("error") == "timeout":
            return check
        elapsed = check.get("elapsed_ms")
        if isinstance(elapsed, int | float) and elapsed >= slow_probe_ms:
            return check
    return None


def run_scan(
    *,
    cwd: Path,
    include_cli: bool = True,
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    scan_budget_seconds: float = DEFAULT_SCAN_BUDGET_SECONDS,
    slow_probe_ms: float = DEFAULT_SLOW_PROBE_MS,
) -> dict[str, Any]:
    scan_started_at = perf_counter()
    scan_deadline = scan_started_at + scan_budget_seconds
    checks: list[dict[str, Any]] = []
    if include_cli:
        for probe in CLI_PROBES:
            remaining_seconds = max(0.0, scan_deadline - perf_counter())
            timeout_seconds = min(probe.timeout_seconds, probe_timeout_seconds, remaining_seconds)
            checks.append(
                scan_cli_command(
                    probe.command,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    profile=probe.profile,
                )
            )
            if checks[-1].get("error") == "scan_budget_exhausted":
                break
    checks.append(scan_mcp_runtime_recovery())
    checks.extend(scan_mcp_key_tool_compact_cards(cwd=cwd))
    failures = [item for item in checks if not item.get("ok")]
    elapsed_ms = round((perf_counter() - scan_started_at) * 1000, 3)
    first_slow = _first_slow_check(checks, slow_probe_ms=slow_probe_ms)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not failures,
        "elapsed_ms": elapsed_ms,
        "scan_budget_seconds": scan_budget_seconds,
        "probe_timeout_seconds": probe_timeout_seconds,
        "slow_probe_ms": slow_probe_ms,
        "first_slow_surface": first_slow.get("surface") if first_slow else None,
        "first_slow_elapsed_ms": first_slow.get("elapsed_ms") if first_slow else None,
        "slow_probe_count": sum(
            1
            for item in checks
            if item.get("error") == "timeout"
            or (
                isinstance(item.get("elapsed_ms"), int | float)
                and float(item["elapsed_ms"]) >= slow_probe_ms
            )
        ),
        "timeout_count": sum(1 for item in checks if item.get("error") == "timeout"),
        "checked_count": len(checks),
        "failure_count": len(failures),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--no-cli",
        action="store_true",
        help="Only scan the in-process MCP recovery payload; used by focused unit tests.",
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=DEFAULT_PROBE_TIMEOUT_SECONDS,
        help="Per CLI probe timeout; timeouts are reported as failed checks.",
    )
    parser.add_argument(
        "--scan-budget-seconds",
        type=float,
        default=DEFAULT_SCAN_BUDGET_SECONDS,
        help="Total local scan budget for representative CLI probes.",
    )
    parser.add_argument(
        "--slow-probe-ms",
        type=float,
        default=DEFAULT_SLOW_PROBE_MS,
        help="Elapsed time threshold for first_slow_surface reporting.",
    )
    args = parser.parse_args(argv)
    report = run_scan(
        cwd=PATHS.repo_root,
        include_cli=not args.no_cli,
        probe_timeout_seconds=args.probe_timeout_seconds,
        scan_budget_seconds=args.scan_budget_seconds,
        slow_probe_ms=args.slow_probe_ms,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"compact surface scan: {'ok' if report['ok'] else 'failed'}")
        for check in report["checks"]:
            if check.get("ok"):
                continue
            print(f"- {check['surface']}: {check.get('denied_field_paths') or check.get('error')}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
