#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job run configuration."""

from __future__ import annotations

from aippocampus_runtime.subconscious.jobs_config import DEFAULT_CONCURRENCY as DEFAULT_CONCURRENCY
from aippocampus_runtime.subconscious.jobs_config import (
    DEFAULT_JOBS_OUTPUT_NAME as DEFAULT_JOBS_OUTPUT_NAME,
)
from aippocampus_runtime.subconscious.jobs_config import (
    DEFAULT_SAMPLES_PER_JOB as DEFAULT_SAMPLES_PER_JOB,
)
from aippocampus_runtime.subconscious.jobs_config import JobsRunConfig as JobsRunConfig
from aippocampus_runtime.subconscious.jobs_config import (
    default_jobs_output_path as default_jobs_output_path,
)
from aippocampus_runtime.subconscious.jobs_config import (
    jobs_run_config_from_args as jobs_run_config_from_args,
)
