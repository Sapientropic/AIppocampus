#!/usr/bin/env python3
"""Read-only Claude Code MCP host probe for AIppocampus."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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
IMPORT_FAILURE_RE = re.compile(
    r"(?i)(ModuleNotFoundError|ImportError|cannot import|No module named)"
)
PATHY_ARG_RE = re.compile(r"(?i)(^[A-Za-z]:[\\/]|^/|^~[\\/]|[\\/].*\.(?:py|exe|cmd|bat|ps1)$)")
EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".exe", ".ps1", ".py"}


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


def split_config_args(text: str) -> list[str]:
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split()
    return [part.strip().strip('"').strip("'") for part in parts if part.strip()]


def parse_claude_mcp_get_config(text: str) -> dict[str, Any]:
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    in_environment = False

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("Command:"):
            command = stripped.split(":", 1)[1].strip()
            in_environment = False
            continue
        if stripped.startswith("Args:"):
            args = split_config_args(stripped.split(":", 1)[1].strip())
            in_environment = False
            continue
        if stripped == "Environment:":
            in_environment = True
            continue
        if in_environment:
            if not raw_line.startswith((" ", "\t", "-")):
                in_environment = False
                continue
            env_line = stripped.removeprefix("-").strip()
            if "=" in env_line:
                key, value = env_line.split("=", 1)
            elif ":" in env_line:
                key, value = env_line.split(":", 1)
            else:
                continue
            key = key.strip()
            if key:
                env[key] = value.strip()

    return {
        "command": command,
        "args": args,
        "environment": env,
        "has_config": command is not None,
    }


def command_is_path_like(value: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
        or value.startswith(("/", "~"))
        or Path(value).suffix.lower() in EXECUTABLE_SUFFIXES
    )


def argument_needs_existing_path(value: str) -> bool:
    suffix = Path(value).suffix.lower()
    return suffix in EXECUTABLE_SUFFIXES or bool(PATHY_ARG_RE.search(value))


def command_resolves(command: str) -> bool:
    if command_is_path_like(command):
        return Path(command).expanduser().is_file()
    return shutil.which(command) is not None


def redacted_config_shape(config: dict[str, Any]) -> dict[str, Any]:
    command = str(config.get("command") or "")
    args = [str(arg) for arg in config.get("args") or []]
    env = config.get("environment") if isinstance(config.get("environment"), dict) else {}
    return {
        "command": sanitize_host_output(command) if command else None,
        "args": [sanitize_host_output(arg) for arg in args],
        "args_count": len(args),
        "environment_key_count": len(env),
        "aippocampus_environment_key_count": sum(
            1
            for key in env
            if str(key).startswith("AIPPOCAMPUS_")
        ),
    }


def jsonrpc_memory_health_requests(cwd: str | None) -> list[dict[str, Any]]:
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "memory_health",
                "arguments": {"cwd": cwd} if cwd else {},
            },
        },
    ]


def parse_jsonrpc_lines(text: str) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, dict):
            responses.append(payload)
    return responses


def memory_health_tool_payload(response: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        return True, {}
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return True, {}
    first = content[0]
    if not isinstance(first, dict):
        return True, {}
    try:
        payload = json.loads(str(first.get("text") or "{}"))
    except json.JSONDecodeError:
        return True, {}
    return False, payload if isinstance(payload, dict) else {}


def persistent_config_repair_hint(status: str) -> str:
    if status == "missing_config":
        return "Add the local server again with `claude mcp add aippocampus -- aippocampus mcp`."
    if status == "bad_command_path":
        return (
            "Remove the stale local server and add a current command again; for example "
            "`claude mcp remove \"aippocampus\" -s local` then "
            "`claude mcp add aippocampus -- aippocampus mcp`."
        )
    if status == "runtime_import_failure":
        return "Run the configured command in the same Python environment or reinstall the package entrypoint."
    if status == "server_start_failure":
        return "Run the configured command manually and inspect startup stderr before changing Claude settings."
    if status == "tool_schema_failure":
        return "Ensure the configured server is an AIppocampus MCP server exposing `memory_health`."
    if status == "tool_call_failure":
        return "The server started but `memory_health` failed; run `aippocampus health` for local artifact repair."
    return "No repair needed for this diagnostic status."


def diagnostic_result(
    status: str,
    *,
    ok: bool = False,
    config: dict[str, Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "status": status,
        "taxonomy": [
            "missing_config",
            "bad_command_path",
            "runtime_import_failure",
            "server_start_failure",
            "tool_schema_failure",
            "tool_call_failure",
            "healthy",
        ],
        "repair_hint": persistent_config_repair_hint(status),
        "privacy": (
            "Persistent-config diagnostics redact local paths, settings paths, source refs, "
            "and secret-like values before public output."
        ),
    }
    if config is not None:
        payload["config"] = redacted_config_shape(config)
    if detail:
        payload.update(detail)
    return payload


def run_persistent_config_diagnostic(
    *,
    get_text: str,
    cwd: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Probe the user's persistent Claude MCP config without mutating it.

    This intentionally does not use the temporary strict MCP config path. It
    parses `claude mcp get`, validates the configured command/args, then runs a
    minimal stdio JSON-RPC client against that configured server. The result is
    diagnostic evidence for the persistent config only; it must not be merged
    with the strict-config live Claude proof.
    """

    config = parse_claude_mcp_get_config(get_text)
    command = config.get("command")
    if not command:
        return diagnostic_result("missing_config", config=config)

    command_text = str(command)
    if not command_resolves(command_text):
        return diagnostic_result(
            "bad_command_path",
            config=config,
            detail={"command_resolved": False, "path_check": "configured_command_missing"},
        )

    args = [str(arg) for arg in config.get("args") or []]
    missing_args = [
        sanitize_host_output(arg)
        for arg in args
        if argument_needs_existing_path(arg) and not Path(arg).expanduser().exists()
    ]
    if missing_args:
        return diagnostic_result(
            "bad_command_path",
            config=config,
            detail={
                "command_resolved": True,
                "path_check": "configured_arg_path_missing",
                "missing_arg_count": len(missing_args),
                "missing_arg_examples": missing_args[:3],
            },
        )

    requests = jsonrpc_memory_health_requests(cwd)
    stdin = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"
    env = os.environ.copy()
    parsed_env = config.get("environment") if isinstance(config.get("environment"), dict) else {}
    env.update({str(key): str(value) for key, value in parsed_env.items()})
    try:
        proc = subprocess.run(
            [command_text, *args],
            input=stdin,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=max(1, int(timeout)),
            cwd=cwd or str(REPO_ROOT),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return diagnostic_result(
            "server_start_failure",
            config=config,
            detail={
                "command_resolved": True,
                "returncode": None,
                "stdout_preview": sanitize_host_output(exc.stdout or "")[:500],
                "stderr_preview": sanitize_host_output(exc.stderr or "")[:500],
                "failure": "timeout",
            },
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = f"{stdout}\n{stderr}"
    if proc.returncode != 0:
        status = "runtime_import_failure" if IMPORT_FAILURE_RE.search(combined) else "server_start_failure"
        return diagnostic_result(
            status,
            config=config,
            detail={
                "command_resolved": True,
                "returncode": proc.returncode,
                "stdout_preview": sanitize_host_output(stdout)[:500],
                "stderr_preview": sanitize_host_output(stderr)[:500],
            },
        )

    responses = parse_jsonrpc_lines(stdout)
    response_by_id = {item.get("id"): item for item in responses}
    response_ids = [item.get("id") for item in responses]
    if not all(request_id in response_by_id for request_id in (1, 2, 3)):
        return diagnostic_result(
            "server_start_failure",
            config=config,
            detail={
                "command_resolved": True,
                "returncode": proc.returncode,
                "json_parse": bool(responses),
                "response_ids": response_ids,
                "stdout_preview": sanitize_host_output(stdout)[:500],
                "stderr_preview": sanitize_host_output(stderr)[:500],
            },
        )

    tools_result = response_by_id[2].get("result")
    tool_names = []
    if isinstance(tools_result, dict) and isinstance(tools_result.get("tools"), list):
        tool_names = [
            str(tool.get("name") or "")
            for tool in tools_result["tools"]
            if isinstance(tool, dict)
        ]
    if "memory_health" not in tool_names:
        return diagnostic_result(
            "tool_schema_failure",
            config=config,
            detail={
                "command_resolved": True,
                "returncode": proc.returncode,
                "tool_count": len(tool_names),
                "memory_health_listed": False,
            },
        )

    tool_is_error, tool_payload = memory_health_tool_payload(response_by_id[3])
    if tool_is_error or not isinstance(tool_payload.get("recommended_actions"), list):
        return diagnostic_result(
            "tool_call_failure",
            config=config,
            detail={
                "command_resolved": True,
                "returncode": proc.returncode,
                "tool_count": len(tool_names),
                "memory_health_listed": True,
                "tool_is_error": tool_is_error,
                "tool_payload_keys": sorted(tool_payload.keys())[:20],
            },
        )

    return diagnostic_result(
        "healthy",
        ok=True,
        config=config,
        detail={
            "command_resolved": True,
            "returncode": proc.returncode,
            "tool_count": len(tool_names),
            "memory_health_listed": True,
            "tool_is_error": False,
            "tool_payload_keys": sorted(tool_payload.keys())[:20],
        },
    )


def run_claude_mcp_probe(
    server_name: str = "aippocampus",
    *,
    call_tool: bool = False,
    persistent_diagnostic: bool = False,
    cwd: str | None = None,
    max_budget_usd: float = 0.25,
    tool_timeout: int = 120,
    diagnostic_timeout: int = 30,
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
    list_raw_text = (list_proc.stdout or list_proc.stderr or "").strip()
    get_raw_text = (get_proc.stdout or get_proc.stderr or "").strip()
    list_text = sanitize_host_output(list_raw_text)
    get_text = sanitize_host_output(get_raw_text)
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
    if persistent_diagnostic:
        persistent_result = run_persistent_config_diagnostic(
            get_text=get_raw_text,
            cwd=cwd,
            timeout=diagnostic_timeout,
        )
        result["persistent_config_diagnostic"] = persistent_result
        result["persistent_config_status"] = persistent_result["status"]
        result["ok"] = bool(persistent_result.get("ok"))
        result["status"] = f"persistent_config_{persistent_result['status']}"
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
        r"(?<![A-Za-z0-9:])/(?:Users|home|private/tmp|tmp|private/var/folders|var/folders)/[^\s]+",
        "<local-path-redacted>",
        text,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-name", default="aippocampus")
    parser.add_argument("--call-tool", action="store_true", help="Also run a minimal live Claude tool-call smoke.")
    parser.add_argument(
        "--persistent-diagnostic",
        action="store_true",
        help="Also run a read-only diagnostic against the configured persistent Claude MCP server.",
    )
    parser.add_argument("--cwd", help="Workspace cwd to pass to memory_health during --call-tool.")
    parser.add_argument("--max-budget-usd", type=float, default=0.25)
    parser.add_argument("--tool-timeout", type=int, default=120)
    parser.add_argument("--diagnostic-timeout", type=int, default=30)
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
        persistent_diagnostic=args.persistent_diagnostic,
        cwd=args.cwd,
        max_budget_usd=args.max_budget_usd,
        tool_timeout=args.tool_timeout,
        diagnostic_timeout=args.diagnostic_timeout,
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
