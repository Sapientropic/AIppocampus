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

from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.subconscious import shell_selection

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
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
PUBLIC_SKIP_REASONS = {
    "disabled_by_env",
    "enqueue_locked",
    "no_due_projects",
    "leased_projects",
    "enqueue_cooldown",
}


@dataclass
class ProjectStats:
    label: str
    clean_turn_count: int
    clean_message_count: int
    thread_count: int
    latest_updated_at: str
    tags: list[str]
    workspaces: list[str]


class FileLock:
    def __init__(self, path: Path, *, stale_seconds: int = DEFAULT_STALE_LOCK_SECONDS) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self.fd: int | None = None
        self.recovered_stale_lock = False
        self.stale_age_seconds: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        last_exists: FileExistsError | None = None
        for _attempt in range(2):
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                last_exists = exc
                try:
                    age = max(0.0, time.time() - self.path.stat().st_mtime)
                except OSError:
                    age = 0.0
                if age <= self.stale_seconds:
                    raise RuntimeError(
                        "subconscious scheduler already running: "
                        f"active local lock {self.path.name} "
                        f"age={age:.1f}s threshold={self.stale_seconds}s"
                    ) from exc
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as unlink_exc:
                    raise RuntimeError(
                        "subconscious scheduler already running: "
                        f"stale local lock {self.path.name} could not be removed"
                    ) from unlink_exc
                self.recovered_stale_lock = True
                self.stale_age_seconds = int(age)
                continue
            payload: dict[str, Any] = {"pid": os.getpid(), "created_at": now_utc()}
            if self.recovered_stale_lock:
                payload.update(
                    {
                        "recovered_stale_lock": True,
                        "stale_age_seconds": self.stale_age_seconds,
                        "stale_threshold_seconds": self.stale_seconds,
                    }
                )
            os.write(self.fd, json.dumps(payload).encode("utf-8"))
            return self
        raise RuntimeError(
            "subconscious scheduler already running: stale local lock recovery raced"
        ) from last_exists

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except OSError:
            pass


def registry_dir(path: Path | None = None) -> Path:
    return path or aippocampus_registry_dir()


def registry_path(root: Path) -> Path:
    return root / "threads.json"


def state_path(root: Path, override: Path | None = None) -> Path:
    return override or (root / "subconscious_state.json")


def public_skip_reason(value: Any) -> str | None:
    reason = str(value or "").strip()
    if reason.startswith("missing_"):
        return "missing_api_key"
    return reason if reason in PUBLIC_SKIP_REASONS else ("runtime_error" if reason else None)


def public_scheduler_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "started": bool(result.get("started")),
        "ran": bool(result.get("ran")),
        "dry_run": bool(result.get("dry_run")),
        "skipped": public_skip_reason(result.get("skipped")),
        "pid_present": bool(result.get("pid")),
        "project_count": len(result.get("projects") or [])
        if isinstance(result.get("projects"), list)
        else 0,
        "result_count": len(result.get("results") or [])
        if isinstance(result.get("results"), list)
        else 0,
        "log_private_artifact": bool(result.get("log")),
        "output_boundary": "scheduler_project_details_are_local_private_artifacts",
    }
    if result.get("error"):
        payload["error"] = {"code": "runtime_error"}
    return payload


def log_path(root: Path) -> Path:
    return root / "subconscious_scheduler.log"


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


def load_state(path: Path) -> dict[str, Any]:
    data = load_json(path)
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
    except Exception:
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


