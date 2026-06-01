#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job circuit contracts."""

from __future__ import annotations

from aippocampus_runtime.subconscious import job_circuits as _job_circuits

JOB_SPECS = _job_circuits.JOB_SPECS
PROMPT_VERSION = _job_circuits.PROMPT_VERSION
job_names = _job_circuits.job_names
jobs_initial_payload = _job_circuits.jobs_initial_payload
ordered_job_names = _job_circuits.ordered_job_names
validate_job_dependency_contract = _job_circuits.validate_job_dependency_contract
