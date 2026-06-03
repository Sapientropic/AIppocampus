#!/usr/bin/env python3
"""Diagnose Codex hook installation, latency, and timeout risk.

This module intentionally emulates the Codex hook host by running configured
hook command strings with synthetic hook JSON on stdin. It gives maintainers a
quick local answer to "which hook is slow or broken?" without reading raw
conversation logs or prompt text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home, now_utc
from aippocampus_runtime.hooks.host_boundary import (
    add_host_integration,
    host_integration_text_lines,
)

DEFAULT_EVENTS = ("UserPromptSubmit", "Stop")
DEFAULT_DIAGNOSTIC_PROMPT = (
    "Can you recover the last memory-system discussion and relevant context?"
)
SCRIPT_PATH_RE = re.compile(r'"([^"]+\.py)"|(?:^|\s)([^\s"]+\.py)(?=\s|$)', re.IGNORECASE)
BLOCKED_UNTRUSTED_SHELL_COMMAND = "blocked_untrusted_shell_command"
SAFE_HOOK_SCRIPT_NAMES = {
    "aippocampus_prompt_hook.py",
    "aippocampus_lifecycle_hook.py",
    # Former names are kept as diagnosable AIppocampus-owned hook shims so old
    # installs can be inspected before reinstall upgrades the command string.
    "ambient_recall_hook.py",
    "memory_maintenance_hook.py",
}
SAFE_HOOK_MODULES = {
    "aippocampus_runtime.hooks.prompt",
    "aippocampus_runtime.hooks.lifecycle",
}
PYTHON_LAUNCHER_NAMES = {"python", "python.exe", "python3", "python3.exe", "py", "py.exe"}
SHELL_CONTROL_TOKENS = {"&", "&&", "|", "||", ";", ">", ">>", "<", "2>", "2>>"}
SHELL_CONTROL_MARKERS = (";", "|", ">", "<", "`", "$(", "${")


def load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"hooks": {}}
    return data if isinstance(data, dict) else {"hooks": {}}


def configured_handlers(data: dict[str, Any], events: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_hooks = data.get("hooks")
    hooks: dict[str, Any] = raw_hooks if isinstance(raw_hooks, dict) else {}
    for event in sorted(events):
        groups = hooks.get(event) or []
        if not isinstance(groups, list):
            continue
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks") or []
            if not isinstance(handlers, list):
                continue
            for handler_index, handler in enumerate(handlers):
                if isinstance(handler, dict):
                    rows.append(
                        {
                            "event": event,
                            "group_index": group_index,
                            "handler_index": handler_index,
                            "matcher": group.get("matcher"),
                            "type": handler.get("type"),
                            "command": str(handler.get("command") or ""),
                            "timeout": float(handler.get("timeout") or 0),
                        }
                    )
    return rows


def script_paths_from_command(command: str) -> list[Path]:
    paths: list[Path] = []
    for match in SCRIPT_PATH_RE.finditer(command):
        text = match.group(1) or match.group(2) or ""
        if text:
            paths.append(Path(text))
    return paths


def _token_basename(value: str) -> str:
    normalized = value.strip().strip('"').strip("'")
    if "\\" in normalized or re.match(r"^[A-Za-z]:", normalized):
        return Path(normalized.replace("\\", "/")).name
    return Path(normalized).name


def _is_python_launcher(value: str) -> bool:
    name = _token_basename(value).lower()
    return name in PYTHON_LAUNCHER_NAMES or bool(re.match(r"python3(?:\.\d+)?(?:\.exe)?$", name))


def _is_safe_hook_script(value: str) -> bool:
    return _token_basename(value) in SAFE_HOOK_SCRIPT_NAMES


def _contains_shell_control(tokens: list[str]) -> bool:
    for token in tokens:
        if token in SHELL_CONTROL_TOKENS:
            return True
        if any(marker in token for marker in SHELL_CONTROL_MARKERS):
            return True
    return False


def _shell_like_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def safe_argv_from_command(command: str) -> tuple[list[str] | None, str | None]:
    """Parse an installed AIppocampus hook command into argv or a block reason.

    Codex stores hook commands as shell strings, and Windows installs need a
    leading PowerShell call operator. Diagnose must understand that one narrow
    host syntax, then switch back to argv execution. Do not broaden this parser
    into a general shell interpreter; unknown syntax should be blocked or run
    only through the explicit operator-chosen ``--allow-shell`` path.
    """
    try:
        tokens = _shell_like_tokens(command)
    except ValueError:
        return None, BLOCKED_UNTRUSTED_SHELL_COMMAND
    if tokens and tokens[0] == "&":
        tokens = tokens[1:]
    if not tokens or _contains_shell_control(tokens):
        return None, BLOCKED_UNTRUSTED_SHELL_COMMAND

    if _is_safe_hook_script(tokens[0]):
        return tokens, None

    if _is_python_launcher(tokens[0]):
        if len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] in SAFE_HOOK_MODULES:
            return tokens, None
        script_index = 1
        if _token_basename(tokens[0]).lower() in {"py", "py.exe"} and len(tokens) > 2:
            if re.match(r"-\d(?:\.\d+)?$", tokens[1]):
                script_index = 2
        if len(tokens) > script_index and _is_safe_hook_script(tokens[script_index]):
            return tokens, None

    return None, BLOCKED_UNTRUSTED_SHELL_COMMAND


def hook_input_for_event(
    event: str, *, cwd: Path, prompt: str, last_assistant_message: str
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "hook_event_name": event,
        "cwd": str(cwd),
        "session_id": "aippocampus-hook-diagnostic",
        "turn_id": "aippocampus-hook-diagnostic",
    }
    if event == "UserPromptSubmit":
        base["prompt"] = prompt
    if event == "Stop":
        base["stop_hook_active"] = False
        base["last_assistant_message"] = last_assistant_message
    return base


def _process_result(proc: subprocess.CompletedProcess[str], *, started: float) -> dict[str, Any]:
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "timed_out": False,
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def _timeout_result(exc: subprocess.TimeoutExpired, *, started: float) -> dict[str, Any]:
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    stdout = (
        exc.stdout.decode("utf-8", errors="replace")
        if isinstance(exc.stdout, bytes)
        else (exc.stdout or "")
    )
    stderr = (
        exc.stderr.decode("utf-8", errors="replace")
        if isinstance(exc.stderr, bytes)
        else (exc.stderr or "")
    )
    return {
        "timed_out": True,
        "returncode": None,
        "elapsed_ms": elapsed_ms,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def run_argv_command(argv: list[str], *, stdin_payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    stdin_text = json.dumps(stdin_payload, ensure_ascii=False)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return _process_result(proc, started=started)
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc, started=started)


def run_shell_command(command: str, *, stdin_payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    stdin_text = json.dumps(stdin_payload, ensure_ascii=False)
    started = time.perf_counter()
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                input=stdin_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        else:
            proc = subprocess.run(
                command,
                input=stdin_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                shell=True,
                check=False,
                timeout=timeout,
            )
        return _process_result(proc, started=started)
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc, started=started)


def blocked_command_result(reason_code: str) -> dict[str, Any]:
    return {
        "blocked": True,
        "reason_code": reason_code,
        "risk": reason_code,
        "execution_mode": "blocked",
        "timed_out": False,
        "returncode": None,
        "stdout_tail": "",
        "stderr_tail": (
            "diagnose_hooks refused to execute this command without --allow-shell"
        ),
    }


def run_command(
    command: str,
    *,
    stdin_payload: dict[str, Any],
    timeout: float,
    allow_shell: bool = False,
) -> dict[str, Any]:
    if allow_shell:
        result = run_shell_command(command, stdin_payload=stdin_payload, timeout=timeout)
        result["execution_mode"] = "unsafe_shell"
        result["unsafe_operator_chosen"] = True
        return result

    argv, reason_code = safe_argv_from_command(command)
    if argv is None:
        return blocked_command_result(reason_code or BLOCKED_UNTRUSTED_SHELL_COMMAND)
    result = run_argv_command(argv, stdin_payload=stdin_payload, timeout=timeout)
    result["execution_mode"] = "safe_argv"
    result["argv"] = argv
    result["unsafe_operator_chosen"] = False
    return result


def diagnose(
    *,
    hooks_json: Path,
    cwd: Path,
    events: set[str],
    run: bool,
    allow_shell: bool = False,
    prompt: str,
    last_assistant_message: str,
    max_seconds: float,
    padding_seconds: float,
    warn_ratio: float,
) -> dict[str, Any]:
    data = load_hooks(hooks_json)
    handlers = configured_handlers(data, events)
    rows: list[dict[str, Any]] = []
    summary = {
        "total": 0,
        "ran": 0,
        "errors": 0,
        "timeouts": 0,
        "would_timeout": 0,
        "slow": 0,
        "missing_scripts": 0,
        "blocked": 0,
    }

    for row in handlers:
        summary["total"] += 1
        command = str(row.get("command") or "")
        timeout = float(row.get("timeout") or 0)
        scripts = script_paths_from_command(command)
        script_checks = [{"path": str(path), "exists": path.exists()} for path in scripts]
        missing_scripts = [item for item in script_checks if not item["exists"]]
        if missing_scripts:
            summary["missing_scripts"] += len(missing_scripts)
        result: dict[str, Any] = {
            **row,
            "scripts": script_checks,
            "ran": False,
            "risk": "not_run",
        }
        if run and command:
            diagnostic_timeout = max_seconds
            if timeout > 0:
                diagnostic_timeout = min(max_seconds, timeout + padding_seconds)
            run_result = run_command(
                command,
                stdin_payload=hook_input_for_event(
                    str(row.get("event") or ""),
                    cwd=cwd,
                    prompt=prompt,
                    last_assistant_message=last_assistant_message,
                ),
                timeout=diagnostic_timeout,
                allow_shell=allow_shell,
            )
            result.update(run_result)
            if run_result.get("blocked"):
                summary["blocked"] += 1
                rows.append(result)
                continue
            summary["ran"] += 1
            result["ran"] = True
            elapsed_ms = float(run_result.get("elapsed_ms") or 0.0)
            would_timeout = bool(timeout > 0 and elapsed_ms > timeout * 1000.0)
            slow = bool(timeout > 0 and elapsed_ms > timeout * warn_ratio * 1000.0)
            result["would_timeout"] = would_timeout
            if run_result.get("timed_out"):
                result["risk"] = "diagnostic_timeout"
                summary["timeouts"] += 1
            elif run_result.get("returncode") not in {0, None}:
                result["risk"] = "error"
                summary["errors"] += 1
            elif would_timeout:
                result["risk"] = "would_timeout"
                summary["would_timeout"] += 1
            elif slow:
                result["risk"] = "slow"
                summary["slow"] += 1
            else:
                result["risk"] = "ok"
        rows.append(result)

    return add_host_integration(
        {
            "kind": "aippocampus_hook_diagnostic",
            "created_at": now_utc(),
            "hooks_json": str(hooks_json),
            "cwd": str(cwd),
            "events": sorted(events),
            "summary": summary,
            "handlers": rows,
        }
    )


def print_text(result: dict[str, Any]) -> None:
    summary = result.get("summary") or {}
    print(
        "hooks diagnostic: "
        f"{summary.get('ran', 0)}/{summary.get('total', 0)} ran, "
        f"errors={summary.get('errors', 0)}, "
        f"timeouts={summary.get('timeouts', 0)}, "
        f"would_timeout={summary.get('would_timeout', 0)}, "
        f"slow={summary.get('slow', 0)}, "
        f"blocked={summary.get('blocked', 0)}"
    )
    print(f"hooks: {result.get('hooks_json')}")
    for line in host_integration_text_lines():
        print(line)
    for item in result.get("handlers") or []:
        label = f"{item.get('event')}[{item.get('group_index')}:{item.get('handler_index')}]"
        risk = item.get("risk")
        timeout = item.get("timeout")
        elapsed = item.get("elapsed_ms")
        if elapsed is None:
            print(f"- {label}: {risk}, timeout={timeout:g}s")
        else:
            print(f"- {label}: {risk}, elapsed={elapsed:g}ms, timeout={timeout:g}s")
        missing = [
            script["path"] for script in item.get("scripts") or [] if not script.get("exists")
        ]
        if missing:
            print("  missing script: " + "; ".join(missing[:3]))
        if item.get("reason_code"):
            print(f"  reason: {item.get('reason_code')}")
        if item.get("execution_mode") == "unsafe_shell":
            print("  execution: unsafe raw shell reproduction requested by operator")
        if item.get("stderr_tail"):
            print("  stderr: " + str(item.get("stderr_tail")).strip().splitlines()[-1][:300])


def parse_events(value: str) -> set[str]:
    events = {item.strip() for item in value.split(",") if item.strip()}
    return events or set(DEFAULT_EVENTS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose configured Codex hooks.")
    parser.add_argument("--hooks-json", default=str(codex_home() / "hooks.json"))
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--events", default=",".join(DEFAULT_EVENTS))
    parser.add_argument("--prompt", default=DEFAULT_DIAGNOSTIC_PROMPT)
    parser.add_argument("--last-assistant-message", default="diagnostic run")
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--run",
        dest="run",
        action="store_true",
        help=(
            "Safely execute known AIppocampus hook commands with shell=False "
            "(default; unknown shell commands are blocked)."
        ),
    )
    run_group.add_argument(
        "--no-run",
        dest="run",
        action="store_false",
        help="Inspect hook config only; do not execute commands.",
    )
    parser.set_defaults(run=True)
    parser.add_argument(
        "--allow-shell",
        action="store_true",
        help=(
            "Unsafe raw shell reproduction for maintainers; executes configured "
            "commands through the host shell and labels results as operator-chosen."
        ),
    )
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--padding-seconds", type=float, default=2.0)
    parser.add_argument("--warn-ratio", type=float, default=0.8)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    result = diagnose(
        hooks_json=Path(args.hooks_json).resolve(),
        cwd=Path(args.cwd).resolve(),
        events=parse_events(args.events),
        run=bool(args.run),
        allow_shell=bool(args.allow_shell),
        prompt=args.prompt,
        last_assistant_message=args.last_assistant_message,
        max_seconds=args.max_seconds,
        padding_seconds=args.padding_seconds,
        warn_ratio=args.warn_ratio,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    summary = result.get("summary") or {}
    return (
        1
        if any(
            int(summary.get(key) or 0)
            for key in ("errors", "timeouts", "would_timeout", "missing_scripts")
        )
        or int(summary.get("blocked") or 0)
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