def parse_utc_ts(value: str) -> float | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
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
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or not finding_mentions_project(item, label):
                continue
            ts = parse_utc_ts(str(item.get("created_at") or ""))
            if ts is not None and (latest is None or ts > latest):
                latest = ts
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
        with log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"\n[{now_utc()}] $ {' '.join(cmd)}\n")
            fh.write(output)
    if proc.returncode != 0:
        raise RuntimeError(output.strip() or f"command failed: {cmd}")
    return output


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
            sys.executable,
            str(SCRIPT_DIR / "build_project_timeline.py"),
            "--registry-dir",
            str(root),
        ],
        [sys.executable, str(SCRIPT_DIR / "build_concept_graph.py"), "--registry-dir", str(root)],
        [
            sys.executable,
            str(SCRIPT_DIR / "subconscious_jobs.py"),
            "--registry-dir",
            str(root),
            "--job",
            "all",
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
            sys.executable,
            str(SCRIPT_DIR / "build_semantic_scope_labels.py"),
            "--registry-dir",
            str(root),
            "--project",
            stats.label,
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "build_project_timeline.py"),
            "--registry-dir",
            str(root),
        ],
        [sys.executable, str(SCRIPT_DIR / "build_cognitive_map.py"), "--registry-dir", str(root)],
        [
            sys.executable,
            str(SCRIPT_DIR / "subconscious_review.py"),
            "--registry-dir",
            str(root),
            "--max-findings",
            str(max_findings),
            "--focus",
            focus_for(stats),
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "semantic_trigger_router.py"),
            "--registry-dir",
            str(root),
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "memory_candidate_router.py"),
            "--registry-dir",
            str(root),
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "dream_sleep_cycle.py"),
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
            sys.executable,
            str(SCRIPT_DIR / "dream_retrospective_lifecycle.py"),
            "--registry-dir",
            str(root),
            "--project",
            stats.label,
            "--summary",
            "--json",
        ],
        [sys.executable, str(SCRIPT_DIR / "build_concept_graph.py"), "--registry-dir", str(root)],
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
    out = log.open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    proc = subprocess.Popen(
        cmd,
        cwd=str(SCRIPT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=subprocess.STDOUT,
        # Hook callers often run with stdout/stderr captured by the host. Do
        # not let detached workers inherit those handles, or the foreground
        # hook may wait until the background DeepSeek pass exits.
        close_fds=True,
        creationflags=creationflags,
    )
    out.close()
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
    registry = load_json(registry_path(root))
    stats_by_label = project_stats_from_registry(registry)
    if all_projects:
        labels = sorted(stats_by_label)
    elif project:
        labels = [project]
    else:
        inferred = project_for_cwd(registry, cwd)
        labels = [inferred] if inferred else []

    due: list[tuple[ProjectStats, str]] = []
    projects_state = state.setdefault("projects", {})
    for label in labels:
        if not label:
            continue
        stats = stats_by_label.get(label)
        if not stats:
            continue
        project_state = projects_state.setdefault(label, {})
        bootstrap_project_state_from_staging(
            root,
            stats,
            project_state,
            now_ts=now_ts,
            cooldown_seconds=cooldown_seconds,
        )
        reason = due_reason(
            stats,
            project_state,
            now_ts=now_ts,
            cooldown_seconds=cooldown_seconds,
            min_new_turns=min_new_turns,
        )
        if reason:
            due.append((stats, reason))
    return due


def maybe_start(args: argparse.Namespace) -> dict[str, Any]:
    root = registry_dir(Path(args.registry_dir).resolve() if args.registry_dir else None)
    state_file = state_path(root, Path(args.state_file).resolve() if args.state_file else None)
    hook_env = os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    if hook_env is None:
        # Keep the old misspelled knob as a compatibility fallback only; the
        # public prefix is AIPPOCAMPUS_* and should be the one documented/used.
        hook_env = os.environ.get("AIIPPOCAMPUS_SUBCONSCIOUS_HOOK", "1")
    if hook_env.lower() in {"0", "false", "off", "no"}:
        return {"started": False, "skipped": "disabled_by_env", "projects": []}
    if not os.environ.get(args.api_key_env):
        return {"started": False, "skipped": f"missing_{args.api_key_env}", "projects": []}

    try:
        lock = FileLock(
            root / "subconscious_enqueue.lock", stale_seconds=DEFAULT_ENQUEUE_LOCK_STALE_SECONDS
        )
        with lock:
            return maybe_start_locked(args, root=root, state_file=state_file)
    except RuntimeError as exc:
        if "already running" in str(exc):
            return {"started": False, "skipped": "enqueue_locked", "projects": []}
        raise


def maybe_start_locked(args: argparse.Namespace, *, root: Path, state_file: Path) -> dict[str, Any]:
    state = load_state(state_file)
    now_ts = time.time()
    shell_override = getattr(args, "shell_selection", "auto")

    due = choose_projects(
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
        return {"started": False, "skipped": "no_due_projects", "projects": []}
    if args.dry_run:
        save_state(state_file, state)
        return {
            "started": False,
            "dry_run": True,
            "projects": [
                shell_selection.scheduler_project_report(stats, reason, root=root, override=shell_override)
                for stats, reason in due
            ],
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
            }
        return {"started": False, "skipped": "enqueue_cooldown", "projects": []}
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "subconscious_scheduler.py"),
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
        args.api_key_env,
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
        "log": str(log_path(root)),
    }


def run_due(args: argparse.Namespace) -> dict[str, Any]:
    root = registry_dir(Path(args.registry_dir).resolve() if args.registry_dir else None)
    state_file = state_path(root, Path(args.state_file).resolve() if args.state_file else None)
    log = log_path(root)
    now_ts = time.time()
    with FileLock(root / "subconscious_scheduler.lock"):
        state = load_state(state_file)
        due = choose_projects(
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
            return {"ran": False, "skipped": "no_due_projects", "projects": []}
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
            payload = shell_selection.private_scheduler_report_payload(result, public_payload) if args.include_private_report else public_payload
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif result.get("started"):
            print(f"subconscious scheduler started: pid {result.get('pid')}")
        elif result.get("ran"):
            print("subconscious scheduler ran")
        else:
            print(f"subconscious scheduler skipped: {public_skip_reason(result.get('skipped'))}")
        return 0
    except Exception as exc:
        if args.json_output:
            print(json.dumps(public_scheduler_payload({"error": str(exc)}), ensure_ascii=False, indent=2))
        else:
            print("subconscious scheduler error: runtime_error", file=sys.stderr)
        return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
