#!/usr/bin/env python3
"""Codex lifecycle hook for deterministic thread-memory maintenance.

This is the "reflex" layer for aippocampus. It moves fixed upkeep
steps out of SKILL.md reminders while keeping heavy or judgment-heavy work out
of the foreground hook path. Prompt-time recall stays in
aippocampus_runtime.hooks.prompt; this file only reacts to turn/session/compaction
lifecycle events. Slow subconscious consolidation is delegated to
aippocampus_runtime.subconscious.scheduler, which can start a detached worker after cooldown and
lock checks instead of blocking the hook.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.hooks import lifecycle_preemptive as preemptive
from aippocampus_runtime.ops import log_retention
from aippocampus_runtime.source import emergency_snapshot

SCRIPT_DIR = Path(__file__).resolve().parents[2]
STATE_SCHEMA_VERSION = 1
STOP_COOLDOWN_SECONDS = 15 * 60
SESSION_COOLDOWN_SECONDS = 60 * 60
COMPACT_COOLDOWN_SECONDS = 2 * 60
DEFAULT_MAX_ELAPSED_MS = int(os.environ.get("AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS", "15000"))
ACTION_TIMEOUT_SECONDS = {
    "build_index": 8.0,
    "build_clean_source": 8.0,
    "build_segments": 10.0,
    "register": 5.0,
    "subconscious_maybe_start": 3.0,
}
DETACHED_ACTION_COOLDOWN_SECONDS = {
    "build_associations": 15 * 60,
    "subconscious_maybe_start": 60,
}
SUPPORTED_EVENTS = {"SessionStart", "Stop", "PreCompact", "PostCompact"}
EMERGENCY_SNAPSHOT_DIAGNOSTIC_KEYS = {
    "ok",
    "status",
    "snapshot_id",
    "schema_version",
    "created_at",
    "message_count",
    "turn_count",
    "text_bytes",
    "artifact",
    "line_span",
    "source",
    "error_type",
}


def state_path(path: Path | None = None) -> Path:
    return path or (aippocampus_registry_dir() / "maintenance_state.json")


def state_key(cwd: Path | str) -> str:
    resolved = str(Path(cwd).resolve()).casefold()
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:16]
    return f"workspace:{digest}"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_state(path: Path | None = None) -> dict[str, Any]:
    data = load_json(state_path(path))
    data.setdefault("schema_version", STATE_SCHEMA_VERSION)
    data.setdefault("workspaces", {})
    return data


def save_state(data: dict[str, Any], path: Path | None = None) -> None:
    data["schema_version"] = STATE_SCHEMA_VERSION
    data["updated_at"] = now_utc()
    save_json(state_path(path), data)


def hook_input_from_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def recommended_action_ids(health: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in health.get("recommended_actions", []) if item.get("id")}


def latest_turn_refresh_marker(health: dict[str, Any]) -> str | None:
    freshness = health.get("freshness") or {}
    rollout = health.get("rollout") or {}
    message_count = freshness.get("rollout_message_count", rollout.get("message_count"))
    last_line = freshness.get("rollout_last_message_line", rollout.get("last_message_line"))
    clean_message_count = freshness.get(
        "expected_clean_source_message_count",
        (health.get("clean_source") or {}).get("expected_message_count"),
    )
    clean_turn_count = freshness.get(
        "expected_clean_source_turn_count",
        (health.get("clean_source") or {}).get("expected_turn_count"),
    )
    if message_count is None and last_line is None and clean_message_count is None:
        return None
    return f"m{message_count}:l{last_line}:cm{clean_message_count}:ct{clean_turn_count}"


def latest_turn_refresh_required_actions(health: dict[str, Any]) -> list[str]:
    freshness = health.get("freshness") or {}
    if not freshness.get("latest_visible_gap"):
        return []
    actions: list[str] = []
    if freshness.get("raw_newer_than_index"):
        actions.append("build_index")
        # Keep clean-source and SQLite freshness together for the current
        # visible turn. Rebuilding only SQLite can make source reopening land on
        # a generated index row while the clean-source audit file is still one
        # final answer behind.
        actions.append("build_clean_source")
    elif freshness.get("raw_newer_than_clean_source"):
        actions.append("build_clean_source")
    return unique_actions(actions)


def latest_turn_refresh_due(health: dict[str, Any], workspace_state: dict[str, Any]) -> bool:
    if not latest_turn_refresh_required_actions(health):
        return False
    marker = latest_turn_refresh_marker(health)
    return bool(marker and workspace_state.get("last_latest_turn_refresh_marker") != marker)


def cooldown_active(state: dict[str, Any], field: str, now_ts: float, cooldown: int) -> bool:
    last = float(state.get(field) or 0.0)
    return last > 0 and now_ts - last < cooldown


def lifecycle_decision_diagnostic(
    event: str,
    health: dict[str, Any],
    workspace_state: dict[str, Any],
    *,
    now_ts: float,
) -> dict[str, Any]:
    if event == "SessionStart":
        cooldown = preemptive.effective_session_cooldown_seconds(
            workspace_state,
            SESSION_COOLDOWN_SECONDS,
        )
        active = cooldown_active(workspace_state, "last_session_ts", now_ts, cooldown)
    elif event == "Stop":
        cooldown = STOP_COOLDOWN_SECONDS
        latest_due = latest_turn_refresh_due(health, workspace_state)
        active = cooldown_active(workspace_state, "last_stop_ts", now_ts, cooldown) and not latest_due
    elif event in {"PreCompact", "PostCompact"}:
        cooldown = COMPACT_COOLDOWN_SECONDS
        active = event == "PostCompact" and cooldown_active(
            workspace_state, "last_compact_ts", now_ts, cooldown
        )
    else:
        cooldown = 0
        active = False
    return {
        "event": event,
        "effective_cooldown_seconds": cooldown,
        "cooldown_active": active,
        **preemptive.preemptive_decision_fields(health),
    }


def decide_actions(
    event: str,
    health: dict[str, Any],
    workspace_state: dict[str, Any],
    *,
    now_ts: float | None = None,
) -> list[str]:
    now_ts = time.time() if now_ts is None else now_ts
    if event not in SUPPORTED_EVENTS:
        return []

    action_ids = recommended_action_ids(health)
    actions: list[str] = []

    if event == "SessionStart":
        if cooldown_active(
            workspace_state,
            "last_session_ts",
            now_ts,
            preemptive.effective_session_cooldown_seconds(
                workspace_state,
                SESSION_COOLDOWN_SECONDS,
            ),
        ):
            return []
        actions.extend(preemptive.preemptive_action_ids(health))
        if actions or (health.get("index") or {}).get("exists"):
            actions.append("register")
            actions.append("build_associations")
            actions.append("subconscious_maybe_start")
        return unique_actions(actions)

    if event == "Stop":
        latest_due = latest_turn_refresh_due(health, workspace_state)
        if (
            cooldown_active(workspace_state, "last_stop_ts", now_ts, STOP_COOLDOWN_SECONDS)
            and not latest_due
        ):
            return []
        if latest_due:
            actions.extend(latest_turn_refresh_required_actions(health))
        elif "build_index" in action_ids:
            actions.append("build_index")
            actions.append("build_clean_source")
        elif "build_clean_source" in action_ids:
            actions.append("build_clean_source")
        segments = health.get("segments") or {}
        if "build_segments" in action_ids and segments.get("exists"):
            actions.append("build_segments")
        if actions or (health.get("index") or {}).get("exists"):
            actions.append("register")
            actions.append("build_associations")
            actions.append("subconscious_maybe_start")
        return unique_actions(actions)

    if event in {"PreCompact", "PostCompact"}:
        if event == "PostCompact" and cooldown_active(
            workspace_state, "last_compact_ts", now_ts, COMPACT_COOLDOWN_SECONDS
        ):
            return []
        actions.append("build_index")
        actions.append("build_clean_source")
        segments = health.get("segments") or {}
        if "build_segments" in action_ids and segments.get("exists"):
            actions.append("build_segments")
        actions.append("register")
        actions.append("build_associations")
        if event == "PostCompact":
            actions.append("subconscious_maybe_start")
        return unique_actions(actions)

    return []


def unique_actions(actions: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        out.append(action)
    return out


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_json_timeout(cmd: list[str], *, timeout: float) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"child command timed out after {timeout:g}s: {' '.join(cmd)}") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return proc.stdout


def module_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def run_health(cwd: Path) -> dict[str, Any]:
    return run_json_timeout(
        module_cmd("aippocampus_runtime.health", "--cwd", str(cwd), "--json"),
        timeout=5.0,
    )


def sanitize_emergency_snapshot_diagnostic(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {key: value[key] for key in EMERGENCY_SNAPSHOT_DIAGNOSTIC_KEYS if key in value}


def emergency_snapshot_failure_diagnostic(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "snapshot_error",
        "schema_version": emergency_snapshot.EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        "error_type": type(exc).__name__,
    }


def run_emergency_thread_snapshot(cwd: Path) -> dict[str, Any]:
    result = emergency_snapshot.create_emergency_snapshot(cwd)
    return emergency_snapshot.public_snapshot_diagnostic(result)


def latest_emergency_thread_snapshot(cwd: Path) -> dict[str, Any]:
    return emergency_snapshot.latest_emergency_snapshot_diagnostic(cwd)


def maintenance_log_path(name: str) -> Path:
    return aippocampus_registry_dir() / "logs" / name


def start_detached_json(cmd: list[str], *, log_name: str) -> dict[str, Any]:
    log = maintenance_log_path(log_name)
    log.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    # Background maintenance can be noisy when a provider or registry pass gets
    # stuck. Route child output through the log-retention runner so no default
    # hook log can grow without a cap while the foreground lifecycle hook still
    # returns immediately.
    wrapped_cmd = log_retention.logged_subprocess_cmd(cmd, log=log, cwd=SCRIPT_DIR)
    proc = subprocess.Popen(
        wrapped_cmd,
        cwd=str(SCRIPT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Keep lifecycle hooks from waiting on descendant handles in the Codex
        # host pipe. On Windows, inherited stdout/stderr handles can make the
        # hook process look alive until the detached maintenance job exits.
        close_fds=True,
        creationflags=creationflags,
    )
    return {"detached": True, "pid": int(proc.pid), "log": str(log), "command": cmd}


def run_action(cwd: Path, action: str) -> dict[str, Any]:
    if action == "build_index":
        return run_json_timeout(
            module_cmd("aippocampus_runtime.recall.index_builder", "--cwd", str(cwd), "--json"),
            timeout=ACTION_TIMEOUT_SECONDS[action],
        )
    if action == "build_clean_source":
        return run_json_timeout(
            [
                *module_cmd("aippocampus_runtime.source.clean_source"),
                "--cwd",
                str(cwd),
                "--json",
            ],
            timeout=ACTION_TIMEOUT_SECONDS[action],
        )
    if action == "build_segments":
        return run_json_timeout(
            module_cmd("aippocampus_runtime.recall.segment_builder", "--cwd", str(cwd), "--json"),
            timeout=ACTION_TIMEOUT_SECONDS[action],
        )
    if action == "register":
        return run_json_timeout(
            [
                *module_cmd("aippocampus_runtime.registry.api"),
                "register",
                "--cwd",
                str(cwd),
                "--json",
            ],
            timeout=ACTION_TIMEOUT_SECONDS[action],
        )
    if action == "build_associations":
        # A full association rebuild scans the global registry. On real
        # installations this can take longer than the Codex lifecycle hook
        # timeout, so hooks enqueue it detached and rely on atomic output writes.
        return start_detached_json(
            module_cmd("aippocampus_runtime.navigation.associations", "--json"),
            log_name="build_associations_hook.log",
        )
    if action == "subconscious_maybe_start":
        # The scheduler itself is hook-safe, but importing Python modules,
        # probing the registry, or waiting on a stale lock can still be enough
        # to hit Codex host hook limits on busy machines. Keep the foreground
        # lifecycle hook to enqueue-only behavior; the scheduler's own lock and
        # per-project leases collapse duplicate starts, and DeepSeek work stays
        # in the detached worker.
        return start_detached_json(
            [
                *module_cmd("aippocampus_runtime.subconscious.scheduler"),
                "--maybe-start",
                "--cwd",
                str(cwd),
                "--json",
            ],
            log_name="subconscious_scheduler_hook.log",
        )
    raise ValueError(f"unknown maintenance action: {action}")


def remaining_ms(start: float, max_elapsed_ms: int | None) -> float | None:
    if not max_elapsed_ms or max_elapsed_ms <= 0:
        return None
    return max(0.0, float(max_elapsed_ms) - ((time.perf_counter() - start) * 1000.0))


def budget_allows(start: float, max_elapsed_ms: int | None, *, reserve_ms: float = 500.0) -> bool:
    remaining = remaining_ms(start, max_elapsed_ms)
    return remaining is None or remaining >= reserve_ms


def detached_action_recent(workspace_state: dict[str, Any], action: str, now_ts: float) -> bool:
    cooldown = DETACHED_ACTION_COOLDOWN_SECONDS.get(action)
    if not cooldown:
        return False
    return cooldown_active(workspace_state, f"last_{action}_enqueue_ts", now_ts, cooldown)


def remember_detached_action(workspace_state: dict[str, Any], action: str, now_ts: float) -> None:
    if action not in DETACHED_ACTION_COOLDOWN_SECONDS:
        return
    workspace_state[f"last_{action}_enqueue_ts"] = now_ts
    workspace_state[f"last_{action}_enqueue_at"] = now_utc()


def update_workspace_state(
    workspace_state: dict[str, Any],
    event: str,
    actions: list[str],
    *,
    now_ts: float,
    health: dict[str, Any] | None = None,
) -> None:
    workspace_state["last_event"] = event
    workspace_state["last_event_ts"] = now_ts
    workspace_state["last_event_at"] = now_utc()
    if event == "SessionStart":
        previous_session_ts = float(workspace_state.get("last_session_ts") or 0.0)
        if previous_session_ts > 0 and now_ts > previous_session_ts:
            workspace_state["last_session_interval_seconds"] = round(
                now_ts - previous_session_ts,
                3,
            )
            workspace_state["last_session_interval_at"] = now_utc()
        workspace_state["last_session_ts"] = now_ts
    elif event == "Stop":
        workspace_state["last_stop_ts"] = now_ts
    elif event in {"PreCompact", "PostCompact"}:
        workspace_state["last_compact_ts"] = now_ts
    if actions:
        workspace_state["last_actions"] = actions
        workspace_state["last_actions_ts"] = now_ts
        workspace_state["last_actions_at"] = now_utc()
        workspace_state["failure_count"] = 0
        if health:
            required = latest_turn_refresh_required_actions(health)
            marker = latest_turn_refresh_marker(health)
            if required and marker and all(action in actions for action in required):
                workspace_state["last_latest_turn_refresh_marker"] = marker
                workspace_state["last_latest_turn_refresh_at"] = now_utc()


def write_log(result: dict[str, Any], *, log_path: Path | None = None) -> None:
    path = log_path or (aippocampus_registry_dir() / "maintenance_hook.jsonl")
    event = {
        "timestamp": now_utc(),
        "event": result.get("event"),
        "cwd_hash": result.get("state_key"),
        "actions": result.get("actions"),
        "skipped": result.get("skipped"),
        "elapsed_ms": result.get("elapsed_ms"),
        "error": result.get("error"),
    }
    log_retention.append_text_with_rotation(path, json.dumps(event, ensure_ascii=False) + "\n")


def run_maintenance(
    event: str,
    cwd: Path,
    *,
    state_file: Path | None = None,
    dry_run: bool = False,
    now_ts: float | None = None,
    max_elapsed_ms: int | None = DEFAULT_MAX_ELAPSED_MS,
) -> dict[str, Any]:
    start = time.perf_counter()
    now_ts = time.time() if now_ts is None else now_ts
    state = load_state(state_file)
    key = state_key(cwd)
    workspace_state = state["workspaces"].setdefault(key, {})

    if event not in SUPPORTED_EVENTS:
        return {
            "event": event,
            "cwd": str(cwd),
            "state_key": key,
            "actions": [],
            "skipped": "unsupported_event",
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    emergency_snapshot_diagnostic: dict[str, Any] | None = None
    if event == "PreCompact" and not dry_run:
        try:
            emergency_snapshot_diagnostic = sanitize_emergency_snapshot_diagnostic(
                run_emergency_thread_snapshot(cwd)
            )
        except Exception as exc:
            emergency_snapshot_diagnostic = emergency_snapshot_failure_diagnostic(exc)
    elif event == "PostCompact":
        try:
            emergency_snapshot_diagnostic = sanitize_emergency_snapshot_diagnostic(
                latest_emergency_thread_snapshot(cwd)
            )
        except Exception as exc:
            emergency_snapshot_diagnostic = emergency_snapshot_failure_diagnostic(exc)

    try:
        health = run_health(cwd)
    except Exception as exc:
        if not dry_run:
            update_workspace_state(workspace_state, event, [], now_ts=now_ts)
            workspace_state["failure_count"] = int(workspace_state.get("failure_count") or 0) + 1
            workspace_state["last_error"] = str(exc)
            workspace_state["last_error_at"] = now_utc()
            save_state(state, state_file)
        return {
            "event": event,
            "cwd": str(cwd),
            "state_key": key,
            "actions": [],
            "dry_run": dry_run,
            "results": [],
            "skipped": "health_error",
            "error": str(exc),
            "emergency_snapshot": emergency_snapshot_diagnostic,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        }
    lifecycle_decision = lifecycle_decision_diagnostic(
        event,
        health,
        workspace_state,
        now_ts=now_ts,
    )
    actions = decide_actions(event, health, workspace_state, now_ts=now_ts)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    completed_actions: list[str] = []
    if not dry_run:
        for action in actions:
            if not budget_allows(start, max_elapsed_ms):
                skipped_actions.append({"id": action, "reason": "foreground_budget"})
                continue
            if detached_action_recent(workspace_state, action, now_ts):
                skipped_actions.append({"id": action, "reason": "detached_enqueue_cooldown"})
                continue
            try:
                result = run_action(cwd, action)
                if result.get("detached"):
                    remember_detached_action(workspace_state, action, now_ts)
                completed_actions.append(action)
                results.append({"id": action, "result": result})
            except Exception as exc:
                error = {"id": action, "error": str(exc)}
                errors.append(error)
                results.append(error)
        update_workspace_state(
            workspace_state,
            event,
            completed_actions,
            now_ts=now_ts,
            health=health,
        )
        if errors:
            workspace_state["failure_count"] = int(workspace_state.get("failure_count") or 0) + 1
            workspace_state["last_error"] = "; ".join(str(item.get("error")) for item in errors[:3])
            workspace_state["last_error_at"] = now_utc()
        save_state(state, state_file)
    preemptive.record_preemptive_outcome(
        lifecycle_decision,
        scheduled_actions=actions,
        completed_actions=completed_actions,
        skipped_actions=skipped_actions,
        dry_run=dry_run,
    )

    return {
        "event": event,
        "cwd": str(cwd),
        "state_key": key,
        "actions": actions,
        "dry_run": dry_run,
        "health_status": health.get("status"),
        "freshness": health.get("freshness"),
        "lifecycle_decision": lifecycle_decision,
        "results": results,
        "errors": errors,
        "skipped_actions": skipped_actions,
        "skipped": None if actions else "no_actions",
        "emergency_snapshot": emergency_snapshot_diagnostic,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--event", help="Dry-run event override. Hook mode reads hook_event_name from stdin."
    )
    parser.add_argument("--cwd", help="Workspace override. Hook mode reads cwd from stdin.")
    parser.add_argument("--state-file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=DEFAULT_MAX_ELAPSED_MS,
        help="Fail-open foreground budget for the lifecycle hook. Use 0 to disable.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    hook_input: dict[str, Any] = {}
    try:
        if args.event:
            event = args.event
            cwd = Path(args.cwd or os.getcwd()).resolve()
        else:
            hook_input = hook_input_from_stdin()
            event = str(hook_input.get("hook_event_name") or "")
            cwd = Path(args.cwd or hook_input.get("cwd") or os.getcwd()).resolve()
        result = run_maintenance(
            event,
            cwd,
            state_file=Path(args.state_file).resolve() if args.state_file else None,
            dry_run=args.dry_run,
            max_elapsed_ms=args.max_elapsed_ms,
        )
        if args.log:
            write_log(result)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        if args.strict:
            raise
        result = {
            "event": args.event or hook_input.get("hook_event_name"),
            "cwd": args.cwd or hook_input.get("cwd"),
            "actions": [],
            "error": str(exc),
        }
        if args.log:
            write_log(result)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
