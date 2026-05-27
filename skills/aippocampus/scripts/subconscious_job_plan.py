#!/usr/bin/env python3
"""Scheduling plan helpers for subconscious job runs.

This module only expands requested job circuits into deterministic sample tasks
and worker counts. Provider calls, retries, validation, and staging writes stay
inside `subconscious_jobs.py` so scheduling policy remains easy to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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
