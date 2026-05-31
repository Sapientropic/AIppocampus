#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job planning helpers."""

from __future__ import annotations

from aippocampus_runtime.subconscious.job_plan import JobRunTask as JobRunTask
from aippocampus_runtime.subconscious.job_plan import (
    plan_job_run_tasks as plan_job_run_tasks,
)
from aippocampus_runtime.subconscious.job_plan import (
    run_tasks_in_sample_waves as run_tasks_in_sample_waves,
)
from aippocampus_runtime.subconscious.job_plan import sample_count as sample_count
from aippocampus_runtime.subconscious.job_plan import (
    task_sample_index as task_sample_index,
)
from aippocampus_runtime.subconscious.job_plan import worker_count as worker_count
