#!/usr/bin/env python3
"""Read-only Claude Code MCP host probe for AIppocampus."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
DEFAULT_SERVER_ARGS = [
    "-c",
    (
        "import sys; "
        f"sys.path.insert(0, {str(SKILL_SCRIPTS)!r}); "
        "from aippocampus_runtime.mcp.server import main; "
        "raise SystemExit(main())"
    ),
]
PROJECT_SKILL = REPO_ROOT / ".claude" / "skills" / "aippocampus" / "SKILL.md"
PROJECT_SKILL_MARKERS = (
    "source-backed continuity",
    "aippocampus mcp list-tools",
    "aippocampus onboard --status",
    "aippocampus onboard --provider claude-code --dry-run",
    "Do not claim model-native memory",
)
HOST_FAILURE_RE = re.compile(
    r"(?i)(status:\s*[✗x]\s*failed to connect|failed to connect|not found|no mcp server)"
)


def host_config_status(
    *, list_returncode: int, get_returncode: int, get_text: str
) -> dict[str, Any]:
    if list_returncode != 0 or get_returncode != 0:
        return {
            "ok": False,
            "status": "command_returncode_failed",
            "reason": "claude_mcp_command_failed",
        }
    if HOST_FAILURE_RE.search(get_text):
        return {
            "ok": False,
            "status": "host_reported_failed_connection",
            "reason": "claude_mcp_get_reported_failed_connection",
        }
    return {
        "ok": True,
        "status": "connected",
        "reason": "claude_mcp_commands_succeeded_without_failure_marker",
    }


def run_claude_mcp_probe(
    server_name: str = "aippocampus",
    *,
    call_tool: bool = False,
    cwd: str | None = None,
    max_budget_usd: float = 0.25,
    tool_timeout: int = 120,
    server_script: Path | None = None,
    server_command: str | None = None,
    server_args: list[str] | None = None,
) -> dict[str, Any]:
    claude = shutil.which("claude")
    if not claude:
        return {
            "ok": False,
            "status": "blocked_missing_claude_cli",
            "blocker": "The `claude` CLI is not available on PATH.",
            "commands": ["claude mcp list", f"claude mcp get {server_name}"],
        }

    list_proc = subprocess.run(
        [claude, "mcp", "list"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    get_proc = subprocess.run(
        [claude, "mcp", "get", server_name],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    list_text = sanitize_host_output((list_proc.stdout or list_proc.stderr or "").strip())
    get_text = sanitize_host_output((get_proc.stdout or get_proc.stderr or "").strip())
    config_status = host_config_status(
        list_returncode=list_proc.returncode,
        get_returncode=get_proc.returncode,
        get_text=get_text,
    )
    host_config_ok = bool(config_status["ok"])
    result: dict[str, Any] = {
        "ok": host_config_ok,
        "status": "reachable" if host_config_ok else "blocked_host_config",
        "server_name": server_name,
        "host_version": read_claude_version(claude),
        "commands": ["claude mcp list", f"claude mcp get {server_name}"],
        "list_returncode": list_proc.returncode,
        "get_returncode": get_proc.returncode,
        "host_config_ok": host_config_ok,
        "host_config_status": config_status,
        "list_summary": list_text[:500],
        "get_summary": get_text[:500],
        "project_skill": inspect_project_skill(),
        "privacy": "This smoke reports command status only and does not print transcript contents.",
    }
    if call_tool:
        tool_call = run_claude_mcp_tool_call(
            claude=claude,
            server_name=server_name,
            cwd=cwd,
            max_budget_usd=max_budget_usd,
            timeout=tool_timeout,
            server_script=server_script,
            server_command=server_command,
            server_args=server_args,
        )
        result["tool_call"] = tool_call
        tool_ok = bool(tool_call.get("ok"))
        result["ok"] = tool_ok
        if tool_ok:
            result["status"] = (
                "tool_call_reachable"
                if host_config_ok
                else "tool_call_reachable_with_persistent_config_blocker"
            )
        else:
            result["status"] = (
                "blocked_tool_call" if host_config_ok else "blocked_host_config_and_tool_call"
            )
    return result


def strict_mcp_config(
    server_name: str,
    *,
    server_script: Path,
    server_command: str | None = None,
    server_args: list[str] | None = None,
) -> dict[str, Any]:
    command = server_command or sys.executable
    args = (
        list(server_args)
        if server_args is not None
        else [str(server_script)]
        if server_script is not None
        else list(DEFAULT_SERVER_ARGS)
    )
    return {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": args,
            }
        }
    }


def read_claude_version(claude: str) -> str | None:
    proc = subprocess.run(
        [claude, "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=10,
    )
    text = sanitize_host_output((proc.stdout or proc.stderr or "").strip())
    return text[:120] if proc.returncode == 0 and text else None


def inspect_project_skill(path: Path = PROJECT_SKILL) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "status": "missing",
            "path": ".claude/skills/aippocampus/SKILL.md",
        }
    text = path.read_text(encoding="utf-8")
    markers = {marker: marker in text for marker in PROJECT_SKILL_MARKERS}
    return {
        "ok": all(markers.values()),
        "status": "present" if all(markers.values()) else "incomplete",
        "path": ".claude/skills/aippocampus/SKILL.md",
        "markers": markers,
        "privacy": "Adapter inspection checks only repository instructions, not Claude transcript contents.",
    }


def run_claude_mcp_tool_call(
    *,
    claude: str,
    server_name: str,
    cwd: str | None,
    max_budget_usd: float,
    timeout: int,
    server_script: Path | None,
    server_command: str | None = None,
    server_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run one minimal Claude Code session that must call the MCP tool.

    This is intentionally opt-in because it can spend a small live-model budget.
    The strict MCP config keeps the probe scoped to AIppocampus instead of
    inheriting unrelated user MCP servers that may need auth or carry secrets.
    """

    tool_name = f"mcp__{server_name}__memory_health"
    with tempfile.TemporaryDirectory(prefix="aippocampus-claude-mcp-") as tmp:
        config_path = Path(tmp) / "mcp.json"
        config_path.write_text(
            json.dumps(
                strict_mcp_config(
                    server_name,
                    server_script=server_script,
                    server_command=server_command,
                    server_args=server_args,
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                claude,
                "-p",
                "--bare",
                "--strict-mcp-config",
                "--mcp-config",
                str(config_path),
                "--output-format",
                "stream-json",
                "--verbose",
                "--max-budget-usd",
                str(max_budget_usd),
                "--allowedTools",
                tool_name,
                "--permission-mode",
                "bypassPermissions",
                "--system-prompt",
                "You are a minimal MCP smoke runner. Use only the requested MCP tool and return compact JSON.",
                (
                    f"Call the {server_name} memory_health MCP tool"
                    + (f" for cwd {cwd}" if cwd else "")
                    + '. Return only {"tool_called":true,"status":"..."} and do not include private paths.'
                ),
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=max(1, int(timeout)),
        )
    events = parse_claude_stream_events(proc.stdout or "")
    tool_call = find_tool_call(events, tool_name)
    stderr_preview = sanitize_host_output(proc.stderr or "")[:400]
    return {
        "ok": proc.returncode == 0 and tool_call["tool_used"] and tool_call["tool_result_observed"],
        "status": (
            "called_memory_health"
            if proc.returncode == 0 and tool_call["tool_used"] and tool_call["tool_result_observed"]
            else "tool_call_failed"
        ),
        "command": "claude -p --bare --strict-mcp-config --mcp-config <temp> --output-format stream-json --allowedTools <aippocampus-memory-health>",
        "returncode": proc.returncode,
        "tool_name": tool_name,
        "tool_called": tool_call["tool_used"],
        "tool_result_observed": tool_call["tool_result_observed"],
        "output_json_parse": bool(events),
        "event_count": len(events),
        "summary": summarize_stream_events(events, tool_name),
        "stderr_preview": stderr_preview,
        "privacy": "The strict-config tool-call smoke redacts local paths and does not print transcript contents.",
    }


def parse_claude_json_output(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_claude_stream_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def find_tool_call(events: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    tool_use_ids: set[str] = set()
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and item.get("name") == tool_name:
                tool_id = item.get("id")
                if isinstance(tool_id, str):
                    tool_use_ids.add(tool_id)
    tool_result_observed = False
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if (
                isinstance(item, dict)
                and item.get("type") == "tool_result"
                and item.get("tool_use_id") in tool_use_ids
            ):
                tool_result_observed = True
    return {
        "tool_used": bool(tool_use_ids),
        "tool_result_observed": tool_result_observed,
    }


def summarize_stream_events(events: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type") or "unknown")
        type_counts[event_type] = type_counts.get(event_type, 0) + 1
    tool_call = find_tool_call(events, tool_name)
    return {
        "event_count": len(events),
        "type_counts": type_counts,
        "tool_name": tool_name,
        "tool_called": tool_call["tool_used"],
        "tool_result_observed": tool_call["tool_result_observed"],
    }


def output_claims_tool_called(text: str) -> bool:
    return bool(re.search(r'"?tool_called"?\s*[:=]\s*true', text, flags=re.IGNORECASE))


def sanitize_host_output(text: str) -> str:
    text = re.sub(
        r"([?&][A-Za-z0-9_.-]*(?:key|token|secret)[A-Za-z0-9_.-]*=)[^&\s]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", text)
    text = re.sub(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s]+", "<local-path-redacted>", text)
    text = re.sub(
        r"(?<![A-Za-z0-9:])/(?:Users|home|private/tmp|tmp)/[^\s]+",
        "<local-path-redacted>",
        text,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-name", default="aippocampus")
    parser.add_argument("--call-tool", action="store_true", help="Also run a minimal live Claude tool-call smoke.")
    parser.add_argument("--cwd", help="Workspace cwd to pass to memory_health during --call-tool.")
    parser.add_argument("--max-budget-usd", type=float, default=0.25)
    parser.add_argument("--tool-timeout", type=int, default=120)
    parser.add_argument("--server-script", type=Path)
    parser.add_argument(
        "--server-command",
        help="Override the strict MCP server command, e.g. a standalone aippocampus.exe.",
    )
    parser.add_argument(
        "--server-arg",
        action="append",
        default=None,
        help="Argument for --server-command. Repeat for multiple args; use --server-arg mcp for the standalone binary.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_claude_mcp_probe(
        server_name=args.server_name,
        call_tool=args.call_tool,
        cwd=args.cwd,
        max_budget_usd=args.max_budget_usd,
        tool_timeout=args.tool_timeout,
        server_script=args.server_script,
        server_command=args.server_command,
        server_args=args.server_arg,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Claude Code MCP host: {result['status']}")
        if result.get("blocker"):
            print(f"blocker: {result['blocker']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
