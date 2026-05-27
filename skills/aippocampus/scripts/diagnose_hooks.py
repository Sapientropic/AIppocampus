#!/usr/bin/env python3
"""Diagnose Codex hook installation, latency, and timeout risk.

This script intentionally emulates the Codex hook host by running configured
hook command strings with synthetic hook JSON on stdin. It gives maintainers a
quick local answer to "which hook is slow or broken?" without reading raw
conversation logs or prompt text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from aippocampuslib import codex_home, now_utc


DEFAULT_EVENTS = ("UserPromptSubmit", "Stop")
DEFAULT_DIAGNOSTIC_PROMPT = "Can you recover the last memory-system discussion and relevant context?"
SCRIPT_PATH_RE = re.compile(r'"([^"]+\.py)"|(?:^|\s)([^\s"]+\.py)(?=\s|$)', re.IGNORECASE)


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
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
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


def hook_input_for_event(event: str, *, cwd: Path, prompt: str, last_assistant_message: str) -> dict[str, Any]:
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


def run_command(command: str, *, stdin_payload: dict[str, Any], timeout: float) -> dict[str, Any]:
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
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "timed_out": False,
            "returncode": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "timed_out": True,
            "returncode": None,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }


def diagnose(
    *,
    hooks_json: Path,
    cwd: Path,
    events: set[str],
    run: bool,
    prompt: str,
    last_assistant_message: str,
    max_seconds: float,
    padding_seconds: float,
    warn_ratio: float,
) -> dict[str, Any]:
    data = load_hooks(hooks_json)
    handlers = configured_handlers(data, events)
    rows: list[dict[str, Any]] = []
    summary = {"total": 0, "ran": 0, "errors": 0, "timeouts": 0, "would_timeout": 0, "slow": 0, "missing_scripts": 0}

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
            summary["ran"] += 1
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
            )
            result.update(run_result)
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

    return {
        "kind": "aippocampus_hook_diagnostic",
        "created_at": now_utc(),
        "hooks_json": str(hooks_json),
        "cwd": str(cwd),
        "events": sorted(events),
        "summary": summary,
        "handlers": rows,
    }


def print_text(result: dict[str, Any]) -> None:
    summary = result.get("summary") or {}
    print(
        "hooks diagnostic: "
        f"{summary.get('ran', 0)}/{summary.get('total', 0)} ran, "
        f"errors={summary.get('errors', 0)}, "
        f"timeouts={summary.get('timeouts', 0)}, "
        f"would_timeout={summary.get('would_timeout', 0)}, "
        f"slow={summary.get('slow', 0)}"
    )
    print(f"hooks: {result.get('hooks_json')}")
    for item in result.get("handlers") or []:
        label = f"{item.get('event')}[{item.get('group_index')}:{item.get('handler_index')}]"
        risk = item.get("risk")
        timeout = item.get("timeout")
        elapsed = item.get("elapsed_ms")
        if elapsed is None:
            print(f"- {label}: {risk}, timeout={timeout:g}s")
        else:
            print(f"- {label}: {risk}, elapsed={elapsed:g}ms, timeout={timeout:g}s")
        missing = [script["path"] for script in item.get("scripts") or [] if not script.get("exists")]
        if missing:
            print("  missing script: " + "; ".join(missing[:3]))
        if item.get("stderr_tail"):
            print("  stderr: " + str(item.get("stderr_tail")).strip().splitlines()[-1][:300])


def parse_events(value: str) -> set[str]:
    events = {item.strip() for item in value.split(",") if item.strip()}
    return events or set(DEFAULT_EVENTS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose configured Codex hooks.")
    parser.add_argument("--hooks-json", default=str(codex_home() / "hooks.json"))
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--events", default=",".join(DEFAULT_EVENTS))
    parser.add_argument("--prompt", default=DEFAULT_DIAGNOSTIC_PROMPT)
    parser.add_argument("--last-assistant-message", default="diagnostic run")
    parser.add_argument("--no-run", action="store_true", help="Only inspect hook config; do not execute commands.")
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--padding-seconds", type=float, default=2.0)
    parser.add_argument("--warn-ratio", type=float, default=0.8)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = diagnose(
        hooks_json=Path(args.hooks_json).resolve(),
        cwd=Path(args.cwd).resolve(),
        events=parse_events(args.events),
        run=not args.no_run,
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
    return 1 if any(int(summary.get(key) or 0) for key in ("errors", "timeouts", "would_timeout", "missing_scripts")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
