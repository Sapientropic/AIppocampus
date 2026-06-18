#!/usr/bin/env python3
"""Detached scheduler for warm ambient-recall scouts.

Foreground hooks are allowed to enqueue warming, but they must not run the
50-lane scout batch inline. This module writes a small redacted job file in the
local registry area and, when requested, starts the packaged warm CLI in a
detached process. The cache writer remains the only path that mutates ambient
cards, so late scout results can warm the next turn without making the current
hook wait.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import (
    now_utc,
    sanitize_external_model_payload,
    sanitize_external_model_text,
    stable_text_fingerprint,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_api_key_env,
    is_default_deepseek_api_key_env,
)
from aippocampus_runtime.recall.active_recall_lock import start_or_update_recall_lock
from aippocampus_runtime.recall.ambient_cache import default_ambient_cache_path
from aippocampus_runtime.warm_ambient.config import (
    DEFAULT_WARM_DETACHED_JOB_CONFIG,
    WarmDetachedJobConfig,
    warm_detached_job_config_from_env,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    expand_scout_lanes,
    scheduler_tier_policy,
    select_scheduler_scouts,
)

JOB_SCHEMA_VERSION = 1
DEFAULT_JOB_DIR_NAME = "ambient_warm_jobs"
DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_SCOUTS = (
    DEFAULT_WARM_DETACHED_JOB_CONFIG.prefix_cache_warmup_scouts
)
DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_DELAY = (
    DEFAULT_WARM_DETACHED_JOB_CONFIG.prefix_cache_warmup_delay
)
DEFAULT_DETACHED_WARM_TIMEOUT = DEFAULT_WARM_DETACHED_JOB_CONFIG.timeout
DEFAULT_WARM_JOB_STALE_SECONDS = 24 * 60 * 60
WARM_STATUS_COMMAND = "aippocampus warm status --json"
WARM_REPAIR_COMMAND = "aippocampus doctor provider --json"
TRUTHY = {"1", "true", "yes", "on", "enabled"}
FALSY = {"0", "false", "no", "off", "disabled"}


def warm_background_enabled(enabled: bool | None = None, *, env: dict[str, str] | None = None) -> bool:
    if enabled is not None:
        return bool(enabled)
    raw = str((env or os.environ).get("AIPPOCAMPUS_WARM_RECALL_BACKGROUND") or "").strip().casefold()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    # Default-on only enqueues detached warming after a foreground cache miss;
    # the prompt hook still stays cache-first, fail-open, and never waits for
    # the 50-lane scout batch. Keep the env opt-out for shared machines or
    # provider-budget debugging.
    return True


def default_warm_job_dir(
    *, registry_path: Path | str | None = None, registry_dir: Path | str | None = None
) -> Path:
    cache_path = default_ambient_cache_path(
        registry_path=Path(registry_path).resolve() if registry_path else None,
        registry_dir=Path(registry_dir).resolve() if registry_dir else None,
    )
    return cache_path.resolve().parent / DEFAULT_JOB_DIR_NAME


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _job_id(*, thread_id: str, workspace: Path, topic_epoch: str | None, prompt: str) -> str:
    seed = f"{time.time_ns()}\n{thread_id}\n{workspace}\n{topic_epoch or ''}\n{prompt}"
    return stable_text_fingerprint(seed, namespace="warm-job", prefix="warm", length=20)


def spawn_warm_job(job_path: Path, *, cwd: Path | None = None) -> dict[str, Any]:
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "aippocampus_runtime.warm_ambient.cli",
            "--job-file",
            str(job_path),
            "--json",
        ],
        cwd=str(cwd or Path.cwd()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
    )
    return {"spawned": True}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds_since(value: Any, *, now: datetime) -> int | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _iso_from_mtime(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        return (
            datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except OSError:
        return None


def _latest_timestamp(*values: Any) -> str | None:
    latest: datetime | None = None
    latest_text: str | None = None
    for value in values:
        parsed = _parse_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_text = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return latest_text


def _load_json_fail_open(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _json_file_timestamp(path: Path) -> str | None:
    payload = _load_json_fail_open(path)
    return _latest_timestamp(
        payload.get("completed_at"),
        payload.get("updated_at"),
        payload.get("created_at"),
        payload.get("timestamp"),
        _iso_from_mtime(path),
    )


def _result_path_for_job(job_path: Path) -> Path:
    return job_path.with_name(job_path.stem + ".result.json")


def warm_job_activity(
    job_dir: Path | str,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_WARM_JOB_STALE_SECONDS,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    target = Path(job_dir)
    latest = None
    pending_recent = 0
    pending_stale = 0
    completed = 0
    scanned = 0
    if not target.exists():
        return {
            "job_dir_present": False,
            "latest_at": None,
            "pending_recent_count": 0,
            "pending_stale_count": 0,
            "completed_count": 0,
            "scanned_job_count": 0,
            "queue_state": "missing",
            "stale_queue_blocked": False,
            "worker_process_active": False,
            "worker_evidence": "not_available",
            "pending_jobs_are_worker_evidence": False,
            "status_command": WARM_STATUS_COMMAND,
        }
    for job_path in sorted(target.glob("*.json"), key=lambda item: item.name)[-200:]:
        if job_path.name.endswith(".result.json"):
            continue
        scanned += 1
        job_latest = _json_file_timestamp(job_path)
        latest = _latest_timestamp(latest, job_latest)
        result_path = _result_path_for_job(job_path)
        result_latest = _json_file_timestamp(result_path)
        latest = _latest_timestamp(latest, result_latest)
        if result_path.exists():
            completed += 1
            continue
        age = _age_seconds_since(job_latest, now=current)
        if age is not None and age <= stale_after_seconds:
            pending_recent += 1
        else:
            pending_stale += 1
    if pending_stale:
        queue_state = "blocked_stale_pending"
    elif pending_recent:
        queue_state = "pending"
    elif scanned:
        queue_state = "complete"
    else:
        queue_state = "empty"
    return {
        "job_dir_present": True,
        "latest_at": latest,
        "pending_recent_count": pending_recent,
        "pending_stale_count": pending_stale,
        "completed_count": completed,
        "scanned_job_count": scanned,
        "queue_state": queue_state,
        "stale_queue_blocked": bool(pending_stale),
        # A pending job file means work is queued, not that a detached process is
        # alive. Keep this false until the scheduler grows an explicit heartbeat.
        "worker_process_active": False,
        "worker_evidence": "not_available",
        "pending_jobs_are_worker_evidence": False,
        "status_command": WARM_STATUS_COMMAND,
    }


def warm_status_payload(
    *,
    job_dir: Path | str,
    enabled: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    activity = warm_job_activity(job_dir, now=now)
    if activity.get("stale_queue_blocked"):
        status = "blocked"
    elif activity.get("pending_recent_count"):
        status = "pending"
    elif activity.get("completed_count"):
        status = "complete"
    else:
        status = "idle"
    agent_next_action: dict[str, Any]
    safe_next_actions: list[dict[str, Any]]
    if status == "blocked":
        action_code = "provider_or_worker_unavailable_optional"
        next_command = WARM_REPAIR_COMMAND
    elif status == "pending":
        action_code = "wait_or_run_worker_when_ready"
        next_command = WARM_STATUS_COMMAND
    else:
        action_code = "no_action"
        next_command = WARM_STATUS_COMMAND
    if status == "blocked":
        agent_next_action = {
            "id": "inspect_provider_status",
            "label": "Inspect provider status",
            "command": WARM_REPAIR_COMMAND,
            "mutation_risk": "read_only",
            "claim_boundary": "provider_presence_only_no_key_values_emitted",
            "why": "Warm ambient has stale queued work; check whether the optional worker can see a provider before changing setup.",
        }
        safe_next_actions = [
            agent_next_action,
            {
                "id": "recheck_warm_status",
                "label": "Recheck warm status",
                "command": WARM_STATUS_COMMAND,
                "mutation_risk": "read_only",
                "claim_boundary": "warm_ambient_optional_not_first_recall_blocker",
                "why": "Use this after provider or configuration review to confirm whether the stale queue is still blocked.",
            },
            {
                "id": "plan_warm_repair",
                "label": "Plan warm repair",
                "command": "aippocampus update plan --json",
                "mutation_risk": "read_only",
                "claim_boundary": "warm_ambient_optional_not_first_recall_blocker",
                "why": "Preview local repair steps before changing warm or hook configuration.",
            },
            {
                "id": "snooze_optional_warm_ambient",
                "label": "Snooze optional warm ambient",
                "command_template": "AIPPOCAMPUS_WARM_RECALL_BACKGROUND=0 aippocampus warm status --json",
                "requires": ["operator_env_change"],
                "template_only": True,
                "env": {"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "0"},
                "mutation_risk": "configuration_change",
                "claim_boundary": "warm_ambient_optional_not_first_recall_blocker",
                "why": "Disable optional background warming in the active host environment when the queue is stale or noisy.",
            },
            {
                "id": "retire_stale_warm_queue_after_review",
                "label": "Retire stale warm queue after review",
                "requires": ["operator_review_of_warm_status"],
                "template_only": True,
                "manual_instruction": (
                    "After reviewing warm status, retire stale pending warm jobs from the configured "
                    "warm job directory or leave warm ambient disabled; ordinary recall remains usable."
                ),
                "mutation_risk": "manual_cleanup",
                "claim_boundary": "warm_ambient_optional_not_first_recall_blocker",
                "why": "A stale warm queue should not be mistaken for a first-recall blocker or a live worker.",
            },
            {
                "id": "continue_with_ordinary_recall",
                "label": "Continue with ordinary recall",
                "command_template": 'aippocampus agent recall "{cue}" --json',
                "requires": ["cue"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "ordinary_recall_usable_without_warm_ambient",
                "why": "Warm ambient is optional; source-backed search and recall can continue.",
            },
        ]
    elif status == "pending":
        agent_next_action = {
            "id": "check_warm_status",
            "label": "Check warm status",
            "command": WARM_STATUS_COMMAND,
            "mutation_risk": "read_only",
            "claim_boundary": "queued_warm_work_is_not_worker_liveness",
            "why": "Recent warm jobs are queued; recheck status rather than assuming a worker is alive.",
        }
        safe_next_actions = [agent_next_action]
    else:
        agent_next_action = {
            "id": "no_warm_action_needed",
            "label": "No warm action needed",
            "command": WARM_STATUS_COMMAND,
            "mutation_risk": "read_only",
            "claim_boundary": "warm_status_is_optional_background_readout",
            "why": "Warm ambient has no blocking foreground action.",
        }
        safe_next_actions = [agent_next_action]
    action_fields = canonical_foreground_action_fields(
        agent_next_action,
        safe_next_actions=safe_next_actions,
    )
    return {
        "kind": "aippocampus_warm_ambient_status",
        "ok": status != "blocked",
        "enabled": warm_background_enabled(enabled),
        "status": status,
        "job_activity": activity,
        "action_code": action_code,
        "next_command": next_command,
        **action_fields,
        "ordinary_recall_usable": True,
        "ordinary_recall_note": "Warm ambient is optional; aippocampus search and agent recall can still use source-backed routes.",
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_job_payload_emitted": False,
            "local_paths_included": False,
            "provider_payload_included": False,
        },
    }


def public_warm_schedule_status(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"status": "not_scheduled"}
    public: dict[str, Any] = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "job_id": result.get("job_id"),
        "spawned": result.get("spawned"),
        "lock_id": result.get("lock_id"),
        "lock_state": result.get("lock_state"),
    }
    return {key: value for key, value in public.items() if value is not None and value != ""}


def schedule_warm_ambient_recall(
    prompt: str,
    *,
    cwd: Path | str,
    thread_id: str | None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    cache_path: Path | str | None = None,
    residue_path: Path | str | None = None,
    lock_path: Path | str | None = None,
    lock_id: str | None = None,
    current_thread_key: str | None = None,
    prompt_trace: list[dict[str, Any]] | None = None,
    topic_epoch: str | None = None,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    user_id: str | None = None,
    scouts: tuple[str, ...] | list[str] | None = None,
    scheduler_tier: str | None = "tier2_background",
    task_profile: str | None = "general",
    timeout: float | None = None,
    quorum: int | None = None,
    max_workers: int | None = None,
    prefix_cache_warmup_scouts: int | None = None,
    prefix_cache_warmup_delay: float | None = None,
    job_dir: Path | str | None = None,
    enabled: bool | None = None,
    spawn: bool = True,
    wait_all_foreground: bool = False,
    detached_config: WarmDetachedJobConfig | None = None,
    runner: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not warm_background_enabled(enabled):
        return {"status": "disabled", "reason": "background warm recall is not enabled"}
    if wait_all_foreground:
        return {"status": "skipped", "reason": "foreground hook must not wait for warm scouts"}
    if not thread_id:
        return {"status": "skipped", "reason": "missing thread id"}

    workspace = Path(cwd).resolve()
    sanitized_prompt, secret_policy = sanitize_external_model_text(prompt)
    if not sanitized_prompt.strip():
        return {"status": "skipped", "reason": "empty prompt after sanitization", "secret_policy": secret_policy}
    if secret_policy.get("hard_block"):
        return {
            "status": "skipped",
            "reason": str(secret_policy.get("reason") or "prompt hard-blocked"),
            "secret_policy": secret_policy,
        }
    resolved_api_key_env = (
        deepseek_api_key_env(os.environ)
        if is_default_deepseek_api_key_env(api_key_env)
        else api_key_env
    )
    if spawn and not os.environ.get(resolved_api_key_env):
        return {"status": "skipped_missing_api_key", "reason": f"{resolved_api_key_env} is not set"}
    tier_policy = scheduler_tier_policy(scheduler_tier)
    explicit_scouts = scouts is not None
    selected_scouts = (
        expand_scout_lanes(tuple(scouts or ()))
        if explicit_scouts
        else select_scheduler_scouts(tier=str(tier_policy["tier"]), task_profile=task_profile)
    )
    # Job-file replay treats an absent/empty scout list as the legacy full
    # matrix. Skip instead so foreground/cache-only tiers and invalid explicit
    # lanes cannot accidentally become a 50-lane detached sweep.
    if not selected_scouts:
        return {
            "status": "skipped",
            "reason": (
                "scheduler tier does not allow fresh warm scouts"
                if not tier_policy["fresh_model_calls_allowed"]
                else "no valid warm scout lanes selected"
            ),
            "scheduler_tier": tier_policy["tier"],
            "task_profile": task_profile or "general",
        }
    job_config = (detached_config or warm_detached_job_config_from_env()).with_overrides(
        timeout=timeout,
        prefix_cache_warmup_scouts=prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=prefix_cache_warmup_delay,
    )

    target_dir = Path(job_dir).resolve() if job_dir else default_warm_job_dir(
        registry_path=registry_path, registry_dir=registry_dir
    )
    job_id = _job_id(
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        prompt=sanitized_prompt,
    )
    job_path = target_dir / f"{job_id}.json"
    result_path = target_dir / f"{job_id}.result.json"
    lock_status: dict[str, Any] = {}
    if lock_path and not lock_id:
        lock = start_or_update_recall_lock(
            Path(lock_path).resolve(),
            prompt=sanitized_prompt,
            thread_id=thread_id,
            workspace=workspace,
            topic_epoch=topic_epoch,
            registry_path=Path(registry_path).resolve() if registry_path else None,
            route_reasons=["warm_ambient_job_scheduled"],
            diagnostics={
                "cold_model_call": True,
                "fast_scout_used": False,
                "thinking_enrichment_pending": True,
            },
            state="pending",
        )
        lock_id = str(lock.get("lock_id") or "") or None
        lock_status = {"lock_id": lock_id, "lock_state": lock.get("state")}
    job = {
        "kind": "aippocampus_warm_ambient_recall_job",
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "created_at": now_utc(),
        "prompt_hash": stable_text_fingerprint(
            sanitized_prompt,
            namespace="warm-prompt",
            length=16,
        ),
        "prompt": sanitized_prompt,
        "secret_policy": secret_policy,
        "privacy_boundary": {
            "sanitized_prompt_stored": True,
            "absolute_paths_are_private_process_pointers": True,
            "public_output": False,
        },
        "cwd": str(workspace),
        "thread_id": thread_id,
        "current_thread_key": current_thread_key,
        "prompt_trace": sanitize_external_model_payload(prompt_trace or []),
        "topic_epoch": topic_epoch,
        "registry_path": str(Path(registry_path).resolve()) if registry_path else None,
        "registry_dir": str(Path(registry_dir).resolve()) if registry_dir else None,
        "cache_path": str(Path(cache_path).resolve()) if cache_path else None,
        "residue_path": str(Path(residue_path).resolve()) if residue_path else None,
        "lock_path": str(Path(lock_path).resolve()) if lock_path else None,
        "lock_id": lock_id,
        "api_key_env": resolved_api_key_env,
        "user_id": user_id,
        "scouts": list(selected_scouts),
        "scheduler": {
            **tier_policy,
            "task_profile": task_profile or "general",
            "explicit_scouts": explicit_scouts,
            "selected_lane_count": len(selected_scouts),
            "selected_lane_total": len(selected_scouts),
            "scout_outputs_are_route_signals_not_memory_truth": True,
        },
        # Detached jobs are allowed to spend seconds because they do not block
        # UserPromptSubmit. Do not inherit the standalone warm CLI's short
        # foreground-style timeout here, or the default-on loop warms nothing.
        "timeout": job_config.timeout,
        "quorum": quorum,
        "max_workers": max_workers,
        "prefix_cache_warmup_scouts": job_config.prefix_cache_warmup_scouts,
        "prefix_cache_warmup_delay": job_config.prefix_cache_warmup_delay,
        "wait_all": True,
        "no_write": False,
        "result_path": str(result_path),
    }
    _write_json_atomic(job_path, job)

    launch = {"spawned": False}
    if spawn:
        launch = (runner or (lambda path: spawn_warm_job(path, cwd=workspace)))(job_path)
    result = {
        "status": "scheduled" if launch.get("spawned") else "queued",
        "job_id": job_id,
        "job_path": str(job_path),
        "result_path": str(result_path),
        "spawned": bool(launch.get("spawned")),
        "prompt_hash": job["prompt_hash"],
        "secret_policy": secret_policy,
        "scheduler_tier": tier_policy["tier"],
        "task_profile": task_profile or "general",
        "selected_lane_count": len(selected_scouts),
        **lock_status,
    }
    if lock_id and not result.get("lock_id"):
        result["lock_id"] = lock_id
        result["lock_state"] = "pending"
    return result
