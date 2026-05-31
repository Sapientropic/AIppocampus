#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job storage helpers."""

from __future__ import annotations

from aippocampus_runtime.subconscious.job_storage import (
    append_job_findings as append_job_findings,
)
from aippocampus_runtime.subconscious.job_storage import (
    concept_findings_to_edges as concept_findings_to_edges,
)
