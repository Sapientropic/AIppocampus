#!/usr/bin/env python3
"""Scheduling plan helpers for subconscious job runs.

This module expands requested job circuits into deterministic sample tasks and
runs sample waves. Provider calls, retries, validation, and staging writes stay
inside `subconscious_jobs.py` so scheduling policy remains easy to inspect.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class JobRunTask:
    index: int
    job: str
    sample_index: int
    sample_count: int


def sample_count(value: int) -> int:
    return max(1, int(value))


def plan_job_run_tasks(jobs: Iterable[str], *, samples_per_job: int) -> list[JobRunTask]:
    count = sample_count(samples_per_job)
    tasks: list[JobRunTask] = []
    for job in jobs:
        for sample_index in range(1, count + 1):
            tasks.append(
                JobRunTask(
                    index=len(tasks),
                    job=str(job),
                    sample_index=sample_index,
                    sample_count=count,
                )
            )
    return tasks


def worker_count(*, concurrency: int, task_count: int) -> int:
    return max(1, min(int(concurrency or 1), int(task_count or 1)))


def task_sample_index(task: Any) -> int:
    if isinstance(task, dict):
        return int(task.get("sample_index") or 1)
    return int(getattr(task, "sample_index", 1) or 1)


def run_tasks_in_sample_waves(
    task_specs: list[Any],
    *,
    max_workers: int,
    run_task,
    failed_task,
) -> list[tuple[int, dict[str, Any]]]:
    """Run sample 1 before same-prefix follow-up samples.

    DeepSeek's KV cache is populated by completed requests. Launching sample 1
    and sample 2 for the same prompt prefix at the exact same time often makes
    both requests cold. Wave scheduling preserves concurrency across distinct
    jobs/batches while giving each prefix one completed warm-up before its
    diversity follow-ups start.
    """
    indexed_results: list[tuple[int, dict[str, Any]]] = []
    if not task_specs:
        return indexed_results
    sample_waves = sorted({task_sample_index(task) for task in task_specs})
    for sample_index in sample_waves:
        wave = [task for task in task_specs if task_sample_index(task) == sample_index]
        wave_workers = min(max(1, int(max_workers)), max(1, len(wave)))
        if wave_workers == 1:
            for task in wave:
                try:
                    indexed_results.append(
                        (
                            int(task["index"] if isinstance(task, dict) else task.index),
                            run_task(task),
                        )
                    )
                except Exception as exc:
                    indexed_results.append(
                        (
                            int(task["index"] if isinstance(task, dict) else task.index),
                            failed_task(task, exc),
                        )
                    )
            continue
        with ThreadPoolExecutor(max_workers=wave_workers) as executor:
            futures = {executor.submit(run_task, task): task for task in wave}
            for future in as_completed(futures):
                task = futures[future]
                task_index = int(task["index"] if isinstance(task, dict) else task.index)
                try:
                    indexed_results.append((task_index, future.result()))
                except Exception as exc:
                    indexed_results.append((task_index, failed_task(task, exc)))
    return indexed_results
