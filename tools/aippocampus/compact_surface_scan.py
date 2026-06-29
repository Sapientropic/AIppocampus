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
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from repo_paths import ensure_repo_imports
except ModuleNotFoundError:  # pragma: no cover - package import path
    from tools.aippocampus.repo_paths import ensure_repo_imports

PATHS = ensure_repo_imports(Path(__file__))

SCHEMA_VERSION = 1

CLI_COMMANDS = (
    "aippocampus hooks prompt status --last --json",
    "aippocampus hooks lifecycle status --json",
    "aippocampus hooks action status --json",
    "aippocampus hooks claude-code status --json",
    "aippocampus agent background --json",
    'aippocampus agent aippo --task "AIppocampus host probe schema freshness" --json',
    "aippocampus warm status --json",
    "aippocampus dream status --json",
    "aippocampus update status --json",
)

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


def scan_cli_command(command: str, *, cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
        timeout=60,
    )
    try:
        payload = _load_json(proc.stdout)
    except Exception as exc:
        return {
            "surface": command,
            "kind": "cli",
            "ok": False,
            "exit_code": proc.returncode,
            "error": f"json_parse_failed:{type(exc).__name__}",
            "stderr_preview": proc.stderr.strip()[:240],
        }
    leaks = denied_field_paths(payload)
    safe_count = safe_action_count(payload)
    return {
        "surface": command,
        "kind": "cli",
        "ok": not leaks and safe_count <= MAX_SAFE_ACTIONS,
        "exit_code": proc.returncode,
        "denied_field_paths": leaks,
        "safe_action_count": safe_count,
    }


def scan_mcp_runtime_recovery() -> dict[str, Any]:
    from aippocampus_runtime.mcp.result_profile import render_profiled_result
    from aippocampus_runtime.mcp.runtime_recovery import (
        foreground_mcp_runtime_recovery_payload,
    )

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
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    leaks = denied_field_paths(structured)
    safe_count = safe_action_count(structured)
    return {
        "surface": "mcp_runtime_recovery:agent_recall",
        "kind": "mcp",
        "ok": isinstance(structured, Mapping) and not leaks and safe_count <= MAX_SAFE_ACTIONS,
        "has_structured_content": isinstance(structured, Mapping),
        "text_item_count": len(result.get("content") or []) if isinstance(result, dict) else 0,
        "denied_field_paths": leaks,
        "safe_action_count": safe_count,
    }


def _mcp_tool_structured_content_check(surface: str, result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    leaks = denied_field_paths(structured)
    safe_count = safe_action_count(structured)
    return {
        "surface": surface,
        "kind": "mcp",
        "ok": isinstance(structured, Mapping) and not leaks and safe_count <= MAX_SAFE_ACTIONS,
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

    return [
        _mcp_tool_structured_content_check(
            "mcp_tool:agent_aippo",
            tool_handlers.call_agent_aippo(
                {
                    "task": "AIppocampus host probe schema freshness",
                    "cwd": str(cwd),
                }
            ),
        ),
        _mcp_tool_structured_content_check(
            "mcp_tool:agent_background",
            tool_handlers.call_agent_background(
                {
                    "cue": "AIppocampus reviewed background findings smoke",
                    "limit": 1,
                    "cwd": str(cwd),
                }
            ),
        ),
    ]


def run_scan(*, cwd: Path, include_cli: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if include_cli:
        checks.extend(scan_cli_command(command, cwd=cwd) for command in CLI_COMMANDS)
    checks.append(scan_mcp_runtime_recovery())
    checks.extend(scan_mcp_key_tool_compact_cards(cwd=cwd))
    failures = [item for item in checks if not item.get("ok")]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not failures,
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
    args = parser.parse_args(argv)
    report = run_scan(cwd=PATHS.repo_root, include_cli=not args.no_cli)
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
