#!/usr/bin/env python3
"""Hook-safe scheduler for AIppocampus subconscious jobs.

The lifecycle hook may call this script frequently, so this file must stay
cheap in `--maybe-start` mode. It only decides whether a project has enough new
clean-source material, records a small state file, and starts a detached worker.
The expensive DeepSeek jobs run in the detached `--run-due` process.

Coordination is intentionally local-process best effort. The lock files and
project leases protect ordinary same-machine hook/worker overlap on local
filesystems; they are not a distributed scheduler, NFS lock protocol, or
multi-host queue. Keep hook failures fail-open unless `--strict` is explicitly
requested by an operator.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.cognitive_worker_mode import resolve_cognitive_worker_mode
from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.model import routing as model_routing
from aippocampus_runtime.ops import log_retention
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.source.io_kernel import (
    iter_jsonl_dict_rows,
    load_json_dict,
    parse_utc,
    write_json_atomic,
)
from aippocampus_runtime.subconscious import (
    agent_fallback_queue,
    scheduler_due_diagnostics,
    shell_selection,
)
from aippocampus_runtime.subconscious.scheduler_lock import FileLock
from aippocampus_runtime.subconscious.scheduler_public import (
    public_scheduler_payload,
    public_skip_reason,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
STATE_SCHEMA_VERSION = 1
DEFAULT_COOLDOWN_SECONDS = 6 * 60 * 60
DEFAULT_MIN_NEW_TURNS = 12
DEFAULT_ENQUEUE_COOLDOWN_SECONDS = 10 * 60
DEFAULT_ENQUEUE_LOCK_STALE_SECONDS = 5 * 60
DEFAULT_PROJECT_LEASE_SECONDS = 2 * 60 * 60
DEFAULT_STALE_LOCK_SECONDS = 2 * 60 * 60
DEFAULT_MAX_TURNS = 96
DEFAULT_MAX_FINDINGS = 220
DEFAULT_JOB_CONCURRENCY = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_JOB_CONCURRENCY", "4"))
DEFAULT_SAMPLES_PER_JOB = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB", "2"))
DEFAULT_API_KEY_ENV = model_routing.DEFAULT_DEEPSEEK_API_KEY_ENV


@dataclass
class ProjectStats:
    label: str
    clean_turn_count: int
    clean_message_count: int
    thread_count: int
    latest_updated_at: str
    tags: list[str]
    workspaces: list[str]


def registry_dir(path: Path | None = None) -> Path:
    return path or aippocampus_registry_dir()


def registry_path(root: Path) -> Path:
    return root / "threads.json"


def state_path(root: Path, override: Path | None = None) -> Path:
    return override or (root / "subconscious_state.json")


def public_json_text(payload: dict[str, Any]) -> str:
    """Serialize scheduler public projections only.

    The caller must pass `public_scheduler_payload(...)` or an explicit private
    policy report. Raw scheduler results can contain project labels and local
    paths, so keeping one output boundary makes CodeQL suppressions auditable.
    """

    return json.dumps(payload, ensure_ascii=False, indent=2)


def log_path(root: Path) -> Path:
    return root / "subconscious_scheduler.log"


def save_json(path: Path, data: dict[str, Any]) -> None:
    write_json_atomic(path, data)


def load_state(path: Path) -> dict[str, Any]:
    data = load_json_dict(path).data
    data.setdefault("schema_version", STATE_SCHEMA_VERSION)
    data.setdefault("projects", {})
    return data


def save_state(path: Path, data: dict[str, Any]) -> None:
    data["schema_version"] = STATE_SCHEMA_VERSION
    data["updated_at"] = now_utc()
    save_json(path, data)


def norm_path(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).resolve()).casefold()
    except (OSError, RuntimeError, ValueError):
        return value.casefold()


def thread_workspace(thread: dict[str, Any]) -> str:
    paths = thread.get("paths") or {}
    return str(paths.get("workspace") or (thread.get("session_meta") or {}).get("cwd") or "")


def thread_project_label(thread: dict[str, Any]) -> str:
    return str(thread.get("project_label") or thread.get("workspace_name") or "default")


def project_stats_from_registry(registry: dict[str, Any]) -> dict[str, ProjectStats]:
    buckets: dict[str, dict[str, Any]] = {}
    for thread in registry.get("threads") or []:
        if not isinstance(thread, dict):
            continue
        label = thread_project_label(thread)
        bucket = buckets.setdefault(
            label,
            {
                "label": label,
                "clean_turn_count": 0,
                "clean_message_count": 0,
                "thread_count": 0,
                "latest_updated_at": "",
                "tags": set(),
                "workspaces": set(),
            },
        )
        bucket["thread_count"] += 1
        bucket["clean_turn_count"] += int(thread.get("clean_turn_count") or 0)
        bucket["clean_message_count"] += int(thread.get("clean_message_count") or 0)
        updated = str(thread.get("updated_at") or "")
        if updated > bucket["latest_updated_at"]:
            bucket["latest_updated_at"] = updated
        for tag in thread.get("project_tags") or []:
            if tag:
                bucket["tags"].add(str(tag))
        workspace = thread_workspace(thread)
        if workspace:
            bucket["workspaces"].add(workspace)
    return {
        label: ProjectStats(
            label=label,
            clean_turn_count=int(bucket["clean_turn_count"]),
            clean_message_count=int(bucket["clean_message_count"]),
            thread_count=int(bucket["thread_count"]),
            latest_updated_at=str(bucket["latest_updated_at"]),
            tags=sorted(bucket["tags"]),
            workspaces=sorted(bucket["workspaces"]),
        )
        for label, bucket in buckets.items()
    }


def project_for_cwd(registry: dict[str, Any], cwd: Path | None) -> str | None:
    if cwd is None:
        return None
    target = norm_path(str(cwd))
    best: tuple[int, str] | None = None
    sep = os.sep.casefold()
    for thread in registry.get("threads") or []:
        if not isinstance(thread, dict):
            continue
        workspace = norm_path(thread_workspace(thread))
        if not workspace:
            continue
        if workspace == target:
            score = 3
        elif target.startswith(workspace + sep) or workspace.startswith(target + sep):
            score = 2
        else:
            continue
        label = thread_project_label(thread)
        if best is None or score > best[0]:
            best = (score, label)
    return best[1] if best else None


def due_reason(
    stats: ProjectStats,
    project_state: dict[str, Any],
    *,
    now_ts: float,
    cooldown_seconds: int,
    min_new_turns: int,
) -> str | None:
    last_run = float(project_state.get("last_run_ts") or 0.0)
    if last_run and now_ts - last_run < cooldown_seconds:
        return None
    last_turns = int(project_state.get("last_clean_turn_count") or 0)
    new_turns = stats.clean_turn_count - last_turns
    if last_run <= 0 and stats.clean_turn_count >= 3:
        return "first_run"
    if new_turns >= min_new_turns:
        return f"new_turns:{new_turns}"
    return None


def iso_from_ts(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def finding_mentions_project(item: dict[str, Any], label: str) -> bool:
    if item.get("project_label") == label:
        return True
    for ref in item.get("source_refs") or []:
        if isinstance(ref, dict) and ref.get("project_label") == label:
            return True
    return False


def latest_staging_ts(root: Path, label: str) -> float | None:
    latest: float | None = None
    for path in [root / "subconscious_jobs.jsonl", root / "promotion_candidates.jsonl"]:
        if not path.exists():
            continue
        for item in iter_jsonl_dict_rows(path):
            if not finding_mentions_project(item, label):
                continue
            created_at = parse_utc(item.get("created_at"))
            if created_at is None:
                continue
            timestamp = created_at.timestamp()
            if latest is None or timestamp > latest:
                latest = timestamp
    return latest


def bootstrap_project_state_from_staging(
    root: Path,
    stats: ProjectStats,
    project_state: dict[str, Any],
    *,
    now_ts: float,
    cooldown_seconds: int,
) -> None:
    if project_state.get("last_run_ts"):
        return
    latest = latest_staging_ts(root, stats.label)
    if latest is None or now_ts - latest >= cooldown_seconds:
        return
    # Manual subconscious runs should count as recent work, or the freshly
    # installed hook will immediately repeat the same expensive project pass.
    project_state["last_run_ts"] = latest
    project_state["last_run_at"] = iso_from_ts(latest)
    project_state["last_clean_turn_count"] = stats.clean_turn_count
    project_state["last_clean_message_count"] = stats.clean_message_count
    project_state["last_thread_count"] = stats.thread_count
    project_state["last_status"] = "bootstrapped_from_staging"


def focus_for(stats: ProjectStats) -> str:
    tag_text = ", ".join(stats.tags[:8])
    if tag_text:
        return f"{stats.label} project memory, recent decisions, architecture, product strategy, user preferences, recall triggers, tags: {tag_text}"
    return f"{stats.label} project memory, recent decisions, architecture, product strategy, user preferences, recall triggers"


def objective_for(stats: ProjectStats) -> str:
    return (
        f"Consolidate recent clean-source memory for project {stats.label}. "
        "Prefer source-backed findings that improve future recall, decision continuity, "
        "project drift awareness, trigger mining, deduplication, and contradiction review. "
        "Avoid trivial short utterances, tool/debug noise, and broad personalization."
    )


def lease_active(project_state: dict[str, Any], now_ts: float) -> bool:
    return float(project_state.get("lease_until_ts") or 0.0) > now_ts


def claim_project_lease(
    project_state: dict[str, Any],
    stats: ProjectStats,
    reason: str,
    *,
    now_ts: float,
    lease_seconds: int,
) -> None:
    lease_id = f"lease-{stats.label}-{int(now_ts)}-{os.getpid()}"
    until = now_ts + max(60, int(lease_seconds or DEFAULT_PROJECT_LEASE_SECONDS))
    project_state["lease_id"] = lease_id
    project_state["lease_started_ts"] = now_ts
    project_state["lease_started_at"] = iso_from_ts(now_ts)
    project_state["lease_until_ts"] = until
    project_state["lease_until_at"] = iso_from_ts(until)
    project_state["lease_reason"] = reason


def clear_project_lease(project_state: dict[str, Any]) -> None:
    for key in [
        "lease_id",
        "lease_started_ts",
        "lease_started_at",
        "lease_until_ts",
        "lease_until_at",
        "lease_reason",
    ]:
        project_state.pop(key, None)


def run_text(cmd: list[str], *, cwd: Path = SCRIPT_DIR, log: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if log:
        log_retention.append_text_with_rotation(
            log,
            f"\n[{now_utc()}] $ {' '.join(cmd)}\n{output}",
        )
    if proc.returncode != 0:
        raise RuntimeError(output.strip() or f"command failed: {cmd}")
    return output


def module_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def resolved_scheduler_api_key_env(api_key_env: str) -> str:
    return (
        model_routing.deepseek_api_key_env(os.environ)
        if model_routing.is_default_deepseek_api_key_env(api_key_env)
        else api_key_env
    )


def run_project(
    stats: ProjectStats,
    *,
    root: Path,
    max_turns: int,
    max_findings: int,
    job_concurrency: int,
    samples_per_job: int,
    log: Path,
) -> dict[str, Any]:
    # Deterministic prep is kept in the detached worker, not the foreground hook,
    # so the hook can return quickly while the sleep-time pass does heavier
    # consolidation safely in staging files.
    commands = [
        [
            *module_cmd("aippocampus_runtime.navigation.project_timeline"),
            "--registry-dir",
            str(root),
        ],
        module_cmd("aippocampus_runtime.navigation.concept_graph", "--registry-dir", str(root)),
        [
            *module_cmd("aippocampus_runtime.subconscious.jobs"),
            "--registry-dir",
            str(root),
            "--job",
            "all",
            "--event-salience-gate",
            "--project",
            stats.label,
            "--objective",
            objective_for(stats),
            "--max-turns",
            str(max_turns),
            "--concurrency",
            str(job_concurrency),
            "--samples-per-job",
            str(samples_per_job),
        ],
        [
            *module_cmd("aippocampus_runtime.source.semantic_scope_builder"),
            "--registry-dir",
            str(root),
            "--project",
            stats.label,
        ],
        [
            *module_cmd("aippocampus_runtime.navigation.project_timeline"),
            "--registry-dir",
            str(root),
        ],
        module_cmd("aippocampus_runtime.navigation.cognitive_map", "--registry-dir", str(root)),
        [
            *module_cmd("aippocampus_runtime.subconscious.review"),
            "--registry-dir",
            str(root),
            "--max-findings",
            str(max_findings),
            "--focus",
            focus_for(stats),
        ],
        [
            *module_cmd("aippocampus_runtime.recall.semantic_trigger_router"),
            "--registry-dir",
            str(root),
        ],
        [
            *module_cmd("aippocampus_runtime.subconscious.candidate_router"),
            "--registry-dir",
            str(root),
        ],
        [
            *module_cmd("aippocampus_runtime.dream.sleep_cycle"),
            "--registry-dir",
            str(root),
            "--project",
            stats.label,
            "--max-items",
            "1",
            "--run-ready",
            "--write-staging",
            "--summary",
            "--json",
        ],
        [
            *module_cmd("aippocampus_runtime.dream.retrospective_lifecycle"),
            "--registry-dir",
            str(root),
            "--project",
            stats.label,
            "--summary",
            "--json",
        ],
        module_cmd("aippocampus_runtime.navigation.concept_graph", "--registry-dir", str(root)),
    ]
    outputs: list[str] = []
    for cmd in commands:
        outputs.append(run_text(cmd, log=log).strip())
    return {
        "project": stats.label,
        "commands": len(commands),
        "last_output": outputs[-1] if outputs else "",
    }


def start_detached(cmd: list[str], *, root: Path) -> int:
    log = log_path(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    wrapped_cmd = log_retention.logged_subprocess_cmd(cmd, log=log, cwd=SCRIPT_DIR)
    proc = subprocess.Popen(
        wrapped_cmd,
        cwd=str(SCRIPT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Hook callers often run with stdout/stderr captured by the host. Do
        # not let detached workers inherit those handles, or the foreground
        # hook may wait until the background DeepSeek pass exits.
        close_fds=True,
        creationflags=creationflags,
    )
    return int(proc.pid)


def choose_projects(
    *,
    root: Path,
    cwd: Path | None,
    project: str | None,
    all_projects: bool,
    state: dict[str, Any],
    now_ts: float,
    cooldown_seconds: int,
    min_new_turns: int,
) -> list[tuple[ProjectStats, str]]:
    due, _diagnostics = choose_projects_with_diagnostics(
        root=root,
        cwd=cwd,
        project=project,
        all_projects=all_projects,
        state=state,
        now_ts=now_ts,
        cooldown_seconds=cooldown_seconds,
        min_new_turns=min_new_turns,
    )
    return due


def choose_projects_with_diagnostics(
    *,
    root: Path,
    cwd: Path | None,
    project: str | None,
    all_projects: bool,
    state: dict[str, Any],
    now_ts: float,
    cooldown_seconds: int,
    min_new_turns: int,
) -> tuple[list[tuple[ProjectStats, str]], list[dict[str, Any]]]:
    registry = load_json_dict(registry_path(root)).data
    stats_by_label = project_stats_from_registry(registry)
    return scheduler_due_diagnostics.choose_projects_with_diagnostics(
        root=root,
        registry=registry,
        stats_by_label=stats_by_label,
        cwd=cwd,
        project=project,
        all_projects=all_projects,
        state=state,
        now_ts=now_ts,
        cooldown_seconds=cooldown_seconds,
        min_new_turns=min_new_turns,
        project_for_cwd=project_for_cwd,
        bootstrap_project_state_from_staging=bootstrap_project_state_from_staging,
        due_reason=due_reason,
        lease_active=lease_active,
    )


def maybe_start(args: argparse.Namespace) -> dict[str, Any]:
    root = registry_dir(Path(args.registry_dir).resolve() if args.registry_dir else None)
    state_file = state_path(root, Path(args.state_file).resolve() if args.state_file else None)
    hook_env = os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    hook_token = str(hook_env or "").strip().lower()
    if hook_token in {"0", "false", "off", "no", "disabled"}:
        return {"started": False, "skipped": "disabled_by_env", "projects": []}
    if hook_token not in {"1", "true", "on", "yes", "enabled"}:
        return {
            "started": False,
            "skipped": "subconscious_hook_consent_required",
            "projects": [],
            "consent": {
                "required_env": "AIPPOCAMPUS_SUBCONSCIOUS_HOOK",
                "accepted_values": ["1", "true", "on", "yes", "enabled"],
            },
        }
    resolved_api_key_env = resolved_scheduler_api_key_env(args.api_key_env)
    worker_mode = resolve_cognitive_worker_mode(
        api_key_env=resolved_api_key_env,
        require_background_model_consent=True,
    )
    resolved_worker_mode = str(worker_mode.get("resolved_mode") or "")
    if resolved_worker_mode == "off":
        return {
            "started": False,
            "skipped": "cognitive_worker_mode_off",
            "projects": [],
            "cognitive_worker": worker_mode,
        }
    if resolved_worker_mode == "deterministic_only":
        if worker_mode.get("status") == "background_model_consent_required":
            return {
                "started": False,
                "skipped": "background_model_consent_required",
                "projects": [],
                "cognitive_worker": worker_mode,
            }
        skipped = (
            "deterministic_only_by_env"
            if worker_mode.get("status") == "deterministic_only_by_env"
            else "missing_api_key"
        )
        return {
            "started": False,
            "skipped": skipped,
            "projects": [],
            "cognitive_worker": worker_mode,
        }

    try:
        lock = FileLock(
            root / "subconscious_enqueue.lock", stale_seconds=DEFAULT_ENQUEUE_LOCK_STALE_SECONDS
        )
        with lock:
            if resolved_worker_mode == "agent_fallback":
                return maybe_enqueue_agent_fallback(args, root=root, state_file=state_file, worker_mode=worker_mode)
            return maybe_start_locked(args, root=root, state_file=state_file)
    except RuntimeError as exc:
        if "already running" in str(exc):
            return {"started": False, "skipped": "enqueue_locked", "projects": []}
        raise


def maybe_enqueue_agent_fallback(
    args: argparse.Namespace, *, root: Path, state_file: Path, worker_mode: dict[str, Any]
) -> dict[str, Any]:
    state = load_state(state_file)
    now_ts = time.time()
    shell_override = getattr(args, "shell_selection", "auto")
    due, diagnostics = choose_projects_with_diagnostics(
        root=root,
        cwd=Path(args.cwd).resolve() if args.cwd else None,
        project=args.project,
        all_projects=args.all_projects,
        state=state,
        now_ts=now_ts,
        cooldown_seconds=args.cooldown_seconds,
        min_new_turns=args.min_new_turns,
    )
    if not due:
        save_state(state_file, state)
        return {
            "started": False,
            "dry_run": bool(getattr(args, "dry_run", False)),
            "skipped": "no_due_projects",
            "projects": [],
            "scheduler_diagnostics": diagnostics,
            "cognitive_worker": worker_mode,
        }
    projects = [
        shell_selection.scheduler_project_report(stats, reason, root=root, override=shell_override)
        for stats, reason in due
    ]
    if args.dry_run:
        save_state(state_file, state)
        return {
            "started": False,
            "dry_run": True,
            "queued": False,
            "skipped": "agent_fallback_queued",
            "projects": projects,
            "scheduler_diagnostics": diagnostics,
            "agent_fallback_task_count": len(projects),
            "cognitive_worker": worker_mode,
        }

    queue_result = agent_fallback_queue.enqueue_due_tasks(
        root=root,
        state=state,
        due=due,
        worker_mode=worker_mode,
        now_ts=now_ts,
        enqueue_cooldown_seconds=DEFAULT_ENQUEUE_COOLDOWN_SECONDS,
    )
    save_state(state_file, state)
    if queue_result.get("queued"):
        result_projects: list[dict[str, Any]] = projects
    elif queue_result.get("leased_projects"):
        result_projects = list(queue_result.get("leased_projects") or [])
    else:
        result_projects = []
    return {
        "started": False,
        "queued": bool(queue_result.get("queued")),
        "skipped": queue_result.get("skipped"),
        "projects": result_projects,
        "scheduler_diagnostics": diagnostics,
        "agent_fallback_task_count": int(queue_result.get("agent_fallback_task_count") or 0),
        "cognitive_worker": worker_mode,
    }


def maybe_start_locked(args: argparse.Namespace, *, root: Path, state_file: Path) -> dict[str, Any]:
    state = load_state(state_file)
    now_ts = time.time()
    shell_override = getattr(args, "shell_selection", "auto")
    resolved_api_key_env = resolved_scheduler_api_key_env(args.api_key_env)

    due, diagnostics = choose_projects_with_diagnostics(
        root=root,
        cwd=Path(args.cwd).resolve() if args.cwd else None,
        project=args.project,
        all_projects=args.all_projects,
        state=state,
        now_ts=now_ts,
        cooldown_seconds=args.cooldown_seconds,
        min_new_turns=args.min_new_turns,
    )
    if not due:
        save_state(state_file, state)
        return {
            "started": False,
            "dry_run": bool(getattr(args, "dry_run", False)),
            "skipped": "no_due_projects",
            "projects": [],
            "scheduler_diagnostics": diagnostics,
        }
    if args.dry_run:
        save_state(state_file, state)
        return {
            "started": False,
            "dry_run": True,
            "projects": [
                shell_selection.scheduler_project_report(stats, reason, root=root, override=shell_override)
                for stats, reason in due
            ],
            "scheduler_diagnostics": diagnostics,
        }
    filtered: list[tuple[ProjectStats, str]] = []
    leased: list[tuple[ProjectStats, str]] = []
    for stats, reason in due:
        project_state = state.setdefault("projects", {}).setdefault(stats.label, {})
        if lease_active(project_state, now_ts):
            leased.append((stats, reason))
            continue
        last_enqueue = float(project_state.get("last_enqueue_ts") or 0.0)
        if last_enqueue and now_ts - last_enqueue < DEFAULT_ENQUEUE_COOLDOWN_SECONDS:
            continue
        project_state["last_enqueue_ts"] = now_ts
        project_state["last_enqueue_at"] = now_utc()
        project_state["last_enqueue_reason"] = reason
        claim_project_lease(
            project_state,
            stats,
            reason,
            now_ts=now_ts,
            lease_seconds=getattr(args, "lease_seconds", DEFAULT_PROJECT_LEASE_SECONDS),
        )
        filtered.append((stats, reason))
    save_state(state_file, state)
    due = filtered
    if not due:
        if leased:
            return {
                "started": False,
                "skipped": "leased_projects",
                "projects": [{"label": stats.label, "reason": reason} for stats, reason in leased],
                "scheduler_diagnostics": [
                    {
                        **scheduler_due_diagnostics.project_due_diagnostic(
                            stats,
                            state.setdefault("projects", {}).setdefault(stats.label, {}),
                            due_reason=reason,
                            now_ts=now_ts,
                            cooldown_seconds=args.cooldown_seconds,
                            min_new_turns=args.min_new_turns,
                            lease_active=True,
                        ),
                        "due_state": "blocked",
                        "skip_reason": "lease_active_or_stale",
                    }
                    for stats, _reason in leased
                ],
            }
        return {
            "started": False,
            "skipped": "enqueue_cooldown",
            "projects": [],
            "scheduler_diagnostics": diagnostics,
        }
    cmd = [
        *module_cmd("aippocampus_runtime.subconscious.scheduler"),
        "--run-due",
        "--registry-dir",
        str(root),
        "--state-file",
        str(state_file),
        "--cooldown-seconds",
        str(args.cooldown_seconds),
        "--min-new-turns",
        str(args.min_new_turns),
        "--max-turns",
        str(args.max_turns),
        "--max-findings",
        str(args.max_findings),
        "--job-concurrency",
        str(getattr(args, "job_concurrency", DEFAULT_JOB_CONCURRENCY)),
        "--samples-per-job",
        str(getattr(args, "samples_per_job", DEFAULT_SAMPLES_PER_JOB)),
        "--api-key-env",
        resolved_api_key_env,
    ]
    if args.cwd:
        cmd.extend(["--cwd", str(Path(args.cwd).resolve())])
    if args.project:
        cmd.extend(["--project", args.project])
    if args.all_projects:
        cmd.append("--all-projects")
    try:
        pid = start_detached(cmd, root=root)
    except Exception:
        for stats, _reason in due:
            clear_project_lease(state.setdefault("projects", {}).setdefault(stats.label, {}))
        save_state(state_file, state)
        raise
    return {
        "started": True,
        "pid": pid,
        "projects": [
            shell_selection.scheduler_project_report(stats, reason, root=root, override=shell_override)
            for stats, reason in due
        ],
        "scheduler_diagnostics": diagnostics,
        "log": str(log_path(root)),
    }


def run_due(args: argparse.Namespace) -> dict[str, Any]:
    root = registry_dir(Path(args.registry_dir).resolve() if args.registry_dir else None)
    state_file = state_path(root, Path(args.state_file).resolve() if args.state_file else None)
    log = log_path(root)
    now_ts = time.time()
    with FileLock(root / "subconscious_scheduler.lock"):
        state = load_state(state_file)
        due, diagnostics = choose_projects_with_diagnostics(
            root=root,
            cwd=Path(args.cwd).resolve() if args.cwd else None,
            project=args.project,
            all_projects=args.all_projects,
            state=state,
            now_ts=now_ts,
            cooldown_seconds=args.cooldown_seconds,
            min_new_turns=args.min_new_turns,
        )
        if not due:
            save_state(state_file, state)
            return {
                "ran": False,
                "skipped": "no_due_projects",
                "projects": [],
                "scheduler_diagnostics": diagnostics,
            }
        results = []
        for stats, reason in due:
            project_state = state.setdefault("projects", {}).setdefault(stats.label, {})
            project_state["last_start_ts"] = time.time()
            project_state["last_start_at"] = now_utc()
            project_state["last_reason"] = reason
            project_state["last_status"] = "running"
            save_state(state_file, state)
            try:
                result = run_project(
                    stats,
                    root=root,
                    max_turns=args.max_turns,
                    max_findings=args.max_findings,
                    job_concurrency=getattr(args, "job_concurrency", DEFAULT_JOB_CONCURRENCY),
                    samples_per_job=getattr(args, "samples_per_job", DEFAULT_SAMPLES_PER_JOB),
                    log=log,
                )
                project_state["last_status"] = "success"
                project_state["last_error"] = None
                project_state["last_run_ts"] = time.time()
                project_state["last_run_at"] = now_utc()
                project_state["last_clean_turn_count"] = stats.clean_turn_count
                project_state["last_clean_message_count"] = stats.clean_message_count
                project_state["last_thread_count"] = stats.thread_count
                results.append(result)
            except Exception as exc:
                project_state["last_status"] = "error"
                project_state["last_error"] = str(exc)
                project_state["last_error_at"] = now_utc()
                results.append({"project": stats.label, "error": str(exc)})
            finally:
                clear_project_lease(project_state)
                project_state["last_finish_at"] = now_utc()
                save_state(state_file, state)
        return {
            "ran": True,
            "projects": [{"label": stats.label, "reason": reason} for stats, reason in due],
            "results": results,
            "scheduler_diagnostics": diagnostics,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--maybe-start",
        action="store_true",
        help="Hook-safe mode: start a detached run only when due.",
    )
    mode.add_argument("--run-due", action="store_true", help="Run due projects synchronously.")
    parser.add_argument("--registry-dir")
    parser.add_argument("--state-file")
    parser.add_argument("--cwd")
    parser.add_argument("--project")
    parser.add_argument("--all-projects", action="store_true")
    parser.add_argument("--cooldown-seconds", type=int, default=DEFAULT_COOLDOWN_SECONDS)
    parser.add_argument("--min-new-turns", type=int, default=DEFAULT_MIN_NEW_TURNS)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-findings", type=int, default=DEFAULT_MAX_FINDINGS)
    parser.add_argument("--job-concurrency", type=int, default=DEFAULT_JOB_CONCURRENCY)
    parser.add_argument("--samples-per-job", type=int, default=DEFAULT_SAMPLES_PER_JOB)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_PROJECT_LEASE_SECONDS)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--shell-selection", choices=["auto", *sorted(shell_selection.VALID_DECISIONS)], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--include-private-report", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero status on scheduler errors. Hook mode stays fail-open by default.",
    )
    args = parser.parse_args()

    try:
        if args.run_due:
            result = run_due(args)
        else:
            result = maybe_start(args)
        if args.json_output:
            public_payload = public_scheduler_payload(result)
            payload = (
                shell_selection.private_scheduler_report_payload(result, public_payload)
                if args.include_private_report
                else public_payload
            )
            emit_public_text(public_json_text(payload))
        elif result.get("started"):
            emit_public_text(f"subconscious scheduler started: pid {result.get('pid')}")
        elif result.get("ran"):
            emit_public_text("subconscious scheduler ran")
        elif result.get("queued") and result.get("skipped") == "agent_fallback_queued":
            emit_public_text("subconscious agent fallback queued: scaffold/manual-only")
        else:
            emit_public_text(f"subconscious scheduler skipped: {public_skip_reason(result.get('skipped'))}")
        return 0
    except Exception as exc:
        if args.json_output:
            error_payload = public_scheduler_payload({"error": str(exc)})
            emit_public_text(public_json_text(error_payload))
        else:
            emit_public_text("subconscious scheduler error: runtime_error", stream=sys.stderr)
        return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
