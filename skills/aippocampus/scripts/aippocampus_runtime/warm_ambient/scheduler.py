#!/usr/bin/env python3
"""Detached scheduler for warm ambient-recall scouts.

Foreground hooks are allowed to enqueue warming, but they must not run the
50-lane scout batch inline. This module writes a small redacted job file in the
local registry area and, when requested, starts `warm_ambient_recall.py` in a
detached process. The cache writer remains the only path that mutates ambient
cards, so late scout results can warm the next turn without making the current
hook wait.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.core import (
    now_utc,
    sanitize_external_model_payload,
    sanitize_external_model_text,
)
from aippocampus_runtime.recall.ambient_cache import default_ambient_cache_path
from aippocampus_runtime.warm_ambient.config import (
    DEFAULT_WARM_DETACHED_JOB_CONFIG,
    WarmDetachedJobConfig,
    warm_detached_job_config_from_env,
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
    return "warm_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def spawn_warm_job(job_path: Path, *, cwd: Path | None = None) -> dict[str, Any]:
    script = Path(__file__).resolve().parents[2] / "warm_ambient_recall.py"
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [sys.executable, str(script), "--job-file", str(job_path), "--json"],
        cwd=str(cwd or Path.cwd()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
    )
    return {"spawned": True}


def public_warm_schedule_status(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"status": "not_scheduled"}
    public: dict[str, Any] = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "job_id": result.get("job_id"),
        "spawned": result.get("spawned"),
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
    current_thread_key: str | None = None,
    prompt_trace: list[dict[str, Any]] | None = None,
    topic_epoch: str | None = None,
    api_key_env: str = "DEEPSEEK_API_KEY",
    user_id: str | None = None,
    scouts: tuple[str, ...] | list[str] | None = None,
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
    if spawn and not os.environ.get(api_key_env):
        return {"status": "skipped_missing_api_key", "reason": f"{api_key_env} is not set"}
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
    job = {
        "kind": "aippocampus_warm_ambient_recall_job",
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "created_at": now_utc(),
        "prompt_sha1": hashlib.sha1(str(prompt or "").encode("utf-8")).hexdigest()[:16],
        "prompt": sanitized_prompt,
        "secret_policy": secret_policy,
        "cwd": str(workspace),
        "thread_id": thread_id,
        "current_thread_key": current_thread_key,
        "prompt_trace": sanitize_external_model_payload(prompt_trace or []),
        "topic_epoch": topic_epoch,
        "registry_path": str(Path(registry_path).resolve()) if registry_path else None,
        "registry_dir": str(Path(registry_dir).resolve()) if registry_dir else None,
        "cache_path": str(Path(cache_path).resolve()) if cache_path else None,
        "residue_path": str(Path(residue_path).resolve()) if residue_path else None,
        "api_key_env": api_key_env,
        "user_id": user_id,
        "scouts": list(scouts or []),
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
    return {
        "status": "scheduled" if launch.get("spawned") else "queued",
        "job_id": job_id,
        "job_path": str(job_path),
        "result_path": str(result_path),
        "spawned": bool(launch.get("spawned")),
        "prompt_sha1": job["prompt_sha1"],
        "secret_policy": secret_policy,
    }
